"""TeeBox backend API test suite."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://tee-social-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "reese@teebox.demo"
DEMO_PASS = "password123"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def me(token):
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=15)
    assert r.status_code == 200
    return r.json()


def H(t):
    return {"Authorization": f"Bearer {t}"}


# ---- Health ----
def test_health():
    r = requests.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---- Auth ----
def test_register_new_and_duplicate():
    email = f"test_{uuid.uuid4().hex[:8]}@teebox.demo"
    payload = {"email": email, "password": "password123", "display_name": "TEST User"}
    r = requests.post(f"{API}/auth/register", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data and "user" in data
    assert data["user"]["email"] == email
    assert "hashed_password" not in data["user"]
    assert "_id" not in data["user"]
    # duplicate
    r2 = requests.post(f"{API}/auth/register", json=payload, timeout=15)
    assert r2.status_code == 400


def test_login_demo(token):
    assert isinstance(token, str) and len(token) > 20


def test_me_returns_user_no_sensitive(me):
    assert me["email"] == DEMO_EMAIL
    assert "hashed_password" not in me
    assert "_id" not in me


def test_unauthenticated_endpoints_401():
    for path in ["/auth/me", "/feed", "/discover/users", "/discover/courses"]:
        r = requests.get(f"{API}{path}", timeout=15)
        assert r.status_code in (401, 403), f"{path} => {r.status_code}"


# ---- Feed ----
def test_feed_has_expected_fields(token):
    r = requests.get(f"{API}/feed", headers=H(token), timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and len(items) >= 1
    it = items[0]
    for k in ("author", "like_count", "comment_count", "liked_by_me", "course_name", "total_score"):
        assert k in it


# ---- Rounds create/get/delete + enrich ----
@pytest.fixture(scope="session")
def created_round(token):
    payload = {"course_name": "TEST Course", "total_score": 85, "par": 72, "notes": "TEST"}
    r = requests.post(f"{API}/rounds", json=payload, headers=H(token), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["author"] is not None
    assert data["like_count"] == 0 and data["comment_count"] == 0
    return data


def test_get_round(created_round, token):
    rid = created_round["id"]
    r = requests.get(f"{API}/rounds/{rid}", headers=H(token), timeout=15)
    assert r.status_code == 200
    assert r.json()["id"] == rid


def test_delete_forbidden_for_non_owner(created_round, token):
    # Register another user
    email = f"other_{uuid.uuid4().hex[:8]}@teebox.demo"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "password123", "display_name": "Other"}, timeout=15)
    other_tok = r.json()["access_token"]
    r2 = requests.delete(f"{API}/rounds/{created_round['id']}", headers=H(other_tok), timeout=15)
    assert r2.status_code == 403


# ---- Like toggle ----
def test_like_toggle(created_round, token):
    rid = created_round["id"]
    r1 = requests.post(f"{API}/rounds/{rid}/like", headers=H(token), timeout=15)
    assert r1.status_code == 200
    assert r1.json()["liked"] is True
    r2 = requests.post(f"{API}/rounds/{rid}/like", headers=H(token), timeout=15)
    assert r2.json()["liked"] is False


# ---- Comments ----
def test_add_and_get_comment(created_round, token):
    rid = created_round["id"]
    r = requests.post(f"{API}/rounds/{rid}/comments", json={"text": "TEST comment"}, headers=H(token), timeout=15)
    assert r.status_code == 200
    assert r.json()["author"]["display_name"]
    r2 = requests.get(f"{API}/rounds/{rid}/comments", headers=H(token), timeout=15)
    assert r2.status_code == 200
    items = r2.json()
    assert any(c["text"] == "TEST comment" for c in items)
    assert items[0]["author"] is not None


# ---- User profile ----
def test_user_profile_fields(me, token):
    r = requests.get(f"{API}/users/{me['id']}", headers=H(token), timeout=15)
    assert r.status_code == 200
    prof = r.json()
    for k in ("round_count", "avg_score", "best_score", "follower_count", "is_following", "is_me"):
        assert k in prof
    assert prof["is_me"] is True


# ---- Follow ----
def test_follow_toggle_and_self(me, token):
    # cannot follow self
    r = requests.post(f"{API}/users/{me['id']}/follow", headers=H(token), timeout=15)
    assert r.status_code == 400
    # find another
    u = requests.get(f"{API}/discover/users", headers=H(token), timeout=15).json()
    assert len(u) >= 1
    other_id = u[0]["id"]
    r1 = requests.post(f"{API}/users/{other_id}/follow", headers=H(token), timeout=15)
    assert r1.json()["following"] is True
    r2 = requests.post(f"{API}/users/{other_id}/follow", headers=H(token), timeout=15)
    assert r2.json()["following"] is False


# ---- Discover ----
def test_discover_users_excludes_self(me, token):
    r = requests.get(f"{API}/discover/users", headers=H(token), timeout=15, params={"q": "j"})
    assert r.status_code == 200
    ids = [u["id"] for u in r.json()]
    assert me["id"] not in ids


def test_discover_courses_aggregates(token):
    r = requests.get(f"{API}/discover/courses", headers=H(token), timeout=15)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and len(items) >= 1
    for k in ("course_name", "play_count", "avg_score", "best_score"):
        assert k in items[0]


# ---- Course reviews ----
def test_course_review_create_and_list(token):
    payload = {"course_name": "TEST Course", "rating": 5, "text": "TEST great course"}
    r = requests.post(f"{API}/courses/reviews", json=payload, headers=H(token), timeout=15)
    assert r.status_code == 200
    r2 = requests.get(f"{API}/courses/TEST Course/reviews", headers=H(token), timeout=15)
    assert r2.status_code == 200
    items = r2.json()
    assert any(x["text"] == "TEST great course" for x in items)
    assert items[0]["author"] is not None
