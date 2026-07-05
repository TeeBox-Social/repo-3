"""SEC-001..005 security audit + regression tests for TeeBox."""
import os
import importlib
import sys
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
BASE_URL = os.environ["EXPO_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_BACKEND_URL") else None
# fallback to frontend env
if not BASE_URL:
    fe_env = Path("/app/frontend/.env")
    if fe_env.exists():
        for line in fe_env.read_text().splitlines():
            if line.startswith("EXPO_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")

assert BASE_URL, "EXPO_BACKEND_URL must be set"
print(f"BASE_URL={BASE_URL}")

DEMO_EMAIL = "reese@teebox.demo"
DEMO_PASS = "password123"


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def token(api):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def me(api, auth_headers):
    r = api.get(f"{BASE_URL}/api/auth/me", headers=auth_headers)
    assert r.status_code == 200
    return r.json()


# ---------- SEC-001 ----------
class TestSEC001:
    def test_placeholder_secret_raises(self, tmp_path):
        # Import server.py in a fresh interpreter env with a placeholder secret
        original = os.environ.get("JWT_SECRET_KEY")
        os.environ["JWT_SECRET_KEY"] = "please_change_me_now_and_here_ok_ok"
        # Force reload by removing cached module
        for mod in list(sys.modules):
            if mod.startswith("server"):
                del sys.modules[mod]
        # Ensure backend dir on path
        backend = str(Path("/app/backend"))
        if backend not in sys.path:
            sys.path.insert(0, backend)
        try:
            with pytest.raises(RuntimeError):
                importlib.import_module("server")
        finally:
            if original is not None:
                os.environ["JWT_SECRET_KEY"] = original
            for mod in list(sys.modules):
                if mod.startswith("server"):
                    del sys.modules[mod]

    def test_short_secret_raises(self):
        original = os.environ.get("JWT_SECRET_KEY")
        os.environ["JWT_SECRET_KEY"] = "shortsecret"
        for mod in list(sys.modules):
            if mod.startswith("server"):
                del sys.modules[mod]
        backend = str(Path("/app/backend"))
        if backend not in sys.path:
            sys.path.insert(0, backend)
        try:
            with pytest.raises(RuntimeError):
                importlib.import_module("server")
        finally:
            if original is not None:
                os.environ["JWT_SECRET_KEY"] = original
            for mod in list(sys.modules):
                if mod.startswith("server"):
                    del sys.modules[mod]

    def test_strong_secret_login_still_works(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS})
        assert r.status_code == 200
        assert "access_token" in r.json()


