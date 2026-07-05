"""
Iter7 – Proxy-aware rate limit verification.

Backend uses slowapi with a custom key_func (_client_ip) that prefers:
  cf-connecting-ip  →  x-forwarded-for (first hop)  →  socket peer

Tests are run against BOTH:
  - the ORIGIN     (http://localhost:8001)   — direct, no Cloudflare in the way
  - the PUBLIC URL (EXPO_PUBLIC_BACKEND_URL) — through Cloudflare + ingress

For each target we verify:
  1. /auth/login  (10/min) trips at request #11 with cf-connecting-ip=1.2.3.4
  2. A different  cf-connecting-ip (5.6.7.8) starts a fresh bucket
  3. /auth/register (5/min) trips at request #6 with cf-connecting-ip=9.9.9.9
  4. Without cf-connecting-ip, x-forwarded-for is used and rate limit still trips.

All test data uses TEST_ prefix. Register cleanup drops any TEST_rl7_* users.
"""

import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

PUBLIC_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or ""
).rstrip("/")
ORIGIN_URL = "http://localhost:8001"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "teebox_db")

# Which targets to test
TARGETS = [("origin", ORIGIN_URL)]
if PUBLIC_URL:
    TARGETS.append(("public", PUBLIC_URL))


# ---- helpers ----
def _fire(url_base, path, headers, body, n):
    """Fire n sequential POSTs, return list of status codes."""
    codes = []
    for _ in range(n):
        try:
            r = requests.post(f"{url_base}{path}", json=body, headers=headers, timeout=15)
            codes.append(r.status_code)
        except requests.RequestException as e:
            codes.append(f"ERR:{e}")
    return codes


def _wait_bucket_reset():
    # slowapi minute bucket = 60s. Sleep 65s to be safe.
    time.sleep(65)


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    try:
        c = MongoClient(MONGO_URL)
        c[DB_NAME].users.delete_many({"email": {"$regex": "^test_rl7_"}})
        c.close()
    except Exception:
        pass


@pytest.fixture(scope="module", autouse=True)
def _health():
    """Ensure origin is up and demo seed user exists (for realistic 401 bad-cred flow)."""
    r = requests.get(f"{ORIGIN_URL}/api/", timeout=10)
    assert r.status_code == 200, f"backend origin not reachable: {r.status_code}"
    # Sleep to make sure prior test runs' rate-limit buckets are clear
    time.sleep(3)


# ---- Tests ----
@pytest.mark.parametrize("label,base", TARGETS)
def test_login_rate_limit_trips_with_cf_connecting_ip(label, base):
    """First 10 login attempts return 401 (bad creds); 11th+ return 429.

    NOTE: Through Cloudflare (public URL) clients CANNOT spoof cf-connecting-ip —
    CF rejects such requests with 403 error 1000. So this scenario is only valid
    at the origin. The public URL is exercised in test_public_url_rate_limit_via_real_ip.
    """
    if label == "public":
        pytest.skip("Cloudflare rejects client-supplied cf-connecting-ip (error 1000); tested at origin.")
    ip = f"1.2.3.{4 + hash(label) % 200}"  # unique IP per target to isolate buckets
    headers = {"cf-connecting-ip": ip, "Content-Type": "application/json"}
    body = {"email": "bad@bad.com", "password": "wrong"}

    codes = _fire(base, "/api/auth/login", headers, body, 12)
    print(f"[{label}] login codes (cf-ip={ip}): {codes}")

    n_401 = sum(1 for c in codes if c == 401)
    n_429 = sum(1 for c in codes if c == 429)

    assert n_401 >= 9, f"[{label}] expected ~10x 401 for bad creds, got {n_401}: {codes}"
    assert n_429 >= 1, f"[{label}] expected rate limit (429) to trip, got none: {codes}"
    # Last codes should include 429 (once limit trips, remaining stay 429)
    assert codes[-1] == 429, f"[{label}] final code should be 429, got {codes[-1]}"


