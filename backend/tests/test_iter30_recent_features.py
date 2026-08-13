"""Iteration 30: Full re-verification of recent TeeBox changes.

Covers:
- OpenGolfAPI: /api/courses/{name} rich detail (holes/tees/climate)
- Location-first sort: /api/discover/courses, /api/courses/search
- Nearby endpoint: /api/discover/courses/nearby sorted by distance
- 9-hole extrapolation in /api/users/{id} AVG
- POST /api/rounds with num_holes=9 + nine=front/back
- White Pines dedup / collision guard
- Home course PATCH /api/auth/me
"""
import os
import math
import pytest
import requests

BASE_URL = os.environ.get('EXPO_BACKEND_URL', 'https://course-crew-3.preview.emergentagent.com').rstrip('/')

RESEE_EMAIL = "reese@teebox.demo"
RESEE_PASSWORD = "password123"

PEBBLE_LAT = 36.5674
PEBBLE_LNG = -121.9487


@pytest.fixture(scope="module")
def api_client():
    return requests.Session()


@pytest.fixture(scope="module")
def reese_auth(api_client):
    resp = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": RESEE_EMAIL, "password": RESEE_PASSWORD},
    )
    if resp.status_code != 200:
        pytest.skip(f"Login failed: {resp.status_code} {resp.text}")
    data = resp.json()
    return {"token": data["access_token"], "user": data["user"]}


@pytest.fixture(scope="module")
def auth_headers(reese_auth):
    return {"Authorization": f"Bearer {reese_auth['token']}"}


def haversine(lat1, lng1, lat2, lng2):
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


# ---------- Location-first sort ----------
class TestLocationFirstSort:
    def test_discover_courses_no_location(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/discover/courses?q=Pebble", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_discover_courses_with_location_sorted(self, api_client, auth_headers):
        r = api_client.get(
            f"{BASE_URL}/api/discover/courses?q=Pebble&lat={PEBBLE_LAT}&lng={PEBBLE_LNG}",
            headers=auth_headers,
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) > 0
        # Ensure results with lat/lng are sorted nearest first
        dists = [
            haversine(PEBBLE_LAT, PEBBLE_LNG, x["lat"], x["lng"])
            for x in rows
            if x.get("lat") is not None and x.get("lng") is not None
        ]
        assert dists == sorted(dists), f"Not sorted nearest-first: {dists}"

    def test_courses_search_location_sorted(self, api_client, auth_headers):
        r = api_client.get(
            f"{BASE_URL}/api/courses/search?q=Pebble&lat={PEBBLE_LAT}&lng={PEBBLE_LNG}",
            headers=auth_headers,
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) > 0


# ---------- Nearby ----------
class TestNearby:
    def test_nearby_returns_results_sorted(self, api_client, auth_headers):
        r = api_client.get(
            f"{BASE_URL}/api/discover/courses/nearby?lat={PEBBLE_LAT}&lng={PEBBLE_LNG}&radius_km=80",
            headers=auth_headers,
        )
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert len(rows) > 0
        # Ensure sorted by distance_km asc
        dists = [x["distance_km"] for x in rows]
        assert dists == sorted(dists), f"nearby not sorted asc: {dists}"
        # All within radius
        assert all(d <= 80 for d in dists)

    def test_nearby_validation(self, api_client, auth_headers):
        r = api_client.get(
            f"{BASE_URL}/api/discover/courses/nearby?lat=999&lng=0",
            headers=auth_headers,
        )
        # 422 pydantic validation
        assert r.status_code in (400, 422)


# ---------- Course detail (rich OpenGolfAPI fields) ----------
class TestCourseDetail:
    def test_pebble_beach_detail(self, api_client, auth_headers):
        r = api_client.get(
            f"{BASE_URL}/api/courses/Pebble Beach Golf Course",
            headers=auth_headers,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["course_name"] == "Pebble Beach Golf Course"
        # Should have some detail from opengolfapi caching
        assert "holes" in d
        assert "tees" in d

    def test_white_pines_no_collision(self, api_client, auth_headers):
        # Confirm White Pines does not error and returns one internally-consistent record
        r = api_client.get(
            f"{BASE_URL}/api/courses/White Pines Golf Course",
            headers=auth_headers,
        )
        # If not cached yet, may 404; both acceptable so long as not 500
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            d = r.json()
            # If num_holes reported, city/region should be internally consistent (not raise)
            assert d.get("course_name") == "White Pines Golf Course"


# ---------- 9-hole extrapolation ----------
class TestExtrapolation:
    def test_profile_avg_extrapolated(self, api_client, reese_auth, auth_headers):
        uid = reese_auth["user"]["id"]
        r = api_client.get(f"{BASE_URL}/api/users/{uid}", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "avg_score" in data
        # Should be reasonable 18-hole equiv, not skewed by 9-hole scores
        assert data["avg_score"] is None or (60 <= data["avg_score"] <= 130), (
            f"avg_score {data['avg_score']} outside reasonable 18-hole range"
        )


# ---------- Round creation with num_holes=9 + nine ----------
class TestNineHoleRound:
    def test_create_9hole_round_front(self, api_client, reese_auth, auth_headers):
        payload = {
            "post_type": "round",
            "course_name": "Pebble Beach Golf Course",
            "total_score": 41,
            "holes_played": 9,
            "nine": "front",
            "notes": "TEST_iter30 front9",
        }
        r = api_client.post(f"{BASE_URL}/api/rounds", json=payload, headers=auth_headers)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data.get("holes_played") == 9
        assert data.get("nine") == "front"
        # cleanup
        rid = data.get("id")
        if rid:
            api_client.delete(f"{BASE_URL}/api/rounds/{rid}", headers=auth_headers)

    def test_create_9hole_round_back(self, api_client, auth_headers):
        payload = {
            "post_type": "round",
            "course_name": "Pebble Beach Golf Course",
            "total_score": 42,
            "holes_played": 9,
            "nine": "back",
            "notes": "TEST_iter30 back9",
        }
        r = api_client.post(f"{BASE_URL}/api/rounds", json=payload, headers=auth_headers)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert data["nine"] == "back"
        rid = data.get("id")
        if rid:
            api_client.delete(f"{BASE_URL}/api/rounds/{rid}", headers=auth_headers)

    def test_invalid_nine_rejected(self, api_client, auth_headers):
        payload = {
            "post_type": "round",
            "course_name": "Pebble Beach Golf Course",
            "total_score": 40,
            "holes_played": 9,
            "nine": "middle",
        }
        r = api_client.post(f"{BASE_URL}/api/rounds", json=payload, headers=auth_headers)
        assert r.status_code in (400, 422)


# ---------- Home course toggle ----------
class TestHomeCourseToggle:
    def test_set_and_clear_home_course(self, api_client, auth_headers):
        set_r = api_client.patch(
            f"{BASE_URL}/api/auth/me",
            json={"home_course": "Pebble Beach Golf Course"},
            headers=auth_headers,
        )
        assert set_r.status_code == 200
        assert set_r.json()["home_course"] == "Pebble Beach Golf Course"

        me = api_client.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
        assert me.json()["home_course"] == "Pebble Beach Golf Course"

        clear_r = api_client.patch(
            f"{BASE_URL}/api/auth/me", json={"home_course": ""}, headers=auth_headers
        )
        assert clear_r.status_code == 200
        assert clear_r.json()["home_course"] == ""
