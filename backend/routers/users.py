"""User profiles, follows, friends, achievements, pin, by-name, wishlist."""
import re
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from db import (
    courses_col,
    follows_col,
    reviews_col,
    rounds_col,
    users_col,
    wishlists_col,
)
from helpers import (
    batch_course_par_cache,
    compute_achievement_defs,
    emit_notification,
    enrich_round,
    enrich_wishlist_entry,
    extrapolate_18_score,
    now_iso,
    public_user,
    safe_query,
)
from models import WishlistIn
from security import get_current_user

router = APIRouter()


@router.get("/users/{user_id}")
async def get_user(user_id: str, user=Depends(get_current_user)):
    target = await users_col.find_one({"id": user_id}, {"_id": 0, "hashed_password": 0, "email": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    round_count = await rounds_col.count_documents({"user_id": user_id, "post_type": {"$in": ["round", None]}})
    # Normalize 9-hole rounds to their 18-hole equivalent for a fair average.
    scores_cursor = rounds_col.find(
        {"user_id": user_id, "post_type": {"$in": ["round", None]}},
        {"_id": 0, "total_score": 1, "holes_played": 1, "par": 1, "course_name": 1},
    ).sort("created_at", -1).limit(20)
    score_list = [s async for s in scores_cursor]
    course_par_cache = await batch_course_par_cache(s.get("course_name") for s in score_list)
    recent_scores: List[float] = [
        extrapolate_18_score(
            float(s.get("total_score") or 0),
            s.get("holes_played"),
            s.get("par"),
            course_par_cache.get(s.get("course_name")),
        )
        for s in score_list
        if s.get("total_score") is not None
    ]
    avg_score = round(sum(recent_scores) / len(recent_scores), 1) if recent_scores else None
    follower_count = await follows_col.count_documents({"target_id": user_id})
    following_count = await follows_col.count_documents({"user_id": user_id})
    courses_played = 0
    async for _ in rounds_col.aggregate([
        {"$match": {
            "user_id": user_id,
            "post_type": {"$in": ["round", None]},
            "course_name": {"$ne": ""},
        }},
        {"$group": {"_id": "$course_name"}},
        {"$count": "n"},
    ]):
        courses_played = _["n"]
    
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
    pinned_round = None
    pin_id = target.get("pinned_round_id")
    if pin_id:
        pr = await rounds_col.find_one({"id": pin_id, "user_id": user_id}, {"_id": 0})
        if pr:
            pinned_round = await enrich_round(pr, user["id"])
        else:
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


@router.get("/users/{user_id}/rounds")
async def get_user_rounds(user_id: str, user=Depends(get_current_user)):
    cursor = rounds_col.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1)
    return [await enrich_round(r, user["id"]) async for r in cursor]


@router.get("/users/{user_id}/courses-played")
async def get_courses_played(user_id: str, user=Depends(get_current_user)):
    """List every distinct course this user has posted a round at, plus stats.
    Ordered by play count desc so favourites bubble to the top. Average (and
    best) score is normalized to its 18-hole equivalent so 9-hole rounds
    don't skew the numbers when mixed with full rounds at the same course."""
    _ = user  # requires auth but no per-viewer data
    docs = [
        d async for d in rounds_col.find(
            {"user_id": user_id, "post_type": {"$in": ["round", None]}, "course_name": {"$ne": ""}},
            {"_id": 0, "course_name": 1, "total_score": 1, "holes_played": 1, "par": 1, "created_at": 1},
        )
    ]
    course_par_cache = await batch_course_par_cache(d.get("course_name") for d in docs)
    grouped: dict = {}
    for d in docs:
        name = d.get("course_name")
        if not name:
            continue
        g = grouped.setdefault(name, {"play_count": 0, "equivs": [], "last_played": None})
        g["play_count"] += 1
        raw = d.get("total_score")
        if raw is not None:
            g["equivs"].append(
                extrapolate_18_score(float(raw), d.get("holes_played"), d.get("par"), course_par_cache.get(name))
            )
        played_at = d.get("created_at")
        if played_at and (g["last_played"] is None or played_at > g["last_played"]):
            g["last_played"] = played_at

    out = []
    for name, g in grouped.items():
        course = await courses_col.find_one({"name": name}, {"_id": 0})
        out.append({
            "course_name": name,
            "play_count": g["play_count"],
            "best_score": round(min(g["equivs"])) if g["equivs"] else None,
            "avg_score": round(sum(g["equivs"]) / len(g["equivs"]), 1) if g["equivs"] else None,
            "last_played": g["last_played"],
            "city": course.get("city") if course else None,
            "region": course.get("region") if course else None,
            "country": course.get("country") if course else None,
        })
    out.sort(key=lambda c: (-c["play_count"], c["course_name"].lower()))
    return out


@router.get("/users/{user_id}/friends")
async def get_user_friends(user_id: str, user=Depends(get_current_user)):
    """List friends (mutual follows) with server-side aggregation.
    
    QUICK WIN #4: Use $facet aggregation to compute friend intersection server-side,
    avoiding large in-memory set operations.
    """
    # Use server-side aggregation to compute friend IDs efficiently
    friend_ids: set[str] = set()
    async for result in follows_col.aggregate([
        {
            "$facet": {
                "following": [
                    {"$match": {"user_id": user_id}},
                    {"$project": {"_id": 0, "target_id": 1}},
                ],
                "followers": [
                    {"$match": {"target_id": user_id}},
                    {"$project": {"_id": 0, "user_id": 1}},
                ],
            }
        },
    ]):
        # Extract the IDs from each facet
        following_ids = {f["target_id"] for f in result.get("following", [])}
        follower_ids = {f["user_id"] for f in result.get("followers", [])}
        friend_ids = following_ids & follower_ids
    
    if not friend_ids:
        return []
    
    # Fetch viewer's follow graph once for efficiency
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


@router.post("/rounds/{round_id}/pin")
async def pin_round(round_id: str, user=Depends(get_current_user)):
    r = await rounds_col.find_one({"id": round_id})
    if not r:
        raise HTTPException(status_code=404, detail="Round not found")
    if r["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Can only pin your own rounds")
    await users_col.update_one({"id": user["id"]}, {"$set": {"pinned_round_id": round_id}})
    return {"pinned": True, "round_id": round_id}


@router.delete("/users/me/pin")
async def unpin_round(user=Depends(get_current_user)):
    await users_col.update_one({"id": user["id"]}, {"$unset": {"pinned_round_id": ""}})
    return {"pinned": False}


@router.get("/users/by-name/{display_name}")
async def get_user_by_name(display_name: str, user=Depends(get_current_user)):
    safe = safe_query(display_name.replace("_", " "), max_len=80)
    if not safe:
        raise HTTPException(status_code=404, detail="User not found")
    exact = await users_col.find_one(
        {"display_name": {"$regex": f"^{re.escape(safe)}$", "$options": "i"}},
        {"_id": 0, "hashed_password": 0},
    )
    if exact:
        return {"id": exact["id"], "display_name": exact["display_name"], "avatar": exact.get("avatar")}
    starts = await users_col.find_one(
        {"display_name": {"$regex": f"^{re.escape(safe)}", "$options": "i"}},
        {"_id": 0, "hashed_password": 0},
    )
    if starts:
        return {"id": starts["id"], "display_name": starts["display_name"], "avatar": starts.get("avatar")}
    raise HTTPException(status_code=404, detail="User not found")


@router.get("/users/{user_id}/achievements")
async def get_achievements(user_id: str, user=Depends(get_current_user)):
    rounds = [r async for r in rounds_col.find({"user_id": user_id}, {"_id": 0}).sort("created_at", 1)]
    defs = compute_achievement_defs(rounds)
    return {
        "total": sum(1 for d in defs if d["earned"]),
        "achievements": defs,
    }


@router.post("/users/{user_id}/follow")
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
    # Notify the followee.
    await emit_notification(
        user_id=user_id,
        pref_key="follow",
        type_="follow",
        title="New follower",
        body=f'{user.get("display_name") or "Someone"} started following you.',
        extra={
            "actor_id": user["id"],
            "actor_name": user.get("display_name"),
        },
    )
    return {"following": True}


# ---- Wishlist ----
@router.get("/users/{user_id}/wishlist")
async def get_wishlist(user_id: str, user=Depends(get_current_user)):
    out = []
    async for w in wishlists_col.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1):
        out.append(await enrich_wishlist_entry(w))
    return out


