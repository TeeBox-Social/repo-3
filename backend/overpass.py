"""OpenStreetMap Overpass API integration for bulk course imports.

Exposes the ``run_import_job`` background task, country bounding boxes and the
tile helpers used by the admin router.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import HTTPException

from db import courses_col, import_jobs_col
from helpers import now_iso

logger = logging.getLogger(__name__)

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Country bounding boxes: south, west, north, east
COUNTRY_BBOXES: dict = {
    "US":   (24.5, -125.0, 49.5, -66.5),
    "AK":   (54.0, -170.0, 71.5, -130.0),
    "HI":   (18.5, -161.0, 22.5, -154.5),
    "CA":   (41.5, -141.0, 60.0, -52.5),
    "MX":   (14.5, -118.5, 32.7, -86.5),
    "UK":   (49.5, -8.5, 60.9, 1.8),
    "IE":   (51.4, -10.6, 55.5, -5.9),
    "FR":   (41.0, -5.5, 51.5, 9.7),
    "DE":   (47.2, 5.8, 55.1, 15.1),
    "ES":   (35.9, -9.5, 43.9, 4.4),
    "PT":   (36.9, -9.6, 42.2, -6.0),
    "IT":   (36.6, 6.6, 47.1, 18.6),
    "NL":   (50.7, 3.3, 53.6, 7.3),
    "BE":   (49.5, 2.5, 51.6, 6.5),
    "CH":   (45.8, 5.9, 47.9, 10.5),
    "AT":   (46.3, 9.5, 49.1, 17.2),
    "SE":   (55.3, 10.9, 69.1, 24.2),
    "NO":   (57.9, 4.6, 71.2, 31.3),
    "DK":   (54.5, 8.0, 57.8, 15.2),
    "FI":   (59.7, 20.5, 70.1, 31.6),
    "AU":   (-44.0, 112.0, -10.0, 154.0),
    "NZ":   (-47.3, 166.3, -34.4, 178.6),
    "JP":   (30.9, 129.4, 45.6, 145.9),
    "KR":   (33.1, 125.9, 38.6, 129.6),
    "CN":   (18.0, 73.5, 53.6, 134.8),
    "TH":   (5.6, 97.3, 20.5, 105.7),
    "SG":   (1.2, 103.6, 1.5, 104.1),
    "IN":   (6.5, 68.1, 35.5, 97.4),
    "AE":   (22.6, 51.5, 26.1, 56.4),
    "ZA":   (-35.0, 16.4, -22.1, 32.9),
    "BR":   (-33.8, -73.9, 5.3, -34.8),
    "AR":   (-55.1, -73.6, -21.8, -53.6),
    "CL":   (-55.9, -75.6, -17.5, -66.9),
    "MA":   (27.7, -13.2, 35.9, -1.0),
    "TR":   (35.8, 25.7, 42.1, 44.8),
}


def overpass_query(south: float, west: float, north: float, east: float, timeout: int = 60) -> str:
    return f"""
    [out:json][timeout:{timeout}];
    (
      node["leisure"="golf_course"]({south},{west},{north},{east});
      way["leisure"="golf_course"]({south},{west},{north},{east});
      relation["leisure"="golf_course"]({south},{west},{north},{east});
    );
    out center tags;
    """


async def overpass_fetch(query: str, timeout: float = 90.0) -> dict:
    """Try each Overpass mirror; raise 502 on all-failed."""
    import httpx
    headers = {
        "User-Agent": "TeeBox/1.0 (+https://teebox.app; support@teebox.app)",
        "Accept": "application/json",
    }
    last_err: Optional[str] = None
    for url in OVERPASS_ENDPOINTS:
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers) as http:
                resp = await http.post(url, data={"data": query})
                if resp.status_code in (403, 406, 429) or resp.status_code >= 500:
                    last_err = f"{url} → {resp.status_code}"
                    continue
                resp.raise_for_status()
                return resp.json()
        except Exception as e:  # noqa: BLE001
            last_err = f"{url} → {e}"
            continue
    raise HTTPException(status_code=502, detail=f"OSM Overpass unreachable: {last_err}")


async def persist_osm_elements(elements: list) -> int:
    """Insert new courses from an Overpass elements payload; return count inserted.
    Idempotent — silently skips duplicates by name."""
    from pymongo.errors import DuplicateKeyError
    inserted = 0
    for el in elements or []:
        tags = el.get("tags", {}) or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        if await courses_col.find_one({"name": name}, {"_id": 1}):
            continue
        lat = el.get("lat") if el.get("type") == "node" else (el.get("center", {}) or {}).get("lat")
        lng = el.get("lon") if el.get("type") == "node" else (el.get("center", {}) or {}).get("lon")
        try:
            await courses_col.insert_one({
                "id": str(uuid.uuid4()),
                "name": name,
                "city": tags.get("addr:city"),
                "region": tags.get("addr:state") or tags.get("addr:region"),
                "country": tags.get("addr:country"),
                "lat": lat,
                "lng": lng,
                "source": "osm",
                "created_at": now_iso(),
            })
            inserted += 1
        except DuplicateKeyError:
            continue
    return inserted


def sweep_tiles(tile: int = 20) -> list:
    """Global sweep tiles covering the habitable lat range."""
    tiles = []
    for south in range(-60, 70, tile):
        for west in range(-180, 180, tile):
            tiles.append((float(south), float(west), float(south + tile), float(west + tile)))
    return tiles


def country_tiles(tile: int = 8) -> list:
    """All-countries sweep: iterate each country bbox and subdivide it."""
    tiles = []
    for _code, (south, west, north, east) in COUNTRY_BBOXES.items():
        lat = south
        while lat < north:
            lng = west
            while lng < east:
                tiles.append((lat, lng, min(lat + tile, north), min(lng + tile, east)))
                lng += tile
            lat += tile
    return tiles


async def run_import_job(job_id: str, tiles: list, delay_s: float = 2.0) -> None:
    """Background job: walks tiles, updates progress in Mongo. Supports cancellation."""
    total = len(tiles)
    processed = 0
    inserted_total = 0
    errors = 0
    try:
        await import_jobs_col.update_one(
            {"id": job_id},
            {"$set": {"status": "running", "total_tiles": total, "started_at": now_iso()}},
        )
        for (south, west, north, east) in tiles:
            latest = await import_jobs_col.find_one({"id": job_id}, {"_id": 0, "status": 1})
            if latest and latest.get("status") == "cancelled":
                logger.info(f"import job {job_id} cancelled at tile {processed}/{total}")
                break
            try:
                data = await overpass_fetch(overpass_query(south, west, north, east, timeout=45), timeout=60.0)
                inserted = await persist_osm_elements(data.get("elements", []))
                inserted_total += inserted
            except HTTPException as e:
                errors += 1
                logger.warning(f"import job {job_id} tile ({south},{west}) failed: {e.detail}")
            except Exception as e:  # noqa: BLE001
                errors += 1
                logger.warning(f"import job {job_id} tile ({south},{west}) failed: {e}")
            processed += 1
            await import_jobs_col.update_one(
                {"id": job_id},
                {"$set": {
                    "processed_tiles": processed,
                    "inserted": inserted_total,
                    "errors": errors,
                    "last_tile": {"south": south, "west": west, "north": north, "east": east},
                    "updated_at": now_iso(),
                }},
            )
            await asyncio.sleep(delay_s)
        total_courses = await courses_col.count_documents({})
        current = await import_jobs_col.find_one({"id": job_id}, {"_id": 0, "status": 1}) or {}
        final_status = "cancelled" if current.get("status") == "cancelled" else "completed"
        await import_jobs_col.update_one(
            {"id": job_id},
            {"$set": {
                "status": final_status,
                "finished_at": now_iso(),
                "total_courses_after": total_courses,
            }},
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"import job {job_id} crashed: {e}")
        await import_jobs_col.update_one(
            {"id": job_id},
            {"$set": {"status": "failed", "error": str(e)[:500], "finished_at": now_iso()}},
        )
