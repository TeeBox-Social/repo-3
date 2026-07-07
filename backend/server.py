from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import math
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
from jose import jwt, JWTError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


def _client_ip(request: Request) -> str:
    """Prefer the real client IP behind proxy/CDN (Cloudflare, ingress) over the socket peer."""
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

users_col = db.users
rounds_col = db.rounds
likes_col = db.likes
comments_col = db.comments
follows_col = db.follows
reviews_col = db.course_reviews
courses_col = db.courses
refresh_tokens_col = db.refresh_tokens
wishlists_col = db.wishlists
import_jobs_col = db.import_jobs
notifications_col = db.notifications

# Auth config
SECRET_KEY = os.environ["JWT_SECRET_KEY"]
ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_EXPIRE_MIN = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
ENABLE_DEMO_SEED = os.environ.get("ENABLE_DEMO_SEED", "false").lower() in ("1", "true", "yes")
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "*").split(",") if o.strip()]
# Auto-populate global course library from OSM on first boot when the library is small.
AUTO_IMPORT_COURSES = os.environ.get("AUTO_IMPORT_COURSES", "true").lower() in ("1", "true", "yes")
AUTO_IMPORT_THRESHOLD = int(os.environ.get("AUTO_IMPORT_COURSES_THRESHOLD", "500"))
# Admins can trigger bulk course imports. Comma-separated list of emails.
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}
# APP_ENV drives production-only safety checks. Any value other than 'production' is
# treated as development for the boot-time guards below.
APP_ENV = os.environ.get("APP_ENV", "development").lower()

def is_admin_user(u: Optional[dict]) -> bool:
    return bool(u and (u.get("email") or "").lower() in ADMIN_EMAILS)

# SEC-001: refuse to boot in production with the seeded demo admin combo
# (`ENABLE_DEMO_SEED=true` + a `@teebox.demo` email in `ADMIN_EMAILS`). The
# demo user has a hard-coded password so this combination is an unauthenticated
# admin-takeover path. Dev / staging can still use it freely.
if APP_ENV == "production":
    if ENABLE_DEMO_SEED:
        raise RuntimeError(
            "SEC-001: ENABLE_DEMO_SEED=true is refused in production. Set "
            "ENABLE_DEMO_SEED=false (or remove) and create real admin accounts."
        )
    _demo_admins = {e for e in ADMIN_EMAILS if e.endswith("@teebox.demo") or e.endswith(".demo")}
    if _demo_admins:
        raise RuntimeError(
            f"SEC-001: ADMIN_EMAILS in production must not include demo addresses ({_demo_admins}). "
            "Set ADMIN_EMAILS to real production admin email(s)."
        )

# SEC-001: refuse to boot with a placeholder secret
_placeholder_tokens = ("change_me", "changeme", "placeholder", "changethis", "your-secret")
if len(SECRET_KEY) < 32 or any(tok in SECRET_KEY.lower() for tok in _placeholder_tokens):
    raise RuntimeError(
        "JWT_SECRET_KEY is missing, too short, or looks like a placeholder. "
        "Set a strong random value (>= 32 chars, no 'change_me'/'placeholder' text) in the environment."
    )

# SEC-003: base64 payload caps (bytes of base64 string, not decoded)
MAX_PHOTO_B64_LEN = 1_500_000   # ~1 MB decoded
MAX_AVATAR_B64_LEN = 800_000     # ~600 KB decoded
MAX_PHOTOS_PER_ROUND = 3

def _validate_b64_image(s: Optional[str], max_len: int, label: str) -> None:
    if s is None:
        return
    if not isinstance(s, str) or len(s) > max_len:
        raise HTTPException(status_code=413, detail=f"{label} too large")
    # Accept only data:image URIs or raw base64 (loose check — we don't decode)
    if s.startswith("data:") and not s.startswith("data:image/"):
        raise HTTPException(status_code=415, detail=f"{label} must be an image data URI")

# SEC-004: escape regex meta chars & cap query length for Mongo $regex
_regex_meta = re.compile(r"[.*+?^${}()|\[\]\\]")

def _safe_query(q: str, max_len: int = 60) -> str:
    q = (q or "").strip()[:max_len]
    return _regex_meta.sub(lambda m: "\\" + m.group(0), q)

# SEC-002: fields never returned for other users
_PUBLIC_USER_KEYS = {"id", "display_name", "handicap", "home_course", "bio", "avatar", "created_at"}

def public_user(u: dict) -> dict:
    return {k: v for k, v in (u or {}).items() if k in _PUBLIC_USER_KEYS}

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# Rate limiter (per real client IP, proxy-aware)
limiter = Limiter(key_func=_client_ip)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
api_router = APIRouter(prefix="/api")

