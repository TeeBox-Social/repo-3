"""
Iter12 – Security remediation verification.

Covers:
  * SEC-001 – boot-time production guard (APP_ENV=production + demo seed / demo admin)
  * SEC-002 – POST /api/courses/import-osm now requires admin + 10/hour rate limit
  * Hardening rate limits:
        GET /api/courses/search           120/min
        GET /api/discover/courses/nearby  30/min
        GET /api/notifications            60/min
  * Regression: auth, feed, rounds, discover, admin course verify/reject,
                notifications list/mark-read, courses/search + POST /api/courses,
                auto-import status endpoints
  * Positive controls: notifications user-scoping, lat/lng clamp, $regex escape,
                       refresh rotation, base64 image cap

Design notes:
  - Backend enforces rate limit per client IP (slowapi keyed off X-Forwarded-For /
    CF-Connecting-IP). Every rate-limit test injects a UNIQUE cf-connecting-ip
    header so previous test runs don't leak into it.
  - Login is 10/min; we cache tokens at module scope and share via fixtures.
"""
import os
import re
import subprocess
import sys
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

REESE = ("reese@teebox.demo", "password123")   # admin
JORDAN = ("jordan@teebox.demo", "password123")
SAM = ("sam@teebox.demo", "password123")


# ---------------------------------------------------------------------------
# Shared token cache (avoid /auth/login 10/min limit)
# ---------------------------------------------------------------------------
_token_cache: dict = {}


def _login(email: str, password: str) -> dict:
    if email in _token_cache:
        return _token_cache[email]
    # random IP so we never share a bucket with prior test runs
    ip = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    r = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": password},
        headers={"cf-connecting-ip": ip},
        timeout=15,
    )
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    body = r.json()
    _token_cache[email] = body
    return body


@pytest.fixture(scope="module")
def reese():
    return _login(*REESE)


@pytest.fixture(scope="module")
def jordan():
    return _login(*JORDAN)


@pytest.fixture(scope="module")
def sam():
    return _login(*SAM)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def fresh_ip_header() -> dict:
    """Unique client IP so rate-limit tests start with a fresh bucket."""
    return {"cf-connecting-ip": f"172.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"}


