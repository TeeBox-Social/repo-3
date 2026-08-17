"""TeeBox FastAPI application entry point.

Kept intentionally slim (~80 lines) — this file only wires the app together.
All business logic lives in dedicated modules:

  * ``config``        env constants & feature flags
  * ``db``            Mongo client + collection handles
  * ``models``        Pydantic request/response schemas
  * ``security``      auth deps, JWT helpers, rate limiter
  * ``helpers``       pure utility helpers (achievements, notifications, geo)
  * ``overpass``      OpenStreetMap import machinery
  * ``routers/*``     endpoint groups (auth, rounds, users, courses, admin…)
  * ``startup_jobs``  index setup, demo seed, admin bootstrap, auto-import
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from starlette.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# Configure logging first so any import-time warnings land in the same stream.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from config import CORS_ORIGINS, ENABLE_DEMO_SEED  # noqa: E402
from db import client  # noqa: E402
from routers import admin as admin_router  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from routers import courses as courses_router  # noqa: E402
from routers import lfg as lfg_router  # noqa: E402
from routers import notifications as notifications_router  # noqa: E402
from routers import rounds as rounds_router  # noqa: E402
from routers import users as users_router  # noqa: E402
from security import get_current_user, limiter  # noqa: E402
from startup_jobs import (  # noqa: E402
    bootstrap_admin_from_env,
    ensure_indexes,
    heal_stale_import_jobs,
    maybe_kick_auto_osm_import,
    seed_demo_data,
)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# All app endpoints live under /api so the k8s ingress can route to us.
api_router = APIRouter(prefix="/api")

# Order matters only for OpenAPI grouping — routes themselves are all distinct.
api_router.include_router(auth_router.router)
api_router.include_router(rounds_router.router)
api_router.include_router(lfg_router.router)
api_router.include_router(users_router.router)
api_router.include_router(courses_router.router)
api_router.include_router(notifications_router.router)
api_router.include_router(admin_router.router)


# ---- Demo seed endpoint (kept here because it's a one-shot bootstrap route) ----
@api_router.post("/seed")
async def seed_endpoint():
    # SEC-005: never callable when demo seeding is disabled.
    if not ENABLE_DEMO_SEED:
        raise HTTPException(status_code=404, detail="Not found")
    return await seed_demo_data()


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    await heal_stale_import_jobs()
    if ENABLE_DEMO_SEED:
        try:
            result = await seed_demo_data()
            if result.get("seeded"):
                logger.info("Auto-seeded demo data (ENABLE_DEMO_SEED=true)")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"seed failed: {e}")
    await bootstrap_admin_from_env()
    await maybe_kick_auto_osm_import()


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# ``get_current_user`` referenced here so linters know the import is intentional
# (the dep is exported for use by any router that needs it at import time).
_ = Depends(get_current_user)
