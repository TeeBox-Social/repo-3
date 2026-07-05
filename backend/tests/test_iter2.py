"""Iteration 2 backend tests: feed scope, course rounds, hole_scores, mentions, achievements, seed."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://tee-social-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def H(t):
    return {"Authorization": f"Bearer {t}"}


def _register(email=None, name="TEST User"):
    email = email or f"t_{uuid.uuid4().hex[:8]}@teebox.demo"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "password123", "display_name": name
    }, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    return data["access_token"], data["user"]


@pytest.fixture(scope="session")
def demo_token():
    r = requests.post(f"{API}/auth/login", json={"email": "reese@teebox.demo", "password": "password123"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ---- Seed sanity: mutual follows exist between 3 demo users ----
def test_seed_demo_users_and_mutual_follows(demo_token):
    r = requests.get(f"{API}/discover/users", headers=H(demo_token), timeout=15)
    assert r.status_code == 200
    users = r.json()
    demo_emails = {u["email"] for u in users if u.get("email", "").endswith("@teebox.demo") and u["email"] != "reese@teebox.demo"}
    # Jordan and Sam must be discoverable
    assert "jordan@teebox.demo" in demo_emails
    assert "sam@teebox.demo" in demo_emails
    # Reese should be following jordan & sam per seed
    for u in users:
        if u["email"] in ("jordan@teebox.demo", "sam@teebox.demo"):
            prof = requests.get(f"{API}/users/{u['id']}", headers=H(demo_token), timeout=15).json()
            assert prof["is_following"] is True, f"Reese should follow {u['email']}"


# ---- Feed scope=followers ----
def test_feed_followers_scope_isolated():
    # Two new users; A follows B; A's followers feed should contain B's round + own, not stranger's
    tok_a, ua = _register(name="TEST_A")
    tok_b, ub = _register(name="TEST_B")
    tok_c, uc = _register(name="TEST_C")  # stranger

    # A follows B
    r = requests.post(f"{API}/users/{ub['id']}/follow", headers=H(tok_a), timeout=15)
    assert r.status_code == 200

    # B and C each create a round
    r_b = requests.post(f"{API}/rounds", json={"course_name": "TEST_CourseB", "total_score": 84}, headers=H(tok_b), timeout=15)
    r_c = requests.post(f"{API}/rounds", json={"course_name": "TEST_CourseC", "total_score": 88}, headers=H(tok_c), timeout=15)
    assert r_b.status_code == 200 and r_c.status_code == 200
    b_round_id = r_b.json()["id"]
    c_round_id = r_c.json()["id"]

    # A's followers feed
    feed = requests.get(f"{API}/feed", headers=H(tok_a), timeout=15).json()
    ids = {x["id"] for x in feed}
    assert b_round_id in ids, "B's round should appear in A's followers feed"
    assert c_round_id not in ids, "C's round must NOT appear (stranger)"


def test_feed_scope_all_returns_more(demo_token):
    all_feed = requests.get(f"{API}/feed", headers=H(demo_token), params={"scope": "all"}, timeout=15).json()
    followers_feed = requests.get(f"{API}/feed", headers=H(demo_token), timeout=15).json()
    assert isinstance(all_feed, list)
    assert isinstance(followers_feed, list)
    # scope=all should be >= followers
    assert len(all_feed) >= len(followers_feed)


# ---- Course rounds ----
def test_course_rounds_endpoint(demo_token):
    # Create a round on a shared TEST course
    course = f"TEST_Course_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/rounds", json={"course_name": course, "total_score": 77}, headers=H(demo_token), timeout=15)
    assert r.status_code == 200
    rr = requests.get(f"{API}/courses/{course}/rounds", headers=H(demo_token), timeout=15)
    assert rr.status_code == 200
    items = rr.json()
    assert isinstance(items, list) and len(items) >= 1
    assert items[0]["course_name"] == course
    assert items[0]["author"] is not None


# ---- Hole scores/pars persistence ----
def test_hole_scores_and_pars_roundtrip(demo_token):
    hs = [4, 5, 3, 4, 4, 5, 3, 4, 4, 4, 5, 3, 4, 4, 5, 4, 3, 5]
    hp = [4, 5, 3, 4, 4, 5, 3, 4, 4, 4, 5, 3, 4, 4, 5, 4, 3, 5]
    payload = {"course_name": "TEST_HoleCourse", "total_score": sum(hs), "hole_scores": hs, "hole_pars": hp}
    r = requests.post(f"{API}/rounds", json=payload, headers=H(demo_token), timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["hole_scores"] == hs
    assert data["hole_pars"] == hp
    # GET back and confirm
    got = requests.get(f"{API}/rounds/{data['id']}", headers=H(demo_token), timeout=15).json()
    assert got["hole_scores"] == hs
    assert got["hole_pars"] == hp


# ---- Comments with mentions ----
def test_comments_with_mentions(demo_token):
    # Create a round on demo user, then comment with mentions
    r = requests.post(f"{API}/rounds", json={"course_name": "TEST_MentionCourse", "total_score": 80},
                     headers=H(demo_token), timeout=15)
    rid = r.json()["id"]
    # Grab another user id from discover
    users = requests.get(f"{API}/discover/users", headers=H(demo_token), timeout=15).json()
    mention_id = users[0]["id"]
    cr = requests.post(f"{API}/rounds/{rid}/comments",
                     json={"text": "Great round @Jordan", "mentions": [mention_id]},
                     headers=H(demo_token), timeout=15)
    assert cr.status_code == 200
    assert cr.json()["mentions"] == [mention_id]
    lst = requests.get(f"{API}/rounds/{rid}/comments", headers=H(demo_token), timeout=15).json()
    assert any(c.get("mentions") == [mention_id] for c in lst)


# ---- Achievements ----
def test_achievements_computation_new_user():
    tok, u = _register(name="TEST_Ach")
    # Post rounds 82, 74, 96, 79 across a couple courses (2 unique => not course_collector)
    for course, score in [("TEST_A", 82), ("TEST_B", 74), ("TEST_A", 96), ("TEST_B", 79)]:
        r = requests.post(f"{API}/rounds", json={"course_name": course, "total_score": score},
                         headers=H(tok), timeout=15)
        assert r.status_code == 200
    ach = requests.get(f"{API}/users/{u['id']}/achievements", headers=H(tok), timeout=15)
    assert ach.status_code == 200
    data = ach.json()
    assert "total" in data and "achievements" in data
    by_key = {a["key"]: a["earned"] for a in data["achievements"]}
    # Earned
    assert by_key["first_round"] is True
    assert by_key["sub_100"] is True
    assert by_key["sub_90"] is True
    assert by_key["sub_80"] is True
    # Not earned
    assert by_key["sub_70"] is False
    assert by_key["ten_rounds"] is False
    assert by_key["fifty_rounds"] is False
    assert by_key["course_collector"] is False
    # Streak: 82, 74, 96, 79 -- 74 alone(1), then break at 96, then 79(1). best_streak = 1 -> not earned
    assert by_key["hot_streak"] is False