# ---- Utils ----
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def create_access_token(sub: str) -> str:
    payload = {
        "sub": sub,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_EXPIRE_MIN),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def create_refresh_token(user_id: str, family_id: Optional[str] = None) -> str:
    jti = str(uuid.uuid4())
    family_id = family_id or jti
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRE_DAYS)
    token = jwt.encode(
        {
            "sub": user_id,
            "type": "refresh",
            "jti": jti,
            "family_id": family_id,
            "exp": expires_at,
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    await refresh_tokens_col.insert_one({
        "jti": jti,
        "user_id": user_id,
        "family_id": family_id,
        "expires_at": expires_at,
        "is_revoked": False,
        "is_rotated": False,
        "created_at": now_iso(),
    })
    return token

async def get_current_user(cred: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if cred is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(cred.credentials, SECRET_KEY, algorithms=[ALGORITHM], options={"leeway": 30})
        if payload.get("type") not in (None, "access"):  # None = legacy tokens
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await users_col.find_one({"id": user_id}, {"_id": 0, "hashed_password": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# ---- Models ----
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    display_name: str = Field(min_length=1, max_length=40)
    home_course: Optional[str] = None
    handicap: Optional[float] = None

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class AuthOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict

class RefreshIn(BaseModel):
    refresh_token: str

class RoundIn(BaseModel):
    course_name: str = Field(min_length=1, max_length=120)
    date: Optional[str] = None  # ISO date
    total_score: int
    par: Optional[int] = 72
    holes_played: Optional[int] = 18
    fairways_hit: Optional[int] = None
    greens_in_regulation: Optional[int] = None
    putts: Optional[int] = None
    notes: Optional[str] = ""
    photos: List[str] = []  # base64 data URIs
    weather: Optional[str] = None
    hole_scores: List[int] = []  # length 18 (or empty)
    hole_pars: List[int] = []    # length 18 (or empty)

class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    mentions: List[str] = []  # optional user ids

class ReviewIn(BaseModel):
    course_name: str
    rating: float = Field(ge=1.0, le=5.0)
    text: str = Field(min_length=1, max_length=1000)

class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    home_course: Optional[str] = Field(default=None, max_length=120)
    handicap: Optional[float] = Field(default=None, ge=-10, le=54)
    bio: Optional[str] = Field(default=None, max_length=280)
    avatar: Optional[str] = None  # base64

# ---- Helpers ----
async def enrich_round(r: dict, viewer_id: Optional[str]) -> dict:
    author = await users_col.find_one({"id": r["user_id"]}, {"_id": 0, "hashed_password": 0, "email": 0})
    like_count = await likes_col.count_documents({"round_id": r["id"]})
    comment_count = await comments_col.count_documents({"round_id": r["id"]})
    liked_by_me = False
    if viewer_id:
        liked_by_me = await likes_col.find_one({"round_id": r["id"], "user_id": viewer_id}) is not None
    r.pop("_id", None)
    return {
        **r,
        "author": {
            "id": author.get("id"),
            "display_name": author.get("display_name"),
            "handicap": author.get("handicap"),
            "avatar": author.get("avatar"),
        } if author else None,
        "like_count": like_count,
        "comment_count": comment_count,
        "liked_by_me": liked_by_me,
    }

# ---- Auth Routes ----
@api_router.get("/")
async def root():
    return {"message": "TeeBox API", "status": "ok"}

@api_router.post("/auth/register", response_model=AuthOut)
@limiter.limit("5/minute; 20/hour")
async def register(request: Request, data: RegisterIn):
    existing = await users_col.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id,
        "email": data.email.lower(),
        "hashed_password": pwd_context.hash(data.password),
        "display_name": data.display_name.strip(),
        "home_course": data.home_course or "",
        "handicap": data.handicap,
        "bio": "",
        "avatar": None,
        "created_at": now_iso(),
    }
    await users_col.insert_one(doc)
    access = create_access_token(user_id)
    refresh = await create_refresh_token(user_id)
    doc.pop("_id", None)
    doc.pop("hashed_password", None)
    doc["is_admin"] = is_admin_user(doc)
    return {"access_token": access, "refresh_token": refresh, "user": doc}

@api_router.post("/auth/login", response_model=AuthOut)
@limiter.limit("10/minute; 60/hour")
async def login(request: Request, data: LoginIn):
    user = await users_col.find_one({"email": data.email.lower()})
    if not user or not pwd_context.verify(data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    access = create_access_token(user["id"])
    refresh = await create_refresh_token(user["id"])
    user.pop("_id", None)
    user.pop("hashed_password", None)
    user["is_admin"] = is_admin_user(user)
    return {"access_token": access, "refresh_token": refresh, "user": user}

@api_router.post("/auth/refresh", response_model=AuthOut)
@limiter.limit("60/minute")
async def refresh(request: Request, data: RefreshIn):
    try:
        payload = jwt.decode(data.refresh_token, SECRET_KEY, algorithms=[ALGORITHM], options={"leeway": 30})
        if payload.get("type") != "refresh":
            raise JWTError("wrong type")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    jti = payload.get("jti")
    family_id = payload.get("family_id")
    user_id = payload.get("sub")
    db_token = await refresh_tokens_col.find_one({"jti": jti})
    if not db_token:
        # Unknown jti = family compromise; revoke everything for this family if we know it
        if family_id:
            await refresh_tokens_col.update_many({"family_id": family_id}, {"$set": {"is_revoked": True}})
        raise HTTPException(status_code=401, detail="Refresh token not recognised")
    if db_token.get("is_rotated") or db_token.get("is_revoked"):
        # Reuse detected — nuke the family
        await refresh_tokens_col.update_many({"family_id": family_id}, {"$set": {"is_revoked": True}})
        raise HTTPException(status_code=401, detail="Refresh token reuse detected — please sign in again")
    # SEC-108: atomic rotate — only one concurrent refresh may win.
    rot = await refresh_tokens_col.find_one_and_update(
        {"jti": jti, "is_rotated": False, "is_revoked": False},
        {"$set": {"is_rotated": True, "rotated_at": now_iso()}},
    )
    if not rot:
        # Someone else already rotated this jti concurrently → treat as reuse
        await refresh_tokens_col.update_many({"family_id": family_id}, {"$set": {"is_revoked": True}})
        raise HTTPException(status_code=401, detail="Refresh token reuse detected — please sign in again")
    user = await users_col.find_one({"id": user_id}, {"_id": 0, "hashed_password": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    new_access = create_access_token(user_id)
    new_refresh = await create_refresh_token(user_id, family_id=family_id)
    # SEC-108 hardening: guard against a race where the family was revoked
    # (by a concurrent reuse-detect) between our rotate + insert. If so,
    # revoke the newly-issued refresh so it can't be spent.
    family_state = await refresh_tokens_col.find_one(
        {"family_id": family_id, "is_revoked": True},
        {"_id": 0, "is_revoked": 1},
    )
    if family_state:
        await refresh_tokens_col.update_many(
            {"family_id": family_id},
            {"$set": {"is_revoked": True}},
        )
        raise HTTPException(status_code=401, detail="Refresh token reuse detected — please sign in again")
    return {"access_token": new_access, "refresh_token": new_refresh, "user": {**user, "is_admin": is_admin_user(user)}}

@api_router.post("/auth/logout")
async def logout(data: RefreshIn):
    try:
        payload = jwt.decode(data.refresh_token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        jti = payload.get("jti")
        if jti:
            await refresh_tokens_col.update_one({"jti": jti}, {"$set": {"is_revoked": True}})
    except JWTError:
        pass
    return {"ok": True}

@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return {**user, "is_admin": is_admin_user(user)}

@api_router.patch("/auth/me")
async def update_me(data: ProfileUpdate, user=Depends(get_current_user)):
    # exclude_unset=True preserves explicit nulls (e.g. clearing handicap)
    # while still ignoring omitted fields.
    updates = data.dict(exclude_unset=True)
    # SEC-102 hardening: display_name is a required identity field and must never be null/empty.
    # (Optional[str] + min_length skips None in Pydantic v1, so guard here.)
    if "display_name" in updates:
        v = updates["display_name"]
        if v is None or not str(v).strip():
            raise HTTPException(status_code=422, detail="display_name cannot be empty")
        updates["display_name"] = str(v).strip()
    if "avatar" in updates and updates["avatar"] is not None:
        _validate_b64_image(updates["avatar"], MAX_AVATAR_B64_LEN, "Avatar")
    if updates:
        await users_col.update_one({"id": user["id"]}, {"$set": updates})
    fresh = await users_col.find_one({"id": user["id"]}, {"_id": 0, "hashed_password": 0})
    return {**fresh, "is_admin": is_admin_user(fresh)}

# ---- Rounds ----
@api_router.post("/rounds")
async def create_round(data: RoundIn, user=Depends(get_current_user)):
    # SEC-003: cap photo count & size
    photos = (data.photos or [])[:MAX_PHOTOS_PER_ROUND]
    for p in photos:
        _validate_b64_image(p, MAX_PHOTO_B64_LEN, "Photo")
    round_id = str(uuid.uuid4())
    doc = {
        "id": round_id,
        "user_id": user["id"],
        "course_name": data.course_name.strip(),
        "date": data.date or now_iso(),
        "total_score": data.total_score,
        "par": data.par or 72,
        "holes_played": data.holes_played or 18,
        "fairways_hit": data.fairways_hit,
        "greens_in_regulation": data.greens_in_regulation,
        "putts": data.putts,
        "notes": data.notes or "",
        "photos": photos,
        "weather": data.weather,
        "hole_scores": data.hole_scores or [],
        "hole_pars": data.hole_pars or [],
        "created_at": now_iso(),
    }
    await rounds_col.insert_one(doc)
    return await enrich_round(doc, user["id"])

@api_router.get("/feed")
async def get_feed(
    scope: str = Query("followers"),
    limit: int = Query(30, ge=1, le=100),
    user=Depends(get_current_user),
):
    query: dict = {}
    if scope == "followers":
        following = [f["target_id"] async for f in follows_col.find({"user_id": user["id"]}, {"_id": 0, "target_id": 1})]
        query = {"user_id": {"$in": following + [user["id"]]}}
    cursor = rounds_col.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    items = [await enrich_round(r, user["id"]) async for r in cursor]
    return items

@api_router.get("/courses/{course_name}/rounds")
async def get_course_rounds(course_name: str, user=Depends(get_current_user)):
    cursor = rounds_col.find({"course_name": course_name}, {"_id": 0}).sort("created_at", -1).limit(50)
    return [await enrich_round(r, user["id"]) async for r in cursor]

@api_router.get("/rounds/{round_id}")
async def get_round(round_id: str, user=Depends(get_current_user)):
    r = await rounds_col.find_one({"id": round_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Round not found")
    return await enrich_round(r, user["id"])

@api_router.delete("/rounds/{round_id}")
async def delete_round(round_id: str, user=Depends(get_current_user)):
    r = await rounds_col.find_one({"id": round_id})
    if not r:
        raise HTTPException(status_code=404, detail="Round not found")
    if r["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    await rounds_col.delete_one({"id": round_id})
    await likes_col.delete_many({"round_id": round_id})
    await comments_col.delete_many({"round_id": round_id})
    return {"ok": True}

@api_router.post("/rounds/{round_id}/like")
async def toggle_like(round_id: str, user=Depends(get_current_user)):
    r = await rounds_col.find_one({"id": round_id})
    if not r:
        raise HTTPException(status_code=404, detail="Round not found")
    existing = await likes_col.find_one({"round_id": round_id, "user_id": user["id"]})
    if existing:
        await likes_col.delete_one({"round_id": round_id, "user_id": user["id"]})
        liked = False
    else:
        await likes_col.insert_one({
            "id": str(uuid.uuid4()),
            "round_id": round_id,
            "user_id": user["id"],
            "created_at": now_iso(),
        })
        liked = True
    count = await likes_col.count_documents({"round_id": round_id})
    return {"liked": liked, "like_count": count}

@api_router.get("/rounds/{round_id}/comments")
async def get_comments(round_id: str, user=Depends(get_current_user)):
    out = []
    async for c in comments_col.find({"round_id": round_id}, {"_id": 0}).sort("created_at", 1):
        author = await users_col.find_one({"id": c["user_id"]}, {"_id": 0, "hashed_password": 0})
        out.append({
            **c,
            "author": {
                "id": author.get("id"),
                "display_name": author.get("display_name"),
                "avatar": author.get("avatar"),
            } if author else None,
        })
    return out

@api_router.post("/rounds/{round_id}/comments")
async def add_comment(round_id: str, data: CommentIn, user=Depends(get_current_user)):
    r = await rounds_col.find_one({"id": round_id})
    if not r:
        raise HTTPException(status_code=404, detail="Round not found")
    doc = {
        "id": str(uuid.uuid4()),
        "round_id": round_id,
        "user_id": user["id"],
        "text": data.text.strip(),
        "mentions": data.mentions or [],
        "created_at": now_iso(),
    }
    await comments_col.insert_one(doc)
    doc.pop("_id", None)
    return {
        **doc,
        "author": {
            "id": user["id"],
            "display_name": user["display_name"],
            "avatar": user.get("avatar"),
        },
    }

# ---- Users / Profiles ----
@api_router.get("/users/{user_id}")
async def get_user(user_id: str, user=Depends(get_current_user)):
    target = await users_col.find_one({"id": user_id}, {"_id": 0, "hashed_password": 0, "email": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    round_count = await rounds_col.count_documents({"user_id": user_id})
    scores_cursor = rounds_col.find({"user_id": user_id}, {"_id": 0, "total_score": 1}).sort("created_at", -1).limit(20)
    recent_scores = [s["total_score"] async for s in scores_cursor]
    avg_score = round(sum(recent_scores) / len(recent_scores), 1) if recent_scores else None
    follower_count = await follows_col.count_documents({"target_id": user_id})
    following_count = await follows_col.count_documents({"user_id": user_id})
    # Distinct courses played
    courses_played = 0
    async for _ in rounds_col.aggregate([
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$course_name"}},
        {"$count": "n"},
    ]):
        courses_played = _["n"]
    # Friends = mutual follows
    following_ids = {f["target_id"] async for f in follows_col.find({"user_id": user_id}, {"_id": 0, "target_id": 1})}
    follower_ids = {f["user_id"] async for f in follows_col.find({"target_id": user_id}, {"_id": 0, "user_id": 1})}
    friend_ids = following_ids & follower_ids
    friends_count = len(friend_ids)
    following = False
    is_friend = False
    if user["id"] != user_id:
        following = await follows_col.find_one({"user_id": user["id"], "target_id": user_id}) is not None
        reverse = await follows_col.find_one({"user_id": user_id, "target_id": user["id"]}) is not None
        is_friend = following and reverse
    # Pinned round
    pinned_round = None
    pin_id = target.get("pinned_round_id")
    if pin_id:
        pr = await rounds_col.find_one({"id": pin_id, "user_id": user_id}, {"_id": 0})
        if pr:
            pinned_round = await enrich_round(pr, user["id"])
        else:
            # Stale pin — clear it
            await users_col.update_one({"id": user_id}, {"$unset": {"pinned_round_id": ""}})
    return {
        **public_user(target),
        "pinned_round": pinned_round,
        "round_count": round_count,
        "avg_score": avg_score,
        "courses_played": courses_played,
        "friends_count": friends_count,
        "follower_count": follower_count,
        "following_count": following_count,
        "wishlist_count": await wishlists_col.count_documents({"user_id": user_id}),
        "is_following": following,
        "is_friend": is_friend,
        "is_me": user["id"] == user_id,
    }

@api_router.get("/users/{user_id}/rounds")
async def get_user_rounds(user_id: str, user=Depends(get_current_user)):
    cursor = rounds_col.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1)
    return [await enrich_round(r, user["id"]) async for r in cursor]

@api_router.get("/users/{user_id}/friends")
async def get_user_friends(user_id: str, user=Depends(get_current_user)):
    following_ids = {f["target_id"] async for f in follows_col.find({"user_id": user_id}, {"_id": 0, "target_id": 1})}
    follower_ids = {f["user_id"] async for f in follows_col.find({"target_id": user_id}, {"_id": 0, "user_id": 1})}
    friend_ids = following_ids & follower_ids
    if not friend_ids:
        return []
    # Viewer perspective
    viewer_following = {f["target_id"] async for f in follows_col.find({"user_id": user["id"]}, {"_id": 0, "target_id": 1})}
    viewer_followers = {f["user_id"] async for f in follows_col.find({"target_id": user["id"]}, {"_id": 0, "user_id": 1})}
    out = []
    async for u in users_col.find({"id": {"$in": list(friend_ids)}}, {"_id": 0, "hashed_password": 0, "email": 0}):
        fid = u["id"]
        is_following = fid in viewer_following
        is_friend = fid in viewer_following and fid in viewer_followers
        rounds = await rounds_col.count_documents({"user_id": fid})
        out.append({
            **public_user(u),
            "round_count": rounds,
            "is_following": is_following,
            "is_friend": is_friend,
            "is_me": fid == user["id"],
        })
    out.sort(key=lambda x: (not x["is_friend"], (x.get("display_name") or "").lower()))
    return out

# ---- Pin a round on your profile ----
@api_router.post("/rounds/{round_id}/pin")
async def pin_round(round_id: str, user=Depends(get_current_user)):
    r = await rounds_col.find_one({"id": round_id})
    if not r:
        raise HTTPException(status_code=404, detail="Round not found")
    if r["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Can only pin your own rounds")
    await users_col.update_one({"id": user["id"]}, {"$set": {"pinned_round_id": round_id}})
    return {"pinned": True, "round_id": round_id}

@api_router.delete("/users/me/pin")
async def unpin_round(user=Depends(get_current_user)):
    await users_col.update_one({"id": user["id"]}, {"$unset": {"pinned_round_id": ""}})
    return {"pinned": False}

@api_router.get("/users/{user_id}/achievements")
async def get_achievements(user_id: str, user=Depends(get_current_user)):
    rounds = [r async for r in rounds_col.find({"user_id": user_id}, {"_id": 0}).sort("created_at", 1)]
    scores = [r["total_score"] for r in rounds]
    courses = {r["course_name"] for r in rounds}
    # Consecutive rounds <= 80 count
    streak = 0
    best_streak = 0
    for s in scores:
        if s <= 80:
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0

    defs = [
        {"key": "first_round", "title": "On the tee", "desc": "Logged your first round.", "icon": "flag", "earned": len(rounds) >= 1},
        {"key": "sub_100", "title": "Broke 100", "desc": "Posted a round under 100.", "icon": "trophy", "earned": any(s < 100 for s in scores)},
        {"key": "sub_90", "title": "Broke 90", "desc": "Posted a round under 90.", "icon": "trophy", "earned": any(s < 90 for s in scores)},
        {"key": "sub_80", "title": "First sub-80", "desc": "Posted a round under 80.", "icon": "trophy", "earned": any(s < 80 for s in scores)},
        {"key": "sub_70", "title": "Sub-70 club", "desc": "Posted a round under 70.", "icon": "star", "earned": any(s < 70 for s in scores)},
        {"key": "ten_rounds", "title": "Regular", "desc": "Logged 10 rounds.", "icon": "golf", "earned": len(rounds) >= 10},
        {"key": "fifty_rounds", "title": "Half-century", "desc": "Logged 50 rounds.", "icon": "medal", "earned": len(rounds) >= 50},
        {"key": "course_collector", "title": "Course collector", "desc": "Played 5 different courses.", "icon": "map", "earned": len(courses) >= 5},
        {"key": "hot_streak", "title": "Hot streak", "desc": "3 rounds in a row at or under 80.", "icon": "flame", "earned": best_streak >= 3},
    ]
    return {
        "total": sum(1 for d in defs if d["earned"]),
        "achievements": defs,
    }

@api_router.post("/users/{user_id}/follow")
async def toggle_follow(user_id: str, user=Depends(get_current_user)):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")
    target = await users_col.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    existing = await follows_col.find_one({"user_id": user["id"], "target_id": user_id})
    if existing:
        await follows_col.delete_one({"user_id": user["id"], "target_id": user_id})
        return {"following": False}
    await follows_col.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "target_id": user_id,
        "created_at": now_iso(),
    })
    return {"following": True}

# ---- Wishlist ----
async def _enrich_wishlist_entry(entry: dict) -> dict:
    course = await courses_col.find_one({"name": entry["course_name"]}, {"_id": 0})
    return {
        "course_name": entry["course_name"],
        "added_at": entry.get("created_at"),
        "city": course.get("city") if course else None,
        "region": course.get("region") if course else None,
        "country": course.get("country") if course else None,
    }

class WishlistIn(BaseModel):
    course_name: str = Field(min_length=1, max_length=120)

@api_router.get("/users/{user_id}/wishlist")
async def get_wishlist(user_id: str, user=Depends(get_current_user)):
    out = []
    async for w in wishlists_col.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1):
        out.append(await _enrich_wishlist_entry(w))
    return out

@api_router.post("/wishlist")
async def add_to_wishlist(data: WishlistIn, user=Depends(get_current_user)):
    course_name = data.course_name.strip()
    # SEC-107: cap wishlist size per user
    count = await wishlists_col.count_documents({"user_id": user["id"]})
    if count >= 200:
        raise HTTPException(status_code=413, detail="Wishlist is full (200 max)")
    existing = await wishlists_col.find_one({"user_id": user["id"], "course_name": course_name})
    if existing:
        return {"added": False, "reason": "already on wishlist"}
    await wishlists_col.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "course_name": course_name,
        "created_at": now_iso(),
    })
    return {"added": True}

@api_router.delete("/wishlist/{course_name}")
async def remove_from_wishlist(course_name: str, user=Depends(get_current_user)):
    res = await wishlists_col.delete_one({"user_id": user["id"], "course_name": course_name})
    return {"removed": res.deleted_count > 0}

@api_router.get("/wishlist/check/{course_name}")
async def check_wishlist(course_name: str, user=Depends(get_current_user)):
    exists = await wishlists_col.find_one({"user_id": user["id"], "course_name": course_name}) is not None
    return {"on_wishlist": exists}

# ---- Discover ----
@api_router.get("/discover/users")
async def discover_users(q: str = "", user=Depends(get_current_user)):
    query = {}
    safe = _safe_query(q)
    if safe:
        query = {"display_name": {"$regex": safe, "$options": "i"}}
    users = []
    async for u in users_col.find(query, {"_id": 0, "hashed_password": 0, "email": 0}).limit(30):
        if u["id"] == user["id"]:
            continue
        round_count = await rounds_col.count_documents({"user_id": u["id"]})
        users.append({**public_user(u), "round_count": round_count})
    return users

@api_router.get("/discover/courses")
async def discover_courses(q: str = "", user=Depends(get_current_user)):
    safe = _safe_query(q)
    # Aggregate rounds by course
    pipeline = []
    if safe:
        pipeline.append({"$match": {"course_name": {"$regex": safe, "$options": "i"}}})
    pipeline += [
        {"$group": {
            "_id": "$course_name",
            "play_count": {"$sum": 1},
            "avg_score": {"$avg": "$total_score"},
            "best_score": {"$min": "$total_score"},
            "last_photo": {"$last": {"$arrayElemAt": ["$photos", 0]}},
        }},
    ]
    round_agg = {}
    async for c in rounds_col.aggregate(pipeline):
        round_agg[c["_id"]] = c

    # Master course list — hide unverified courses from other users, but keep
    # unverified courses submitted by the current user so they can find them.
    course_query: dict = {
        "$or": [
            {"verified": {"$ne": False}},        # verified=True OR verified missing (legacy)
            {"submitted_by": user["id"]},
        ]
    }
    if safe:
        course_query = {"$and": [course_query, {"name": {"$regex": safe, "$options": "i"}}]}
    master = [c async for c in courses_col.find(course_query, {"_id": 0}).limit(100)]

    seen = set()
    out = []
    # Master first, enriched with any round agg
    for m in master:
        name = m["name"]
        seen.add(name)
        r = round_agg.get(name)
        review_count = await reviews_col.count_documents({"course_name": name})
        avg_rating = None
        async for x in reviews_col.aggregate([
            {"$match": {"course_name": name}},
            {"$group": {"_id": None, "avg": {"$avg": "$rating"}}},
        ]):
            avg_rating = round(x["avg"], 2)
        out.append({
            "course_name": name,
            "city": m.get("city"),
            "region": m.get("region"),
            "country": m.get("country"),
            "lat": m.get("lat"),
            "lng": m.get("lng"),
            "play_count": r["play_count"] if r else 0,
            "avg_score": round(r["avg_score"], 1) if r and r["avg_score"] else None,
            "best_score": r["best_score"] if r else None,
            "last_photo": r.get("last_photo") if r else None,
            "review_count": review_count,
            "avg_rating": avg_rating,
        })
    # Any played courses not in master list, append after
    for name, r in round_agg.items():
        if name in seen:
            continue
        review_count = await reviews_col.count_documents({"course_name": name})
        avg_rating = None
        async for x in reviews_col.aggregate([
            {"$match": {"course_name": name}},
            {"$group": {"_id": None, "avg": {"$avg": "$rating"}}},
        ]):
            avg_rating = round(x["avg"], 2)
        out.append({
            "course_name": name,
            "city": None,
            "region": None,
            "country": None,
            "lat": None,
            "lng": None,
            "play_count": r["play_count"],
            "avg_score": round(r["avg_score"], 1) if r["avg_score"] else None,
            "best_score": r["best_score"],
            "last_photo": r.get("last_photo"),
            "review_count": review_count,
            "avg_rating": avg_rating,
        })
    # Sort: played first (desc play_count), then master (alphabetical)
    out.sort(key=lambda c: (-c["play_count"], c["course_name"].lower()))
    return out[:60]


# ---- Nearby courses (location-based) ----
def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


@api_router.get("/discover/courses/nearby")
@limiter.limit("30/minute")
async def discover_courses_nearby(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(80.0, ge=1, le=500),
    limit: int = Query(30, ge=1, le=60),
    user=Depends(get_current_user),
):
    """Return courses within a radius, sorted by distance ascending.
    Uses a lat/lng bounding-box pre-filter then per-candidate haversine so we
    don't need a 2dsphere index. This scales fine for < ~50k courses."""
    # Bounding box radius in degrees:
    # 1° latitude ≈ 111 km; 1° longitude ≈ 111 km * cos(lat)
    d_lat = radius_km / 111.0
    cos_lat = max(0.01, math.cos(math.radians(lat)))
    d_lng = radius_km / (111.0 * cos_lat)
    box_query = {
        "lat": {"$gte": lat - d_lat, "$lte": lat + d_lat, "$ne": None},
        "lng": {"$gte": lng - d_lng, "$lte": lng + d_lng, "$ne": None},
        "$or": [
            {"verified": {"$ne": False}},
            {"submitted_by": user["id"]},
        ],
    }

    candidates = []
    # Cap the scan at 500 candidate docs to keep this cheap on dense areas.
    async for c in courses_col.find(box_query, {"_id": 0}).limit(500):
        clat = c.get("lat")
        clng = c.get("lng")
        if clat is None or clng is None:
            continue
        dist = _haversine_km(lat, lng, clat, clng)
        if dist > radius_km:
            continue
        candidates.append((dist, c))

    candidates.sort(key=lambda x: x[0])
    out = []
    for dist, c in candidates[:limit]:
        name = c["name"]
        play_count = await rounds_col.count_documents({"course_name": name})
        avg_rating = None
        async for x in reviews_col.aggregate([
            {"$match": {"course_name": name}},
            {"$group": {"_id": None, "avg": {"$avg": "$rating"}}},
        ]):
            avg_rating = round(x["avg"], 2)
        review_count = await reviews_col.count_documents({"course_name": name})
        out.append({
            "course_name": name,
            "city": c.get("city"),
            "region": c.get("region"),
            "country": c.get("country"),
            "lat": c.get("lat"),
            "lng": c.get("lng"),
            "distance_km": round(dist, 1),
            "play_count": play_count,
            "review_count": review_count,
            "avg_rating": avg_rating,
        })
    return out


# ---- Course search (lightweight autocomplete for Log Round) ----
@api_router.get("/courses/search")
@limiter.limit("120/minute")
async def course_search(request: Request, q: str = "", limit: int = Query(15, ge=1, le=30), user=Depends(get_current_user)):
    """Prefix-friendly course lookup for the Log Round autocomplete.
    Returns verified courses + the current user's own submissions."""
    safe = _safe_query(q, max_len=80)
    if not safe:
        return []
    query = {
        "name": {"$regex": safe, "$options": "i"},
        "$or": [
            {"verified": {"$ne": False}},
            {"submitted_by": user["id"]},
        ],
    }
    out = []
    async for c in courses_col.find(query, {"_id": 0}).limit(limit):
        out.append({
            "id": c.get("id"),
            "name": c["name"],
            "city": c.get("city"),
            "region": c.get("region"),
            "country": c.get("country"),
            "par": c.get("par"),
            "verified": c.get("verified", True),  # missing = legacy = considered verified
            "submitted_by_me": c.get("submitted_by") == user["id"],
        })
    return out

# ---- User-submitted courses (community add) ----
class NewCourseIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    par: int = Field(ge=27, le=90)  # 9-hole par ~27 up to par-90 mega courses
    city: Optional[str] = Field(default=None, max_length=80)
    region: Optional[str] = Field(default=None, max_length=80)
    country: Optional[str] = Field(default=None, max_length=60)

@api_router.post("/courses")
@limiter.limit("10/hour")
async def submit_course(request: Request, data: NewCourseIn, user=Depends(get_current_user)):
    """Community submission of a missing course. Persists with verified=False
    and is only visible to the submitter until an admin approves it."""
    name = data.name.strip()
    # Case-insensitive dup check — mongo unique index is exact-match, so we also
    # guard here to avoid "Pebble Beach" vs "pebble beach" duplicates.
    existing = await courses_col.find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"_id": 0, "id": 1, "name": 1, "verified": 1, "submitted_by": 1},
    )
    if existing:
        # If it exists and is theirs / already verified, just return it — no error.
        return {"course": existing, "created": False}
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "par": data.par,
        "city": (data.city or "").strip() or None,
        "region": (data.region or "").strip() or None,
        "country": (data.country or "").strip() or None,
        "lat": None,
        "lng": None,
        "source": "community",
        "verified": False,
        "submitted_by": user["id"],
        "submitted_by_name": user.get("display_name"),
        "created_at": now_iso(),
    }
    try:
        await courses_col.insert_one(doc)
    except Exception:
        raise HTTPException(status_code=409, detail="A course with this name already exists")
    doc.pop("_id", None)
    return {"course": doc, "created": True}


# ---- Admin: pending courses queue & verification ----
@api_router.get("/admin/courses/pending")
async def admin_list_pending(user=Depends(get_current_user)):
    _require_admin(user)
    out = []
    async for c in courses_col.find({"verified": False}, {"_id": 0}).sort("created_at", -1).limit(100):
        # Attach round-count so admin can see if this course is being actively used
        used = await rounds_col.count_documents({"course_name": c["name"]})
        out.append({**c, "round_count": used})
    return out


class RejectIn(BaseModel):
    reason: Optional[str] = Field(default="", max_length=280)


@api_router.post("/admin/courses/{course_id}/verify")
async def admin_verify_course(course_id: str, user=Depends(get_current_user)):
    _require_admin(user)
    course = await courses_col.find_one({"id": course_id}, {"_id": 0})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.get("verified"):
        return {"ok": True, "already_verified": True}
    await courses_col.update_one(
        {"id": course_id},
        {"$set": {"verified": True, "verified_at": now_iso(), "verified_by": user["id"]}},
    )
    # Silent approval — no notification (per product spec).
    return {"ok": True}


@api_router.post("/admin/courses/{course_id}/reject")
async def admin_reject_course(course_id: str, data: RejectIn, user=Depends(get_current_user)):
    _require_admin(user)
    course = await courses_col.find_one({"id": course_id}, {"_id": 0})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.get("verified"):
        raise HTTPException(status_code=400, detail="Cannot reject a course that is already verified")
    submitter = course.get("submitted_by")
    reason = (data.reason or "").strip()
    # Notify the submitter first (before deletion), so we retain the course_name
    if submitter:
        await notifications_col.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": submitter,
            "type": "course_rejected",
            "title": "Course submission rejected",
            "body": (
                f'Your submission "{course["name"]}" was not approved.'
                + (f" Reason: {reason}" if reason else "")
            ),
            "course_name": course["name"],
            "reason": reason or None,
            "read": False,
            "created_at": now_iso(),
        })
    await courses_col.delete_one({"id": course_id})
    return {"ok": True}


# ---- Notifications ----
@api_router.get("/notifications")
@limiter.limit("60/minute")
async def list_notifications(request: Request, user=Depends(get_current_user)):
    out = []
    async for n in notifications_col.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(50):
        out.append(n)
    unread = await notifications_col.count_documents({"user_id": user["id"], "read": False})
    return {"notifications": out, "unread": unread}


@api_router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, user=Depends(get_current_user)):
    await notifications_col.update_one(
        {"id": notification_id, "user_id": user["id"]},
        {"$set": {"read": True, "read_at": now_iso()}},
    )
    return {"ok": True}


@api_router.post("/notifications/read-all")
async def mark_all_notifications_read(user=Depends(get_current_user)):
    await notifications_col.update_many(
        {"user_id": user["id"], "read": False},
        {"$set": {"read": True, "read_at": now_iso()}},
    )
    return {"ok": True}


# ---- Course Reviews ----
@api_router.get("/courses/{course_name}/reviews")
async def get_reviews(course_name: str, user=Depends(get_current_user)):
    out = []
    async for r in reviews_col.find({"course_name": course_name}, {"_id": 0}).sort("created_at", -1):
        author = await users_col.find_one({"id": r["user_id"]}, {"_id": 0, "hashed_password": 0, "email": 0})
        out.append({
            **r,
            "author": {
                "id": author.get("id"),
                "display_name": author.get("display_name"),
                "avatar": author.get("avatar"),
                "handicap": author.get("handicap"),
            } if author else None,
        })
    return out

@api_router.get("/courses/{course_name}")
async def get_course(course_name: str, user=Depends(get_current_user)):
    """Return course metadata (from master list) merged with rounds/reviews stats."""
    course = await courses_col.find_one({"name": course_name}, {"_id": 0})
    play_count = await rounds_col.count_documents({"course_name": course_name})
    review_count = await reviews_col.count_documents({"course_name": course_name})
    avg_rating = None
    async for x in reviews_col.aggregate([
        {"$match": {"course_name": course_name}},
        {"$group": {"_id": None, "avg": {"$avg": "$rating"}}},
    ]):
        avg_rating = round(x["avg"], 2)
    return {
        "course_name": course_name,
        "city": course.get("city") if course else None,
        "region": course.get("region") if course else None,
        "country": course.get("country") if course else None,
        "lat": course.get("lat") if course else None,
        "lng": course.get("lng") if course else None,
        "play_count": play_count,
        "review_count": review_count,
        "avg_rating": avg_rating,
    }

@api_router.post("/courses/reviews")
async def create_review(data: ReviewIn, user=Depends(get_current_user)):
    # Round to nearest 0.25 to keep data tidy
    rating = round(data.rating * 4) / 4
    rating = max(1.0, min(5.0, rating))
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "course_name": data.course_name.strip(),
        "rating": rating,
        "text": data.text.strip(),
        "created_at": now_iso(),
    }
    await reviews_col.insert_one(doc)
    doc.pop("_id", None)
    return doc

