"""Iter10 backend tests: verify post-security-audit remediation.

Coverage:
  SEC-102: PATCH /api/auth/me validation caps (display_name/bio/handicap/home_course).
  SEC-102-friend-guard: /users/{id}/friends survives poisoned null display_name.
  P3 wishlist cap (200) -> 413.
  P3 atomic refresh rotation (concurrent refresh -> one wins, family revoked).
  Regressions: register/login, refresh happy path, logout, wishlist add/dup/delete/check,
               pin/unpin owner-only, friends shape+sort, /users/{id} 4-stat row,
               PATCH null-clear for handicap/bio/home_course/avatar, avatar 413.
"""
import os
import asyncio
import base64
import uuid
import pytest
import requests
import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL"))
assert BASE_URL, "backend URL missing"
BASE_URL = BASE_URL.rstrip("/")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

PASS = "password123"


# ---------- helpers ----------
def _login(email: str) -> dict:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PASS}, timeout=20)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return r.json()


def _hdr(auth):
    return {"Authorization": f"Bearer {auth['access_token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def reese():
    return _login("reese@teebox.demo")


@pytest.fixture(scope="module")
def jordan():
    return _login("jordan@teebox.demo")


@pytest.fixture(scope="module")
def sam():
    return _login("sam@teebox.demo")


@pytest.fixture(autouse=True)
def _restore_reese(reese):
    """Restore Reese seed defaults after each test to keep state clean."""
    yield
    seed = {
        "display_name": "Reese Callahan",
        "home_course": "Pebble Meadows GC",
        "handicap": 8.4,
        "bio": "Weekend warrior. Always chasing the sunrise tee time.",
        "avatar": None,
    }
    try:
        requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese), json=seed, timeout=10)
    except Exception:
        pass


# ---------- SEC-102: display_name validation ----------
class TestSEC102DisplayName:
    def test_empty_display_name_422(self, reese):
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese), json={"display_name": ""})
        assert r.status_code == 422, f"expected 422 got {r.status_code} {r.text}"

    def test_null_display_name_no_clear(self, reese):
        # null must not clear display_name (min_length=1). Server should either 422 or
        # ignore (leave existing). Either way GET must show non-empty display_name.
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese), json={"display_name": None})
        assert r.status_code in (200, 422), f"unexpected status {r.status_code}"
        g = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(reese))
        assert g.status_code == 200
        name = g.json().get("display_name")
        assert isinstance(name, str) and len(name) >= 1, f"display_name got cleared/null: {name!r}"

    def test_too_long_display_name_422(self, reese):
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese), json={"display_name": "x" * 60})
        assert r.status_code == 422

    def test_normal_display_name_ok(self, reese):
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese), json={"display_name": "Reese Callahan"})
        assert r.status_code == 200
        assert r.json()["display_name"] == "Reese Callahan"


# ---------- SEC-102: friends endpoint defensive .lower() guard ----------
class TestSEC102FriendsGuard:
    @pytest.mark.asyncio
    async def test_friends_survives_null_display_name(self, reese):
        """Insert a poisoned user with display_name=None, make it mutually follow reese,
        then hit GET /users/{reese_id}/friends. Must be 200 (no 500 from .lower())."""
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(reese)).json()
        reese_id = me["id"]
        poison_id = f"TEST_iter10_poison_{uuid.uuid4().hex[:8]}"
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        try:
            await db.users.insert_one({
                "id": poison_id,
                "email": f"TEST_iter10_{poison_id}@teebox.dev",
                "display_name": None,
                "home_course": "",
                "handicap": None,
                "bio": None,
                "avatar": None,
                "hashed_password": "$2b$12$abcdefghijklmnopqrstuv",
                "created_at": "2026-01-01T00:00:00+00:00",
            })
            await db.follows.insert_one({"user_id": reese_id, "target_id": poison_id})
            await db.follows.insert_one({"user_id": poison_id, "target_id": reese_id})

            r = requests.get(f"{BASE_URL}/api/users/{reese_id}/friends", headers=_hdr(reese))
            assert r.status_code == 200, f"expected 200 got {r.status_code} {r.text[:200]}"
            names = [f.get("display_name") for f in r.json()]
            # poison user should be present (its display_name None or missing) but no crash
            ids = [f.get("id") for f in r.json()]
            assert poison_id in ids
        finally:
            await db.follows.delete_many({"$or": [{"user_id": poison_id}, {"target_id": poison_id}]})
            await db.users.delete_one({"id": poison_id})
            client.close()


