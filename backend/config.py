"""Runtime configuration & feature flags. Reads env vars once at import.

Separated from ``server.py`` so any module (routers, helpers, background jobs)
can import the constants they need without pulling in the whole FastAPI app.
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ---- MongoDB ----
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

# ---- Auth / JWT ----
SECRET_KEY = os.environ["JWT_SECRET_KEY"]
ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_EXPIRE_MIN = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

# ---- Environment gates ----
ENABLE_DEMO_SEED = os.environ.get("ENABLE_DEMO_SEED", "false").lower() in ("1", "true", "yes")
APP_ENV = os.environ.get("APP_ENV", "development").lower()
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "*").split(",") if o.strip()]

# ---- Auto-populate global course library from OSM ----
AUTO_IMPORT_COURSES = os.environ.get("AUTO_IMPORT_COURSES", "true").lower() in ("1", "true", "yes")
AUTO_IMPORT_THRESHOLD = int(os.environ.get("AUTO_IMPORT_COURSES_THRESHOLD", "500"))

# ---- Admins ----
# Mutable at runtime (bootstrap script adds the seeded admin here). Sets are picked
# because callers frequently `if email in ADMIN_EMAILS` — O(1) check.
ADMIN_EMAILS: set[str] = {
    e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()
}

# ---- Base64 payload caps (SEC-003) ----
MAX_PHOTO_B64_LEN = 1_500_000   # ~1 MB decoded
MAX_AVATAR_B64_LEN = 800_000     # ~600 KB decoded
MAX_PHOTOS_PER_ROUND = 3

# ---- Notification preferences ----
# Per-event toggles the user can flip in Settings. All default ON so existing
# users keep the current experience unless they explicitly opt out.
NOTIFICATION_PREF_KEYS: set[str] = {
    "comment_like",           # someone liked my comment
    "achievement_unlocked",   # I just unlocked a new badge (self)
    "post_like",              # someone liked my round
    "post_comment",           # someone commented on my round
    "mention",                # someone @-mentioned me
    "follow",                 # someone followed me
    "course_verified",        # my submitted course was approved/rejected
}
DEFAULT_NOTIFICATION_PREFS = {k: True for k in NOTIFICATION_PREF_KEYS}


def is_admin_email(email: str | None) -> bool:
    return bool(email and email.lower() in ADMIN_EMAILS)


def is_admin_user(u: dict | None) -> bool:
    return bool(u and is_admin_email((u.get("email") or "").lower()))


# ---- Boot-time safety checks ----
# SEC-001: refuse to boot in production with the seeded demo admin combo
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
