"""App startup work: index setup, self-heal, demo seed, admin bootstrap, OSM auto-import.

Split out of ``server.py`` so the entry point stays under 100 lines.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

import config
from config import (
    ADMIN_EMAILS,
    AUTO_IMPORT_COURSES,
    AUTO_IMPORT_THRESHOLD,
    ENABLE_DEMO_SEED,
)
from db import (
    courses_col,
    follows_col,
    import_jobs_col,
    notifications_col,
    refresh_tokens_col,
    rounds_col,
    users_col,
    wishlists_col,
)
from helpers import now_iso
from overpass import country_tiles, run_import_job
from security import pwd_context

logger = logging.getLogger(__name__)


async def ensure_indexes() -> None:
    try:
        await refresh_tokens_col.create_index("jti", unique=True)
        await refresh_tokens_col.create_index("expires_at", expireAfterSeconds=0)
        await refresh_tokens_col.create_index("family_id")
        await wishlists_col.create_index([("user_id", 1), ("course_name", 1)], unique=True)
        try:
            async for grp in courses_col.aggregate([
                {"$group": {"_id": "$name", "ids": {"$push": "$_id"}, "n": {"$sum": 1}}},
                {"$match": {"n": {"$gt": 1}}},
            ]):
                extra = grp["ids"][1:]
                if extra:
                    await courses_col.delete_many({"_id": {"$in": extra}})
        except Exception as de:
            logger.warning(f"course dedupe pass skipped: {de}")
        await courses_col.create_index("name", unique=True)
        await courses_col.create_index([("lat", 1), ("lng", 1)])
        await import_jobs_col.create_index("status")
        await import_jobs_col.create_index([("created_at", -1)])
        await notifications_col.create_index([("user_id", 1), ("created_at", -1)])
        await notifications_col.create_index([("user_id", 1), ("read", 1)])
    except Exception as e:
        logger.warning(f"index setup skipped: {e}")


async def heal_stale_import_jobs() -> None:
    try:
        stale = await import_jobs_col.update_many(
            {"status": {"$in": ["queued", "running"]}},
            {"$set": {"status": "interrupted", "finished_at": now_iso()}},
        )
        if stale.modified_count:
            logger.info(f"cleaned up {stale.modified_count} stale import jobs from previous run")
    except Exception as e:
        logger.warning(f"stale-job cleanup skipped: {e}")


async def seed_demo_data() -> dict:
    """Idempotently seed demo users/rounds/courses. Also used by the /seed endpoint."""
    if not ENABLE_DEMO_SEED:
        return {"seeded": False, "reason": "ENABLE_DEMO_SEED off"}
    if await users_col.count_documents({}) > 0:
        return {"seeded": False, "reason": "already has users"}
    demo_users = [
        {"email": "reese@teebox.demo", "display_name": "Reese Callahan", "home_course": "Pebble Meadows GC", "handicap": 8.4, "bio": "Weekend warrior. Always chasing the sunrise tee time."},
        {"email": "jordan@teebox.demo", "display_name": "Jordan Kim", "home_course": "Whistling Oak", "handicap": 14.2, "bio": "New to the game, deep in the honeymoon phase."},
        {"email": "sam@teebox.demo", "display_name": "Sam Rivera", "home_course": "Bear Creek CC", "handicap": 3.1, "bio": "College team alum. Grinding to plus."},
    ]
    ids = []
    for u in demo_users:
        uid = str(uuid.uuid4())
        ids.append(uid)
        await users_col.insert_one({
            "id": uid,
            "email": u["email"],
            "hashed_password": pwd_context.hash("password123"),
            "display_name": u["display_name"],
            "home_course": u["home_course"],
            "handicap": u["handicap"],
            "bio": u["bio"],
            "avatar": None,
            "created_at": now_iso(),
        })
    demo_rounds = [
        (ids[0], "Pebble Meadows GC", 82, 72, "Front nine was clean. Ran into trouble on 14 tee.", None),
        (ids[2], "Bear Creek CC", 74, 72, "Best putting round in months. Rolled in a 30-footer on 18.", None),
        (ids[1], "Whistling Oak", 96, 72, "First time breaking 100 in sight! Fell apart on the par 5s.", None),
        (ids[0], "Cypress Ridge", 79, 71, "Windy from the west all day. Grinded out a couple pars late.", None),
    ]
    for uid, course, score, par, notes, _photo in demo_rounds:
        rid = str(uuid.uuid4())
        await rounds_col.insert_one({
            "id": rid,
            "user_id": uid,
            "course_name": course,
            "date": now_iso(),
            "total_score": score,
            "par": par,
            "holes_played": 18,
            "fairways_hit": None,
            "greens_in_regulation": None,
            "putts": None,
            "notes": notes,
            "photos": [],
            "weather": None,
            "hole_scores": [],
            "hole_pars": [],
            "created_at": now_iso(),
        })
    for a in ids:
        for b in ids:
            if a == b:
                continue
            await follows_col.insert_one({
                "id": str(uuid.uuid4()),
                "user_id": a,
                "target_id": b,
                "created_at": now_iso(),
            })
    catalog = [
        ("Pebble Beach Golf Links", "Pebble Beach", "CA", "USA", 36.5686, -121.9494),
        ("Cypress Point Club", "Pebble Beach", "CA", "USA", 36.5811, -121.9739),
        ("Augusta National Golf Club", "Augusta", "GA", "USA", 33.5030, -82.0199),
        ("TPC Sawgrass — Stadium Course", "Ponte Vedra Beach", "FL", "USA", 30.1970, -81.3910),
        ("Bethpage State Park — Black Course", "Farmingdale", "NY", "USA", 40.7431, -73.4553),
        ("Torrey Pines — South Course", "La Jolla", "CA", "USA", 32.9012, -117.2470),
        ("Pinehurst No. 2", "Pinehurst", "NC", "USA", 35.1899, -79.4726),
        ("Chambers Bay", "University Place", "WA", "USA", 47.2018, -122.5691),
        ("Whistling Straits — Straits Course", "Kohler", "WI", "USA", 43.8511, -87.7264),
        ("The Ocean Course at Kiawah Island", "Kiawah Island", "SC", "USA", 32.6083, -80.0439),
        ("TPC Harding Park", "San Francisco", "CA", "USA", 37.7245, -122.4930),
        ("Bandon Dunes", "Bandon", "OR", "USA", 43.1836, -124.4054),
        ("Pacific Dunes", "Bandon", "OR", "USA", 43.1968, -124.4108),
        ("Streamsong Blue", "Bowling Green", "FL", "USA", 27.6572, -81.9214),
        ("Erin Hills", "Erin", "WI", "USA", 43.2439, -88.3417),
        ("Shinnecock Hills Golf Club", "Southampton", "NY", "USA", 40.9040, -72.4415),
        ("Winged Foot — West Course", "Mamaroneck", "NY", "USA", 40.9583, -73.7500),
        ("Oakmont Country Club", "Oakmont", "PA", "USA", 40.5300, -79.8386),
        ("Muirfield Village Golf Club", "Dublin", "OH", "USA", 40.1408, -83.1650),
        ("Hazeltine National Golf Club", "Chaska", "MN", "USA", 44.8534, -93.6250),
        ("Congressional Country Club", "Bethesda", "MD", "USA", 39.0104, -77.1717),
        ("Merion Golf Club — East Course", "Ardmore", "PA", "USA", 40.0055, -75.3005),
        ("Riviera Country Club", "Pacific Palisades", "CA", "USA", 34.0475, -118.5069),
        ("Medinah Country Club — No. 3", "Medinah", "IL", "USA", 41.9736, -88.0525),
        ("Oak Hill Country Club — East Course", "Rochester", "NY", "USA", 43.1372, -77.5300),
        ("Bay Hill Club & Lodge", "Orlando", "FL", "USA", 28.4600, -81.5133),
        ("St Andrews Links — Old Course", "St Andrews", "Fife", "Scotland", 56.3438, -2.8010),
        ("Royal County Down Golf Club", "Newcastle", "County Down", "Northern Ireland", 54.2200, -5.8830),
        ("Old Head Golf Links", "Kinsale", "County Cork", "Ireland", 51.6083, -8.5361),
        ("Royal Melbourne Golf Club — West", "Black Rock", "VIC", "Australia", -37.9647, 145.0322),
    ]
    for name, city, region, country, lat, lng in catalog:
        try:
            await courses_col.insert_one({
                "id": str(uuid.uuid4()),
                "name": name,
                "city": city,
                "region": region,
                "country": country,
                "lat": lat,
                "lng": lng,
                "source": "seed",
                "created_at": now_iso(),
            })
        except Exception:
            continue
    return {"seeded": True, "users": len(demo_users), "rounds": len(demo_rounds), "courses": len(catalog)}


async def bootstrap_admin_from_env() -> None:
    seed_email = (os.environ.get("SEED_ADMIN_EMAIL") or "").strip().lower()
    seed_password = os.environ.get("SEED_ADMIN_PASSWORD") or ""
    seed_name = (os.environ.get("SEED_ADMIN_NAME") or "Admin").strip() or "Admin"
    if not (seed_email and seed_password):
        return
    try:
        existing = await users_col.find_one({"email": seed_email})
        if existing:
            logger.info(f"admin bootstrap: user already exists ({seed_email}), skipping")
            return
        if len(seed_password) < 8:
            logger.warning("admin bootstrap: SEED_ADMIN_PASSWORD must be >= 8 chars, skipping")
            return
        doc = {
            "id": str(uuid.uuid4()),
            "email": seed_email,
            "display_name": seed_name,
            "hashed_password": pwd_context.hash(seed_password),
            "handicap": None,
            "bio": None,
            "home_course": None,
            "avatar": None,
            "created_at": now_iso(),
        }
        await users_col.insert_one(doc)
        # Mutate the config-level set so the runtime admin check works without a restart.
        ADMIN_EMAILS.add(seed_email)
        config.ADMIN_EMAILS.add(seed_email)  # noqa: SLF001 — intentional runtime mutation
        logger.info(f"admin bootstrap: created initial admin user ({seed_email})")
    except Exception as e:
        logger.warning(f"admin bootstrap failed: {e}")


async def maybe_kick_auto_osm_import() -> None:
    if not AUTO_IMPORT_COURSES:
        return
    try:
        current = await courses_col.count_documents({})
        prior = await import_jobs_col.find_one(
            {"kind": "global", "status": "completed", "inserted": {"$gte": 200}},
            {"_id": 0, "id": 1, "inserted": 1},
        )
        if current < AUTO_IMPORT_THRESHOLD and not prior:
            tiles = country_tiles(tile=5)
            job_id = str(uuid.uuid4())
            await import_jobs_col.insert_one({
                "id": job_id,
                "kind": "global",
                "tile_deg": 5,
                "status": "queued",
                "total_tiles": len(tiles),
                "processed_tiles": 0,
                "inserted": 0,
                "errors": 0,
                "created_at": now_iso(),
                "triggered_by": "system:auto_import",
            })
            asyncio.create_task(run_import_job(job_id, tiles, delay_s=3.0))
            logger.info(
                f"auto-import kicked off: job_id={job_id} tiles={len(tiles)} "
                f"(current courses={current}, threshold={AUTO_IMPORT_THRESHOLD})"
            )
        else:
            logger.info(
                f"auto-import skipped: current_courses={current} "
                f"threshold={AUTO_IMPORT_THRESHOLD} prior_completed={bool(prior)}"
            )
    except Exception as e:
        logger.warning(f"auto-import kickoff failed: {e}")