# ---- OSM import ----
# Overpass API is public/free but heavy queries can 429/timeout. We keep global sweeps
# well-behaved: 20°×20° tiles, per-tile timeout 60s, 2s pause between tiles, multi-mirror
# fallback if the primary is down.
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

def _overpass_query(south: float, west: float, north: float, east: float, timeout: int = 60) -> str:
    return f"""
    [out:json][timeout:{timeout}];
    (
      node["leisure"="golf_course"]({south},{west},{north},{east});
      way["leisure"="golf_course"]({south},{west},{north},{east});
      relation["leisure"="golf_course"]({south},{west},{north},{east});
    );
    out center tags;
    """

async def _overpass_fetch(query: str, timeout: float = 90.0) -> dict:
    """Try each Overpass mirror in turn. Raise on all-failed.
    Overpass etiquette: identify with a stable User-Agent and only re-attempt on
    rate-limit / server-error / not-acceptable responses."""
    import httpx
    headers = {
        # Overpass servers ask clients to identify themselves; anonymous or generic
        # UAs are sometimes rejected with 406/403.
        "User-Agent": "TeeBox/1.0 (+https://teebox.app; support@teebox.app)",
        "Accept": "application/json",
    }
    last_err: Optional[str] = None
    for url in OVERPASS_ENDPOINTS:
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers) as http:
                resp = await http.post(url, data={"data": query})
                # 406/403/429/5xx → try next mirror; anything else raise for status
                if resp.status_code in (403, 406, 429) or resp.status_code >= 500:
                    last_err = f"{url} → {resp.status_code}"
                    continue
                resp.raise_for_status()
                return resp.json()
        except Exception as e:  # noqa: BLE001
            last_err = f"{url} → {e}"
            continue
    raise HTTPException(status_code=502, detail=f"OSM Overpass unreachable: {last_err}")