@pytest.mark.parametrize("label,base", TARGETS)
def test_login_different_ip_starts_fresh_bucket(label, base):
    """A different cf-connecting-ip should get its own counter (10 fresh 401s)."""
    if label == "public":
        pytest.skip("Cloudflare rejects client-supplied cf-connecting-ip.")
    ip = f"5.6.7.{8 + hash(label) % 200}"
    headers = {"cf-connecting-ip": ip, "Content-Type": "application/json"}
    body = {"email": "bad@bad.com", "password": "wrong"}

    codes = _fire(base, "/api/auth/login", headers, body, 10)
    print(f"[{label}] fresh-ip login codes (cf-ip={ip}): {codes}")

    n_401 = sum(1 for c in codes if c == 401)
    n_429 = sum(1 for c in codes if c == 429)

    assert n_401 == 10, f"[{label}] fresh IP should get 10 401s, got {n_401}: {codes}"
    assert n_429 == 0, f"[{label}] fresh IP should NOT be rate-limited yet: {codes}"


@pytest.mark.parametrize("label,base", TARGETS)
def test_register_rate_limit_trips_with_cf_connecting_ip(label, base):
    """/auth/register is 5/min — 6th+ from same cf-connecting-ip should 429."""
    if label == "public":
        pytest.skip("Cloudflare rejects client-supplied cf-connecting-ip.")
    _wait_bucket_reset()  # register bucket may have been used in previous tests
    ip = f"9.9.9.{9 + hash(label) % 200}"
    headers = {"cf-connecting-ip": ip, "Content-Type": "application/json"}

    codes = []
    for i in range(7):
        body = {
            "email": f"test_rl7_{label}_{uuid.uuid4().hex[:8]}@teebox.demo",
            "password": "password123",
            "display_name": f"TEST rl7 {label} {i}",
        }
        try:
            r = requests.post(f"{base}/api/auth/register", json=body, headers=headers, timeout=15)
            codes.append(r.status_code)
        except requests.RequestException as e:
            codes.append(f"ERR:{e}")

    print(f"[{label}] register codes (cf-ip={ip}): {codes}")
    n_200 = sum(1 for c in codes if c == 200)
    n_429 = sum(1 for c in codes if c == 429)

    assert n_200 == 5, f"[{label}] expected 5 successful registers, got {n_200}: {codes}"
    assert n_429 >= 1, f"[{label}] expected register rate limit (429), got none: {codes}"
    assert codes[-1] == 429, f"[{label}] final register code should be 429: {codes[-1]}"


@pytest.mark.parametrize("label,base", TARGETS)
def test_login_rate_limit_trips_with_xff_only(label, base):
    """Without cf-connecting-ip, x-forwarded-for is used — limit should still trip.

    At the ORIGIN we set x-forwarded-for directly.
    At the PUBLIC URL Cloudflare/ingress will inject its own x-forwarded-for chain
    (real client IP = this test host), so we just fire from the same host and expect
    the per-real-IP limit to trip.
    """
    _wait_bucket_reset()
    if label == "public":
        headers = {"Content-Type": "application/json"}
    else:
        ip = f"10.11.12.{13 + hash(label) % 200}"
        headers = {"x-forwarded-for": ip, "Content-Type": "application/json"}
    body = {"email": "bad@bad.com", "password": "wrong"}

    codes = _fire(base, "/api/auth/login", headers, body, 12)
    print(f"[{label}] login codes (xff-fallback): {codes}")

    n_429 = sum(1 for c in codes if c == 429)
    assert n_429 >= 1, f"[{label}] expected 429 via x-forwarded-for / real-client-IP fallback: {codes}"
    assert codes[-1] == 429, f"[{label}] final code should be 429: {codes[-1]}"


# ---- Iter5 regression: refresh reuse detection, logout, wishlist ----
@pytest.fixture(scope="module")
def demo_session():
    """Login demo user (with cf-connecting-ip to avoid interfering with rate-limit tests)."""
    _wait_bucket_reset()
    ip = "77.77.77.77"
    headers = {"cf-connecting-ip": ip, "Content-Type": "application/json"}
    r = requests.post(
        f"{ORIGIN_URL}/api/auth/login",
        json={"email": "reese@teebox.demo", "password": "password123"},
        headers=headers,
        timeout=15,
    )
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    return r.json()


