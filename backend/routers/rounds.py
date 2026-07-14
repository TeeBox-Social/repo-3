"""Rounds, likes, feed, comments and comment-likes."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from config import MAX_PHOTO_B64_LEN, MAX_PHOTOS_PER_ROUND
from db import comments_col, follows_col, likes_col, rounds_col, users_col
from helpers import (
    compute_achievement_defs,
    emit_notification,
    enrich_round,
    now_iso,
    validate_b64_image,
)
from models import CommentIn, CommentUpdate, RoundIn, RoundUpdate
from security import get_current_user

router = APIRouter()


# ---- Rounds ----
@router.post("/rounds")
async def create_round(data: RoundIn, user=Depends(get_current_user)):
    photos = (data.photos or [])[:MAX_PHOTOS_PER_ROUND]
    for p in photos:
        validate_b64_image(p, MAX_PHOTO_B64_LEN, "Photo")
    post_type = data.post_type or "round"
    # Server-side validation of the discriminator invariants
    if post_type == "round":
        if data.total_score is None:
            raise HTTPException(status_code=422, detail="Score is required for a round post")
        if not (data.course_name or "").strip():
            raise HTTPException(status_code=422, detail="Course is required for a round post")
    if post_type in ("text", "lfg"):
        # Body must contain SOMETHING so we don't feed empty posts.
        if not (data.notes or "").strip() and not photos:
            raise HTTPException(status_code=422, detail="Post cannot be empty")
    round_id = str(uuid.uuid4())
    doc = {
        "id": round_id,
        "user_id": user["id"],
        "post_type": post_type,
        "course_name": (data.course_name or "").strip(),
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
        "meetup_date": data.meetup_date if post_type == "lfg" else None,
        "looking_for_count": data.looking_for_count if post_type == "lfg" else None,
        "created_at": now_iso(),
    }
    # Only diff achievements for actual round posts.
    if post_type == "round":
        prior_rounds = [
            r async for r in rounds_col.find(
                {"user_id": user["id"], "post_type": {"$in": ["round", None]}}, {"_id": 0},
            )
        ]
        before_keys = {d["key"] for d in compute_achievement_defs(prior_rounds) if d["earned"]}
        after_defs = compute_achievement_defs(prior_rounds + [doc])
        new_achs = [
            {"key": d["key"], "title": d["title"], "desc": d["desc"], "icon": d["icon"]}
            for d in after_defs
            if d["earned"] and d["key"] not in before_keys
        ]
        doc["new_achievements"] = new_achs
    else:
        doc["new_achievements"] = []
    await rounds_col.insert_one(doc)
    for ach in doc.get("new_achievements", []):
        await emit_notification(
            user_id=user["id"],
            pref_key="achievement_unlocked",
            type_="achievement_unlocked",
            title="Achievement unlocked",
            body=f'{ach.get("title", "New badge")} — {ach.get("desc", "")}'.strip(" —"),
            extra={
                "achievement_key": ach.get("key"),
                "achievement_icon": ach.get("icon"),
                "round_id": round_id,
            },
        )
    return await enrich_round(doc, user["id"])


@router.patch("/rounds/{round_id}")
async def update_round(round_id: str, data: RoundUpdate, user=Depends(get_current_user)):
    r = await rounds_col.find_one({"id": round_id})
    if not r:
        raise HTTPException(status_code=404, detail="Round not found")
    if r["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    updates = data.dict(exclude_unset=True)
    if "photos" in updates and updates["photos"] is not None:
        updates["photos"] = (updates["photos"] or [])[:MAX_PHOTOS_PER_ROUND]
        for p in updates["photos"]:
            validate_b64_image(p, MAX_PHOTO_B64_LEN, "Photo")
    if "course_name" in updates and updates["course_name"] is not None:
        updates["course_name"] = str(updates["course_name"]).strip()
    updates["edited_at"] = now_iso()
    await rounds_col.update_one({"id": round_id}, {"$set": updates})
    fresh = await rounds_col.find_one({"id": round_id}, {"_id": 0})
    return await enrich_round(fresh, user["id"])


@router.get("/feed")
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
    return [await enrich_round(r, user["id"]) async for r in cursor]


@router.get("/rounds/{round_id}")
async def get_round(round_id: str, user=Depends(get_current_user)):
    r = await rounds_col.find_one({"id": round_id}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Round not found")
    return await enrich_round(r, user["id"])


@router.delete("/rounds/{round_id}")
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


@router.post("/rounds/{round_id}/like")
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
        # Notify round author of new like (skip self-likes).
        if r.get("user_id") and r["user_id"] != user["id"]:
            await emit_notification(
                user_id=r["user_id"],
                pref_key="post_like",
                type_="post_like",
                title="New like on your round",
                body=f'{user.get("display_name") or "Someone"} liked your round at {r.get("course_name") or "a course"}.',
                extra={
                    "round_id": round_id,
                    "actor_id": user["id"],
                    "actor_name": user.get("display_name"),
                },
            )
    count = await likes_col.count_documents({"round_id": round_id})
    return {"liked": liked, "like_count": count}


# ---- Comments ----
@router.get("/rounds/{round_id}/comments")
async def get_comments(round_id: str, user=Depends(get_current_user)):
    out = []
    async for c in comments_col.find({"round_id": round_id}, {"_id": 0}).sort("created_at", 1):
        author = await users_col.find_one({"id": c["user_id"]}, {"_id": 0, "hashed_password": 0})
        liked_by = c.get("liked_by") or []
        out.append({
            **c,
            "author": {
                "id": author.get("id"),
                "display_name": author.get("display_name"),
                "avatar": author.get("avatar"),
            } if author else None,
            "like_count": len(liked_by),
            "liked_by_me": user["id"] in liked_by,
        })
    return out


@router.post("/rounds/{round_id}/comments")
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
        "liked_by": [],
        "created_at": now_iso(),
    }
    await comments_col.insert_one(doc)
    doc.pop("_id", None)
    # Notify round author about the new comment (skip self-comments).
    if r.get("user_id") and r["user_id"] != user["id"]:
        await emit_notification(
            user_id=r["user_id"],
            pref_key="post_comment",
            type_="post_comment",
            title="New comment on your round",
            body=f'{user.get("display_name") or "Someone"} commented on your round.',
            extra={
                "round_id": round_id,
                "comment_id": doc["id"],
                "actor_id": user["id"],
                "actor_name": user.get("display_name"),
            },
        )
    # Notify every @-mentioned user.
    for mention_id in (data.mentions or []):
        if mention_id and mention_id != user["id"]:
            await emit_notification(
                user_id=mention_id,
                pref_key="mention",
                type_="mention",
                title="You were mentioned",
                body=f'{user.get("display_name") or "Someone"} mentioned you in a comment.',
                extra={
                    "round_id": round_id,
                    "comment_id": doc["id"],
                    "actor_id": user["id"],
                    "actor_name": user.get("display_name"),
                },
            )
    return {
        **doc,
        "author": {
            "id": user["id"],
            "display_name": user["display_name"],
            "avatar": user.get("avatar"),
        },
        "like_count": 0,
        "liked_by_me": False,
    }


@router.patch("/rounds/{round_id}/comments/{comment_id}")
async def update_comment(
    round_id: str,
    comment_id: str,
    data: CommentUpdate,
    user=Depends(get_current_user),
):
    c = await comments_col.find_one({"id": comment_id, "round_id": round_id})
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    if c["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    updates: dict = {
        "text": data.text.strip(),
        "edited_at": now_iso(),
    }
    if data.mentions is not None:
        updates["mentions"] = data.mentions
    await comments_col.update_one({"id": comment_id}, {"$set": updates})
    fresh = await comments_col.find_one({"id": comment_id}, {"_id": 0})
    liked_by = fresh.get("liked_by") or []
    return {
        **fresh,
        "author": {
            "id": user["id"],
            "display_name": user["display_name"],
            "avatar": user.get("avatar"),
        },
        "like_count": len(liked_by),
        "liked_by_me": user["id"] in liked_by,
    }


@router.delete("/rounds/{round_id}/comments/{comment_id}")
async def delete_comment(round_id: str, comment_id: str, user=Depends(get_current_user)):
    c = await comments_col.find_one({"id": comment_id, "round_id": round_id})
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    if c["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    await comments_col.delete_one({"id": comment_id})
    return {"ok": True}


@router.post("/rounds/{round_id}/comments/{comment_id}/like")
async def toggle_comment_like(round_id: str, comment_id: str, user=Depends(get_current_user)):
    c = await comments_col.find_one({"id": comment_id, "round_id": round_id})
    if not c:
        raise HTTPException(status_code=404, detail="Comment not found")
    liked_by = c.get("liked_by") or []
    if user["id"] in liked_by:
        await comments_col.update_one({"id": comment_id}, {"$pull": {"liked_by": user["id"]}})
        liked_by = [u for u in liked_by if u != user["id"]]
        liked = False
    else:
        await comments_col.update_one({"id": comment_id}, {"$addToSet": {"liked_by": user["id"]}})
        liked_by = liked_by + [user["id"]]
        liked = True
        author_id = c.get("user_id")
        if author_id and author_id != user["id"]:
            await emit_notification(
                user_id=author_id,
                pref_key="comment_like",
                type_="comment_like",
                title="New like on your comment",
                body=f'{user.get("display_name") or "Someone"} liked your comment.',
                extra={
                    "round_id": round_id,
                    "comment_id": comment_id,
                    "actor_id": user["id"],
                    "actor_name": user.get("display_name"),
                },
            )
    return {"liked": liked, "like_count": len(liked_by)}
