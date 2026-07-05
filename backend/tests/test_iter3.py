"""Iteration 3 backend tests: course catalog seed, discover merge, reviews (fractional rating), OSM import."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://tee-social-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def H(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="session")
def reese_token():
    r = requests.post(f"{API}/auth/login", json={"email": "reese@teebox.demo", "password": "password123"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def jordan_token():
    r = requests.post(f"{API}/auth/login", json={"email": "jordan@teebox.demo", "password": "password123"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ---- Seed course catalog ----
def test_course_catalog_seeded_with_famous_courses(reese_token):
    r = requests.get(f"{API}/discover/courses", headers=H(reese_token), timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 30, f"expected >=30 courses, got {len(items)}"
    names = {c["course_name"] for c in items}
    for expected in [
        "Augusta National Golf Club",
        "Bandon Dunes",
        "St Andrews Links — Old Course",
        "Pebble Beach Golf Links",
        "TPC Sawgrass — Stadium Course",
    ]:
        assert expected in names, f"missing seeded course '{expected}'"
    # City/region populated on famous ones
    for c in items:
        if c["course_name"] == "Augusta National Golf Club":
            assert c["city"] == "Augusta"
            assert c["region"] == "GA"
            assert c["country"] == "USA"
            assert c["lat"] is not None and c["lng"] is not None


# ---- Discover merges master + played rounds ----
def test_discover_courses_shape_and_played_first(reese_token):
    # Create a round on a seeded course so play_count > 0
    r = requests.post(f"{API}/rounds", json={"course_name": "Bandon Dunes", "total_score": 88},
                     headers=H(reese_token), timeout=15)
    assert r.status_code == 200
    items = requests.get(f"{API}/discover/courses", headers=H(reese_token), timeout=15).json()
    # Required keys
    for k in ("course_name", "city", "region", "country", "lat", "lng",
              "play_count", "avg_score", "best_score", "review_count", "avg_rating"):
        assert k in items[0], f"missing key {k}"
    # Played courses (play_count>0) sorted first
    played = [c for c in items if c["play_count"] > 0]
    if played:
        first_zero_idx = next((i for i, c in enumerate(items) if c["play_count"] == 0), len(items))
        for i, c in enumerate(items[:first_zero_idx]):
            assert c["play_count"] > 0, f"played course expected first at idx {i}"


# ---- Course detail avg_rating ----
def test_course_detail_avg_rating_null_and_rounded(reese_token, jordan_token):
    # A fresh course with no reviews -> avg_rating null
    fresh = f"TEST_NoReviewCourse_{uuid.uuid4().hex[:6]}"
    # Post a round so it exists in aggregation-friendly way (course detail doesn't require it)
    got = requests.get(f"{API}/courses/{fresh}", headers=H(reese_token), timeout=15)
    assert got.status_code == 200
    assert got.json()["avg_rating"] is None
    assert got.json()["review_count"] == 0

    # Now post 2 reviews of different ratings and verify avg rounds to 2 dp
    course = f"TEST_ReviewCourse_{uuid.uuid4().hex[:6]}"
    r1 = requests.post(f"{API}/courses/reviews",
                       json={"course_name": course, "rating": 4.25, "text": "TEST review A"},
                       headers=H(reese_token), timeout=15)
    assert r1.status_code == 200
    r2 = requests.post(f"{API}/courses/reviews",
                       json={"course_name": course, "rating": 3.75, "text": "TEST review B"},
                       headers=H(jordan_token), timeout=15)
    assert r2.status_code == 200
    det = requests.get(f"{API}/courses/{course}", headers=H(reese_token), timeout=15).json()
    assert det["review_count"] == 2
    assert det["avg_rating"] == 4.0  # (4.25+3.75)/2 = 4.0 -> rounded to 2 dp = 4.0


# ---- Fractional rating validation ----
def test_review_rating_fractional_and_rounding(reese_token):
    course = f"TEST_Frac_{uuid.uuid4().hex[:6]}"
    # 3.6 should be rounded to 3.5
    r = requests.post(f"{API}/courses/reviews",
                      json={"course_name": course, "rating": 3.6, "text": "TEST rounding"},
                      headers=H(reese_token), timeout=15)
    assert r.status_code == 200
    assert r.json()["rating"] == 3.5
    # 4.25 should be stored as-is
    r = requests.post(f"{API}/courses/reviews",
                      json={"course_name": course, "rating": 4.25, "text": "TEST exact"},
                      headers=H(reese_token), timeout=15)
    assert r.status_code == 200
    assert r.json()["rating"] == 4.25


def test_review_rating_out_of_range_rejected(reese_token):
    # Below 1.0
    r = requests.post(f"{API}/courses/reviews",
                      json={"course_name": "TEST_X", "rating": 0.5, "text": "TEST"},
                      headers=H(reese_token), timeout=15)
    assert r.status_code == 422, r.text
    # Above 5.0
    r = requests.post(f"{API}/courses/reviews",
                      json={"course_name": "TEST_X", "rating": 5.5, "text": "TEST"},
                      headers=H(reese_token), timeout=15)
    assert r.status_code == 422, r.text


# ---- Reviews include author.handicap ----
def test_review_list_includes_handicap(reese_token):
    course = f"TEST_HC_{uuid.uuid4().hex[:6]}"
    requests.post(f"{API}/courses/reviews",
                  json={"course_name": course, "rating": 4.0, "text": "TEST hc"},
                  headers=H(reese_token), timeout=15)
    lst = requests.get(f"{API}/courses/{course}/reviews", headers=H(reese_token), timeout=15).json()
    assert len(lst) >= 1
    assert lst[0]["author"] is not None
    assert "handicap" in lst[0]["author"]
    assert lst[0]["author"]["handicap"] == 8.4  # reese's HC


# ---- OSM import ----
def test_osm_import_bad_bbox_returns_400(reese_token):
    r = requests.post(f"{API}/courses/import-osm?bbox=not-a-bbox", headers=H(reese_token), timeout=15)
    assert r.status_code == 400, r.text


def test_osm_import_requires_auth():
    r = requests.post(f"{API}/courses/import-osm?bbox=32.5,-117.5,33.5,-116.5", timeout=15)
    assert r.status_code == 401


def test_osm_import_live_call(reese_token):
    """Live-network call. If Overpass is unreachable, endpoint must return 502."""
    r = requests.post(f"{API}/courses/import-osm?bbox=32.5,-117.5,33.5,-116.5",
                      headers=H(reese_token), timeout=60)
    if r.status_code == 502:
        pytest.skip("Overpass API unreachable from backend — endpoint correctly returned 502")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "inserted" in data
    assert "total_courses" in data
    assert isinstance(data["inserted"], int)
    assert data["total_courses"] >= 30
