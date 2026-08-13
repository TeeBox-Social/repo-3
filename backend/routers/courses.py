"""Course discovery, search, submission, reviews, nearby lookup."""
import logging
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import opengolf_client
from db import courses_col, reviews_col, rounds_col, users_col
from helpers import haversine_km, now_iso, safe_query
from models import NewCourseIn, ReviewIn
from security import get_current_user, limiter

router = APIRouter()
logger = logging.getLogger(__name__)

# ---- OpenGolfAPI: nationwide (32,700+ US courses) cache-aside integration ----
DETAILS_TTL_DAYS = 30
NAME_COLLISION_GUARD_KM = 40  # generic names (e.g. "White Pines Golf Course")
                               # can exist multiple times nationwide — never
                               # merge OpenGolfAPI facts onto a course we
                               # already know is somewhere else entirely.


async def _cache_opengolf_compact(c: dict) -> None:
    """Best-effort upsert of a compact OpenGolfAPI search result into our own
    ``courses_col``. Enriches an existing course (matched by exact name) without
    clobbering its ``source``/``verified`` flag; inserts a new verified,
    nationwide-sourced course otherwise. Never raises.

    Guards against nationwide name collisions (e.g. two unrelated real courses
    both called "White Pines Golf Course"): if the doc we already have on file
    for this exact name has its own coordinates and they're far from this
    candidate, we skip entirely rather than risk attaching the wrong
    ``external_id``/facts to the wrong course. If the identity (external_id)
    is legitimately changing, we also clear any previously-cached rich detail
    (tees/holes/climate/etc.) since it belongs to the *old* external_id and
    would otherwise keep showing stale, mismatched facts.
    """
    name = (c.get("course_name") or "").strip()
    if not name:
        return
    clat, clng = c.get("lat"), c.get("lng")
    try:
        existing = await courses_col.find_one({"name": name}, {"_id": 0, "lat": 1, "lng": 1, "external_id": 1})
        if existing:
            elat, elng = existing.get("lat"), existing.get("lng")
            if elat is not None and elng is not None and clat is not None and clng is not None:
                if haversine_km(elat, elng, clat, clng) > NAME_COLLISION_GUARD_KM:
                    logger.warning(
                        f"opengolf name-collision guard: skipping cache for {name!r} — "
                        f"match is >{NAME_COLLISION_GUARD_KM}km from the course already on file "
                        f"(likely a different course sharing this name)"
                    )
                    return
        country_iso = c.get("country_iso") or "US"
        set_fields = {
            "city": c.get("city"),
            "region": c.get("state"),
            "country": "USA" if country_iso == "US" else country_iso,
            "lat": clat,
            "lng": clng,
            "par": c.get("par"),
            "course_type": c.get("type"),
            "num_holes": c.get("holes"),
            "external_id": c.get("id"),
        }
        old_external_id = existing.get("external_id") if existing else None
        new_external_id = c.get("id")
        if old_external_id and new_external_id and old_external_id != new_external_id:
            # Identity changed — any cached rich detail was fetched for the
            # OLD (now-superseded) external_id and must not keep showing.
            logger.warning(f"opengolf identity change for {name!r}: {old_external_id} -> {new_external_id}; clearing stale detail cache")
            set_fields.update({
                "total_yardage": None, "architect": None, "year_built": None,
                "phone": None, "website": None, "address": None,
                "tees": [], "holes": [], "climate": {}, "insights": {},
                "details_synced_at": None, "detail_external_id": None,
            })
        await courses_col.update_one(
            {"name": name},
            {
                "$set": set_fields,
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "source": "opengolfapi",
                    "verified": True,
                    "created_at": now_iso(),
                },
            },
            upsert=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"opengolf cache upsert skipped for {name!r}: {e}")


