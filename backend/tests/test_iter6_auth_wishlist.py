"""
TeeBox iteration 6 backend tests.
Coverage:
  - Access + rotating refresh tokens (15 min access, reuse detection).
  - Rate limiting on /api/auth/login (10/min) and /api/auth/register (5/min).
  - CORS via CORS_ALLOWED_ORIGINS env (checked separately by shell script).
  - Wishlist CRUD + read-only cross-user reads + wishlist_count on /api/users/{id}.
"""
import os
import time
import uuid
import pytest
import requests
from jose import jwt

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
BASE_URL = BASE_URL.rstrip("/")

SECRET_KEY = os.environ.get("JWT_SECRET_KEY")


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def reese(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": "reese@teebox.demo", "password": "password123"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data and "refresh_token" in data and "user" in data
    return data


@pytest.fixture(scope="module")
def jordan(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": "jordan@teebox.demo", "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- AUTH: access token shape ----------
class TestAccessToken:
    def test_login_returns_pair(self, reese):
        assert reese["access_token"] and reese["refresh_token"]
        assert reese["user"]["email"] == "reese@teebox.demo"

    def test_access_token_has_type_access(self, reese):
        payload = jwt.decode(reese["access_token"], SECRET_KEY, algorithms=["HS256"])
        assert payload.get("type") == "access"
        # ~15 min TTL -> exp - iat ~ 900s. We can only sanity check exp is future
        assert payload["exp"] - int(time.time()) <= 15 * 60 + 5

    def test_me_works_with_access_token(self, api, reese):
        r = api.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(reese["access_token"]))
        assert r.status_code == 200
        assert r.json()["email"] == "reese@teebox.demo"

    def test_refresh_token_rejected_as_access(self, api, reese):
        # Bearer using a refresh token should be 401 (wrong type)
        r = api.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(reese["refresh_token"]))
        assert r.status_code == 401

    def test_legacy_no_type_still_accepted(self, api, reese):
        # backwards compat: token without type claim should still work
        payload = {
            "sub": reese["user"]["id"],
            "exp": int(time.time()) + 300,
        }
        legacy = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        r = api.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(legacy))
        assert r.status_code == 200


# ---------- AUTH: refresh flow + reuse detection ----------
class TestRefreshFlow:
    def test_refresh_returns_fresh_pair_and_old_rejected(self, api):
        # Fresh login so we don't disturb the module-scope reese token
        login = api.post(f"{BASE_URL}/api/auth/login",
                        json={"email": "sam@teebox.demo", "password": "password123"})
        assert login.status_code == 200
        old_refresh = login.json()["refresh_token"]

        # First refresh: success
        r1 = api.post(f"{BASE_URL}/api/auth/refresh", json={"refresh_token": old_refresh})
        assert r1.status_code == 200, r1.text
        new_pair = r1.json()
        assert new_pair["access_token"] and new_pair["refresh_token"]
        assert new_pair["refresh_token"] != old_refresh

        # Reuse old refresh -> 401 with reuse-detected message
        r2 = api.post(f"{BASE_URL}/api/auth/refresh", json={"refresh_token": old_refresh})
        assert r2.status_code == 401
        assert "reuse" in r2.json().get("detail", "").lower()

        # New refresh token from the family should now also be revoked
        r3 = api.post(f"{BASE_URL}/api/auth/refresh", json={"refresh_token": new_pair["refresh_token"]})
        assert r3.status_code == 401

    def test_refresh_invalid_token(self, api):
        assert api.post(f"{BASE_URL}/api/auth/refresh",
                        json={"refresh_token": "not-a-jwt"}).status_code == 401
        forged = jwt.encode({"sub": "x", "type": "refresh", "jti": "y", "family_id": "z",
                             "exp": int(time.time()) + 300}, "wrong-secret-32chars-xxxxxxxxxxx", algorithm="HS256")
        assert api.post(f"{BASE_URL}/api/auth/refresh",
                        json={"refresh_token": forged}).status_code == 401

    def test_logout_revokes_refresh(self, api):
        login = api.post(f"{BASE_URL}/api/auth/login",
                        json={"email": "jordan@teebox.demo", "password": "password123"})
        assert login.status_code == 200
        rt = login.json()["refresh_token"]
        lo = api.post(f"{BASE_URL}/api/auth/logout", json={"refresh_token": rt})
        assert lo.status_code == 200
        # Subsequent refresh -> 401
        r = api.post(f"{BASE_URL}/api/auth/refresh", json={"refresh_token": rt})
        assert r.status_code == 401


