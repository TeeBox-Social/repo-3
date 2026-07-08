"""Iter20 backend tests:
- Comment like toggle endpoint (idempotent, persists to liked_by[])
- Comments list surfaces like_count/liked_by_me
- new_achievements on POST /api/rounds (first_round for new user, empty for uneventful subsequent)
- Existing GET /api/users/{id}/achievements shape preserved
- new_achievements surfaced via GET /api/rounds/{id} and /api/feed
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL"
) else os.environ["EXPO_BACKEND_URL"].rstrip("/")


def _register(session, suffix=""):
    tag = f"TEST_iter20_{suffix}_{uuid.uuid4().hex[:8]}"
    payload = {
        "email": f"{tag}@example.com",
        "password": "password12345",
        "display_name": tag,
    }
    r = session.post(f"{BASE_URL}/api/auth/register", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    session.headers["Authorization"] = f"Bearer {data['access_token']}"
    return data["user"]


@pytest.fixture
def user_a():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    u = _register(s, "a")
    return s, u


@pytest.fixture
def user_b():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    u = _register(s, "b")
    return s, u


def _make_round(session, score=85):
    payload = {
        "course_name": f"TEST_Course_{uuid.uuid4().hex[:6]}",
        "total_score": score,
        "par": 72,
        "holes_played": 18,
    }
    r = session.post(f"{BASE_URL}/api/rounds", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- new_achievements ----------
class TestNewAchievements:
    def test_first_round_returns_first_round_achievement(self, user_a):
        s, _ = user_a
        rd = _make_round(s, score=95)  # under 100 → first_round + sub_100
        assert "new_achievements" in rd
        keys = {a["key"] for a in rd["new_achievements"]}
        assert "first_round" in keys, f"expected first_round in {keys}"

    def test_subsequent_uneventful_round_returns_empty(self, user_a):
        s, _ = user_a
        _make_round(s, score=95)  # first
        rd2 = _make_round(s, score=97)  # same course-agnostic; no new badge
        assert rd2["new_achievements"] == [], rd2["new_achievements"]

    def test_new_achievements_persisted_in_feed_and_round(self, user_a):
        s, _ = user_a
        rd = _make_round(s, score=95)
        # Fetch round
        r = s.get(f"{BASE_URL}/api/rounds/{rd['id']}")
        assert r.status_code == 200
        assert isinstance(r.json().get("new_achievements"), list)
        assert len(r.json()["new_achievements"]) >= 1
        # Fetch feed
        f = s.get(f"{BASE_URL}/api/feed?scope=followers")
        assert f.status_code == 200
        feed = f.json()
        matched = [x for x in feed if x["id"] == rd["id"]]
        assert matched and isinstance(matched[0]["new_achievements"], list)
        assert len(matched[0]["new_achievements"]) >= 1


# ---------- comment like ----------
class TestCommentLike:
    def test_toggle_and_persistence(self, user_a, user_b):
        sa, ua = user_a
        sb, ub = user_b
        rd = _make_round(sa, score=95)
        # user_b comments
        cr = sb.post(
            f"{BASE_URL}/api/rounds/{rd['id']}/comments",
            json={"text": "TEST_comment nice round"},
        )
        assert cr.status_code == 200, cr.text
        comment = cr.json()
        cid = comment["id"]
        assert comment["like_count"] == 0
        assert comment["liked_by_me"] is False

        # user_a likes it
        r = sa.post(f"{BASE_URL}/api/rounds/{rd['id']}/comments/{cid}/like")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["liked"] is True
        assert body["like_count"] == 1

        # Idempotent toggle: same user tapping again = unlike
        r2 = sa.post(f"{BASE_URL}/api/rounds/{rd['id']}/comments/{cid}/like")
        assert r2.status_code == 200
        assert r2.json() == {"liked": False, "like_count": 0}

        # Re-like, then verify listing reflects flags for each viewer
        sa.post(f"{BASE_URL}/api/rounds/{rd['id']}/comments/{cid}/like")

        # Viewer A (liker): liked_by_me=True
        la = sa.get(f"{BASE_URL}/api/rounds/{rd['id']}/comments")
        assert la.status_code == 200
        row_a = next(c for c in la.json() if c["id"] == cid)
        assert row_a["like_count"] == 1
        assert row_a["liked_by_me"] is True

        # Viewer B (author of comment, hasn't liked): liked_by_me=False
        lb = sb.get(f"{BASE_URL}/api/rounds/{rd['id']}/comments")
        row_b = next(c for c in lb.json() if c["id"] == cid)
        assert row_b["like_count"] == 1
        assert row_b["liked_by_me"] is False

    def test_like_missing_comment_returns_404(self, user_a):
        sa, _ = user_a
        rd = _make_round(sa, score=95)
        r = sa.post(f"{BASE_URL}/api/rounds/{rd['id']}/comments/does-not-exist/like")
        assert r.status_code == 404


# ---------- achievement endpoint shape preserved ----------
class TestAchievementsEndpoint:
    def test_shape(self, user_a):
        sa, ua = user_a
        _make_round(sa, score=95)
        r = sa.get(f"{BASE_URL}/api/users/{ua['id']}/achievements")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data and "achievements" in data
        assert isinstance(data["achievements"], list)
        assert data["total"] >= 1
        sample = data["achievements"][0]
        for k in ("key", "title", "desc", "icon", "earned"):
            assert k in sample, f"missing {k}"
