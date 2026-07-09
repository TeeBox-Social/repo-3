"""Auth endpoints: register, login, refresh, logout, me, patch me,
plus email verification, password reset, and account lockout logic."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from jose import JWTError, jwt

from config import (
    ALGORITHM,
    DEFAULT_NOTIFICATION_PREFS,
    EMAIL_VERIFY_TOKEN_HOURS,
    LOCKOUT_DURATION_HOURS,
    LOCKOUT_MAX_ATTEMPTS,
    LOCKOUT_WINDOW_MINUTES,
    MAX_AVATAR_B64_LEN,
    NOTIFICATION_PREF_KEYS,
    PASSWORD_RESET_TOKEN_MINUTES,
    SECRET_KEY,
    is_admin_user,
)
from db import refresh_tokens_col, users_col
from emailer import (
    build_reset_url,
    build_verify_url,
    send_reset_email,
    send_verify_email,
)
from helpers import (
    notification_prefs_of,
    now_iso,
    validate_b64_image,
)
from models import (
    AuthOut,
    GoogleAuthIn,
    LoginIn,
    ProfileUpdate,
    RefreshIn,
    RegisterIn,
    RequestResetIn,
    ResendVerifyIn,
    ResetPasswordIn,
    TokenIn,
)
from security import (
    create_access_token,
    create_refresh_token,
    create_typed_token,
    decode_typed_token,
    get_current_user,
    limiter,
    pwd_context,
)
import logging
import uuid

logger = logging.getLogger(__name__)
router = APIRouter()


# ---- Lockout helpers ------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_aware(dt) -> Optional[datetime]:
    """Motor returns naive UTC datetimes; make them aware so comparisons work."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


async def _record_failed_login(user: dict) -> None:
    """Bump the failed-attempt counter and lock the account past the threshold.

    Uses a sliding time window: attempts older than LOCKOUT_WINDOW_MINUTES reset
    the counter so a stale streak from months ago doesn't lock a real user.
    """
    now = _now()
    window_start = _to_aware(user.get("failed_login_window_start")) or now
    if (now - window_start).total_seconds() > LOCKOUT_WINDOW_MINUTES * 60:
        # window has expired; start fresh
        failures = 1
        window_start = now
    else:
        failures = int(user.get("failed_login_attempts") or 0) + 1

    updates: dict = {
        "failed_login_attempts": failures,
        "failed_login_window_start": window_start,
    }
    if failures >= LOCKOUT_MAX_ATTEMPTS:
        updates["lockout_until"] = now + timedelta(hours=LOCKOUT_DURATION_HOURS)
    await users_col.update_one({"id": user["id"]}, {"$set": updates})


async def _clear_login_failures(user_id: str) -> None:
    await users_col.update_one(
        {"id": user_id},
        {"$set": {
            "failed_login_attempts": 0,
            "failed_login_window_start": None,
            "lockout_until": None,
        }},
    )