async def _ensure_course_details(course: dict | None) -> dict | None:
    """Lazily fetch + cache full OpenGolfAPI detail (tees, hole-by-hole
    yardages, climate, insights) for a course that carries an ``external_id``.
    Cached for ``DETAILS_TTL_DAYS`` days. Best-effort — a slow/down upstream
    just means the course renders without the extra facts.

    The cache is only trusted if it was fetched for the *current*
    ``external_id`` (tracked via ``detail_external_id``) — if the identity was
    corrected since the last fetch, we always re-fetch regardless of TTL. As a
    second safety net, if the freshly-fetched detail's own coordinates are far
    from this course's known coordinates, we treat it as a name collision and
    clear the facts instead of showing data for the wrong real-world course."""
    if not course or not course.get("external_id"):
        return course
    ext_id = course["external_id"]
    synced = course.get("details_synced_at")
    if synced and course.get("holes") and course.get("detail_external_id") == ext_id:
        try:
            age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(synced)).days
            if age_days < DETAILS_TTL_DAYS:
                return course
        except Exception:
            pass
    detail = await opengolf_client.get_course_detail(ext_id)
    if not detail:
        return course
    clat, clng = course.get("lat"), course.get("lng")
    dlat, dlng = detail.get("lat"), detail.get("lng")
    if clat is not None and clng is not None and dlat is not None and dlng is not None:
        if haversine_km(clat, clng, dlat, dlng) > NAME_COLLISION_GUARD_KM:
            logger.warning(
                f"opengolf detail mismatch for {course.get('name')!r}: external_id {ext_id} "
                f"is >{NAME_COLLISION_GUARD_KM}km away from the course's own location — clearing"
            )
            clear = {
                "external_id": None, "detail_external_id": None, "par": course.get("par"),
                "total_yardage": None, "course_type": course.get("course_type"),
                "architect": None, "year_built": None, "phone": None, "website": None,
                "address": None, "tees": [], "holes": [], "climate": {}, "insights": {},
                "details_synced_at": now_iso(),
            }
            try:
                await courses_col.update_one({"name": course["name"]}, {"$set": clear})
            except Exception:
                pass
            course.update(clear)
            return course
    update = {
        "par": detail.get("par") or course.get("par"),
        "total_yardage": detail.get("yardage"),
        "course_type": detail.get("type") or course.get("course_type"),
        "num_holes": detail.get("holes") or course.get("num_holes"),
        "architect": detail.get("architect"),
        "year_built": detail.get("year_built"),
        "phone": detail.get("phone"),
        "website": detail.get("website"),
        "address": detail.get("address"),
        "tees": detail.get("tees") or [],
        "holes": detail.get("holes_data") or [],
        "climate": detail.get("climate") or {},
        "insights": detail.get("insights") or {},
        "details_synced_at": now_iso(),
        "detail_external_id": ext_id,
    }
    try:
        await courses_col.update_one({"name": course["name"]}, {"$set": update})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"opengolf detail cache write skipped for {course.get('name')!r}: {e}")
    course.update(update)
    return course

# ---- QUICK WIN #2: Pre-compute review stats aggregation helper ----
async def _get_review_stats_map(course_names: list[str]) -> dict[str, dict]:
    """
    Fetch review stats (count, avg rating) for multiple courses in a single aggregation.
    Returns a dict mapping course_name -> {count: int, avg_rating: float}.
    """
    stats_map = {}
    if not course_names:
        return stats_map
    
    async for result in reviews_col.aggregate([
        {"$match": {"course_name": {"$in": course_names}}},
        {
            "$group": {
                "_id": "$course_name",
                "count": {"$sum": 1},
                "avg": {"$avg": "$rating"},
            }
        },
    ]):
        course_name = result["_id"]
        stats_map[course_name] = {
            "count": result["count"],
            "avg_rating": round(result["avg"], 2) if result.get("avg") else None,
        }
    return stats_map