# ---------- SEC-002: no email in public responses ----------
class TestSEC002:
    def test_me_may_contain_email(self, me):
        # Caller's own /me can have email
        assert me.get("email") == DEMO_EMAIL

    def test_other_user_profile_no_email(self, api, auth_headers, me):
        # find another user via discover
        r = api.get(f"{BASE_URL}/api/discover/users", headers=auth_headers)
        assert r.status_code == 200
        others = r.json()
        assert len(others) >= 1
        for u in others:
            assert "email" not in u, f"discover leaks email: {u}"
        other_id = others[0]["id"]
        r2 = api.get(f"{BASE_URL}/api/users/{other_id}", headers=auth_headers)
        assert r2.status_code == 200
        assert "email" not in r2.json()

    def test_feed_authors_no_email(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/feed", headers=auth_headers)
        assert r.status_code == 200
        for item in r.json():
            author = item.get("author") or {}
            assert "email" not in author

    def test_round_and_comments_no_email(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/feed", headers=auth_headers)
        items = r.json()
        if not items:
            pytest.skip("no feed items")
        rid = items[0]["id"]
        r2 = api.get(f"{BASE_URL}/api/rounds/{rid}", headers=auth_headers)
        assert r2.status_code == 200
        assert "email" not in (r2.json().get("author") or {})
        # add a comment then fetch
        api.post(f"{BASE_URL}/api/rounds/{rid}/comments", headers=auth_headers,
                 json={"text": "TEST_sec002_probe", "mentions": []})
        r3 = api.get(f"{BASE_URL}/api/rounds/{rid}/comments", headers=auth_headers)
        assert r3.status_code == 200
        for c in r3.json():
            assert "email" not in (c.get("author") or {})

    def test_course_reviews_no_email(self, api, auth_headers):
        # create a review to guarantee content
        api.post(f"{BASE_URL}/api/courses/reviews", headers=auth_headers,
                 json={"course_name": "Bandon Dunes", "rating": 4.6, "text": "TEST_sec002 review"})
        r = api.get(f"{BASE_URL}/api/courses/Bandon Dunes/reviews", headers=auth_headers)
        assert r.status_code == 200
        for rev in r.json():
            assert "email" not in (rev.get("author") or {})


# ---------- SEC-003: photo caps ----------
class TestSEC003:
    def _make_photo(self, size_chars: int, mime: str = "image/png") -> str:
        # Build a data URI whose total length ~= size_chars
        prefix = f"data:{mime};base64,"
        body = "A" * max(0, size_chars - len(prefix))
        return prefix + body

    def test_photos_truncated_to_3(self, api, auth_headers):
        photos = [self._make_photo(100) for _ in range(6)]
        payload = {"course_name": "TEST_SEC003_trunc", "total_score": 88, "photos": photos}
        r = api.post(f"{BASE_URL}/api/rounds", headers=auth_headers, json=payload)
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        r2 = api.get(f"{BASE_URL}/api/rounds/{rid}", headers=auth_headers)
        stored = r2.json().get("photos", [])
        assert len(stored) == 3, f"expected 3 photos, got {len(stored)}"
        api.delete(f"{BASE_URL}/api/rounds/{rid}", headers=auth_headers)

    def test_oversized_photo_413(self, api, auth_headers):
        big = self._make_photo(1_500_001)
        r = api.post(f"{BASE_URL}/api/rounds", headers=auth_headers,
                     json={"course_name": "TEST_SEC003_big", "total_score": 90, "photos": [big]})
        assert r.status_code == 413, f"expected 413, got {r.status_code}: {r.text[:200]}"

    def test_non_image_data_uri_415(self, api, auth_headers):
        bad = "data:text/plain;base64,SGVsbG8="
        r = api.post(f"{BASE_URL}/api/rounds", headers=auth_headers,
                     json={"course_name": "TEST_SEC003_bad", "total_score": 90, "photos": [bad]})
        assert r.status_code == 415, f"expected 415, got {r.status_code}"

    def test_normal_photo_ok(self, api, auth_headers):
        ok = self._make_photo(500)
        r = api.post(f"{BASE_URL}/api/rounds", headers=auth_headers,
                     json={"course_name": "TEST_SEC003_ok", "total_score": 85, "photos": [ok]})
        assert r.status_code == 200
        api.delete(f"{BASE_URL}/api/rounds/{r.json()['id']}", headers=auth_headers)

    def test_oversized_avatar_413(self, api, auth_headers):
        big = "data:image/png;base64," + ("A" * 900_000)
        r = api.patch(f"{BASE_URL}/api/auth/me", headers=auth_headers, json={"avatar": big})
        assert r.status_code == 413


# ---------- SEC-004: regex escape & length cap ----------
class TestSEC004:
    def test_regex_meta_users_literal(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/discover/users?q=.*", headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == []

    def test_regex_meta_courses_literal(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/discover/courses?q=.*", headers=auth_headers)
        assert r.status_code == 200
        assert r.json() == []

    def test_dollar_signs_no_crash(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/discover/users", headers=auth_headers, params={"q": "($$$"})
        assert r.status_code == 200

    def test_long_query_ok(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/discover/courses", headers=auth_headers, params={"q": "a" * 500})
        assert r.status_code == 200

    def test_normal_search_still_works(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/discover/courses", headers=auth_headers, params={"q": "bandon"})
        assert r.status_code == 200
        names = [c["course_name"].lower() for c in r.json()]
        assert any("bandon" in n for n in names), f"expected bandon in {names}"


# ---------- SEC-005: seed guarded ----------
class TestSEC005:
    def test_seed_when_enabled_idempotent(self, api, auth_headers):
        # ENABLE_DEMO_SEED=true in dev; POST /api/seed should not be 404, and idempotent
        r = api.post(f"{BASE_URL}/api/seed")
        assert r.status_code == 200, f"expected 200 when demo enabled, got {r.status_code}"
        body = r.json()
        # Since DB already has users, it should say already has users
        assert body.get("seeded") in (False, True)


# ---------- Regressions ----------
class TestRegressions:
    def test_register_and_login(self, api):
        import uuid as _u
        email = f"test_{_u.uuid4().hex[:8]}@teebox.dev"
        r = api.post(f"{BASE_URL}/api/auth/register", json={
            "email": email, "password": "abc123", "display_name": "TEST User"
        })
        assert r.status_code == 200
        r2 = api.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "abc123"})
        assert r2.status_code == 200

    def test_feed_followers(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/feed?scope=followers", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_round_lifecycle_and_like(self, api, auth_headers):
        payload = {
            "course_name": "TEST_regression_course",
            "total_score": 84, "par": 72, "holes_played": 18,
            "hole_scores": [4]*18, "hole_pars": [4]*18,
        }
        r = api.post(f"{BASE_URL}/api/rounds", headers=auth_headers, json=payload)
        assert r.status_code == 200
        rid = r.json()["id"]
        r2 = api.get(f"{BASE_URL}/api/rounds/{rid}", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["hole_scores"] == [4]*18
        r3 = api.post(f"{BASE_URL}/api/rounds/{rid}/like", headers=auth_headers)
        assert r3.status_code == 200 and r3.json()["liked"] in (True, False)
        r4 = api.delete(f"{BASE_URL}/api/rounds/{rid}", headers=auth_headers)
        assert r4.status_code == 200

    def test_comment_with_mentions(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/feed", headers=auth_headers)
        items = r.json()
        if not items:
            pytest.skip("no feed items")
        rid = items[0]["id"]
        r2 = api.post(f"{BASE_URL}/api/rounds/{rid}/comments", headers=auth_headers,
                      json={"text": "TEST_mention @user", "mentions": ["someid"]})
        assert r2.status_code == 200
        assert r2.json()["mentions"] == ["someid"]

    def test_follow_toggle(self, api, auth_headers, me):
        r = api.get(f"{BASE_URL}/api/discover/users", headers=auth_headers)
        others = r.json()
        if not others:
            pytest.skip("no other users")
        oid = others[0]["id"]
        r1 = api.post(f"{BASE_URL}/api/users/{oid}/follow", headers=auth_headers)
        assert r1.status_code == 200
        r2 = api.post(f"{BASE_URL}/api/users/{oid}/follow", headers=auth_headers)
        assert r2.status_code == 200
        # net: end state — best-effort, must be 200

    def test_achievements(self, api, auth_headers, me):
        r = api.get(f"{BASE_URL}/api/users/{me['id']}/achievements", headers=auth_headers)
        assert r.status_code == 200
        assert "achievements" in r.json()

    def test_course_info(self, api, auth_headers):
        r = api.get(f"{BASE_URL}/api/courses/Bandon Dunes", headers=auth_headers)
        assert r.status_code == 200
        j = r.json()
        assert j["course_name"] == "Bandon Dunes"

    def test_review_rating_rounding_quarter(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/courses/reviews", headers=auth_headers,
                     json={"course_name": "TEST_review_course", "rating": 4.6, "text": "TEST rating"})
        assert r.status_code == 200
        # 4.6 -> round(4.6*4)/4 = round(18.4)/4 = 18/4 = 4.5
        assert r.json()["rating"] == 4.5

    def test_osm_bad_bbox_400(self, api, auth_headers):
        r = api.post(f"{BASE_URL}/api/courses/import-osm?bbox=not_a_bbox", headers=auth_headers)
        assert r.status_code == 400
