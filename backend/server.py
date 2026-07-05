from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
from jose import jwt, JWTError


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

# Auth config
SECRET_KEY = os.environ["JWT_SECRET_KEY"]
ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
EXPIRE_MIN = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

app = FastAPI()
api_router = APIRouter(prefix="/api")

# ---- Utils ----
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def create_token(sub: str) -> str:
    payload = {"sub": sub, "exp": datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_MIN)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(cred: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if cred is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(cred.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
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
    token_type: str = "bearer"
    user: dict

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
    display_name: Optional[str] = None
    home_course: Optional[str] = None
    handicap: Optional[float] = None
    bio: Optional[str] = None
    avatar: Optional[str] = None  # base64

# ---- Helpers ----
async def enrich_round(r: dict, viewer_id: Optional[str]) -> dict:
    author = await users_col.find_one({"id": r["user_id"]}, {"_id": 0, "hashed_password": 0})
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
async def register(data: RegisterIn):
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
    token = create_token(user_id)
    doc.pop("_id", None)
    doc.pop("hashed_password", None)
    return {"access_token": token, "user": doc}

@api_router.post("/auth/login", response_model=AuthOut)
async def login(data: LoginIn):
    user = await users_col.find_one({"email": data.email.lower()})
    if not user or not pwd_context.verify(data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = create_token(user["id"])
    user.pop("_id", None)
    user.pop("hashed_password", None)
    return {"access_token": token, "user": user}

@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user

@api_router.patch("/auth/me")
async def update_me(data: ProfileUpdate, user=Depends(get_current_user)):
    updates = {k: v for k, v in data.dict().items() if v is not None}
    if updates:
        await users_col.update_one({"id": user["id"]}, {"$set": updates})
    fresh = await users_col.find_one({"id": user["id"]}, {"_id": 0, "hashed_password": 0})
    return fresh

# ---- Rounds ----
@api_router.post("/rounds")
async def create_round(data: RoundIn, user=Depends(get_current_user)):
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
        "photos": data.photos or [],
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
    target = await users_col.find_one({"id": user_id}, {"_id": 0, "hashed_password": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    round_count = await rounds_col.count_documents({"user_id": user_id})
    scores_cursor = rounds_col.find({"user_id": user_id}, {"_id": 0, "total_score": 1}).sort("created_at", -1).limit(20)
    recent_scores = [s["total_score"] async for s in scores_cursor]
    avg_score = round(sum(recent_scores) / len(recent_scores), 1) if recent_scores else None
    best = min(recent_scores) if recent_scores else None
    follower_count = await follows_col.count_documents({"target_id": user_id})
    following_count = await follows_col.count_documents({"user_id": user_id})
    following = False
    if user["id"] != user_id:
        following = await follows_col.find_one({"user_id": user["id"], "target_id": user_id}) is not None
    return {
        **target,
        "round_count": round_count,
        "avg_score": avg_score,
        "best_score": best,
        "follower_count": follower_count,
        "following_count": following_count,
        "is_following": following,
        "is_me": user["id"] == user_id,
    }

@api_router.get("/users/{user_id}/rounds")
async def get_user_rounds(user_id: str, user=Depends(get_current_user)):
    cursor = rounds_col.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1)
    return [await enrich_round(r, user["id"]) async for r in cursor]

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

# ---- Discover ----
@api_router.get("/discover/users")
async def discover_users(q: str = "", user=Depends(get_current_user)):
    query = {}
    if q.strip():
        query = {"display_name": {"$regex": q.strip(), "$options": "i"}}
    users = []
    async for u in users_col.find(query, {"_id": 0, "hashed_password": 0}).limit(30):
        if u["id"] == user["id"]:
            continue
        round_count = await rounds_col.count_documents({"user_id": u["id"]})
        users.append({**u, "round_count": round_count})
    return users

@api_router.get("/discover/courses")
async def discover_courses(q: str = "", user=Depends(get_current_user)):
    q_str = q.strip()
    # Aggregate rounds by course
    pipeline = []
    if q_str:
        pipeline.append({"$match": {"course_name": {"$regex": q_str, "$options": "i"}}})
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

    # Master course list
    course_query: dict = {}
    if q_str:
        course_query = {"name": {"$regex": q_str, "$options": "i"}}
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

# ---- Course Reviews ----
@api_router.get("/courses/{course_name}/reviews")
async def get_reviews(course_name: str, user=Depends(get_current_user)):
    out = []
    async for r in reviews_col.find({"course_name": course_name}, {"_id": 0}).sort("created_at", -1):
        author = await users_col.find_one({"id": r["user_id"]}, {"_id": 0, "hashed_password": 0})
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
@api_router.post("/courses/import-osm")
async def import_courses_osm(
    bbox: str = Query(..., description="south,west,north,east — e.g. 32.5,-117.5,33.5,-116.5"),
    user=Depends(get_current_user),
):
    """Bulk-import golf course names + locations from OpenStreetMap Overpass API (free, no key)."""
    try:
        parts = [float(p) for p in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must have 4 numbers")
        south, west, north, east = parts
    except Exception:
        raise HTTPException(status_code=400, detail="bbox must be 'south,west,north,east'")

    import httpx
    query = f"""
    [out:json][timeout:30];
    (
      node["leisure"="golf_course"]({south},{west},{north},{east});
      way["leisure"="golf_course"]({south},{west},{north},{east});
      relation["leisure"="golf_course"]({south},{west},{north},{east});
    );
    out center tags;
    """
    try:
        async with httpx.AsyncClient(timeout=45.0) as http:
            resp = await http.post("https://overpass-api.de/api/interpreter", data={"data": query})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OSM Overpass error: {e}")

    inserted = 0
    for el in data.get("elements", []):
        tags = el.get("tags", {}) or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        # Skip duplicates
        if await courses_col.find_one({"name": name}):
            continue
        lat = el.get("lat") if el.get("type") == "node" else (el.get("center", {}) or {}).get("lat")
        lng = el.get("lon") if el.get("type") == "node" else (el.get("center", {}) or {}).get("lon")
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
    total = await courses_col.count_documents({})
    return {"inserted": inserted, "total_courses": total}

# ---- Seed demo data (idempotent) ----
@api_router.post("/seed")
async def seed():
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

    return {"seeded": True, "users": len(demo_users), "rounds": len(demo_rounds), "courses": len(catalog)}

# Mount router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
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
    # Auto-seed if empty for smooth demo
    if await users_col.count_documents({}) == 0:
        try:
            await seed()
            logger.info("Auto-seeded demo data")
        except Exception as e:
            logger.warning(f"seed failed: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
