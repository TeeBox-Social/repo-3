"""Iter19 — @-mention name resolution tests.

Endpoints under test:
- GET /api/users/by-name/{display_name}
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://course-crew-3.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def jordan_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "jordan@teebox.demo", "password": "password123",
    }, timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(jordan_token):
    return {"Authorization": f"Bearer {jordan_token}", "Content-Type": "application/json"}


# ---------- by-name resolution ----------

class TestUserByName:
    def test_underscore_variant_resolves(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/users/by-name/Sam_Rivera", headers=auth_headers, timeout=10)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert "id" in data and data["id"]
        assert data.get("display_name", "").lower() == "sam rivera"

    def test_space_variant_resolves(self, auth_headers):
        # url-encoded 'sam rivera'
        r = requests.get(f"{BASE_URL}/api/users/by-name/sam%20rivera", headers=auth_headers, timeout=10)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert data.get("display_name", "").lower() == "sam rivera"

    def test_case_insensitive(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/users/by-name/SAM_RIVERA", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        assert r.json().get("display_name", "").lower() == "sam rivera"

    def test_both_variants_same_user(self, auth_headers):
        a = requests.get(f"{BASE_URL}/api/users/by-name/Sam_Rivera", headers=auth_headers, timeout=10).json()
        b = requests.get(f"{BASE_URL}/api/users/by-name/sam%20rivera", headers=auth_headers, timeout=10).json()
        assert a["id"] == b["id"]

    def test_nonexistent_returns_404(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/users/by-name/DoesNotExist_XYZ", headers=auth_headers, timeout=10)
        assert r.status_code == 404

    def test_unauthenticated_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/users/by-name/Sam_Rivera", timeout=10)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_response_shape(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/users/by-name/Sam_Rivera", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        # required keys
        assert "id" in data
        assert "display_name" in data
        # avatar key optional but should not blow up if included
        assert set(data.keys()).issubset({"id", "display_name", "avatar"})


# ---------- Regression: core flows still work ----------

class TestRegression:
    def test_login_works(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "jordan@teebox.demo", "password": "password123",
        }, timeout=15)
        assert r.status_code == 200

    def test_feed_loads(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/feed?scope=all", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_discover_users(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/discover/users?q=sam", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_log_round_and_achievements(self, auth_headers):
        # Create a round with a mention in the notes to seed a test artifact.
        payload = {
            "course_name": "TEST_Mention Course",
            "total_score": 82,
            "holes_played": 18,
            "notes": "TEST_ROUND @Sam_Rivera nice one!",
            "rating": 4,
        }
        r = requests.post(f"{BASE_URL}/api/rounds", json=payload, headers=auth_headers, timeout=15)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        rd = r.json()
        assert rd.get("notes", "").startswith("TEST_ROUND @Sam_Rivera")
        round_id = rd["id"]

        # Verify it shows in feed
        feed = requests.get(f"{BASE_URL}/api/feed?scope=all", headers=auth_headers, timeout=15).json()
        assert any(r_.get("id") == round_id for r_ in feed)

        # Achievements endpoint still works & respects splits
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=10).json()
        ach = requests.get(f"{BASE_URL}/api/users/{me['id']}/achievements", headers=auth_headers, timeout=15)
        assert ach.status_code == 200
        assert "achievements" in ach.json()

        # Clean up
        d = requests.delete(f"{BASE_URL}/api/rounds/{round_id}", headers=auth_headers, timeout=10)
        assert d.status_code in (200, 204)
