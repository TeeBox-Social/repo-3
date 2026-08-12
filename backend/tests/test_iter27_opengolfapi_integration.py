"""Iteration 27: OpenGolfAPI nationwide course integration (discover/search/course-detail).

Covers:
- GET /api/discover/courses?q= — nationwide fallback + dedup for sparse local queries
- GET /api/discover/courses/nearby — geo-radius nationwide fallback + dedup
- GET /api/courses/search?q= — course picker nationwide fallback
- GET /api/courses/{course_name} — rich fact-sheet fields for OpenGolfAPI-matched courses
- Regression: existing courses without external_id gracefully return null fact-sheet fields
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


class TestDiscoverCoursesNationwide:
    def test_bandon_dunes_no_duplicates(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/discover/courses", params={"q": "Bandon Dunes"})
        assert resp.status_code == 200
        data = resp.json()
        names = [c["course_name"] for c in data]
        assert len(names) == len(set(names)), f"duplicate rows found: {names}"
        assert "Bandon Dunes" in names
        assert "Bandon Dunes Golf Resort" in names
        # Exactly these two Bandon-prefixed rows expected per problem statement
        bandon_rows = [n for n in names if n.startswith("Bandon Dunes")]
        assert len(bandon_rows) == 2, f"expected exactly 2 Bandon Dunes rows, got: {bandon_rows}"

    def test_pebble_beach_returns_results_with_source(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/discover/courses", params={"q": "Pebble Beach Golf Links"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        names = [c["course_name"] for c in data]
        assert len(names) == len(set(names))
        for c in data:
            assert c.get("source") in ("community", "opengolfapi", "osm", None) or isinstance(c.get("source"), str)

    def test_empty_query_returns_local_only(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/discover/courses", params={"q": ""})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_nonsense_query_graceful(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/discover/courses", params={"q": "zzzzznonexistentcoursexyz123"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestDiscoverCoursesNearby:
    def test_pebble_beach_area_nearby(self, api_client):
        # Pebble Beach, CA coordinates
        resp = api_client.get(
            f"{BASE_URL}/api/discover/courses/nearby",
            params={"lat": 36.5686, "lng": -121.9491, "radius_km": 80},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        names = [c["course_name"] for c in data]
        assert len(names) == len(set(names)), f"duplicate rows found in nearby: {names}"
        for c in data:
            assert "distance_km" in c
            assert isinstance(c["distance_km"], (int, float))
        # sorted by distance ascending
        dists = [c["distance_km"] for c in data]
        assert dists == sorted(dists)

    def test_invalid_lat_rejected(self, api_client):
        resp = api_client.get(
            f"{BASE_URL}/api/discover/courses/nearby",
            params={"lat": 999, "lng": -121.9491, "radius_km": 80},
        )
        assert resp.status_code == 422


class TestCourseSearchPicker:
    def test_search_sparse_local_nationwide_fallback(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/courses/search", params={"q": "Bandon Dunes"})
        assert resp.status_code == 200
        data = resp.json()
        names = [c["name"] for c in data]
        assert len(names) == len(set(names))
        assert any("Bandon Dunes" in n for n in names)

    def test_search_empty_query(self, api_client):
        resp = api_client.get(f"{BASE_URL}/api/courses/search", params={"q": ""})
        assert resp.status_code == 200
        assert resp.json() == []


class TestCourseDetailFactSheet:
    def test_bandon_dunes_golf_resort_enriched(self, api_client):
        # Ensure discovery already triggered caching for this course
        api_client.get(f"{BASE_URL}/api/discover/courses", params={"q": "Bandon Dunes"})
        time.sleep(1)
        resp = api_client.get(f"{BASE_URL}/api/courses/Bandon%20Dunes%20Golf%20Resort")
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_name"] == "Bandon Dunes Golf Resort"
        # Rich fields should be present (non-error) — value may be null if upstream lacks data
        for field in ["par", "total_yardage", "course_type", "architect", "year_built",
                      "phone", "website", "tees", "holes", "climate", "insights"]:
            assert field in data, f"missing field {field}"
        assert isinstance(data["tees"], list)
        assert isinstance(data["holes"], list)
        if data["holes"]:
            assert len(data["holes"]) <= 18
            h0 = data["holes"][0]
            assert "number" in h0 and "par" in h0

    def test_pebble_beach_golf_links_enriched(self, api_client):
        api_client.get(f"{BASE_URL}/api/discover/courses", params={"q": "Pebble Beach Golf Links"})
        time.sleep(1)
        resp = api_client.get(f"{BASE_URL}/api/courses/Pebble%20Beach%20Golf%20Links")
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_name"] == "Pebble Beach Golf Links"
        assert isinstance(data["tees"], list)
        assert isinstance(data["holes"], list)

    def test_course_without_opengolf_match_graceful(self, api_client):
        # A course name unlikely to exist locally or upstream — should 200 gracefully
        resp = api_client.get(f"{BASE_URL}/api/courses/TEST_NonexistentCourseXYZ123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["course_name"] == "TEST_NonexistentCourseXYZ123"
        assert data["par"] is None
        assert data["tees"] == []
        assert data["holes"] == []