async def _persist_osm_elements(elements: list) -> int:
    """Insert new courses from an Overpass elements payload; return count inserted.
    Idempotent: silently skips duplicates by name (unique index enforces this too)."""
    from pymongo.errors import DuplicateKeyError
    inserted = 0
    for el in elements or []:
        tags = el.get("tags", {}) or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        if await courses_col.find_one({"name": name}, {"_id": 1}):
            continue
        lat = el.get("lat") if el.get("type") == "node" else (el.get("center", {}) or {}).get("lat")
        lng = el.get("lon") if el.get("type") == "node" else (el.get("center", {}) or {}).get("lon")
        try:
            await courses_col.insert_one({
                "id": str(uuid.uuid4()),
                "name": name,
                "city": tags.get("addr:city"),
                "region": tags.get("addr:state") or tags.get("addr:region"),
                "country": tags.get("addr:country"),
                "lat": lat,
                "lng": lng,
                "source": "osm",
                "created_at": now_iso(),
            })
            inserted += 1
        except DuplicateKeyError:
            # Another tile inserted this course first — safe to skip.
            continue
    return inserted

def _sweep_tiles(tile: int = 20) -> list:
    """Global sweep tiles: covers -60..70 lat × -180..180 lng."""
    tiles = []
    for south in range(-60, 70, tile):
        for west in range(-180, 180, tile):
            tiles.append((float(south), float(west), float(south + tile), float(west + tile)))
    return tiles


