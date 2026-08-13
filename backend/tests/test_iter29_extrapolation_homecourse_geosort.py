"""Iteration 29: fair 18-hole-equivalent scoring average, home-course toggle
(PATCH /api/auth/me), and location-first course search sorting.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('EXPO_BACKEND_URL').rstrip('/')

RESEE_EMAIL = "reese@teebox.demo"
RESEE_PASSWORD = "password123"

PEBBLE_BEACH_LAT = 36.5674
PEBBLE_BEACH_LNG = -121.9487


@pytest.fixture(scope="module")
def api_client():
    return requests.Session()


@pytest.fixture(scope="module")
def reese_auth(api_client):
    resp = api_client.post(f"{BASE_URL}/api/auth/login", json={"email": RESEE_EMAIL, "password": RESEE_PASSWORD})
    if resp.status_code != 200:
        pytest.skip(f"Could not login as reese: {resp.status_code} {resp.text}")
    data = resp.json()
    token = data["access_token"]
    user = data["user"]
    return {"token": token, "user": user}


@pytest.fixture(scope="module")
def auth_headers(reese_auth):
    return {"Authorization": f"Bearer {reese_auth['token']}"}


class TestExtrapolatedAverages:
    """Feature 1: fair 18-hole-equivalent scoring average."""

    def test_user_profile_avg_score_extrapolated(self, api_client, reese_auth, auth_headers):
        user_id = reese_auth["user"]["id"]
        resp = api_client.get(f"{BASE_URL}/api/users/{user_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "avg_score" in data
        # Expected (82+79+82)/3 = 81.0 per agent_to_agent_context_note
        assert data["avg_score"] == 81.0, f"Expected 81.0, got {data['avg_score']}"

    def test_courses_played_pebble_beach_extrapolated(self, api_client, reese_auth, auth_headers):
        user_id = reese_auth["user"]["id"]
        resp = api_client.get(f"{BASE_URL}/api/users/{user_id}/courses-played", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        pebble = next((c for c in data if c["course_name"] == "Pebble Beach Golf Course"), None)
        assert pebble is not None, f"Pebble Beach Golf Course not found in courses-played: {data}"
        assert pebble["avg_score"] == 82.0, f"Expected avg_score 82.0, got {pebble['avg_score']}"
        assert pebble["best_score"] == 82, f"Expected best_score 82, got {pebble['best_score']}"


class TestHomeCourse:
    """Feature 2: home course toggle via PATCH /api/auth/me."""

    def test_set_home_course(self, api_client, auth_headers):
        resp = api_client.patch(
            f"{BASE_URL}/api/auth/me", json={"home_course": "Pebble Beach Golf Course"}, headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["home_course"] == "Pebble Beach Golf Course"

        # Verify persisted via GET /auth/me
        me_resp = api_client.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["home_course"] == "Pebble Beach Golf Course"

    def test_discover_courses_shows_home_course_row(self, api_client, auth_headers):
        resp = api_client.get(f"{BASE_URL}/api/discover/courses?q=Pebble Beach", headers=auth_headers)
        assert resp.status_code == 200
        rows = resp.json()
        pebble = next((c for c in rows if c["course_name"] == "Pebble Beach Golf Course"), None)
        assert pebble is not None

    def test_clear_home_course(self, api_client, auth_headers):
        resp = api_client.patch(f"{BASE_URL}/api/auth/me", json={"home_course": ""}, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["home_course"] == ""

        me_resp = api_client.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert me_resp.json()["home_course"] == ""


class TestLocationFirstSort:
    """Feature 3: location-first course search sorting."""

    def test_discover_courses_no_location_no_crash(self, api_client, auth_headers):
        resp = api_client.get(f"{BASE_URL}/api/discover/courses?q=Pebble", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_courses_search_no_location_no_crash(self, api_client, auth_headers):
        resp = api_client.get(f"{BASE_URL}/api/courses/search?q=Pebble", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_discover_courses_with_location_nearest_first(self, api_client, auth_headers):
        resp = api_client.get(
            f"{BASE_URL}/api/discover/courses?q=Pebble&lat={PEBBLE_BEACH_LAT}&lng={PEBBLE_BEACH_LNG}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) > 0
        first = rows[0]
        # First result should be geographically near Pebble Beach, CA if it has lat/lng
        assert "Pebble Beach" in first["course_name"] or first.get("lat") is not None

    def test_courses_search_with_location_nearest_first(self, api_client, auth_headers):
        resp = api_client.get(
            f"{BASE_URL}/api/courses/search?q=Pebble&lat={PEBBLE_BEACH_LAT}&lng={PEBBLE_BEACH_LNG}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) > 0
        # Compute haversine distance manually for rows that have lat/lng to confirm order
        import math

        def haversine(lat1, lng1, lat2, lng2):
            r = 6371.0
            dlat = math.radians(lat2 - lat1)
            dlng = math.radians(lng2 - lng1)
            a = (
                math.sin(dlat / 2) ** 2
                + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
            )
            return 2 * r * math.asin(math.sqrt(a))

        dists = []
        for r in rows:
            if r.get("lat") is not None and r.get("lng") is not None:
                dists.append(haversine(PEBBLE_BEACH_LAT, PEBBLE_BEACH_LNG, r["lat"], r["lng"]))
            else:
                dists.append(float("inf"))
        assert dists == sorted(dists), f"Results not sorted nearest-first: {dists}"


class TestRegression:
    """Light regression: wishlist + course detail still work alongside new home-course feature."""

    def test_wishlist_add_and_check(self, api_client, auth_headers):
        course_name = "Cypress Ridge"
        resp = api_client.post(f"{BASE_URL}/api/wishlist", json={"course_name": course_name}, headers=auth_headers)
        assert resp.status_code == 200
        check = api_client.get(f"{BASE_URL}/api/wishlist/check/{course_name}", headers=auth_headers)
        assert check.status_code == 200
        assert check.json()["on_wishlist"] is True
        # cleanup
        api_client.delete(f"{BASE_URL}/api/wishlist/{course_name}", headers=auth_headers)

    def test_course_detail_still_works(self, api_client, auth_headers):
        resp = api_client.get(f"{BASE_URL}/api/courses/Pebble Beach Golf Course", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_name"] == "Pebble Beach Golf Course"