def _lockout_error(unlock_at: datetime) -> HTTPException:
    minutes = max(1, int((unlock_at - _now()).total_seconds() // 60))
    return HTTPException(
        status_code=423,
        detail=(
            f"Account temporarily locked after {LOCKOUT_MAX_ATTEMPTS} failed logins. "
            f"Try again in ~{minutes} min or reset your password to unlock now."
        ),
    )


# ---- Public routes --------------------------------------------------------
@router.get("/")
async def root():
    return {"message": "TeeBox API", "status": "ok"}


@router.post("/auth/register", response_model=AuthOut)
@limiter.limit("5/minute; 20/hour")
async def register(request: Request, data: RegisterIn, background_tasks: BackgroundTasks):
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
        "email_verified": False,
        "failed_login_attempts": 0,
        "created_at": now_iso(),
    }
    await users_col.insert_one(doc)

    # Fire the verification email asynchronously so the API returns fast.
    verify_token = create_typed_token(user_id, "verify_email", EMAIL_VERIFY_TOKEN_HOURS * 60)
    background_tasks.add_task(
        send_verify_email,
        doc["email"],
        doc["display_name"],
        build_verify_url(verify_token),
    )

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
    if not user:
        # Constant-time-ish: run a fake verify so response timing is similar.
        pwd_context.dummy_verify() if hasattr(pwd_context, "dummy_verify") else pwd_context.hash("x")
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    # 1. Lockout check — locked accounts short-circuit even if the password is right,
    # forcing the user through the password-reset flow (which unlocks on success).
    unlock_at = _to_aware(user.get("lockout_until"))
    if unlock_at and unlock_at > _now():
        raise _lockout_error(unlock_at)

    # 2. Password check
    if not pwd_context.verify(data.password, user["hashed_password"]):
        await _record_failed_login(user)
        # Re-read to see if THIS attempt tipped us over the edge.
        fresh = await users_col.find_one({"id": user["id"]}, {"_id": 0, "lockout_until": 1})
        unlock_at = _to_aware((fresh or {}).get("lockout_until"))
        if unlock_at and unlock_at > _now():
            raise _lockout_error(unlock_at)
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    # 3. Success — clear any accumulated failures.
    await _clear_login_failures(user["id"])
    access = create_access_token(user["id"])
    refresh = await create_refresh_token(user["id"])
    user.pop("_id", None)
    user.pop("hashed_password", None)
    user["is_admin"] = is_admin_user(user)
    user["notification_prefs"] = notification_prefs_of(user)
    # Legacy accounts (pre email-verify feature) are treated as verified so we
    # don't lock existing users out on rollout.
    if "email_verified" not in user:
        user["email_verified"] = True
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
    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "user": {
            **user,
            "is_admin": is_admin_user(user),
            "notification_prefs": notification_prefs_of(user),
        },
    }


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
    return {
        **user,
        "is_admin": is_admin_user(user),
        "notification_prefs": notification_prefs_of(user),
        "email_verified": bool(user.get("email_verified", True)),
    }


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
        "email_verified": bool(fresh.get("email_verified", True)),
    }


# ---- Password reset -------------------------------------------------------
@router.post("/auth/request-password-reset")
@limiter.limit("5/minute; 20/hour")
async def request_password_reset(
    request: Request,
    data: RequestResetIn,
    background_tasks: BackgroundTasks,
):
    """Send a signed reset link to the user's email. Always returns 200 so
    attackers can't enumerate registered emails."""
    user = await users_col.find_one({"email": data.email.lower()})
    if user:
        token = create_typed_token(user["id"], "password_reset", PASSWORD_RESET_TOKEN_MINUTES)
        background_tasks.add_task(
            send_reset_email,
            user["email"],
            user.get("display_name", ""),
            build_reset_url(token),
        )
    return {"ok": True, "message": "If that email is registered, a reset link is on the way."}