@router.get("/discover/courses")
async def discover_courses(q: str = "", lat: Optional[float] = None, lng: Optional[float] = None, user=Depends(get_current_user)):
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

    # ---- QUICK WIN #2: Pre-compute all review stats in one aggregation ----
    all_course_names = set()
    for m in master:
        all_course_names.add(m["name"])
    for name in round_agg.keys():
        all_course_names.add(name)
    
    review_stats = await _get_review_stats_map(list(all_course_names))

    seen = set()
    by_name: dict = {}
    out = []
    for m in master:
        name = m["name"]
        seen.add(name)
        r = round_agg.get(name)
        stats = review_stats.get(name, {})
        row = {
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
            "review_count": stats.get("count", 0),
            "avg_rating": stats.get("avg_rating"),
            "source": m.get("source", "community"),
        }
        by_name[name] = row
        out.append(row)
    
    for name, r in round_agg.items():
        if name in seen:
            continue
        stats = review_stats.get(name, {})
        row = {
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
            "review_count": stats.get("count", 0),
            "avg_rating": stats.get("avg_rating"),
            "source": "community",
        }
        seen.add(name)
        by_name[name] = row
        out.append(row)

    # ---- Nationwide fallback: a named search with few local hits queries
    # OpenGolfAPI's 32,700+ US course database live and caches new matches
    # into our own catalog so future searches are instant. Best-effort.
    # Caching runs even for names we already know locally (e.g. a
    # seeded/OSM course) so it gets backfilled with par/tees/holes/climate,
    # and the already-visible row is patched in place with any facts it was
    # missing (city/region/lat/lng) rather than only benefiting the *next* search. ----
    if safe and len(out) < 8:
        try:
            live = await opengolf_client.search_courses(q=safe, limit=20)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"opengolf nationwide search skipped: {e}")
            live = []
        for c in live:
            name = (c.get("course_name") or "").strip()
            if not name:
                continue
            await _cache_opengolf_compact(c)
            if name in seen:
                existing = by_name.get(name)
                if existing:
                    existing["city"] = existing.get("city") or c.get("city")
                    existing["region"] = existing.get("region") or c.get("state")
                    existing["country"] = existing.get("country") or "USA"
                    existing["lat"] = existing.get("lat") if existing.get("lat") is not None else c.get("lat")
                    existing["lng"] = existing.get("lng") if existing.get("lng") is not None else c.get("lng")
                continue
            seen.add(name)
            out.append({
                "course_name": name,
                "city": c.get("city"),
                "region": c.get("state"),
                "country": "USA",
                "lat": c.get("lat"),
                "lng": c.get("lng"),
                "play_count": 0,
                "avg_score": None,
                "best_score": None,
                "last_photo": None,
                "review_count": 0,
                "avg_rating": None,
                "source": "opengolfapi",
            })

    out.sort(key=lambda c: (-c["play_count"], c["course_name"].lower()))
    # ---- Location-first sort: when we know where the user is, the nearest
    # courses should lead, with popularity (play count) as the tiebreaker.
    # Falls back to popularity-only sort above when location isn't available. ----
    if lat is not None and lng is not None:
        def _dist_key(c):
            if c.get("lat") is not None and c.get("lng") is not None:
                return haversine_km(lat, lng, c["lat"], c["lng"])
            return float("inf")
        out.sort(key=lambda c: (_dist_key(c), -c["play_count"], c["course_name"].lower()))
    # ---- QUICK WIN #6: Enforce pagination limit before returning ----
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

    # ---- Nationwide fallback: sparse local coverage near this point queries
    # OpenGolfAPI's geo-radius search live and caches new matches (including
    # backfilling external_id/par onto courses we already have locally, so
    # their detail page picks up tees/holes/climate). Best-effort. ----
    if len(candidates) < limit:
        try:
            live = await opengolf_client.search_courses(
                lat=lat, lng=lng, radius_mi=radius_km * 0.621371, limit=limit,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"opengolf nationwide nearby search skipped: {e}")
            live = []
        existing_names = {c["name"] for _, c in candidates}
        for c in live:
            name = (c.get("course_name") or "").strip()
            if not name:
                continue
            await _cache_opengolf_compact(c)
            if name in existing_names:
                continue
            existing_names.add(name)
            dist_mi = c.get("distance_mi")
            clat, clng = c.get("lat"), c.get("lng")
            dist_km = (
                dist_mi * 1.60934 if dist_mi is not None
                else (haversine_km(lat, lng, clat, clng) if clat is not None and clng is not None else radius_km)
            )
            candidates.append((dist_km, {
                "name": name,
                "city": c.get("city"),
                "region": c.get("state"),
                "country": "USA",
                "lat": clat,
                "lng": clng,
                "par": c.get("par"),
                "num_holes": c.get("holes"),
                "source": "opengolfapi",
            }))
        candidates.sort(key=lambda x: x[0])

    # ---- QUICK WIN #2: Pre-compute review stats for candidate courses ----
    candidate_courses = [c["name"] for _, c in candidates[:limit]]
    review_stats = await _get_review_stats_map(candidate_courses)
    
    # ---- QUICK WIN #6: Apply limit before querying play counts ----
    out = []
    for dist, c in candidates[:limit]:
        name = c["name"]
        play_count = await rounds_col.count_documents({"course_name": name})
        stats = review_stats.get(name, {})
        out.append({
            "course_name": name,
            "city": c.get("city"),
            "region": c.get("region"),
            "country": c.get("country"),
            "lat": c.get("lat"),
            "lng": c.get("lng"),
            "par": c.get("par"),
            "num_holes": c.get("num_holes"),
            "distance_km": round(dist, 1),
            "play_count": play_count,
            "review_count": stats.get("count", 0),
            "avg_rating": stats.get("avg_rating"),
            "source": c.get("source", "osm"),
        })
    return out