def _country_tiles(tile: int = 8) -> list:
    """All-countries sweep: iterate every known country bbox and subdivide it into
    Overpass-friendly tiles. Faster and more reliable than a global grid because
    ocean is skipped naturally and each tile hits a hand-tuned box."""
    tiles = []
    for _code, (south, west, north, east) in COUNTRY_BBOXES.items():
        lat = south
        while lat < north:
            lng = west
            while lng < east:
                tiles.append((lat, lng, min(lat + tile, north), min(lng + tile, east)))
                lng += tile
            lat += tile
    return tiles

# Country bounding boxes: south, west, north, east
COUNTRY_BBOXES: dict = {
    "US":   (24.5, -125.0, 49.5, -66.5),
    "AK":   (54.0, -170.0, 71.5, -130.0),
    "HI":   (18.5, -161.0, 22.5, -154.5),
    "CA":   (41.5, -141.0, 60.0, -52.5),
    "MX":   (14.5, -118.5, 32.7, -86.5),
    "UK":   (49.5, -8.5, 60.9, 1.8),
    "IE":   (51.4, -10.6, 55.5, -5.9),
    "FR":   (41.0, -5.5, 51.5, 9.7),
    "DE":   (47.2, 5.8, 55.1, 15.1),
    "ES":   (35.9, -9.5, 43.9, 4.4),
    "PT":   (36.9, -9.6, 42.2, -6.0),
    "IT":   (36.6, 6.6, 47.1, 18.6),
    "NL":   (50.7, 3.3, 53.6, 7.3),
    "BE":   (49.5, 2.5, 51.6, 6.5),
    "CH":   (45.8, 5.9, 47.9, 10.5),
    "AT":   (46.3, 9.5, 49.1, 17.2),
    "SE":   (55.3, 10.9, 69.1, 24.2),
    "NO":   (57.9, 4.6, 71.2, 31.3),
    "DK":   (54.5, 8.0, 57.8, 15.2),
    "FI":   (59.7, 20.5, 70.1, 31.6),
    "AU":   (-44.0, 112.0, -10.0, 154.0),
    "NZ":   (-47.3, 166.3, -34.4, 178.6),
    "JP":   (30.9, 129.4, 45.6, 145.9),
    "KR":   (33.1, 125.9, 38.6, 129.6),
    "CN":   (18.0, 73.5, 53.6, 134.8),
    "TH":   (5.6, 97.3, 20.5, 105.7),
    "SG":   (1.2, 103.6, 1.5, 104.1),
    "IN":   (6.5, 68.1, 35.5, 97.4),
    "AE":   (22.6, 51.5, 26.1, 56.4),
    "ZA":   (-35.0, 16.4, -22.1, 32.9),
    "BR":   (-33.8, -73.9, 5.3, -34.8),
    "AR":   (-55.1, -73.6, -21.8, -53.6),
    "CL":   (-55.9, -75.6, -17.5, -66.9),
    "MA":   (27.7, -13.2, 35.9, -1.0),
    "TR":   (35.8, 25.7, 42.1, 44.8),
}