@router.post("/auth/reset-password")
@limiter.limit("10/hour")
async def reset_password(request: Request, data: ResetPasswordIn):
    payload = decode_typed_token(data.token, "password_reset")
    user_id = payload.get("sub")
    user = await users_col.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if len(data.new_password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")
    await users_col.update_one(
        {"id": user_id},
        {"$set": {
            "hashed_password": pwd_context.hash(data.new_password),
            # A successful reset also unlocks the account and clears failures.
            "failed_login_attempts": 0,
            "failed_login_window_start": None,
            "lockout_until": None,
            "password_updated_at": now_iso(),
        }},
    )
    # Invalidate every outstanding refresh token so any attacker session dies.
    await refresh_tokens_col.update_many(
        {"user_id": user_id},
        {"$set": {"is_revoked": True}},
    )
    return {"ok": True, "message": "Password updated. Please sign in with your new password."}


# ---- Email verification ---------------------------------------------------
@router.post("/auth/verify-email")
async def verify_email(data: TokenIn):
    payload = decode_typed_token(data.token, "verify_email")
    user_id = payload.get("sub")
    res = await users_col.update_one(
        {"id": user_id},
        {"$set": {"email_verified": True, "email_verified_at": now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    return {"ok": True, "message": "Email verified. Welcome to TeeBox!"}


@router.post("/auth/resend-verification")
@limiter.limit("3/hour")
async def resend_verification(
    request: Request,
    data: ResendVerifyIn,
    background_tasks: BackgroundTasks,
):
    user = await users_col.find_one({"email": data.email.lower()})
    if user and not user.get("email_verified", False):
        token = create_typed_token(user["id"], "verify_email", EMAIL_VERIFY_TOKEN_HOURS * 60)
        background_tasks.add_task(
            send_verify_email,
            user["email"],
            user.get("display_name", ""),
            build_verify_url(token),
        )
    return {"ok": True, "message": "If that email is registered and unverified, we've resent the link."}


# ---- Google Sign-In (Emergent OAuth) -------------------------------------
EMERGENT_SESSION_DATA_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


@router.post("/auth/google", response_model=AuthOut)
@limiter.limit("20/minute; 200/hour")
async def google_sign_in(request: Request, data: GoogleAuthIn):
    """Verify an Emergent OAuth session_id, upsert by email, and issue our
    own JWT access+refresh tokens so the rest of the app doesn't care that the
    user came in via Google."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(
                EMERGENT_SESSION_DATA_URL,
                headers={"X-Session-ID": data.session_id},
            )
        if resp.status_code != 200:
            logger.warning("Emergent OAuth session-data returned %s: %s", resp.status_code, resp.text[:200])
            raise HTTPException(status_code=401, detail="Google session invalid or expired")
        payload = resp.json()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("Emergent OAuth verify failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not reach Google auth service")

    email = (payload.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=400, detail="Google account did not share an email")
    google_name = (payload.get("name") or "").strip()
    picture = (payload.get("picture") or "").strip() or None

    existing = await users_col.find_one({"email": email})
    if existing:
        # Merge: link the Google provider onto the existing account without
        # touching their password or profile fields.
        providers = set(existing.get("auth_providers") or [])
        providers.add("google")
        if not existing.get("email_verified"):
            # Google confirmed the email address is real.
            providers.add("email_verified_by_google")
        set_fields: dict = {
            "auth_providers": sorted(providers - {"email_verified_by_google"}),
            "email_verified": True,
            "google_last_login_at": now_iso(),
        }
        # Only fill in avatar if the user hasn't already uploaded a custom one.
        if picture and not existing.get("avatar"):
            set_fields["avatar"] = picture
        # Never overwrite a chosen display name; only fill it when blank.
        if google_name and not existing.get("display_name"):
            set_fields["display_name"] = google_name
        await users_col.update_one({"id": existing["id"]}, {"$set": set_fields})
        user_doc = await users_col.find_one({"id": existing["id"]}, {"_id": 0, "hashed_password": 0})
    else:
        # New account — no password, provider list = ['google'].
        new_id = str(uuid.uuid4())
        user_doc = {
            "id": new_id,
            "email": email,
            # No password login until they set one via password reset.
            "hashed_password": None,
            "display_name": google_name or email.split("@", 1)[0],
            "avatar": picture,
            "home_course": "",
            "handicap": None,
            "bio": "",
            "notification_prefs": dict(DEFAULT_NOTIFICATION_PREFS),
            "email_verified": True,
            "auth_providers": ["google"],
            "failed_login_attempts": 0,
            "created_at": now_iso(),
            "google_last_login_at": now_iso(),
        }
        await users_col.insert_one(user_doc)
        user_doc.pop("_id", None)
        user_doc.pop("hashed_password", None)

    # Any successful Google login clears any brute-force lockout state.
    await users_col.update_one(
        {"id": user_doc["id"]},
        {"$set": {
            "failed_login_attempts": 0,
            "failed_login_window_start": None,
            "lockout_until": None,
        }},
    )

    access = create_access_token(user_doc["id"])
    refresh = await create_refresh_token(user_doc["id"])
    user_doc["is_admin"] = is_admin_user(user_doc)
    user_doc["notification_prefs"] = notification_prefs_of(user_doc)
    user_doc["email_verified"] = True
    return {"access_token": access, "refresh_token": refresh, "user": user_doc}