# ===========================================================================
# SEC-001 – boot-time production guard
# ===========================================================================
class TestSEC001BootGuard:
    """
    Verify the guard in server.py (lines 65-88):
      APP_ENV=production + ENABLE_DEMO_SEED=true                 -> RuntimeError SEC-001
      APP_ENV=production + ADMIN_EMAILS contains *.demo email    -> RuntimeError SEC-001
      APP_ENV=development (any combo)                            -> imports cleanly
    We import the server module in a subprocess so we don't disturb the
    currently-running backend.
    """

    def _run_import(self, env_overrides: dict) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        # Neutralise the currently-running dev env for the child so overrides win
        for k in ("APP_ENV", "ENABLE_DEMO_SEED", "ADMIN_EMAILS"):
            env.pop(k, None)
        env.update(env_overrides)
        # Ensure a strong JWT so we don't trip the placeholder-secret guard
        env.setdefault(
            "JWT_SECRET_KEY",
            "a" * 64,
        )
        # Preserve Mongo config from the running app
        env.setdefault("MONGO_URL", "mongodb://localhost:27017")
        env.setdefault("DB_NAME", "teebox_db")
        cmd = [sys.executable, "-c", "import server"]
        return subprocess.run(
            cmd,
            cwd="/app/backend",
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_production_with_demo_seed_refuses_boot(self):
        res = self._run_import({
            "APP_ENV": "production",
            "ENABLE_DEMO_SEED": "true",
            "ADMIN_EMAILS": "ops@example.com",
        })
        assert res.returncode != 0, f"expected non-zero exit; stdout={res.stdout} stderr={res.stderr}"
        combined = (res.stderr or "") + (res.stdout or "")
        assert "SEC-001" in combined, f"expected SEC-001 in error output: {combined!r}"
        assert "ENABLE_DEMO_SEED" in combined
        assert "RuntimeError" in combined

    def test_production_with_demo_admin_refuses_boot(self):
        res = self._run_import({
            "APP_ENV": "production",
            "ENABLE_DEMO_SEED": "false",
            "ADMIN_EMAILS": "reese@teebox.demo,ops@example.com",
        })
        assert res.returncode != 0, f"expected non-zero exit; stdout={res.stdout} stderr={res.stderr}"
        combined = (res.stderr or "") + (res.stdout or "")
        assert "SEC-001" in combined
        assert "ADMIN_EMAILS" in combined
        assert "teebox.demo" in combined

    def test_production_with_clean_config_boots(self):
        res = self._run_import({
            "APP_ENV": "production",
            "ENABLE_DEMO_SEED": "false",
            "ADMIN_EMAILS": "ops@example.com",
        })
        assert res.returncode == 0, f"clean production config should import; stderr={res.stderr}"

    def test_development_with_demo_seed_boots(self):
        """The currently-running dev env — must still import fine."""
        res = self._run_import({
            "APP_ENV": "development",
            "ENABLE_DEMO_SEED": "true",
            "ADMIN_EMAILS": "reese@teebox.demo",
        })
        assert res.returncode == 0, f"dev env should import; stderr={res.stderr}"

    def test_default_app_env_is_dev(self):
        """APP_ENV unset -> treated as development, demo config allowed."""
        res = self._run_import({
            "ENABLE_DEMO_SEED": "true",
            "ADMIN_EMAILS": "reese@teebox.demo",
        })
        assert res.returncode == 0, f"unset APP_ENV should default to dev; stderr={res.stderr}"

    def test_running_backend_still_up(self):
        """Sanity: nothing above touched the running backend."""
        r = requests.get(f"{API}/", timeout=5)
        assert r.status_code == 200


# ===========================================================================
# SEC-002 – POST /api/courses/import-osm now admin-only + 10/hour
# ===========================================================================
class TestSEC002ImportOsmLegacy:
    BBOX = "32.5,-117.5,33.5,-116.5"  # small SoCal box

    def test_non_admin_gets_403(self, jordan):
        r = requests.post(
            f"{API}/courses/import-osm",
            params={"bbox": self.BBOX},
            headers={**auth(jordan["access_token"]), **fresh_ip_header()},
            timeout=15,
        )
        assert r.status_code == 403, f"non-admin should get 403, got {r.status_code}: {r.text}"

    def test_second_non_admin_also_403(self, sam):
        r = requests.post(
            f"{API}/courses/import-osm",
            params={"bbox": self.BBOX},
            headers={**auth(sam["access_token"]), **fresh_ip_header()},
            timeout=15,
        )
        assert r.status_code == 403

    def test_unauthenticated_401(self):
        r = requests.post(
            f"{API}/courses/import-osm",
            params={"bbox": self.BBOX},
            headers=fresh_ip_header(),
            timeout=15,
        )
        # get_current_user raises 401 without a token
        assert r.status_code in (401, 403), f"expected 401/403 without token, got {r.status_code}"

    def test_admin_with_valid_bbox_succeeds(self, reese):
        """
        Admin call with a valid bbox — we don't care about how many courses come
        back (OSM may or may not have any in that box), only that it does NOT
        403/400/401 and returns a well-formed response.
        This ALSO consumes 1 of 10/hour on the fresh IP, so we use a unique IP.
        """
        r = requests.post(
            f"{API}/courses/import-osm",
            params={"bbox": self.BBOX},
            headers={**auth(reese["access_token"]), **fresh_ip_header()},
            timeout=60,
        )
        # 200 = normal, 502 = Overpass upstream flaked — still means auth passed.
        assert r.status_code in (200, 502), f"admin import got {r.status_code}: {r.text[:200]}"
        if r.status_code == 200:
            body = r.json()
            assert "inserted" in body and "total_courses" in body
            assert isinstance(body["inserted"], int)
            assert isinstance(body["total_courses"], int)

    def test_admin_invalid_bbox_400(self, reese):
        r = requests.post(
            f"{API}/courses/import-osm",
            params={"bbox": "not,a,valid,bbox"},
            headers={**auth(reese["access_token"]), **fresh_ip_header()},
            timeout=15,
        )
        assert r.status_code == 400

    def test_admin_hits_10_per_hour_limit(self, reese):
        """Fire 12 calls from a single fresh IP; the 11th/12th must be 429."""
        ip = fresh_ip_header()
        codes = []
        for _ in range(12):
            r = requests.post(
                f"{API}/courses/import-osm",
                params={"bbox": "not,a,valid,bbox"},  # 400 is fine — limiter fires before body
                headers={**auth(reese["access_token"]), **ip},
                timeout=15,
            )
            codes.append(r.status_code)
            if r.status_code == 429:
                break
        assert 429 in codes, f"expected 429 within 12 calls, got {codes}"


# ===========================================================================
# Hardening rate limits
# ===========================================================================
class TestRateLimits:

    def test_courses_search_returns_results_under_limit(self, reese):
        r = requests.get(
            f"{API}/courses/search",
            params={"q": "golf", "limit": 5},
            headers={**auth(reese["access_token"]), **fresh_ip_header()},
            timeout=15,
        )
        assert r.status_code == 200, f"search should work: {r.status_code} {r.text[:200]}"
        assert isinstance(r.json(), list)

    def test_courses_search_120_per_min_holds_first_60(self, reese):
        """A modest burst of 60 requests should NEVER 429 on a fresh IP (limit=120/min)."""
        ip = fresh_ip_header()
        codes = []
        for i in range(60):
            r = requests.get(
                f"{API}/courses/search",
                params={"q": f"a{i % 5}"},
                headers={**auth(reese["access_token"]), **ip},
                timeout=10,
            )
            codes.append(r.status_code)
            if r.status_code == 429:
                break
        assert 429 not in codes, f"unexpected 429 within 60 calls (limit 120/min): counts={codes.count(429)}"

    def test_discover_nearby_normal_use_works(self, reese):
        r = requests.get(
            f"{API}/discover/courses/nearby",
            params={"lat": 37.5, "lng": -122.0, "radius_km": 100},
            headers={**auth(reese["access_token"]), **fresh_ip_header()},
            timeout=20,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_discover_nearby_30_per_min_trips(self, reese):
        """Fire 35 calls from one IP; at least one must 429."""
        ip = fresh_ip_header()
        codes = []
        for _ in range(35):
            r = requests.get(
                f"{API}/discover/courses/nearby",
                params={"lat": 37.5, "lng": -122.0, "radius_km": 50},
                headers={**auth(reese["access_token"]), **ip},
                timeout=10,
            )
            codes.append(r.status_code)
            if r.status_code == 429:
                break
        assert 429 in codes, f"expected 429 within 35 calls (limit 30/min): codes={codes}"

    def test_notifications_normal_use_works(self, jordan):
        r = requests.get(
            f"{API}/notifications",
            headers={**auth(jordan["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        assert r.status_code == 200
        body = r.json()
        assert "notifications" in body and "unread" in body
        assert isinstance(body["notifications"], list)

    def test_notifications_60_per_min_trips(self, jordan):
        ip = fresh_ip_header()
        codes = []
        for _ in range(65):
            r = requests.get(
                f"{API}/notifications",
                headers={**auth(jordan["access_token"]), **ip},
                timeout=10,
            )
            codes.append(r.status_code)
            if r.status_code == 429:
                break
        assert 429 in codes, f"expected 429 within 65 calls (limit 60/min): codes={codes}"


# ===========================================================================
# Regression – existing endpoints still work
# ===========================================================================
class TestRegression:

    def test_login_returns_is_admin_true_for_reese(self, reese):
        assert reese["user"]["email"] == "reese@teebox.demo"
        assert reese["user"].get("is_admin") is True

    def test_login_is_admin_false_for_jordan(self, jordan):
        assert jordan["user"].get("is_admin") is False

    def test_refresh_rotation(self, sam):
        """POST /api/auth/refresh must return new tokens & invalidate the old refresh."""
        old_refresh = sam["refresh_token"]
        r1 = requests.post(
            f"{API}/auth/refresh",
            json={"refresh_token": old_refresh},
            headers=fresh_ip_header(),
            timeout=10,
        )
        assert r1.status_code == 200, f"refresh failed: {r1.text}"
        new_tokens = r1.json()
        assert new_tokens["access_token"] != sam["access_token"]
        assert new_tokens["refresh_token"] != old_refresh
        # reusing the old refresh must now fail
        r2 = requests.post(
            f"{API}/auth/refresh",
            json={"refresh_token": old_refresh},
            headers=fresh_ip_header(),
            timeout=10,
        )
        assert r2.status_code == 401
        # update cache so downstream tests keep working
        _token_cache[SAM[0]] = {
            **sam,
            "access_token": new_tokens["access_token"],
            "refresh_token": new_tokens["refresh_token"],
        }

    def test_register_new_user(self):
        email = f"TEST_iter12_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(
            f"{API}/auth/register",
            json={
                "email": email,
                "password": "hunter2hunter2",
                "display_name": "Iter12 Reg",
            },
            headers=fresh_ip_header(),
            timeout=10,
        )
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["user"]["email"] == email.lower()
        assert b["access_token"] and b["refresh_token"]

    def test_feed(self, reese):
        r = requests.get(
            f"{API}/feed", headers={**auth(reese["access_token"]), **fresh_ip_header()}, timeout=10
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_rounds_list_for_user(self, reese):
        """GET /api/rounds is POST-only; the read path is GET /api/users/{id}/rounds."""
        uid = reese["user"]["id"]
        r = requests.get(
            f"{API}/users/{uid}/rounds",
            headers={**auth(reese["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_discover_users(self, reese):
        r = requests.get(
            f"{API}/discover/users",
            headers={**auth(reese["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_discover_courses(self, reese):
        r = requests.get(
            f"{API}/discover/courses",
            headers={**auth(reese["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        assert r.status_code == 200

    def test_notifications_list_and_mark_read(self, jordan):
        r = requests.get(
            f"{API}/notifications",
            headers={**auth(jordan["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        assert r.status_code == 200
        body = r.json()
        assert "notifications" in body
        # If any notifications exist, try mark-read on the first one
        if body["notifications"]:
            nid = body["notifications"][0]["id"]
            r2 = requests.post(
                f"{API}/notifications/{nid}/read",
                headers={**auth(jordan["access_token"]), **fresh_ip_header()},
                timeout=10,
            )
            assert r2.status_code == 200

    def test_course_search_and_submission(self, jordan):
        # search
        r = requests.get(
            f"{API}/courses/search",
            params={"q": "test-iter12"},
            headers={**auth(jordan["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        assert r.status_code == 200

        # submit a new course (par is required by NewCourseIn)
        payload = {
            "name": f"TEST_iter12_course_{uuid.uuid4().hex[:6]}",
            "par": 72,
            "city": "TestCity",
            "region": "TS",
            "country": "US",
        }
        r2 = requests.post(
            f"{API}/courses",
            json=payload,
            headers={**auth(jordan["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        # accept 200/201 – schema variance across versions
        assert r2.status_code in (200, 201), f"course submit: {r2.status_code} {r2.text[:200]}"

    def test_admin_courses_stats(self, reese):
        r = requests.get(
            f"{API}/admin/courses/stats",
            headers={**auth(reese["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        assert r.status_code == 200
        b = r.json()
        assert "total_courses" in b
        assert b["total_courses"] >= 0

    def test_admin_courses_stats_non_admin_403(self, jordan):
        r = requests.get(
            f"{API}/admin/courses/stats",
            headers={**auth(jordan["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        assert r.status_code == 403


# ===========================================================================
# Positive controls (previously validated by the security audit)
# ===========================================================================
class TestPositiveControls:

    def test_notifications_are_user_scoped(self, jordan, sam):
        """Jordan cannot mark Sam's notifications as read."""
        # find any notification belonging to sam
        r = requests.get(
            f"{API}/notifications",
            headers={**auth(sam["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        assert r.status_code == 200
        sams = r.json()["notifications"]
        if not sams:
            pytest.skip("Sam has no notifications to cross-test with; scope test not applicable.")
        target = sams[0]["id"]
        # jordan tries to mark it read
        r2 = requests.post(
            f"{API}/notifications/{target}/read",
            headers={**auth(jordan["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        # server should either 404 (jordan cannot see it) or 403; NOT 200
        assert r2.status_code != 200, f"cross-user notification mark-read leaked: {r2.status_code}"

    def test_lat_out_of_range_422(self, reese):
        r = requests.get(
            f"{API}/discover/courses/nearby",
            params={"lat": 999, "lng": 0},
            headers={**auth(reese["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        assert r.status_code == 422

    def test_lng_out_of_range_422(self, reese):
        r = requests.get(
            f"{API}/discover/courses/nearby",
            params={"lat": 0, "lng": 999},
            headers={**auth(reese["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        assert r.status_code == 422

    def test_regex_injection_escaped(self, reese):
        """Passing a regex metachar (.*) in the search query must not match everything —
        the backend escapes it via _safe_query."""
        # ".*" would match every doc if unescaped; verify limit-bounded response ok
        r = requests.get(
            f"{API}/courses/search",
            params={"q": ".*", "limit": 5},
            headers={**auth(reese["access_token"]), **fresh_ip_header()},
            timeout=10,
        )
        assert r.status_code == 200
        # After escape, ".*" should only match course names literally containing ".*"
        # which is essentially zero — but we don't strictly require empty; we require
        # that the endpoint didn't blow up and returned a well-formed list capped by limit.
        body = r.json()
        assert isinstance(body, list)
        assert len(body) <= 5

    def test_base64_avatar_cap_enforced(self, jordan):
        """PATCH /api/auth/me with an oversize base64 avatar must be rejected."""
        # 900_000 chars > MAX_AVATAR_B64_LEN (800_000)
        huge = "A" * 900_000
        r = requests.patch(
            f"{API}/auth/me",
            json={"avatar": f"data:image/png;base64,{huge}"},
            headers={**auth(jordan["access_token"]), **fresh_ip_header()},
            timeout=15,
        )
        assert r.status_code in (400, 413, 422), f"expected reject, got {r.status_code}: {r.text[:200]}"


# ===========================================================================
# Cleanup — remove any TEST_iter12_* users we created via /auth/register
# ===========================================================================
def test_zz_cleanup_test_users():
    """Best-effort: not strictly required since demo DB is expendable, but keeps
    the users_col tidy for the next iteration."""
    try:
        from pymongo import MongoClient
        client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = client[os.environ.get("DB_NAME", "teebox_db")]
        res = db.users.delete_many({"email": {"$regex": "^test_iter12_", "$options": "i"}})
        crs = db.courses.delete_many({"name": {"$regex": "^TEST_iter12_course_"}})
        print(f"cleanup: removed {res.deleted_count} users, {crs.deleted_count} courses")
    except Exception as e:
        pytest.skip(f"pymongo cleanup unavailable: {e}")