async def _run_import_job(job_id: str, tiles: list, delay_s: float = 2.0) -> None:
    """Background job: walks tiles, updates progress in Mongo. Supports cancellation."""
    import asyncio
    total = len(tiles)
    processed = 0
    inserted_total = 0
    errors = 0
    try:
        await import_jobs_col.update_one(
            {"id": job_id},
            {"$set": {"status": "running", "total_tiles": total, "started_at": now_iso()}},
        )
        for (south, west, north, east) in tiles:
            latest = await import_jobs_col.find_one({"id": job_id}, {"_id": 0, "status": 1})
            if latest and latest.get("status") == "cancelled":
                logger.info(f"import job {job_id} cancelled at tile {processed}/{total}")
                break
            try:
                data = await _overpass_fetch(_overpass_query(south, west, north, east, timeout=45), timeout=60.0)
                inserted = await _persist_osm_elements(data.get("elements", []))
                inserted_total += inserted
            except HTTPException as e:
                errors += 1
                logger.warning(f"import job {job_id} tile ({south},{west}) failed: {e.detail}")
            except Exception as e:  # noqa: BLE001
                errors += 1
                logger.warning(f"import job {job_id} tile ({south},{west}) failed: {e}")
            processed += 1
            await import_jobs_col.update_one(
                {"id": job_id},
                {"$set": {
                    "processed_tiles": processed,
                    "inserted": inserted_total,
                    "errors": errors,
                    "last_tile": {"south": south, "west": west, "north": north, "east": east},
                    "updated_at": now_iso(),
                }},
            )
            await asyncio.sleep(delay_s)
        total_courses = await courses_col.count_documents({})
        current = await import_jobs_col.find_one({"id": job_id}, {"_id": 0, "status": 1}) or {}
        final_status = "cancelled" if current.get("status") == "cancelled" else "completed"
        await import_jobs_col.update_one(
            {"id": job_id},
            {"$set": {
                "status": final_status,
                "finished_at": now_iso(),
                "total_courses_after": total_courses,
            }},
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"import job {job_id} crashed: {e}")
        await import_jobs_col.update_one(
            {"id": job_id},
            {"$set": {"status": "failed", "error": str(e)[:500], "finished_at": now_iso()}},
        )


def _require_admin(user: dict) -> None:
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Admin access required")