# ---------- RATE LIMITING ----------
class TestRateLimit:
    def test_login_rate_limited(self):
        # Uses shell curl to reuse TCP connection & match the auth-playbook
        # verification pattern. Fires 30 rapid requests; with 10/minute the
        # bucket should trip.
        import subprocess, time
        time.sleep(60)  # drain bucket from previous tests
        cmd = "; ".join(
            [f'curl -s -o /dev/null -w "%{{http_code}} " -X POST '
             f'{BASE_URL}/api/auth/login -H "Content-Type: application/json" '
             f'-d \'{{"email":"nobody-rl@teebox.demo","password":"wrongwrong"}}\''
             for _ in range(30)]
        )
        out = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=60)
        codes = [int(x) for x in out.stdout.split() if x.isdigit()]
        # We expect ~10 401s then 429s. Ingress may distribute across pods,
        # softening the bucket, so we require *at least one* 429 in a 30-shot burst.
        assert 429 in codes, f"expected at least one 429 in 30-burst, got {codes}"

    def test_register_rate_limited(self):
        # /api/auth/register is 5/minute — much lower ceiling, easier to hit.
        import subprocess, time, uuid as _uuid
        time.sleep(60)
        cmd = "; ".join(
            [f'curl -s -o /dev/null -w "%{{http_code}} " -X POST '
             f'{BASE_URL}/api/auth/register -H "Content-Type: application/json" '
             f'-d \'{{"email":"TEST_rl_{_uuid.uuid4().hex[:6]}@teebox.dev","password":"password123","display_name":"x"}}\''
             for _ in range(15)]
        )
        out = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=60)
        codes = [int(x) for x in out.stdout.split() if x.isdigit()]
        assert 429 in codes, f"expected at least one 429 in 15-burst, got {codes}"

    def test_feed_not_rate_limited(self, api, reese):
        # Fire 15 rapid /api/feed calls; none should be 429
        codes = []
        for _ in range(15):
            r = api.get(f"{BASE_URL}/api/feed", headers=auth_headers(reese["access_token"]))
            codes.append(r.status_code)
        assert 429 not in codes, codes
        assert all(c == 200 for c in codes)


# ---------- WISHLIST ----------
@pytest.fixture(scope="module")
def fresh_user(api):
    # rate-limit friendly: wait out any register bucket used by test_register_rate_limited
    time.sleep(65)
    email = f"TEST_wl_{uuid.uuid4().hex[:8]}@teebox.dev"
    r = api.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "password123",
        "display_name": "TEST Wishlister"
    })
    assert r.status_code == 200, r.text
    return r.json()


class TestWishlist:
    def test_add_and_check(self, api, fresh_user):
        h = auth_headers(fresh_user["access_token"])
        r = api.post(f"{BASE_URL}/api/wishlist",
                     json={"course_name": "Bandon Dunes"}, headers=h)
        assert r.status_code == 200
        assert r.json() == {"added": True}

        chk = api.get(f"{BASE_URL}/api/wishlist/check/Bandon Dunes", headers=h)
        assert chk.status_code == 200
        assert chk.json() == {"on_wishlist": True}

    def test_duplicate_returns_added_false(self, api, fresh_user):
        h = auth_headers(fresh_user["access_token"])
        r = api.post(f"{BASE_URL}/api/wishlist",
                     json={"course_name": "Bandon Dunes"}, headers=h)
        assert r.status_code == 200
        body = r.json()
        assert body["added"] is False
        assert "already" in body.get("reason", "").lower()

    def test_get_own_wishlist_enriched_and_ordered(self, api, fresh_user):
        h = auth_headers(fresh_user["access_token"])
        # add a second course
        api.post(f"{BASE_URL}/api/wishlist",
                 json={"course_name": "Pacific Dunes"}, headers=h)
        r = api.get(f"{BASE_URL}/api/users/{fresh_user['user']['id']}/wishlist", headers=h)
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 2
        # newest first -> Pacific Dunes should be [0]
        assert items[0]["course_name"] == "Pacific Dunes"
        assert items[1]["course_name"] == "Bandon Dunes"
        # enriched from master catalog
        for it in items:
            assert it["city"] == "Bandon"
            assert it["region"] == "OR"
            assert it["country"] == "USA"
            assert it.get("added_at")

    def test_wishlist_count_on_user(self, api, fresh_user):
        h = auth_headers(fresh_user["access_token"])
        r = api.get(f"{BASE_URL}/api/users/{fresh_user['user']['id']}", headers=h)
        assert r.status_code == 200
        assert r.json().get("wishlist_count") == 2

    def test_cross_user_readonly(self, api, fresh_user, reese):
        # Reese reads fresh_user's wishlist
        r = api.get(f"{BASE_URL}/api/users/{fresh_user['user']['id']}/wishlist",
                    headers=auth_headers(reese["access_token"]))
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_delete_removes(self, api, fresh_user):
        h = auth_headers(fresh_user["access_token"])
        r = api.delete(f"{BASE_URL}/api/wishlist/Bandon Dunes", headers=h)
        assert r.status_code == 200
        assert r.json() == {"removed": True}
        chk = api.get(f"{BASE_URL}/api/wishlist/check/Bandon Dunes", headers=h)
        assert chk.json() == {"on_wishlist": False}

    def test_wishlist_requires_auth(self, api):
        r = api.post(f"{BASE_URL}/api/wishlist", json={"course_name": "X"})
        assert r.status_code == 401