# ---------- SEC-102: other field caps ----------
class TestSEC102OtherCaps:
    def test_bio_too_long_422(self, reese):
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese), json={"bio": "x" * 281})
        assert r.status_code == 422

    def test_handicap_high_422(self, reese):
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese), json={"handicap": 100})
        assert r.status_code == 422

    def test_handicap_low_422(self, reese):
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese), json={"handicap": -20})
        assert r.status_code == 422

    def test_home_course_too_long_422(self, reese):
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese), json={"home_course": "x" * 121})
        assert r.status_code == 422

    def test_normal_values_ok(self, reese):
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese),
                           json={"bio": "short bio", "handicap": 10.2, "home_course": "Test Course"})
        assert r.status_code == 200
        body = r.json()
        assert body["bio"] == "short bio"
        assert body["handicap"] == 10.2
        assert body["home_course"] == "Test Course"


# ---------- P3 wishlist cap ----------
class TestWishlistCap:
    @pytest.fixture
    def fresh_user(self):
        """Register a throwaway user for cap test (avoids polluting demo accounts)."""
        email = f"TEST_iter10_wish_{uuid.uuid4().hex[:8]}@teebox.dev"
        rr = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": email, "password": PASS, "display_name": "TEST Wish"
        })
        assert rr.status_code == 200, rr.text
        auth = rr.json()
        yield auth
        # cleanup wishlist via API (delete anything left)
        pass  # DB TTL/cleanup not critical

    def test_cap_and_regressions(self, fresh_user):
        hdr = _hdr(fresh_user)
        # 1) add up to 200 quickly
        for i in range(200):
            r = requests.post(f"{BASE_URL}/api/wishlist", headers=hdr,
                              json={"course_name": f"TEST_i10_c{i:03d}"})
            assert r.status_code == 200, f"add {i} failed: {r.status_code} {r.text[:200]}"
        # 2) 201st -> 413
        r = requests.post(f"{BASE_URL}/api/wishlist", headers=hdr,
                          json={"course_name": "TEST_i10_c200"})
        assert r.status_code == 413, f"expected 413 got {r.status_code} {r.text[:200]}"

        # 3) duplicate returns added:false
        r = requests.post(f"{BASE_URL}/api/wishlist", headers=hdr,
                          json={"course_name": "TEST_i10_c000"})
        # already-cap path currently returns 413 before dedup check. Accept either
        # 413 (cap enforced before dedup) or 200+added:false.
        assert r.status_code in (200, 413)

        # 4) delete existing -> removed True
        r = requests.delete(f"{BASE_URL}/api/wishlist/TEST_i10_c000", headers=hdr)
        assert r.status_code == 200 and r.json()["removed"] is True

        # 5) check endpoint reflects removal
        r = requests.get(f"{BASE_URL}/api/wishlist/check/TEST_i10_c000", headers=hdr)
        assert r.status_code == 200 and r.json()["on_wishlist"] is False

        # 6) re-add now works (we're back under 200)
        r = requests.post(f"{BASE_URL}/api/wishlist", headers=hdr,
                          json={"course_name": "TEST_i10_c000"})
        assert r.status_code == 200 and r.json()["added"] is True

        # 7) duplicate -> added:false
        r = requests.post(f"{BASE_URL}/api/wishlist", headers=hdr,
                          json={"course_name": "TEST_i10_c000"})
        # We're at cap again — accept 413 or 200+added:false. If under cap, must be added:false.
        assert r.status_code in (200, 413)
        if r.status_code == 200:
            assert r.json()["added"] is False


# ---------- P3 atomic refresh rotation ----------
class TestRefreshAtomic:
    def test_concurrent_refresh_one_winner_family_revoked(self, sam):
        # Use sam (independent of other tests) so we don't clobber reese/jordan sessions.
        refresh_token = sam["refresh_token"]

        async def _hit():
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=20) as c:
                return await c.post("/api/auth/refresh", json={"refresh_token": refresh_token})

        async def _run_both():
            return await asyncio.gather(_hit(), _hit(), return_exceptions=True)

        results = asyncio.run(_run_both())
        statuses = sorted([r.status_code for r in results if hasattr(r, "status_code")])
        assert len(statuses) == 2, f"expected 2 http results, got {results}"
        # Exactly one 200, one 401
        assert statuses == [200, 401], f"expected [200,401] got {statuses}"

        # Find the 401 response and confirm reuse-detected message
        for r in results:
            if r.status_code == 401:
                assert "reuse" in r.text.lower() or "recognised" in r.text.lower()

        # After reuse-detection the whole family should be revoked; the new refresh_token
        # from the winner is *also* revoked because the loser triggers family-wide revoke.
        winner = next(r for r in results if r.status_code == 200)
        new_refresh = winner.json()["refresh_token"]
        r3 = requests.post(f"{BASE_URL}/api/auth/refresh", json={"refresh_token": new_refresh})
        assert r3.status_code == 401, f"family should be revoked, got {r3.status_code}"


