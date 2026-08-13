"""Iteration 28: OpenGolfAPI name-collision fix (White Pines Golf Course,
Swanton OH) + Log tab nine (front/back) field + LFG course tagging.

Covers:
- GET /api/courses/White%20Pines%20Golf%20Course -> correct Swanton, OH data
- Regression: Pebble Beach Golf Links / Bandon Dunes Golf Resort still enriched
- POST /api/rounds with nine="front"/"back" persists correctly (18-hole course)
- POST /api/rounds holes_played=18 -> nine forced to None even if supplied
- POST /api/rounds post_type="lfg" with optional course_name, no score required
- PATCH /api/rounds/{id} can update nine
"""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("EXPO_PUBLIC_BACKEND_URL")).rstrip("/")
LOGIN_EMAIL = "reese@teebox.demo"
LOGIN_PASSWORD = "password123"


@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
    )
    if resp.status_code != 200:
        pytest.skip(f"login failed: {resp.status_code} {resp.text}")
    token = resp.json().get("access_token") or resp.json().get("token")
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    return session


class TestWhitePinesCollisionFix:
    """Verifies the >40km proximity guard fixed the Swanton OH <-> MA collision."""

    def test_white_pines_is_swanton_ohio_not_massachusetts(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/courses/White%20Pines%20Golf%20Course")
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_name"] == "White Pines Golf Course"
        assert data["city"] == "Swanton"
        assert data["region"] == "OH"
        assert data["par"] == 36
        assert data["num_holes"] == 9
        # Coordinates should be near Swanton, OH (~41.49, -83.90), NOT Massachusetts (~42.x, -71.x)
        assert data["lat"] is not None and data["lng"] is not None
        assert 40 < data["lat"] < 43
        assert -85 < data["lng"] < -82

    def test_white_pines_website_phone_match_swanton_course(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/courses/White%20Pines%20Golf%20Course")
        data = resp.json()
        # The real Swanton OH course phone area code is 419 (NW Ohio)
        if data.get("phone"):
            assert "419" in data["phone"], f"unexpected phone (looks like wrong-course data): {data['phone']}"
        if data.get("website"):
            assert "whitepinesgc" in data["website"].lower()


class TestRegressionEnrichment:
    """Collision-guard fix must not break normal (non-colliding) enrichment."""

    def test_pebble_beach_golf_links_still_enriched(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/courses/Pebble%20Beach%20Golf%20Links")
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_name"] == "Pebble Beach Golf Links"
        assert data["region"] == "CA"
        assert data["par"] == 72
        assert data["num_holes"] == 18
        assert isinstance(data["holes"], list) and len(data["holes"]) == 18
        assert isinstance(data["tees"], list) and len(data["tees"]) > 0

    def test_bandon_dunes_golf_resort_still_enriched(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/courses/Bandon%20Dunes%20Golf%20Resort")
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_name"] == "Bandon Dunes Golf Resort"
        assert data["region"] == "OR"
        assert data["par"] == 72
        assert isinstance(data["holes"], list) and len(data["holes"]) == 18


class TestRoundNineField:
    """Round create/update persistence for the new 'nine' (front/back) field."""

    created_ids = []

    def test_create_round_18_holes_nine_forced_none(self, api_client):
        payload = {
            "post_type": "round",
            "course_name": "TEST_Nine_Field_Course_18",
            "total_score": 82,
            "par": 72,
            "holes_played": 18,
            "nine": "front",  # should be ignored/forced None server-side for 18 holes
            "notes": "TEST round 18 holes",
        }
        resp = api_client.post(f"{BASE_URL}/api/rounds", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["holes_played"] == 18
        assert data["nine"] is None
        self.created_ids.append(data["id"])

    def test_create_round_9_holes_front_nine_persists(self, api_client):
        payload = {
            "post_type": "round",
            "course_name": "TEST_Nine_Field_Course_9",
            "total_score": 40,
            "par": 35,
            "holes_played": 9,
            "nine": "front",
            "notes": "TEST round front 9",
        }
        resp = api_client.post(f"{BASE_URL}/api/rounds", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["holes_played"] == 9
        assert data["nine"] == "front"
        assert data["par"] == 35
        round_id = data["id"]
        self.created_ids.append(round_id)

        # GET-equivalent verification via round detail
        get_resp = api_client.get(f"{BASE_URL}/api/rounds/{round_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["nine"] == "front"

    def test_update_round_nine_to_back(self, api_client):
        payload = {
            "post_type": "round",
            "course_name": "TEST_Nine_Field_Course_9b",
            "total_score": 41,
            "par": 37,
            "holes_played": 9,
            "nine": "front",
        }
        resp = api_client.post(f"{BASE_URL}/api/rounds", json=payload)
        assert resp.status_code == 200
        round_id = resp.json()["id"]
        self.created_ids.append(round_id)

        patch_resp = api_client.patch(f"{BASE_URL}/api/rounds/{round_id}", json={"nine": "back"})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["nine"] == "back"

        get_resp = api_client.get(f"{BASE_URL}/api/rounds/{round_id}")
        assert get_resp.json()["nine"] == "back"

    def test_invalid_nine_value_rejected(self, api_client):
        payload = {
            "post_type": "round",
            "course_name": "TEST_Nine_Field_Invalid",
            "total_score": 82,
            "par": 72,
            "holes_played": 18,
            "nine": "middle",
        }
        resp = api_client.post(f"{BASE_URL}/api/rounds", json=payload)
        assert resp.status_code == 422

    @classmethod
    def teardown_class(cls):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        )
        token = resp.json().get("access_token") if resp.status_code == 200 else None
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
        for rid in cls.created_ids:
            session.delete(f"{BASE_URL}/api/rounds/{rid}")


class TestLfgCourseOptional:
    """LFG posts support an optional course tag; no score/photos required."""

    created_ids = []

    def test_lfg_without_course_succeeds(self, api_client):
        payload = {
            "post_type": "lfg",
            "notes": "TEST Looking for 2 more, Saturday morning",
            "looking_for_count": 2,
            "meetup_date": "Sat 8:30 AM",
        }
        resp = api_client.post(f"{BASE_URL}/api/rounds", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["post_type"] == "lfg"
        assert data.get("course_name") == ""
        self.created_ids.append(data["id"])

    def test_lfg_with_course_persists_course_name(self, api_client):
        payload = {
            "post_type": "lfg",
            "notes": "TEST Playing Pebble Beach, need 1 more",
            "course_name": "Pebble Beach Golf Links",
            "looking_for_count": 1,
        }
        resp = api_client.post(f"{BASE_URL}/api/rounds", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["course_name"] == "Pebble Beach Golf Links"
        round_id = data["id"]
        self.created_ids.append(round_id)

        get_resp = api_client.get(f"{BASE_URL}/api/rounds/{round_id}")
        assert get_resp.json()["course_name"] == "Pebble Beach Golf Links"

    def test_lfg_empty_notes_and_no_photos_rejected(self, api_client):
        payload = {"post_type": "lfg", "notes": "", "photos": []}
        resp = api_client.post(f"{BASE_URL}/api/rounds", json=payload)
        assert resp.status_code == 422

    @classmethod
    def teardown_class(cls):
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        )
        token = resp.json().get("access_token") if resp.status_code == 200 else None
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
        for rid in cls.created_ids:
            session.delete(f"{BASE_URL}/api/rounds/{rid}")
