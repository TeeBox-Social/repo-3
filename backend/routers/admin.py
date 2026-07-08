"""Admin-only endpoints: course moderation, OSM bulk imports, demo purge, legacy import."""
import asyncio
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from db import (
    comments_col,
    courses_col,
    follows_col,
    import_jobs_col,
    likes_col,
    notifications_col,
    refresh_tokens_col,
    reviews_col,
    rounds_col,
    users_col,
    wishlists_col,
)
from helpers import emit_notification, now_iso
from models import PurgeIn, RejectIn
from overpass import (
    COUNTRY_BBOXES,
    country_tiles,
    overpass_fetch,
    overpass_query,
    persist_osm_elements,
    run_import_job,
    sweep_tiles,
)
from security import get_current_user, limiter, require_admin

router = APIRouter()


# ---- Pending courses ----
@router.get("/admin/courses/pending")
async def admin_list_pending(user=Depends(get_current_user)):
    require_admin(user)
    out = []
    async for c in courses_col.find({"verified": False}, {"_id": 0}).sort("created_at", -1).limit(100):
        used = await rounds_col.count_documents({"course_name": c["name"]})
        out.append({**c, "round_count": used})
    return out


@router.post("/admin/courses/{course_id}/verify")
async def admin_verify_course(course_id: str, user=Depends(get_current_user)):
    require_admin(user)
    course = await courses_col.find_one({"id": course_id}, {"_id": 0})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.get("verified"):
        return {"ok": True, "already_verified": True}
    await courses_col.update_one(
        {"id": course_id},
        {"$set": {"verified": True, "verified_at": now_iso(), "verified_by": user["id"]}},
    )
    # Notify the submitter of approval.
    submitter = course.get("submitted_by")
    if submitter:
        await emit_notification(
            user_id=submitter,
            pref_key="course_verified",
            type_="course_verified",
            title="Course submission approved",
            body=f'Your submission "{course["name"]}" is now live for everyone to use.',
            extra={"course_name": course["name"], "course_id": course_id},
        )
    return {"ok": True}


@router.post("/admin/courses/{course_id}/reject")
async def admin_reject_course(course_id: str, data: RejectIn, user=Depends(get_current_user)):
    require_admin(user)
    course = await courses_col.find_one({"id": course_id}, {"_id": 0})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.get("verified"):
        raise HTTPException(status_code=400, detail="Cannot reject a course that is already verified")
    submitter = course.get("submitted_by")
    reason = (data.reason or "").strip()
    if submitter:
        # Kept as a direct insert (not pref-gated) so rejection is always audited
        # even if the user opted out of course_verified notifications.
        await notifications_col.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": submitter,
            "type": "course_rejected",
            "title": "Course submission rejected",
            "body": (
                f'Your submission "{course["name"]}" was not approved.'
                + (f" Reason: {reason}" if reason else "")
            ),
            "course_name": course["name"],
            "reason": reason or None,
            "read": False,
            "created_at": now_iso(),
        })
    await courses_col.delete_one({"id": course_id})
    return {"ok": True}


# ---- OSM bulk imports ----
@router.post("/admin/courses/import-osm-global")
async def admin_import_osm_global(
    tile: int = Query(20, ge=5, le=40),
    delay: float = Query(2.0, ge=0.5, le=10.0),
    user=Depends(get_current_user),
):
    require_admin(user)
    active = await import_jobs_col.find_one({"status": {"$in": ["queued", "running"]}}, {"_id": 0, "id": 1})
    if active:
        raise HTTPException(status_code=409, detail=f"Import job {active['id']} is already active")
    tiles = sweep_tiles(tile=tile)
    job_id = str(uuid.uuid4())
    await import_jobs_col.insert_one({
        "id": job_id,
        "kind": "global",
        "tile_deg": tile,
        "status": "queued",
        "total_tiles": len(tiles),
        "processed_tiles": 0,
        "inserted": 0,
        "errors": 0,
        "created_at": now_iso(),
        "triggered_by": user["id"],
    })
    asyncio.create_task(run_import_job(job_id, tiles, delay_s=delay))
    return {"job_id": job_id, "total_tiles": len(tiles), "status": "queued"}


@router.post("/admin/courses/import-osm-country")
async def admin_import_osm_country(
    country: str = Query(...),
    tile: int = Query(10, ge=2, le=30),
    delay: float = Query(2.0, ge=0.5, le=10.0),
    user=Depends(get_current_user),
):
    require_admin(user)
    code = country.upper().strip()
    if code not in COUNTRY_BBOXES:
        raise HTTPException(status_code=400, detail=f"Unknown country code. Supported: {sorted(COUNTRY_BBOXES.keys())}")
    active = await import_jobs_col.find_one({"status": {"$in": ["queued", "running"]}}, {"_id": 0, "id": 1})
    if active:
        raise HTTPException(status_code=409, detail=f"Import job {active['id']} is already active")
    south, west, north, east = COUNTRY_BBOXES[code]
    tiles = []
    lat = south
    while lat < north:
        lng = west
        while lng < east:
            tiles.append((lat, lng, min(lat + tile, north), min(lng + tile, east)))
            lng += tile
        lat += tile
    job_id = str(uuid.uuid4())
    await import_jobs_col.insert_one({
        "id": job_id,
        "kind": "country",
        "country": code,
        "tile_deg": tile,
        "status": "queued",
        "total_tiles": len(tiles),
        "processed_tiles": 0,
        "inserted": 0,
        "errors": 0,
        "created_at": now_iso(),
        "triggered_by": user["id"],
    })
    asyncio.create_task(run_import_job(job_id, tiles, delay_s=delay))
    return {"job_id": job_id, "total_tiles": len(tiles), "country": code, "status": "queued"}