@api_router.post("/admin/courses/import-osm-global")
async def admin_import_osm_global(
    tile: int = Query(20, ge=5, le=40, description="Tile size in degrees"),
    delay: float = Query(2.0, ge=0.5, le=10.0, description="Seconds to pause between tiles"),
    user=Depends(get_current_user),
):
    """Admin-only: kick off a background world sweep of OSM golf courses."""
    import asyncio
    _require_admin(user)
    active = await import_jobs_col.find_one({"status": {"$in": ["queued", "running"]}}, {"_id": 0, "id": 1})
    if active:
        raise HTTPException(status_code=409, detail=f"Import job {active['id']} is already active")

    tiles = _sweep_tiles(tile=tile)
    job_id = str(uuid.uuid4())
    await import_jobs_col.insert_one({
        "id": job_id,
        "kind": "global",
        "tile_deg": tile,
        "status": "queued",
        "total_tiles": len(tiles),
        "processed_tiles": 0,
        "inserted": 0,
        "errors": 0,
        "created_at": now_iso(),
        "triggered_by": user["id"],
    })
    asyncio.create_task(_run_import_job(job_id, tiles, delay_s=delay))
    return {"job_id": job_id, "total_tiles": len(tiles), "status": "queued"}


@api_router.post("/admin/courses/import-osm-country")
async def admin_import_osm_country(
    country: str = Query(..., description="Country code (US, UK, JP, etc.)"),
    tile: int = Query(10, ge=2, le=30),
    delay: float = Query(2.0, ge=0.5, le=10.0),
    user=Depends(get_current_user),
):
    """Admin-only: sweep a single country using a hand-tuned bounding box."""
    import asyncio
    _require_admin(user)
    code = country.upper().strip()
    if code not in COUNTRY_BBOXES:
        raise HTTPException(status_code=400, detail=f"Unknown country code. Supported: {sorted(COUNTRY_BBOXES.keys())}")
    active = await import_jobs_col.find_one({"status": {"$in": ["queued", "running"]}}, {"_id": 0, "id": 1})
    if active:
        raise HTTPException(status_code=409, detail=f"Import job {active['id']} is already active")

    south, west, north, east = COUNTRY_BBOXES[code]
    tiles = []
    lat = south
    while lat < north:
        lng = west
        while lng < east:
            tiles.append((lat, lng, min(lat + tile, north), min(lng + tile, east)))
            lng += tile
        lat += tile
    job_id = str(uuid.uuid4())
    await import_jobs_col.insert_one({
        "id": job_id,
        "kind": "country",
        "country": code,
        "tile_deg": tile,
        "status": "queued",
        "total_tiles": len(tiles),
        "processed_tiles": 0,
        "inserted": 0,
        "errors": 0,
        "created_at": now_iso(),
        "triggered_by": user["id"],
    })
    asyncio.create_task(_run_import_job(job_id, tiles, delay_s=delay))
    return {"job_id": job_id, "total_tiles": len(tiles), "country": code, "status": "queued"}


@api_router.get("/admin/courses/import-jobs/{job_id}")
async def admin_get_import_job(job_id: str, user=Depends(get_current_user)):
    _require_admin(user)
    job = await import_jobs_col.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@api_router.get("/admin/courses/import-jobs")
async def admin_list_import_jobs(limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user)):
    _require_admin(user)
    cursor = import_jobs_col.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    jobs = [j async for j in cursor]
    total_courses = await courses_col.count_documents({})
    return {"jobs": jobs, "total_courses": total_courses}