# ---------- Regressions ----------
class TestRegressions:
    def test_register_login(self):
        email = f"TEST_iter10_reg_{uuid.uuid4().hex[:8]}@teebox.dev"
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": email, "password": PASS, "display_name": "TEST Reg"
        })
        assert r.status_code == 200
        assert "access_token" in r.json()
        r2 = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PASS})
        assert r2.status_code == 200

    def test_refresh_happy_path(self, jordan):
        r = requests.post(f"{BASE_URL}/api/auth/refresh", json={"refresh_token": jordan["refresh_token"]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["access_token"] and body["refresh_token"] != jordan["refresh_token"]
        # update jordan token pair so subsequent tests use the fresh one
        jordan["access_token"] = body["access_token"]
        jordan["refresh_token"] = body["refresh_token"]

    def test_logout(self):
        # register a temp user so we don't kill demo account sessions
        email = f"TEST_iter10_logout_{uuid.uuid4().hex[:8]}@teebox.dev"
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": email, "password": PASS, "display_name": "TEST Logout"
        })
        auth = r.json()
        r2 = requests.post(f"{BASE_URL}/api/auth/logout", json={"refresh_token": auth["refresh_token"]})
        assert r2.status_code == 200 and r2.json()["ok"] is True
        # refresh should now fail
        r3 = requests.post(f"{BASE_URL}/api/auth/refresh", json={"refresh_token": auth["refresh_token"]})
        assert r3.status_code == 401

    def test_friends_shape_and_sort(self, reese):
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(reese)).json()
        r = requests.get(f"{BASE_URL}/api/users/{me['id']}/friends", headers=_hdr(reese))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for f in data:
            for k in ("id", "display_name", "is_friend", "is_following", "round_count"):
                assert k in f, f"friend missing key {k}: {f}"
        # sort: friends first
        seen_non_friend = False
        for f in data:
            if not f["is_friend"]:
                seen_non_friend = True
            elif seen_non_friend:
                pytest.fail("sort broken: friend after non-friend")

    def test_user_profile_4stats(self, reese):
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=_hdr(reese)).json()
        r = requests.get(f"{BASE_URL}/api/users/{me['id']}", headers=_hdr(reese))
        assert r.status_code == 200
        body = r.json()
        for k in ("round_count", "avg_score", "courses_played", "friends_count"):
            assert k in body, f"profile missing stat {k}"

    def test_pin_unpin_owner_only(self, reese, jordan):
        # reese creates a round, jordan can't pin/unpin
        r = requests.post(f"{BASE_URL}/api/rounds", headers=_hdr(reese),
                          json={"course_name": "TEST_iter10_pin", "total_score": 80})
        assert r.status_code == 200
        rid = r.json()["id"]
        try:
            # jordan pins reese's round -> 403
            r2 = requests.post(f"{BASE_URL}/api/rounds/{rid}/pin", headers=_hdr(jordan))
            assert r2.status_code == 403
            # non-existent round -> 404
            r3 = requests.post(f"{BASE_URL}/api/rounds/does-not-exist/pin", headers=_hdr(reese))
            assert r3.status_code == 404
            # owner pin -> 200
            r4 = requests.post(f"{BASE_URL}/api/rounds/{rid}/pin", headers=_hdr(reese))
            assert r4.status_code == 200
            # owner unpin -> 200 (endpoint is DELETE /users/me/pin)
            r5 = requests.delete(f"{BASE_URL}/api/users/me/pin", headers=_hdr(reese))
            assert r5.status_code == 200
        finally:
            requests.delete(f"{BASE_URL}/api/rounds/{rid}", headers=_hdr(reese))

    def test_null_clears_iter6(self, reese):
        # PATCH null-clear on handicap/bio/home_course/avatar still works (iter9 behaviour)
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese),
                           json={"handicap": None, "bio": None, "home_course": None, "avatar": None})
        assert r.status_code == 200
        body = r.json()
        assert body["handicap"] is None
        assert body["bio"] is None
        assert body["home_course"] is None
        assert body.get("avatar") is None

    def test_avatar_oversize_413(self, reese):
        big = "data:image/png;base64," + ("A" * 900_000)
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese), json={"avatar": big})
        assert r.status_code == 413

    def test_wishlist_basic(self, jordan):
        course = f"TEST_iter10_wl_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{BASE_URL}/api/wishlist", headers=_hdr(jordan),
                          json={"course_name": course})
        assert r.status_code == 200 and r.json()["added"] is True
        # dup
        r2 = requests.post(f"{BASE_URL}/api/wishlist", headers=_hdr(jordan),
                           json={"course_name": course})
        assert r2.status_code == 200 and r2.json()["added"] is False
        # check
        r3 = requests.get(f"{BASE_URL}/api/wishlist/check/{course}", headers=_hdr(jordan))
        assert r3.status_code == 200 and r3.json()["on_wishlist"] is True
        # delete
        r4 = requests.delete(f"{BASE_URL}/api/wishlist/{course}", headers=_hdr(jordan))
        assert r4.status_code == 200 and r4.json()["removed"] is True