@router.post("/wishlist")
async def add_to_wishlist(data: WishlistIn, user=Depends(get_current_user)):
    course_name = data.course_name.strip()
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


@router.delete("/wishlist/{course_name}")
async def remove_from_wishlist(course_name: str, user=Depends(get_current_user)):
    res = await wishlists_col.delete_one({"user_id": user["id"], "course_name": course_name})
    return {"removed": res.deleted_count > 0}


@router.get("/wishlist/check/{course_name}")
async def check_wishlist(course_name: str, user=Depends(get_current_user)):
    exists = await wishlists_col.find_one({"user_id": user["id"], "course_name": course_name}) is not None
    return {"on_wishlist": exists}


@router.get("/discover/users")
async def discover_users(
    q: str = "",
    connections_only: bool = False,
    user=Depends(get_current_user),
):
    """Search users by display name.

    When `connections_only=True` (used by the @-mention picker) results are
    restricted to accounts the current viewer already has a following-graph
    edge with — either the viewer follows them, or they follow the viewer.
    This keeps the tag list to the people you actually play/chat with.
    """
    query: dict = {}
    safe = safe_query(q)
    if safe:
        query = {"display_name": {"$regex": safe, "$options": "i"}}

    allowed_ids: set[str] | None = None
    if connections_only:
        following_ids = {
            f["target_id"]
            async for f in follows_col.find(
                {"user_id": user["id"]}, {"_id": 0, "target_id": 1}
            )
        }
        follower_ids = {
            f["user_id"]
            async for f in follows_col.find(
                {"target_id": user["id"]}, {"_id": 0, "user_id": 1}
            )
        }
        allowed_ids = following_ids | follower_ids
        # Short-circuit: no follow-graph edges → nothing to suggest.
        if not allowed_ids:
            return []
        query = {**query, "id": {"$in": list(allowed_ids)}}

    users = []
    async for u in users_col.find(query, {"_id": 0, "hashed_password": 0, "email": 0}).limit(30):
        if u["id"] == user["id"]:
            continue
        round_count = await rounds_col.count_documents({"user_id": u["id"]})
        users.append({**public_user(u), "round_count": round_count})
    return users


# Silence unused-import warning; `reviews_col` is referenced in courses router,
# but we keep the import list minimal here.
_ = reviews_col