@api_router.post("/admin/courses/import-jobs/{job_id}/cancel")
async def admin_cancel_import_job(job_id: str, user=Depends(get_current_user)):
    _require_admin(user)
    res = await import_jobs_col.update_one(
        {"id": job_id, "status": {"$in": ["queued", "running"]}},
        {"$set": {"status": "cancelled", "cancelled_at": now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Job not found or not cancellable")
    return {"ok": True}


@api_router.get("/admin/courses/stats")
async def admin_courses_stats(user=Depends(get_current_user)):
    _require_admin(user)
    total = await courses_col.count_documents({})
    by_source: dict = {}
    async for doc in courses_col.aggregate([{"$group": {"_id": "$source", "n": {"$sum": 1}}}]):
        by_source[doc["_id"] or "unknown"] = doc["n"]
    return {"total_courses": total, "by_source": by_source, "supported_countries": sorted(COUNTRY_BBOXES.keys())}


# ---- Legacy single-bbox OSM import (admin only, throttled) ----
@api_router.post("/courses/import-osm")
@limiter.limit("10/hour")
async def import_courses_osm(
    request: Request,
    bbox: str = Query(..., description="south,west,north,east — e.g. 32.5,-117.5,33.5,-116.5"),
    user=Depends(get_current_user),
):
    """Bulk-import golf course names + locations from OpenStreetMap Overpass API (free, no key).
    Admin-only: prevents abuse of the outbound Overpass call and DB writes."""
    _require_admin(user)
    try:
        parts = [float(p) for p in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must have 4 numbers")
        south, west, north, east = parts
    except Exception:
        raise HTTPException(status_code=400, detail="bbox must be 'south,west,north,east'")

    try:
        data = await _overpass_fetch(_overpass_query(south, west, north, east, timeout=30), timeout=45.0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OSM Overpass error: {e}")

    inserted = await _persist_osm_elements(data.get("elements", []))
    total = await courses_col.count_documents({})
    return {"inserted": inserted, "total_courses": total}

# ---- Seed demo data (idempotent) ----
@api_router.post("/seed")
async def seed():
    # SEC-005: never callable when demo seeding disabled
    if not ENABLE_DEMO_SEED:
        raise HTTPException(status_code=404, detail="Not found")
    # Only seed if empty
    if await users_col.count_documents({}) > 0:
        return {"seeded": False, "reason": "already has users"}
    demo_users = [
        {"email": "reese@teebox.demo", "display_name": "Reese Callahan", "home_course": "Pebble Meadows GC", "handicap": 8.4, "bio": "Weekend warrior. Always chasing the sunrise tee time."},
        {"email": "jordan@teebox.demo", "display_name": "Jordan Kim", "home_course": "Whistling Oak", "handicap": 14.2, "bio": "New to the game, deep in the honeymoon phase."},
        {"email": "sam@teebox.demo", "display_name": "Sam Rivera", "home_course": "Bear Creek CC", "handicap": 3.1, "bio": "College team alum. Grinding to plus."},
    ]
    ids = []
    for u in demo_users:
        uid = str(uuid.uuid4())
        ids.append(uid)
        await users_col.insert_one({
            "id": uid,
            "email": u["email"],
            "hashed_password": pwd_context.hash("password123"),
            "display_name": u["display_name"],
            "home_course": u["home_course"],
            "handicap": u["handicap"],
            "bio": u["bio"],
            "avatar": None,
            "created_at": now_iso(),
        })
    demo_rounds = [
        (ids[0], "Pebble Meadows GC", 82, 72, "Front nine was clean. Ran into trouble on 14 tee.", None),
        (ids[2], "Bear Creek CC", 74, 72, "Best putting round in months. Rolled in a 30-footer on 18.", None),
        (ids[1], "Whistling Oak", 96, 72, "First time breaking 100 in sight! Fell apart on the par 5s.", None),
        (ids[0], "Cypress Ridge", 79, 71, "Windy from the west all day. Grinded out a couple pars late.", None),
    ]
    for uid, course, score, par, notes, photo in demo_rounds:
        rid = str(uuid.uuid4())
        await rounds_col.insert_one({
            "id": rid,
            "user_id": uid,
            "course_name": course,
            "date": now_iso(),
            "total_score": score,
            "par": par,
            "holes_played": 18,
            "fairways_hit": None,
            "greens_in_regulation": None,
            "putts": None,
            "notes": notes,
            "photos": [],
            "weather": None,
            "hole_scores": [],
            "hole_pars": [],
            "created_at": now_iso(),
        })
    # Mutual follows across demo users so followers-only feed has content
    for a in ids:
        for b in ids:
            if a == b:
                continue
            await follows_col.insert_one({
                "id": str(uuid.uuid4()),
                "user_id": a,
                "target_id": b,
                "created_at": now_iso(),
            })

    # Master course catalog (real courses, name + location only)
    catalog = [
        ("Pebble Beach Golf Links", "Pebble Beach", "CA", "USA", 36.5686, -121.9494),
        ("Cypress Point Club", "Pebble Beach", "CA", "USA", 36.5811, -121.9739),
        ("Augusta National Golf Club", "Augusta", "GA", "USA", 33.5030, -82.0199),
        ("TPC Sawgrass — Stadium Course", "Ponte Vedra Beach", "FL", "USA", 30.1970, -81.3910),
        ("Bethpage State Park — Black Course", "Farmingdale", "NY", "USA", 40.7431, -73.4553),
        ("Torrey Pines — South Course", "La Jolla", "CA", "USA", 32.9012, -117.2470),
        ("Pinehurst No. 2", "Pinehurst", "NC", "USA", 35.1899, -79.4726),
        ("Chambers Bay", "University Place", "WA", "USA", 47.2018, -122.5691),
        ("Whistling Straits — Straits Course", "Kohler", "WI", "USA", 43.8511, -87.7264),
        ("The Ocean Course at Kiawah Island", "Kiawah Island", "SC", "USA", 32.6083, -80.0439),
        ("TPC Harding Park", "San Francisco", "CA", "USA", 37.7245, -122.4930),
        ("Bandon Dunes", "Bandon", "OR", "USA", 43.1836, -124.4054),
        ("Pacific Dunes", "Bandon", "OR", "USA", 43.1968, -124.4108),
        ("Streamsong Blue", "Bowling Green", "FL", "USA", 27.6572, -81.9214),
        ("Erin Hills", "Erin", "WI", "USA", 43.2439, -88.3417),
        ("Shinnecock Hills Golf Club", "Southampton", "NY", "USA", 40.9040, -72.4415),
        ("Winged Foot — West Course", "Mamaroneck", "NY", "USA", 40.9583, -73.7500),
        ("Oakmont Country Club", "Oakmont", "PA", "USA", 40.5300, -79.8386),
        ("Muirfield Village Golf Club", "Dublin", "OH", "USA", 40.1408, -83.1650),
        ("Hazeltine National Golf Club", "Chaska", "MN", "USA", 44.8534, -93.6250),
        ("Congressional Country Club", "Bethesda", "MD", "USA", 39.0104, -77.1717),
        ("Merion Golf Club — East Course", "Ardmore", "PA", "USA", 40.0055, -75.3005),
        ("Riviera Country Club", "Pacific Palisades", "CA", "USA", 34.0475, -118.5069),
        ("Medinah Country Club — No. 3", "Medinah", "IL", "USA", 41.9736, -88.0525),
        ("Oak Hill Country Club — East Course", "Rochester", "NY", "USA", 43.1372, -77.5300),
        ("Bay Hill Club & Lodge", "Orlando", "FL", "USA", 28.4600, -81.5133),
        ("St Andrews Links — Old Course", "St Andrews", "Fife", "Scotland", 56.3438, -2.8010),
        ("Royal County Down Golf Club", "Newcastle", "County Down", "Northern Ireland", 54.2200, -5.8830),
        ("Old Head Golf Links", "Kinsale", "County Cork", "Ireland", 51.6083, -8.5361),
        ("Royal Melbourne Golf Club — West", "Black Rock", "VIC", "Australia", -37.9647, 145.0322),
    ]
    for name, city, region, country, lat, lng in catalog:
        try:
            await courses_col.insert_one({
                "id": str(uuid.uuid4()),
                "name": name,
                "city": city,
                "region": region,
                "country": country,
                "lat": lat,
                "lng": lng,
                "source": "seed",
                "created_at": now_iso(),
            })
        except Exception:
            # Unique index on `name` — safely skip re-seeding a course that already
            # exists from a previous run or OSM import.
            continue

    return {"seeded": True, "users": len(demo_users), "rounds": len(demo_rounds), "courses": len(catalog)}

# Mount router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def on_startup():
    # Refresh token indexes: unique jti + auto-expire once past exp
    try:
        await refresh_tokens_col.create_index("jti", unique=True)
        await refresh_tokens_col.create_index("expires_at", expireAfterSeconds=0)
        await refresh_tokens_col.create_index("family_id")
        await wishlists_col.create_index([("user_id", 1), ("course_name", 1)], unique=True)
        # Course name uniqueness. First, defensively dedupe existing docs so the
        # unique index build never fails on a legacy DB.
        try:
            async for grp in courses_col.aggregate([
                {"$group": {"_id": "$name", "ids": {"$push": "$_id"}, "n": {"$sum": 1}}},
                {"$match": {"n": {"$gt": 1}}},
            ]):
                # Keep the first _id, remove the rest
                extra = grp["ids"][1:]
                if extra:
                    await courses_col.delete_many({"_id": {"$in": extra}})
        except Exception as de:
            logger.warning(f"course dedupe pass skipped: {de}")
        await courses_col.create_index("name", unique=True)
        await courses_col.create_index([("lat", 1), ("lng", 1)])
        await import_jobs_col.create_index("status")
        await import_jobs_col.create_index([("created_at", -1)])
        await notifications_col.create_index([("user_id", 1), ("created_at", -1)])
        await notifications_col.create_index([("user_id", 1), ("read", 1)])
    except Exception as e:
        logger.warning(f"index setup skipped: {e}")

    # Self-heal: any 'queued'/'running' import jobs from a previous process are dead now.
    # Mark them as 'interrupted' so the UI shows a clean history and a new auto-import
    # can safely start.
    try:
        stale = await import_jobs_col.update_many(
            {"status": {"$in": ["queued", "running"]}},
            {"$set": {"status": "interrupted", "finished_at": now_iso()}},
        )
        if stale.modified_count:
            logger.info(f"cleaned up {stale.modified_count} stale import jobs from previous run")
    except Exception as e:
        logger.warning(f"stale-job cleanup skipped: {e}")

    # SEC-005: only auto-seed demo data when explicitly enabled (dev / demo)
    if ENABLE_DEMO_SEED and await users_col.count_documents({}) == 0:
        try:
            await seed()
            logger.info("Auto-seeded demo data (ENABLE_DEMO_SEED=true)")
        except Exception as e:
            logger.warning(f"seed failed: {e}")

    # Auto-populate global course library from OpenStreetMap on first boot.
    # Uses a country-tiled sweep (~8° per tile) which is *much* more reliable than a
    # global lat/lng grid — hand-tuned country bboxes skip ocean and keep tiles small
    # enough for Overpass to answer quickly.
    #
    # Only runs when:
    #   - AUTO_IMPORT_COURSES env flag is on (default true)
    #   - Total courses in DB < AUTO_IMPORT_COURSES_THRESHOLD (default 500)
    #   - No global sweep has ever completed successfully (idempotency guard)
    # Runs in background so the API is available immediately.
    if AUTO_IMPORT_COURSES:
        try:
            import asyncio
            current = await courses_col.count_documents({})
            # Consider a prior sweep meaningful only if it actually inserted a reasonable number
            # of courses. If a previous sweep bailed early due to Overpass throttling, we retry.
            prior = await import_jobs_col.find_one(
                {"kind": "global", "status": "completed", "inserted": {"$gte": 200}},
                {"_id": 0, "id": 1, "inserted": 1},
            )
            if current < AUTO_IMPORT_THRESHOLD and not prior:
                tiles = _country_tiles(tile=5)
                job_id = str(uuid.uuid4())
                await import_jobs_col.insert_one({
                    "id": job_id,
                    "kind": "global",
                    "tile_deg": 5,
                    "status": "queued",
                    "total_tiles": len(tiles),
                    "processed_tiles": 0,
                    "inserted": 0,
                    "errors": 0,
                    "created_at": now_iso(),
                    "triggered_by": "system:auto_import",
                })
                asyncio.create_task(_run_import_job(job_id, tiles, delay_s=3.0))
                logger.info(
                    f"auto-import kicked off: job_id={job_id} tiles={len(tiles)} "
                    f"(current courses={current}, threshold={AUTO_IMPORT_THRESHOLD})"
                )
            else:
                logger.info(
                    f"auto-import skipped: current_courses={current} "
                    f"threshold={AUTO_IMPORT_THRESHOLD} prior_completed={bool(prior)}"
                )
        except Exception as e:
            logger.warning(f"auto-import kickoff failed: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
