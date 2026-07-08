"""Utility helpers used across routers.

All functions here are pure (no FastAPI decorators). Keeping them in one place
makes the router files easier to skim.
"""
from __future__ import annotations

import logging
import math
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException

from config import NOTIFICATION_PREF_KEYS
from db import (
    comments_col,
    courses_col,
    likes_col,
    notifications_col,
    users_col,
)

logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Regex safety (SEC-004) ----
_regex_meta = re.compile(r"[.*+?^${}()|\[\]\\]")


def safe_query(q: str, max_len: int = 60) -> str:
    q = (q or "").strip()[:max_len]
    return _regex_meta.sub(lambda m: "\\" + m.group(0), q)


# ---- Base64 image validation (SEC-003) ----
def validate_b64_image(s: Optional[str], max_len: int, label: str) -> None:
    if s is None:
        return
    if not isinstance(s, str) or len(s) > max_len:
        raise HTTPException(status_code=413, detail=f"{label} too large")
    if s.startswith("data:") and not s.startswith("data:image/"):
        raise HTTPException(status_code=415, detail=f"{label} must be an image data URI")


# ---- Public user projection (SEC-002) ----
_PUBLIC_USER_KEYS = {"id", "display_name", "handicap", "home_course", "bio", "avatar", "created_at"}


def public_user(u: dict) -> dict:
    return {k: v for k, v in (u or {}).items() if k in _PUBLIC_USER_KEYS}


# ---- Notification preferences ----
def notification_prefs_of(u: dict) -> dict:
    """Return a fully-populated notification_prefs dict, defaulting missing keys to True."""
    stored = (u or {}).get("notification_prefs") or {}
    return {k: bool(stored.get(k, True)) for k in NOTIFICATION_PREF_KEYS}


async def emit_notification(
    *,
    user_id: str,
    pref_key: str,
    type_: str,
    title: str,
    body: str,
    extra: Optional[dict] = None,
) -> None:
    """Insert an in-app notification IFF the target user hasn't opted out.
    Silent no-op on any error so notifications never break the caller's happy path."""
    try:
        target = await users_col.find_one({"id": user_id}, {"_id": 0, "notification_prefs": 1})
        if target is None:
            return
        if not notification_prefs_of(target).get(pref_key, True):
            return
        doc = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "type": type_,
            "title": title,
            "body": body,
            "read": False,
            "created_at": now_iso(),
        }
        if extra:
            doc.update({k: v for k, v in extra.items() if v is not None})
        await notifications_col.insert_one(doc)
    except Exception:
        logger.exception("Failed to emit notification type=%s user=%s", type_, user_id)


# ---- Round enrichment ----
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
        "new_achievements": r.get("new_achievements") or [],
    }


# ---- Achievements ----
def compute_achievement_defs(rounds: List[dict]) -> List[dict]:
    """Compute the ordered list of achievement definitions with ``earned`` flags."""
    rounds_sorted = sorted(rounds, key=lambda r: r.get("created_at") or "")
    rounds_18 = [r for r in rounds_sorted if int(r.get("holes_played") or 18) >= 18]
    rounds_9 = [r for r in rounds_sorted if int(r.get("holes_played") or 18) == 9]
    scores_18 = [r["total_score"] for r in rounds_18]
    scores_9 = [r["total_score"] for r in rounds_9]
    courses = {r["course_name"] for r in rounds_sorted}

    streak = 0
    best_streak = 0
    for s in scores_18:
        if s <= 80:
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0

    streak9 = 0
    best_streak9 = 0
    for s in scores_9:
        if s <= 40:
            streak9 += 1
            best_streak9 = max(best_streak9, streak9)
        else:
            streak9 = 0

    return [
        {"key": "first_round", "title": "On the tee", "desc": "Logged your first round.", "icon": "flag", "earned": len(rounds_sorted) >= 1},
        {"key": "sub_100", "title": "Broke 100", "desc": "Posted an 18-hole round under 100.", "icon": "trophy", "earned": any(s < 100 for s in scores_18)},
        {"key": "sub_90", "title": "Broke 90", "desc": "Posted an 18-hole round under 90.", "icon": "trophy", "earned": any(s < 90 for s in scores_18)},
        {"key": "sub_80", "title": "First sub-80", "desc": "Posted an 18-hole round under 80.", "icon": "trophy", "earned": any(s < 80 for s in scores_18)},
        {"key": "sub_70", "title": "Sub-70 club", "desc": "Posted an 18-hole round under 70.", "icon": "star", "earned": any(s < 70 for s in scores_18)},
        {"key": "sub_50_9", "title": "Broke 50 (9)", "desc": "Posted a 9-hole round under 50.", "icon": "trophy", "earned": any(s < 50 for s in scores_9)},
        {"key": "sub_45_9", "title": "Broke 45 (9)", "desc": "Posted a 9-hole round under 45.", "icon": "trophy", "earned": any(s < 45 for s in scores_9)},
        {"key": "sub_40_9", "title": "Broke 40 (9)", "desc": "Posted a 9-hole round under 40.", "icon": "trophy", "earned": any(s < 40 for s in scores_9)},
        {"key": "sub_par_9", "title": "Broke par (9)", "desc": "Beat par on a 9-hole round.", "icon": "star", "earned": any(
            r["total_score"] < int(r.get("par") or 36) for r in rounds_9
        )},
        {"key": "ten_rounds", "title": "Regular", "desc": "Logged 10 rounds.", "icon": "golf", "earned": len(rounds_sorted) >= 10},
        {"key": "fifty_rounds", "title": "Half-century", "desc": "Logged 50 rounds.", "icon": "medal", "earned": len(rounds_sorted) >= 50},
        {"key": "course_collector", "title": "Course collector", "desc": "Played 5 different courses.", "icon": "map", "earned": len(courses) >= 5},
        {"key": "hot_streak", "title": "Hot streak", "desc": "3 eighteen-hole rounds in a row at or under 80.", "icon": "flame", "earned": best_streak >= 3},
        {"key": "hot_streak_9", "title": "Hot streak (9)", "desc": "3 nine-hole rounds in a row at or under 40.", "icon": "flame", "earned": best_streak9 >= 3},
    ]


# ---- Geo helpers ----
def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


# ---- Wishlist enrichment ----
async def enrich_wishlist_entry(entry: dict) -> dict:
    course = await courses_col.find_one({"name": entry["course_name"]}, {"_id": 0})
    return {
        "course_name": entry["course_name"],
        "added_at": entry.get("created_at"),
        "city": course.get("city") if course else None,
        "region": course.get("region") if course else None,
        "country": course.get("country") if course else None,
    }