def test_refresh_rotation_reuse_detection(demo_session):
    """Rotating a refresh token twice with the same jti = family compromise → 401."""
    rt1 = demo_session["refresh_token"]
    # First rotate — should succeed
    r1 = requests.post(f"{ORIGIN_URL}/api/auth/refresh", json={"refresh_token": rt1}, timeout=15)
    assert r1.status_code == 200, f"first refresh should succeed, got {r1.status_code}"
    new_pair = r1.json()
    # Reuse old rt1 — should be detected
    r2 = requests.post(f"{ORIGIN_URL}/api/auth/refresh", json={"refresh_token": rt1}, timeout=15)
    assert r2.status_code == 401, f"reuse should be 401, got {r2.status_code}"
    # Sibling in the same family should also be revoked now
    r3 = requests.post(
        f"{ORIGIN_URL}/api/auth/refresh",
        json={"refresh_token": new_pair["refresh_token"]},
        timeout=15,
    )
    assert r3.status_code == 401, f"family should be nuked, sibling should 401, got {r3.status_code}"


def test_logout_and_wishlist_crud():
    """Fresh login → wishlist add/get/remove → logout revokes refresh token."""
    _wait_bucket_reset()
    headers = {"cf-connecting-ip": "88.88.88.88", "Content-Type": "application/json"}
    r = requests.post(
        f"{ORIGIN_URL}/api/auth/login",
        json={"email": "jordan@teebox.demo", "password": "password123"},
        headers=headers,
        timeout=15,
    )
    assert r.status_code == 200
    sess = r.json()
    access = sess["access_token"]
    refresh = sess["refresh_token"]
    user_id = sess["user"]["id"]
    auth = {"Authorization": f"Bearer {access}"}

    # Wishlist add
    add = requests.post(
        f"{ORIGIN_URL}/api/wishlist",
        json={"course_name": "Pacific Dunes"},
        headers=auth,
        timeout=15,
    )
    assert add.status_code == 200
    # Get list
    lst = requests.get(f"{ORIGIN_URL}/api/users/{user_id}/wishlist", headers=auth, timeout=15)
    assert lst.status_code == 200
    assert any(w["course_name"] == "Pacific Dunes" for w in lst.json())
    # Remove
    rm = requests.delete(f"{ORIGIN_URL}/api/wishlist/Pacific Dunes", headers=auth, timeout=15)
    assert rm.status_code == 200 and rm.json().get("removed") is True

    # Logout — refresh token should no longer be accepted
    lo = requests.post(f"{ORIGIN_URL}/api/auth/logout", json={"refresh_token": refresh}, timeout=15)
    assert lo.status_code == 200
    ref = requests.post(f"{ORIGIN_URL}/api/auth/refresh", json={"refresh_token": refresh}, timeout=15)
    assert ref.status_code == 401, f"revoked refresh should 401, got {ref.status_code}"


def test_feed_and_courses_regression(demo_session):
    """Quick regression: /feed, /discover/courses, /rounds/{id}/comments unaffected."""
    # demo_session refresh was rotated already, re-login to get a fresh access token
    _wait_bucket_reset()
    r = requests.post(
        f"{ORIGIN_URL}/api/auth/login",
        json={"email": "sam@teebox.demo", "password": "password123"},
        headers={"cf-connecting-ip": "99.99.99.99"},
        timeout=15,
    )
    assert r.status_code == 200
    auth = {"Authorization": f"Bearer {r.json()['access_token']}"}
    for path in ["/api/feed", "/api/discover/courses", "/api/discover/users"]:
        rr = requests.get(f"{ORIGIN_URL}{path}", headers=auth, timeout=15)
        assert rr.status_code == 200, f"{path} regressed: {rr.status_code}"
        assert isinstance(rr.json(), list)
