"""Auth endpoints: register, login, refresh, logout, me, patch me."""
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError, jwt

from config import (
    ALGORITHM,
    DEFAULT_NOTIFICATION_PREFS,
    MAX_AVATAR_B64_LEN,
    NOTIFICATION_PREF_KEYS,
    SECRET_KEY,
    is_admin_user,
)
from db import refresh_tokens_col, users_col
from helpers import (
    notification_prefs_of,
    now_iso,
    validate_b64_image,
)
from models import AuthOut, LoginIn, ProfileUpdate, RefreshIn, RegisterIn
from security import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    limiter,
    pwd_context,
)
import uuid

router = APIRouter()


@router.get("/")
async def root():
    return {"message": "TeeBox API", "status": "ok"}


@router.post("/auth/register", response_model=AuthOut)
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
        # Persist defaults so DB truth matches API truth and future pref keys
        # don't hit the truthy-vs-empty-dict trap.
        "notification_prefs": dict(DEFAULT_NOTIFICATION_PREFS),
        "created_at": now_iso(),
    }
    await users_col.insert_one(doc)
    access = create_access_token(user_id)
    refresh = await create_refresh_token(user_id)
    doc.pop("_id", None)
    doc.pop("hashed_password", None)
    doc["is_admin"] = is_admin_user(doc)
    doc["notification_prefs"] = notification_prefs_of(doc)
    return {"access_token": access, "refresh_token": refresh, "user": doc}


@router.post("/auth/login", response_model=AuthOut)
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
    user["notification_prefs"] = notification_prefs_of(user)
    return {"access_token": access, "refresh_token": refresh, "user": user}


@router.post("/auth/refresh", response_model=AuthOut)
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
        if family_id:
            await refresh_tokens_col.update_many({"family_id": family_id}, {"$set": {"is_revoked": True}})
        raise HTTPException(status_code=401, detail="Refresh token not recognised")
    if db_token.get("is_rotated") or db_token.get("is_revoked"):
        await refresh_tokens_col.update_many({"family_id": family_id}, {"$set": {"is_revoked": True}})
        raise HTTPException(status_code=401, detail="Refresh token reuse detected — please sign in again")
    rot = await refresh_tokens_col.find_one_and_update(
        {"jti": jti, "is_rotated": False, "is_revoked": False},
        {"$set": {"is_rotated": True, "rotated_at": now_iso()}},
    )
    if not rot:
        await refresh_tokens_col.update_many({"family_id": family_id}, {"$set": {"is_revoked": True}})
        raise HTTPException(status_code=401, detail="Refresh token reuse detected — please sign in again")
    user = await users_col.find_one({"id": user_id}, {"_id": 0, "hashed_password": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    new_access = create_access_token(user_id)
    new_refresh = await create_refresh_token(user_id, family_id=family_id)
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


@router.post("/auth/logout")
async def logout(data: RefreshIn):
    try:
        payload = jwt.decode(data.refresh_token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        jti = payload.get("jti")
        if jti:
            await refresh_tokens_col.update_one({"jti": jti}, {"$set": {"is_revoked": True}})
    except JWTError:
        pass
    return {"ok": True}


@router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return {**user, "is_admin": is_admin_user(user), "notification_prefs": notification_prefs_of(user)}


@router.patch("/auth/me")
async def update_me(data: ProfileUpdate, user=Depends(get_current_user)):
    updates = data.dict(exclude_unset=True)
    if "display_name" in updates:
        v = updates["display_name"]
        if v is None or not str(v).strip():
            raise HTTPException(status_code=422, detail="display_name cannot be empty")
        updates["display_name"] = str(v).strip()
    if "avatar" in updates and updates["avatar"] is not None:
        validate_b64_image(updates["avatar"], MAX_AVATAR_B64_LEN, "Avatar")
    if "notification_prefs" in updates:
        incoming = updates.pop("notification_prefs") or {}
        current = notification_prefs_of(user)
        for k, v in incoming.items():
            if k in NOTIFICATION_PREF_KEYS:
                current[k] = bool(v)
        updates["notification_prefs"] = current
    if updates:
        await users_col.update_one({"id": user["id"]}, {"$set": updates})
    fresh = await users_col.find_one({"id": user["id"]}, {"_id": 0, "hashed_password": 0})
    return {
        **fresh,
        "is_admin": is_admin_user(fresh),
        "notification_prefs": notification_prefs_of(fresh),
    }