@router.get("/courses/search")
@limiter.limit("120/minute")
async def course_search(
    request: Request,
    q: str = "",
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    limit: int = Query(15, ge=1, le=30),
    user=Depends(get_current_user),
):
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
    seen_names = set()
    out = []
    async for c in courses_col.find(query, {"_id": 0}).limit(limit):
        seen_names.add(c["name"])
        out.append({
            "id": c.get("id"),
            "name": c["name"],
            "city": c.get("city"),
            "region": c.get("region"),
            "country": c.get("country"),
            "lat": c.get("lat"),
            "lng": c.get("lng"),
            "par": c.get("par"),
            "num_holes": c.get("num_holes"),
            "verified": c.get("verified", True),
            "submitted_by_me": c.get("submitted_by") == user["id"],
            "source": c.get("source", "community"),
        })

    # ---- Nationwide fallback: sparse local matches fall through to
    # OpenGolfAPI's 32,700+ US course database so any course can be logged. ----
    if len(out) < limit:
        try:
            live = await opengolf_client.search_courses(q=safe, limit=limit)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"opengolf nationwide course-search skipped: {e}")
            live = []
        for c in live:
            if len(out) >= limit:
                break
            name = (c.get("course_name") or "").strip()
            if not name:
                continue
            await _cache_opengolf_compact(c)
            if name in seen_names:
                continue
            seen_names.add(name)
            out.append({
                "id": None,
                "name": name,
                "city": c.get("city"),
                "region": c.get("state"),
                "country": "USA",
                "lat": c.get("lat"),
                "lng": c.get("lng"),
                "par": c.get("par"),
                "num_holes": c.get("holes"),
                "verified": True,
                "submitted_by_me": False,
                "source": "opengolfapi",
            })

    # ---- Location-first sort: nearest matches lead (name relevance is
    # already guaranteed by the regex query above); ties broken by whether
    # the course is locally verified, then alphabetically. Unchanged
    # (name-match order) when location isn't available. ----
    if lat is not None and lng is not None:
        def _dist_key(c):
            if c.get("lat") is not None and c.get("lng") is not None:
                return haversine_km(lat, lng, c["lat"], c["lng"])
            return float("inf")
        out.sort(key=lambda c: (_dist_key(c), 0 if c.get("verified") else 1, c["name"].lower()))
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
    # ---- Lazily fetch + cache OpenGolfAPI facts (tees, holes, climate, insights) ----
    course = await _ensure_course_details(course)
    play_count = await rounds_col.count_documents({"course_name": course_name})
    
    # ---- QUICK WIN #2: Use pre-aggregated stats instead of loop ----
    stats = await _get_review_stats_map([course_name])
    stats_data = stats.get(course_name, {})
    
    return {
        "course_name": course_name,
        "city": course.get("city") if course else None,
        "region": course.get("region") if course else None,
        "country": course.get("country") if course else None,
        "lat": course.get("lat") if course else None,
        "lng": course.get("lng") if course else None,
        "par": course.get("par") if course else None,
        "total_yardage": course.get("total_yardage") if course else None,
        "course_type": course.get("course_type") if course else None,
        "num_holes": course.get("num_holes") if course else None,
        "architect": course.get("architect") if course else None,
        "year_built": course.get("year_built") if course else None,
        "phone": course.get("phone") if course else None,
        "website": course.get("website") if course else None,
        "tees": (course.get("tees") if course else None) or [],
        "holes": (course.get("holes") if course else None) or [],
        "climate": course.get("climate") if course else None,
        "insights": course.get("insights") if course else None,
        "source": course.get("source") if course else None,
        "play_count": play_count,
        "review_count": stats_data.get("count", 0),
        "avg_rating": stats_data.get("avg_rating"),
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
