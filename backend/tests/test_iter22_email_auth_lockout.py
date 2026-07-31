"""Iteration 22 tests — email verification, password reset, account lockout.

Backend URL comes from EXPO_PUBLIC_BACKEND_URL. JWTs for out-of-band flows are
generated directly via the security module (per agent-to-agent context note)
so we don't depend on real email delivery.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

# Make backend modules importable to reach create_typed_token + mongo helpers
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from security import create_typed_token, pwd_context  # noqa: E402
from helpers import now_iso  # noqa: E402
from config import DEFAULT_NOTIFICATION_PREFS, MONGO_URL, DB_NAME  # noqa: E402

# Use SYNC pymongo for direct DB seeding/cleanup — avoids motor's per-loop
# event-loop reuse issue when pytest-asyncio spins a fresh loop per test.
from pymongo import MongoClient  # noqa: E402
_sync_client = MongoClient(MONGO_URL)
users_col = _sync_client[DB_NAME]["users"]

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://course-crew-3.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ---- Fixtures -------------------------------------------------------------
def _unique_email(tag: str) -> str:
    return f"test-iter22-{tag}-{uuid.uuid4().hex[:8]}@teebox.demo"


@pytest.fixture
def api_client():
    s = requests.Session()
    # Fake an X-Forwarded-For unique to this session so rate-limits (which key
    # off client IP) don't cross-pollinate between tests.
    fake_ip = f"10.99.{uuid.uuid4().int % 256}.{uuid.uuid4().int % 256}"
    s.headers.update({"Content-Type": "application/json", "X-Forwarded-For": fake_ip})
    return s


@pytest.fixture
def fresh_user(api_client):
    """Insert a fresh unverified user directly into Mongo (bypasses register
    rate-limit). Returns dict with tokens+email+id — tokens created via login."""
    email = _unique_email("user")
    password = "InitialPass1!"
    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id,
        "email": email.lower(),
        "hashed_password": pwd_context.hash(password),
        "display_name": "Iter22 Tester",
        "home_course": "",
        "handicap": None,
        "bio": "",
        "avatar": None,
        "notification_prefs": dict(DEFAULT_NOTIFICATION_PREFS),
        "email_verified": False,
        "failed_login_attempts": 0,
        "created_at": now_iso(),
    }
    users_col.insert_one(doc)
    r = api_client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    yield {
        "email": email,
        "password": password,
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "user": data["user"],
    }
    users_col.delete_one({"id": user_id})


# ---- 1. Register creates email_verified=false & returns tokens ------------
class TestRegister:
    def test_register_returns_tokens_and_unverified_user(self, api_client):
        email = _unique_email("reg")
        r = api_client.post(f"{API}/auth/register", json={
            "email": email,
            "password": "TestPass1!",
            "display_name": "Reg Tester",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data and data["access_token"]
        assert "refresh_token" in data and data["refresh_token"]
        assert data["user"]["email"] == email.lower()
        assert data["user"].get("email_verified") is False


# ---- 2. verify-email endpoint --------------------------------------------
class TestVerifyEmail:
    def test_valid_token_flips_flag(self, api_client, fresh_user):
        token = create_typed_token(fresh_user["user"]["id"], "verify_email", 60)
        r = api_client.post(f"{API}/auth/verify-email", json={"token": token})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # Verify via /auth/me (needs bearer)
        headers = {"Authorization": f"Bearer {fresh_user['access_token']}"}
        me = api_client.get(f"{API}/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json().get("email_verified") is True

    def test_wrong_token_type_returns_400(self, api_client, fresh_user):
        # Password reset token used as verify token → 400 invalid type
        bad = create_typed_token(fresh_user["user"]["id"], "password_reset", 30)
        r = api_client.post(f"{API}/auth/verify-email", json={"token": bad})
        assert r.status_code == 400
        assert "type" in r.json().get("detail", "").lower() or "invalid" in r.json().get("detail", "").lower()

    def test_tampered_token_returns_400(self, api_client, fresh_user):
        token = create_typed_token(fresh_user["user"]["id"], "verify_email", 60)
        # Flip last char
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        r = api_client.post(f"{API}/auth/verify-email", json={"token": tampered})
        assert r.status_code == 400

    def test_expired_token_returns_400(self, api_client, fresh_user):
        # Create an already-expired token
        token = create_typed_token(fresh_user["user"]["id"], "verify_email", -1)
        r = api_client.post(f"{API}/auth/verify-email", json={"token": token})
        assert r.status_code == 400


# ---- 3. resend-verification ------------------------------------------------
class TestResendVerification:
    def test_returns_200_for_unknown_email(self, api_client):
        r = api_client.post(f"{API}/auth/resend-verification", json={"email": "test-nobody@teebox.demo"})
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_returns_200_for_existing_unverified(self, api_client, fresh_user):
        r = api_client.post(f"{API}/auth/resend-verification", json={"email": fresh_user["email"]})
        assert r.status_code == 200


# ---- 4. request-password-reset --------------------------------------------
class TestRequestPasswordReset:
    def test_returns_200_for_unknown_email(self, api_client):
        r = api_client.post(f"{API}/auth/request-password-reset", json={"email": "test-nowhere@teebox.demo"})
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_returns_200_for_existing(self, api_client, fresh_user):
        r = api_client.post(f"{API}/auth/request-password-reset", json={"email": fresh_user["email"]})
        assert r.status_code == 200


# ---- 5. reset-password ----------------------------------------------------
class TestResetPassword:
    def test_reset_flow_updates_password_and_unlocks(self, api_client, fresh_user):
        new_password = "BrandNewPass1!"
        token = create_typed_token(fresh_user["user"]["id"], "password_reset", 30)

        r = api_client.post(f"{API}/auth/reset-password", json={
            "token": token, "new_password": new_password,
        })
        assert r.status_code == 200, r.text

        # Old password rejected
        old_login = api_client.post(f"{API}/auth/login", json={
            "email": fresh_user["email"], "password": fresh_user["password"],
        })
        assert old_login.status_code == 401

        # New password works
        new_login = api_client.post(f"{API}/auth/login", json={
            "email": fresh_user["email"], "password": new_password,
        })
        assert new_login.status_code == 200

        # Old refresh token revoked
        rt = api_client.post(f"{API}/auth/refresh", json={"refresh_token": fresh_user["refresh_token"]})
        assert rt.status_code == 401

    def test_wrong_token_type_returns_400(self, api_client, fresh_user):
        bad = create_typed_token(fresh_user["user"]["id"], "verify_email", 60)
        r = api_client.post(f"{API}/auth/reset-password", json={"token": bad, "new_password": "ValidPass1!"})
        assert r.status_code == 400


# ---- 6. Account lockout ---------------------------------------------------
class TestLockout:
    def test_lockout_after_10_failed_logins(self, api_client):
        # Insert fresh user directly (register endpoint is rate-limited to 5/min)
        email = _unique_email("lock")
        password = "GoodPass1!"
        user_id = str(uuid.uuid4())
        users_col.insert_one({
            "id": user_id, "email": email.lower(),
            "hashed_password": pwd_context.hash(password),
            "display_name": "Lock T", "email_verified": False,
            "failed_login_attempts": 0, "created_at": now_iso(),
        })
        try:
            def _login(pwd: str):
                # rotate XFF so we don't hit the 10/min per-IP login limit
                headers = {"X-Forwarded-For": f"10.77.{uuid.uuid4().int % 256}.{uuid.uuid4().int % 256}"}
                return api_client.post(f"{API}/auth/login", json={"email": email, "password": pwd}, headers=headers)

            # Attempts 1..9 should return 401
            for i in range(1, 10):
                resp = _login("WRONG")
                assert resp.status_code == 401, f"attempt {i}: {resp.status_code} {resp.text}"

            # 10th attempt should return 423
            resp = _login("WRONG")
            assert resp.status_code == 423, f"attempt 10 expected 423: {resp.status_code} {resp.text}"
            assert "lock" in resp.json().get("detail", "").lower()

            # While locked, even the correct password returns 423
            resp = _login(password)
            assert resp.status_code == 423, f"expected 423 (locked) got {resp.status_code}"

            # Password reset should unlock the account
            reset_token = create_typed_token(user_id, "password_reset", 30)
            r2 = api_client.post(f"{API}/auth/reset-password", json={
                "token": reset_token, "new_password": "AfterReset1!",
            }, headers={"X-Forwarded-For": f"10.77.{uuid.uuid4().int % 256}.{uuid.uuid4().int % 256}"})
            assert r2.status_code == 200

            # And a successful login now succeeds
            good = _login("AfterReset1!")
            assert good.status_code == 200, good.text
        finally:
            users_col.delete_one({"id": user_id})

    def test_sliding_window_resets_stale_failures(self, api_client):
        """Failed-attempt window is sliding. If we age failed_login_window_start
        past LOCKOUT_WINDOW_MINUTES, next failed login should reset the counter
        to 1 (not carry the old count)."""
        email = _unique_email("slide")
        password = "Slide1!Pass"
        user_id = str(uuid.uuid4())
        users_col.insert_one({
            "id": user_id, "email": email.lower(),
            "hashed_password": pwd_context.hash(password),
            "display_name": "Slide T", "email_verified": False,
            "failed_login_attempts": 0, "created_at": now_iso(),
        })
        try:
            # Rack up 5 failed attempts
            for _ in range(5):
                resp = api_client.post(f"{API}/auth/login", json={"email": email, "password": "WRONG"})
                assert resp.status_code == 401

            # Directly age the window to 2 hours ago
            stale = datetime.now(timezone.utc) - timedelta(hours=2)
            result = users_col.update_one(
                {"id": user_id},
                {"$set": {"failed_login_window_start": stale, "failed_login_attempts": 5}},
            )
            assert result.matched_count == 1

            # Next failed login should reset to counter=1 (window expired)
            resp = api_client.post(f"{API}/auth/login", json={"email": email, "password": "WRONG"})
            assert resp.status_code == 401

            # Read back doc; counter should be 1
            doc = users_col.find_one({"id": user_id})
            assert doc is not None
            assert int(doc.get("failed_login_attempts") or 0) == 1, (
                f"expected counter reset to 1 after stale window, got {doc.get('failed_login_attempts')}"
            )
        finally:
            users_col.delete_one({"id": user_id})


# ---- 7. Legacy flows regression -------------------------------------------
class TestLegacyFlows:
    def test_seeded_admin_login_and_me(self, api_client):
        r = api_client.post(f"{API}/auth/login", json={
            "email": "reese@teebox.demo", "password": "password123",
        })
        assert r.status_code == 200, r.text
        access = r.json()["access_token"]
        me = api_client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert me.status_code == 200
        body = me.json()
        assert body["email"] == "reese@teebox.demo"
        # Legacy accounts must be treated as verified
        assert body.get("email_verified") is True

    def test_feed_endpoint(self, api_client):
        r = api_client.post(f"{API}/auth/login", json={
            "email": "reese@teebox.demo", "password": "password123",
        })
        assert r.status_code == 200
        access = r.json()["access_token"]
        feed = api_client.get(f"{API}/feed?scope=followers",
                              headers={"Authorization": f"Bearer {access}"})
        assert feed.status_code == 200
        assert isinstance(feed.json(), list)

    def test_notification_prefs_default(self, api_client):
        r = api_client.post(f"{API}/auth/login", json={
            "email": "jordan@teebox.demo", "password": "password123",
        })
        assert r.status_code == 200
        access = r.json()["access_token"]
        me = api_client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert me.status_code == 200
        prefs = me.json().get("notification_prefs") or {}
        for key in ("comment_like", "achievement_unlocked", "post_like", "post_comment",
                    "mention", "follow", "course_verified"):
            assert key in prefs, f"missing pref key {key}"