@router.get("/admin/courses/import-jobs/{job_id}")
async def admin_get_import_job(job_id: str, user=Depends(get_current_user)):
    require_admin(user)
    job = await import_jobs_col.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/admin/courses/import-jobs")
async def admin_list_import_jobs(limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user)):
    require_admin(user)
    cursor = import_jobs_col.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    jobs = [j async for j in cursor]
    total_courses = await courses_col.count_documents({})
    return {"jobs": jobs, "total_courses": total_courses}


@router.post("/admin/courses/import-jobs/{job_id}/cancel")
async def admin_cancel_import_job(job_id: str, user=Depends(get_current_user)):
    require_admin(user)
    res = await import_jobs_col.update_one(
        {"id": job_id, "status": {"$in": ["queued", "running"]}},
        {"$set": {"status": "cancelled", "cancelled_at": now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Job not found or not cancellable")
    return {"ok": True}


@router.get("/admin/courses/stats")
async def admin_courses_stats(user=Depends(get_current_user)):
    require_admin(user)
    total = await courses_col.count_documents({})
    by_source: dict = {}
    async for doc in courses_col.aggregate([{"$group": {"_id": "$source", "n": {"$sum": 1}}}]):
        by_source[doc["_id"] or "unknown"] = doc["n"]
    return {"total_courses": total, "by_source": by_source, "supported_countries": sorted(COUNTRY_BBOXES.keys())}


# ---- Demo purge ----
@router.post("/admin/purge-demo")
async def admin_purge_demo(data: PurgeIn, user=Depends(get_current_user)):
    require_admin(user)
    if data.domains is None:
        raw_domains = ["teebox.demo"]
    else:
        raw_domains = data.domains
    domains = [d.strip().lower().lstrip("@") for d in raw_domains if d and d.strip()]
    if not domains:
        raise HTTPException(status_code=400, detail="At least one domain is required")

    pattern = "|".join(re.escape(d) for d in domains)
    email_regex = {"$regex": f"@({pattern})$", "$options": "i"}
    victims_q = {"email": email_regex}

    victims = [u async for u in users_col.find(victims_q, {"_id": 0, "id": 1, "email": 1})]
    user_ids = [v["id"] for v in victims]

    report: dict = {
        "domains": domains,
        "matched_users": len(victims),
        "matched_emails": [v["email"] for v in victims],
        "dry_run": data.dry_run,
    }

    async def _count(col, q):
        return await col.count_documents(q)

    if user_ids:
        report["rounds"] = await _count(rounds_col, {"user_id": {"$in": user_ids}})
        report["likes"] = await _count(likes_col, {"user_id": {"$in": user_ids}})
        report["comments"] = await _count(comments_col, {"user_id": {"$in": user_ids}})
        report["follows_from"] = await _count(follows_col, {"user_id": {"$in": user_ids}})
        report["follows_to"] = await _count(follows_col, {"target_id": {"$in": user_ids}})
        report["notifications"] = await _count(notifications_col, {"user_id": {"$in": user_ids}})
        report["refresh_tokens"] = await _count(refresh_tokens_col, {"user_id": {"$in": user_ids}})
        report["wishlists"] = await _count(wishlists_col, {"user_id": {"$in": user_ids}})
        report["reviews"] = await _count(reviews_col, {"user_id": {"$in": user_ids}})
        report["submitted_courses"] = await _count(
            courses_col, {"submitted_by": {"$in": user_ids}, "verified": False},
        )
    else:
        report.update({
            "rounds": 0, "likes": 0, "comments": 0, "follows_from": 0, "follows_to": 0,
            "notifications": 0, "refresh_tokens": 0, "wishlists": 0, "reviews": 0,
            "submitted_courses": 0,
        })

    if data.dry_run or not user_ids:
        return {"ok": True, **report}

    await rounds_col.delete_many({"user_id": {"$in": user_ids}})
    await likes_col.delete_many({"user_id": {"$in": user_ids}})
    await comments_col.delete_many({"user_id": {"$in": user_ids}})
    await follows_col.delete_many({"user_id": {"$in": user_ids}})
    await follows_col.delete_many({"target_id": {"$in": user_ids}})
    await notifications_col.delete_many({"user_id": {"$in": user_ids}})
    await refresh_tokens_col.delete_many({"user_id": {"$in": user_ids}})
    await wishlists_col.delete_many({"user_id": {"$in": user_ids}})
    await reviews_col.delete_many({"user_id": {"$in": user_ids}})
    await courses_col.delete_many({"submitted_by": {"$in": user_ids}, "verified": False})
    await users_col.delete_many({"id": {"$in": user_ids}})

    return {"ok": True, **report}


# ---- Legacy single-bbox import ----
@router.post("/courses/import-osm")
@limiter.limit("10/hour")
async def import_courses_osm(
    request: Request,
    bbox: str = Query(...),
    user=Depends(get_current_user),
):
    require_admin(user)
    try:
        parts = [float(p) for p in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must have 4 numbers")
        south, west, north, east = parts
    except Exception:
        raise HTTPException(status_code=400, detail="bbox must be 'south,west,north,east'")

    try:
        data = await overpass_fetch(overpass_query(south, west, north, east, timeout=30), timeout=45.0)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OSM Overpass error: {e}")

    inserted = await persist_osm_elements(data.get("elements", []))
    total = await courses_col.count_documents({})
    return {"inserted": inserted, "total_courses": total}
