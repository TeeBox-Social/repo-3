"""Course discovery, search, submission, reviews, nearby lookup."""
import math
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from db import courses_col, reviews_col, rounds_col, users_col
from helpers import haversine_km, now_iso, safe_query
from models import NewCourseIn, ReviewIn
from security import get_current_user, limiter

router = APIRouter()


@router.get("/discover/courses")
async def discover_courses(q: str = "", user=Depends(get_current_user)):
    safe = safe_query(q)
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

    course_query: dict = {
        "$or": [
            {"verified": {"$ne": False}},
            {"submitted_by": user["id"]},
        ]
    }
    if safe:
        course_query = {"$and": [course_query, {"name": {"$regex": safe, "$options": "i"}}]}
    master = [c async for c in courses_col.find(course_query, {"_id": 0}).limit(100)]

    seen = set()
    out = []
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
    out.sort(key=lambda c: (-c["play_count"], c["course_name"].lower()))
    return out[:60]


@router.get("/discover/courses/nearby")
@limiter.limit("30/minute")
async def discover_courses_nearby(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(80.0, ge=1, le=500),
    limit: int = Query(30, ge=1, le=60),
    user=Depends(get_current_user),
):
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
    async for c in courses_col.find(box_query, {"_id": 0}).limit(500):
        clat = c.get("lat")
        clng = c.get("lng")
        if clat is None or clng is None:
            continue
        dist = haversine_km(lat, lng, clat, clng)
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


@router.get("/courses/search")
@limiter.limit("120/minute")
async def course_search(request: Request, q: str = "", limit: int = Query(15, ge=1, le=30), user=Depends(get_current_user)):
    safe = safe_query(q, max_len=80)
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
            "verified": c.get("verified", True),
            "submitted_by_me": c.get("submitted_by") == user["id"],
        })
    return out


@router.post("/courses")
@limiter.limit("10/hour")
async def submit_course(request: Request, data: NewCourseIn, user=Depends(get_current_user)):
    name = data.name.strip()
    existing = await courses_col.find_one(
        {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        {"_id": 0, "id": 1, "name": 1, "verified": 1, "submitted_by": 1},
    )
    if existing:
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


@router.get("/courses/{course_name}/rounds")
async def get_course_rounds(course_name: str, user=Depends(get_current_user)):
    from helpers import enrich_round
    cursor = rounds_col.find({"course_name": course_name}, {"_id": 0}).sort("created_at", -1).limit(50)
    return [await enrich_round(r, user["id"]) async for r in cursor]


@router.get("/courses/{course_name}/reviews")
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


@router.get("/courses/{course_name}")
async def get_course(course_name: str, user=Depends(get_current_user)):
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


@router.post("/courses/reviews")
async def create_review(data: ReviewIn, user=Depends(get_current_user)):
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
