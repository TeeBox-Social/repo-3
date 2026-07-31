"""
Tests for Log Round refactor + achievement hole-count split.

Covers:
  - POST /api/rounds with holes_played=9, par=36
  - POST /api/rounds with holes_played=18, par=72
  - GET /api/users/{id}/achievements returns new keys and correct earn state
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://course-crew-3.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str = "password123") -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    body = r.json()
    return body.get("access_token") or body.get("token")


@pytest.fixture(scope="module")
def jordan_auth():
    tok = _login("jordan@teebox.demo")
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    assert r.status_code == 200
    return {"token": tok, "id": r.json()["id"], "headers": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture(scope="module")
def sam_auth():
    tok = _login("sam@teebox.demo")
    r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    assert r.status_code == 200
    return {"token": tok, "id": r.json()["id"], "headers": {"Authorization": f"Bearer {tok}"}}


# -- Basic auth sanity
class TestAuthSanity:
    def test_jordan_login(self, jordan_auth):
        assert jordan_auth["id"]

    def test_sam_login(self, sam_auth):
        assert sam_auth["id"]


# -- Rounds: verify holes_played=9 with par=36 is accepted
class TestRoundsPost:
    def test_create_9_hole_round(self, jordan_auth):
        payload = {
            "course_name": f"TEST 9h Course {uuid.uuid4().hex[:6]}",
            "total_score": 41,
            "par": 36,
            "holes_played": 9,
            "notes": "TEST 9-hole",
            "photos": [],
            "hole_scores": [],
        }
        r = requests.post(f"{API}/rounds", json=payload, headers=jordan_auth["headers"], timeout=20)
        assert r.status_code in (200, 201), f"POST /rounds failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("holes_played") == 9
        assert body.get("par") == 36
        assert body.get("total_score") == 41

    def test_create_18_hole_round(self, jordan_auth):
        payload = {
            "course_name": f"TEST 18h Course {uuid.uuid4().hex[:6]}",
            "total_score": 82,
            "par": 72,
            "holes_played": 18,
            "notes": "TEST 18-hole",
            "photos": [],
            "hole_scores": [],
        }
        r = requests.post(f"{API}/rounds", json=payload, headers=jordan_auth["headers"], timeout=20)
        assert r.status_code in (200, 201)
        body = r.json()
        assert body.get("holes_played") == 18
        assert body.get("par") == 72


# -- Achievements: new keys, hole-count aware behaviour
class TestAchievements:
    def test_achievement_keys_present(self, jordan_auth):
        r = requests.get(
            f"{API}/users/{jordan_auth['id']}/achievements",
            headers=jordan_auth["headers"],
            timeout=20,
        )
        assert r.status_code == 200
        body = r.json()
        keys = {d["key"] for d in body["achievements"]}
        for k in ("sub_50_9", "sub_45_9", "sub_40_9", "sub_par_9", "hot_streak_9",
                  "sub_100", "sub_90", "sub_80", "sub_70", "hot_streak"):
            assert k in keys, f"Missing achievement key: {k}"

    def test_sub_100_description_mentions_18_hole(self, jordan_auth):
        r = requests.get(
            f"{API}/users/{jordan_auth['id']}/achievements",
            headers=jordan_auth["headers"],
            timeout=20,
        )
        body = r.json()
        sub100 = next(d for d in body["achievements"] if d["key"] == "sub_100")
        assert "18-hole" in sub100["desc"], f"sub_100 desc should mention 18-hole, got: {sub100['desc']}"

    def test_9_hole_user_earns_sub_50_9_but_not_sub_100(self, sam_auth):
        """Sam gets a fresh isolated 9-hole round.
        Note: Sam may have existing rounds from seed data — we only assert the direction
        of the achievement given at least one 9-hole round scoring <50.
        """
        payload = {
            "course_name": f"TEST Sam 9h {uuid.uuid4().hex[:6]}",
            "total_score": 41,
            "par": 36,
            "holes_played": 9,
            "notes": "TEST sam 9-hole",
            "photos": [],
            "hole_scores": [],
        }
        r = requests.post(f"{API}/rounds", json=payload, headers=sam_auth["headers"], timeout=20)
        assert r.status_code in (200, 201)

        # Now fetch achievements
        r = requests.get(
            f"{API}/users/{sam_auth['id']}/achievements",
            headers=sam_auth["headers"],
            timeout=20,
        )
        body = r.json()
        by_key = {d["key"]: d for d in body["achievements"]}
        assert by_key["sub_50_9"]["earned"] is True, "Should have earned sub_50_9 after 41 on par-36 9-hole round"

    def test_only_9_hole_rounds_do_not_award_18_hole_badges(self):
        """Create a brand-new user whose ONLY round is 9-hole/41 — sub_100 must NOT be earned."""
        email = f"test9only_{uuid.uuid4().hex[:8]}@teebox.demo"
        password = "password123"
        reg = requests.post(f"{API}/auth/register", json={
            "email": email, "password": password, "display_name": "TEST 9hOnly"
        }, timeout=20)
        assert reg.status_code in (200, 201), f"register failed: {reg.status_code} {reg.text}"
        tok = reg.json().get("access_token") or reg.json().get("token")
        assert tok, f"register response missing token: {reg.text[:200]}"
        headers = {"Authorization": f"Bearer {tok}"}
        me = requests.get(f"{API}/auth/me", headers=headers, timeout=15).json()
        uid = me["id"]

        # Log ONE 9-hole round
        payload = {
            "course_name": f"TEST 9only {uuid.uuid4().hex[:6]}",
            "total_score": 41, "par": 36, "holes_played": 9,
            "notes": "TEST", "photos": [], "hole_scores": [],
        }
        r = requests.post(f"{API}/rounds", json=payload, headers=headers, timeout=20)
        assert r.status_code in (200, 201)

        r = requests.get(f"{API}/users/{uid}/achievements", headers=headers, timeout=20)
        body = r.json()
        by_key = {d["key"]: d for d in body["achievements"]}
        assert by_key["sub_50_9"]["earned"] is True
        assert by_key["sub_100"]["earned"] is False, "sub_100 must not be earned from a 9-hole round"
        assert by_key["sub_90"]["earned"] is False
        assert by_key["sub_80"]["earned"] is False
        assert by_key["hot_streak"]["earned"] is False

    def test_great_18_hole_round_does_not_award_9_hole_badges(self):
        """Create a new user whose only round is an 18-hole/85 — sub_50_9 should NOT be earned."""
        email = f"test18only_{uuid.uuid4().hex[:8]}@teebox.demo"
        password = "password123"
        reg = requests.post(f"{API}/auth/register", json={
            "email": email, "password": password, "display_name": "TEST 18hOnly"
        }, timeout=20)
        assert reg.status_code in (200, 201)
        tok = reg.json().get("access_token") or reg.json().get("token")
        assert tok, f"register response missing token: {reg.text[:200]}"
        headers = {"Authorization": f"Bearer {tok}"}
        uid = requests.get(f"{API}/auth/me", headers=headers, timeout=15).json()["id"]

        payload = {
            "course_name": f"TEST 18only {uuid.uuid4().hex[:6]}",
            "total_score": 85, "par": 72, "holes_played": 18,
            "notes": "TEST", "photos": [], "hole_scores": [],
        }
        r = requests.post(f"{API}/rounds", json=payload, headers=headers, timeout=20)
        assert r.status_code in (200, 201)

        r = requests.get(f"{API}/users/{uid}/achievements", headers=headers, timeout=20)
        body = r.json()
        by_key = {d["key"]: d for d in body["achievements"]}
        assert by_key["sub_100"]["earned"] is True
        assert by_key["sub_90"]["earned"] is True
        assert by_key["sub_80"]["earned"] is False, "85 is not < 80"
        assert by_key["sub_50_9"]["earned"] is False, "sub_50_9 must not be earned from an 18-hole round"
        assert by_key["sub_45_9"]["earned"] is False
        assert by_key["sub_40_9"]["earned"] is False
        assert by_key["sub_par_9"]["earned"] is False


# -- Discover users (used by MentionInput)
class TestMentionSearch:
    def test_discover_users_query_sa(self, jordan_auth):
        r = requests.get(f"{API}/discover/users?q=sa", headers=jordan_auth["headers"], timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        names = [u.get("display_name", "").lower() for u in data]
        assert any("sa" in n for n in names), f"Expected a match for 'sa' in discover results, got: {names}"
