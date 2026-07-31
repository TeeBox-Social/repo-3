"""Iteration 23 tests — Emergent-managed Google Sign-In.

Test strategy:
- Invalid session_id: hit the real deployed /api/auth/google endpoint via HTTP
  (Emergent returns 401 to gibberish session IDs → we expect 401).
- Valid session (new user, merge existing user, tokens+lockout clearing):
  use FastAPI TestClient in-process with httpx.AsyncClient.get monkeypatched
  to return a canned Emergent session-data response.
- Regression: legacy iter22 endpoints (register with email_verified=false,
  forgot/reset password, lockout, refresh, /auth/me, /auth/logout) still work.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from security import create_typed_token, pwd_context  # noqa: E402
from helpers import now_iso  # noqa: E402
from config import DEFAULT_NOTIFICATION_PREFS, MONGO_URL, DB_NAME  # noqa: E402

from pymongo import MongoClient  # noqa: E402
_sync_client = MongoClient(MONGO_URL)
users_col = _sync_client[DB_NAME]["users"]

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://course-crew-3.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _unique_email(tag: str) -> str:
    return f"test-iter23-{tag}-{uuid.uuid4().hex[:8]}@teebox.demo"


# ---- Fixtures -------------------------------------------------------------
@pytest.fixture
def api_client():
    s = requests.Session()
    fake_ip = f"10.98.{uuid.uuid4().int % 256}.{uuid.uuid4().int % 256}"
    s.headers.update({"Content-Type": "application/json", "X-Forwarded-For": fake_ip})
    return s


@pytest.fixture(scope="session")
def test_client():
    """Session-scoped in-process FastAPI TestClient so motor's event loop is
    reused across tests (avoids 'Event loop is closed' from per-test TestClient
    recreation)."""
    from fastapi.testclient import TestClient
    from server import app
    with TestClient(app) as c:
        yield c


def _fake_httpx_response(status: int, json_body: dict):
    """Build an object that quacks like httpx.Response for the router path."""
    class _Resp:
        status_code = status
        text = str(json_body)
        def json(self):
            return json_body
    return _Resp()


def _patched_httpx(status: int, body: dict):
    """Return a patch that swaps httpx.AsyncClient with a stub whose
    async .get returns our canned response and whose async context manager
    yields itself."""
    class _Client:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def get(self, url, headers=None):
            return _fake_httpx_response(status, body)
    return patch("httpx.AsyncClient", _Client)


# ---- 1. Invalid session_id via real endpoint ------------------------------
class TestInvalidSession:
    def test_bogus_session_id_returns_401(self, api_client):
        # Well-formed length but not a real Emergent session
        r = api_client.post(f"{API}/auth/google", json={"session_id": "bogusfakestringabc12345"})
        # Emergent's session-data endpoint returns non-200 → our router maps to 401.
        # If Emergent itself is unreachable we accept 502.
        assert r.status_code in (401, 502), f"expected 401 or 502, got {r.status_code} {r.text}"
        if r.status_code == 401:
            assert "invalid" in r.json().get("detail", "").lower() or \
                   "expired" in r.json().get("detail", "").lower()

    def test_too_short_session_id_returns_422(self, api_client):
        # session_id has min_length=8 in Pydantic model
        r = api_client.post(f"{API}/auth/google", json={"session_id": "abc"})
        assert r.status_code == 422


# ---- 2. Valid session, new user -------------------------------------------
class TestGoogleNewUser:
    def test_new_user_created_with_google_provider(self, test_client):
        email = _unique_email("new")
        body = {"email": email, "name": "Googler McTest", "picture": "https://g.example/p.png"}
        created_id = None
        try:
            with _patched_httpx(200, body):
                r = test_client.post("/api/auth/google", json={"session_id": "validstubbedsession"})
            assert r.status_code == 200, r.text
            data = r.json()
            assert "access_token" in data and data["access_token"]
            assert "refresh_token" in data and data["refresh_token"]
            user = data["user"]
            assert user["email"] == email
            assert user["email_verified"] is True
            assert "google" in user.get("auth_providers", [])
            assert user.get("display_name") == "Googler McTest"
            assert user.get("avatar") == "https://g.example/p.png"

            # Persistence — DB doc has no hashed_password
            doc = users_col.find_one({"email": email})
            assert doc is not None
            created_id = doc["id"]
            assert doc.get("hashed_password") is None
            assert doc.get("email_verified") is True
            assert "google" in (doc.get("auth_providers") or [])
        finally:
            if created_id:
                users_col.delete_one({"id": created_id})


# ---- 3. Existing email/password user — merge, don't clobber ---------------
class TestGoogleMerge:
    def test_existing_user_merged_password_untouched(self, test_client):
        email = _unique_email("merge")
        original_pw = "OriginalPass1!"
        original_hash = pwd_context.hash(original_pw)
        user_id = str(uuid.uuid4())
        users_col.insert_one({
            "id": user_id,
            "email": email.lower(),
            "hashed_password": original_hash,
            "display_name": "Existing Name",     # should NOT be overwritten
            "avatar": "data:image/png;base64,AAA",  # existing custom avatar
            "home_course": "",
            "handicap": None,
            "bio": "",
            "notification_prefs": dict(DEFAULT_NOTIFICATION_PREFS),
            "email_verified": False,
            "failed_login_attempts": 3,          # simulate prior lockout state
            "lockout_until": datetime.now(timezone.utc) + timedelta(hours=1),
            "created_at": now_iso(),
        })
        try:
            google_body = {
                "email": email,
                "name": "Google Provided Name",           # should be IGNORED (display_name already set)
                "picture": "https://g.example/other.png", # should be IGNORED (avatar already set)
            }
            with _patched_httpx(200, google_body):
                r = test_client.post("/api/auth/google", json={"session_id": "validstubbedsession"})
            assert r.status_code == 200, r.text
            data = r.json()
            user = data["user"]
            assert user["email"] == email
            assert "google" in user.get("auth_providers", [])
            assert user["display_name"] == "Existing Name", "display_name should NOT be overwritten"
            assert user["avatar"] == "data:image/png;base64,AAA", "avatar should NOT be overwritten"
            assert user["email_verified"] is True

            # Password left intact
            doc = users_col.find_one({"id": user_id})
            assert doc.get("hashed_password") == original_hash
            # Lockout cleared
            assert doc.get("failed_login_attempts") == 0
            assert doc.get("lockout_until") is None
        finally:
            users_col.delete_one({"id": user_id})

    def test_existing_user_fills_blank_display_name_and_avatar(self, test_client):
        email = _unique_email("blank")
        user_id = str(uuid.uuid4())
        users_col.insert_one({
            "id": user_id,
            "email": email.lower(),
            "hashed_password": pwd_context.hash("pw123456"),
            "display_name": "",   # blank → should be filled
            "avatar": None,       # blank → should be filled
            "home_course": "",
            "handicap": None,
            "bio": "",
            "notification_prefs": dict(DEFAULT_NOTIFICATION_PREFS),
            "email_verified": False,
            "failed_login_attempts": 0,
            "created_at": now_iso(),
        })
        try:
            with _patched_httpx(200, {"email": email, "name": "FromGoogle", "picture": "https://g.example/p2.png"}):
                r = test_client.post("/api/auth/google", json={"session_id": "validstubbedsession"})
            assert r.status_code == 200, r.text
            doc = users_col.find_one({"id": user_id})
            assert doc["display_name"] == "FromGoogle"
            assert doc["avatar"] == "https://g.example/p2.png"
        finally:
            users_col.delete_one({"id": user_id})


# ---- 4. Emergent returned 401/malformed → our endpoint returns 401 --------
class TestGoogleUpstreamFailure:
    def test_emergent_returns_401_maps_to_401(self, test_client):
        with _patched_httpx(401, {"detail": "invalid session"}):
            r = test_client.post("/api/auth/google", json={"session_id": "stubbedsession01"})
        assert r.status_code == 401
        assert "invalid" in r.json().get("detail", "").lower() or \
               "expired" in r.json().get("detail", "").lower()

    def test_emergent_returns_200_without_email_returns_400(self, test_client):
        with _patched_httpx(200, {"name": "NoEmail"}):
            r = test_client.post("/api/auth/google", json={"session_id": "stubbedsession01"})
        assert r.status_code == 400


# ---- 5. Legacy iter22 flows regression -----------------------------------
class TestLegacyFlowsRegression:
    def test_seeded_admin_login_and_me(self, api_client):
        r = api_client.post(f"{API}/auth/login", json={
            "email": "reese@teebox.demo", "password": "password123",
        })
        assert r.status_code == 200, r.text
        access = r.json()["access_token"]
        me = api_client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert me.status_code == 200
        assert me.json().get("email_verified") is True

    def test_refresh_and_logout(self, api_client):
        r = api_client.post(f"{API}/auth/login", json={
            "email": "jordan@teebox.demo", "password": "password123",
        })
        assert r.status_code == 200
        refresh = r.json()["refresh_token"]
        r2 = api_client.post(f"{API}/auth/refresh", json={"refresh_token": refresh})
        assert r2.status_code == 200, r2.text
        new_refresh = r2.json()["refresh_token"]
        # logout with the rotated refresh
        r3 = api_client.post(f"{API}/auth/logout", json={"refresh_token": new_refresh})
        assert r3.status_code == 200
        # old refresh no longer valid
        r4 = api_client.post(f"{API}/auth/refresh", json={"refresh_token": refresh})
        assert r4.status_code == 401

    def test_forgot_and_reset_password_flow(self, api_client):
        # Create user directly
        email = _unique_email("fpwd")
        user_id = str(uuid.uuid4())
        users_col.insert_one({
            "id": user_id, "email": email.lower(),
            "hashed_password": pwd_context.hash("StartPw1!"),
            "display_name": "FP T", "email_verified": True,
            "failed_login_attempts": 0, "created_at": now_iso(),
        })
        try:
            r = api_client.post(f"{API}/auth/request-password-reset", json={"email": email})
            assert r.status_code == 200
            # Direct token → reset
            token = create_typed_token(user_id, "password_reset", 30)
            r2 = api_client.post(f"{API}/auth/reset-password", json={
                "token": token, "new_password": "AfterReset1!",
            })
            assert r2.status_code == 200
            # Login with new password
            r3 = api_client.post(f"{API}/auth/login", json={
                "email": email, "password": "AfterReset1!",
            })
            assert r3.status_code == 200
        finally:
            users_col.delete_one({"id": user_id})

    def test_lockout_still_triggers_after_10_failures(self, api_client):
        email = _unique_email("lock")
        password = "Right1Pw!"
        user_id = str(uuid.uuid4())
        users_col.insert_one({
            "id": user_id, "email": email.lower(),
            "hashed_password": pwd_context.hash(password),
            "display_name": "LT", "email_verified": True,
            "failed_login_attempts": 0, "created_at": now_iso(),
        })
        try:
            def _login(pw):
                headers = {"X-Forwarded-For": f"10.66.{uuid.uuid4().int % 256}.{uuid.uuid4().int % 256}"}
                return api_client.post(f"{API}/auth/login", json={"email": email, "password": pw}, headers=headers)

            for i in range(1, 10):
                assert _login("WRONG").status_code == 401
            # 10th tips over the edge
            resp = _login("WRONG")
            assert resp.status_code == 423
            # Correct password now also locked
            assert _login(password).status_code == 423
        finally:
            users_col.delete_one({"id": user_id})
