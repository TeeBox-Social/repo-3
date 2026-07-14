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
    compute_achievement_defs,
    emit_notification,
    enrich_round,
    enrich_wishlist_entry,
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
    round_count = await rounds_col.count_documents({"user_id": user_id})
    # Normalize 9-hole rounds to their 18-hole equivalent for a fair average.
    scores_cursor = rounds_col.find(
        {"user_id": user_id},
        {"_id": 0, "total_score": 1, "holes_played": 1, "par": 1, "course_name": 1},
    ).sort("created_at", -1).limit(20)
    recent_scores: List[float] = []
    course_par_cache: dict[str, int] = {}
    async for s in scores_cursor:
        holes = int(s.get("holes_played") or 18)
        raw = float(s.get("total_score") or 0)
        if holes >= 18:
            recent_scores.append(raw)
            continue
        target_par = 72
        cname = s.get("course_name")
        if cname:
            if cname in course_par_cache:
                target_par = course_par_cache[cname]
            else:
                course = await courses_col.find_one({"name": cname}, {"_id": 0, "par": 1})
                cp = int(course.get("par") or 0) if course else 0
                if cp >= 60:
                    target_par = cp
                else:
                    target_par = int(s.get("par") or 36) * 2
                course_par_cache[cname] = target_par
        else:
            target_par = int(s.get("par") or 36) * 2
        round_par = int(s.get("par") or 36) or 36
        equiv = raw * (target_par / round_par)
        recent_scores.append(equiv)
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
    Ordered by play count desc so favourites bubble to the top."""
    _ = user  # requires auth but no per-viewer data
    out = []
    async for c in rounds_col.aggregate([
        {"$match": {"user_id": user_id, "post_type": {"$in": ["round", None]}}},
        {"$group": {
            "_id": "$course_name",
            "play_count": {"$sum": 1},
            "best_score": {"$min": "$total_score"},
            "avg_score": {"$avg": "$total_score"},
            "last_played": {"$max": "$created_at"},
        }},
        {"$match": {"_id": {"$ne": ""}}},
        {"$sort": {"play_count": -1, "_id": 1}},
    ]):
        name = c["_id"]
        if not name:
            continue
        course = await courses_col.find_one({"name": name}, {"_id": 0})
        out.append({
            "course_name": name,
            "play_count": c["play_count"],
            "best_score": c.get("best_score"),
            "avg_score": round(c["avg_score"], 1) if c.get("avg_score") else None,
            "last_played": c.get("last_played"),
            "city": course.get("city") if course else None,
            "region": course.get("region") if course else None,
            "country": course.get("country") if course else None,
        })
    return out


@router.get("/users/{user_id}/friends")
async def get_user_friends(user_id: str, user=Depends(get_current_user)):
    following_ids = {f["target_id"] async for f in follows_col.find({"user_id": user_id}, {"_id": 0, "target_id": 1})}
    follower_ids = {f["user_id"] async for f in follows_col.find({"target_id": user_id}, {"_id": 0, "user_id": 1})}
    friend_ids = following_ids & follower_ids
    if not friend_ids:
        return []
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
async def discover_users(q: str = "", user=Depends(get_current_user)):
    query = {}
    safe = safe_query(q)
    if safe:
        query = {"display_name": {"$regex": safe, "$options": "i"}}
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
