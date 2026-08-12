"""OpenGolfAPI integration — free, keyless golf course data (32,700+ US courses).

Read-only client used to power nationwide course search and rich course detail
(tees, hole-by-hole yardages, climate, insights) on top of our own MongoDB
course catalog. All ``courses/*`` reads on OpenGolfAPI are keyless; an optional
``OPENGOLF_API_KEY`` env var raises the daily rate ceiling but is never
required. Every call here is best-effort — network errors, timeouts and
non-2xx responses are swallowed and logged so a slow/unreachable upstream
never breaks discovery for data we already have cached locally.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("OPENGOLF_API_BASE", "https://api.opengolfapi.org/api/v1")
API_KEY = os.environ.get("OPENGOLF_API_KEY", "")


def _headers() -> dict:
    return {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}


async def _get(path: str, params: Optional[dict] = None, timeout: float = 8.0) -> Optional[dict]:
    url = f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params, headers=_headers())
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            logger.warning(f"opengolfapi GET {path} -> {resp.status_code}")
            return None
        return resp.json()
    except Exception as e:  # noqa: BLE001 — never let upstream flakiness bubble up
        logger.warning(f"opengolfapi GET {path} failed: {e}")
        return None


async def search_courses(
    q: str = "",
    state: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_mi: Optional[float] = None,
    limit: int = 20,
) -> list:
    """Nationwide course search by name and/or geo-radius.

    Returns a list of ``CourseCompact`` dicts:
    ``{id, course_name, city, state, country_iso, lat, lng, type, par, holes}``
    (``holes`` here is the hole *count*, not hole detail).
    """
    params: dict = {"limit": limit}
    if q:
        params["q"] = q
    if state:
        params["state"] = state
    if lat is not None and lng is not None:
        params["lat"] = lat
        params["lng"] = lng
        if radius_mi:
            params["radius_mi"] = radius_mi
    data = await _get("courses/search", params)
    if not data:
        return []
    return data.get("courses") or []


async def get_course_detail(course_id: str) -> Optional[dict]:
    """Full course detail in a single call — already embeds ``tees``,
    ``holes_data`` (hole-by-hole par/yardage/handicap) and ``climate``, so no
    extra round-trips are needed to enrich a course record."""
    return await _get(f"courses/{course_id}")
