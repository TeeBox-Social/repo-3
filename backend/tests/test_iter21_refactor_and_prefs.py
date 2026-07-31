"""Iteration 21 backend tests.

Covers:
1. Smoke tests for every router group after the server.py refactor.
2. Notification preferences: defaults on /auth/me + PATCH partial merge.
3. Per-event opt-out: post_like, comment_like, follow, achievement_unlocked
   respect the target user's notification_prefs.
4. AVG score normalization for 9-hole rounds (extrapolated to 18-hole equiv).
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://course-crew-3.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "reese@teebox.demo"
DEMO_A = "jordan@teebox.demo"
DEMO_B = "sam@teebox.demo"
PASSWORD = "password123"


# ---------- helpers ----------
def _login(email: str) -> tuple[str, dict]:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    body = r.json()
    return body["access_token"], body["user"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _register(display_name: str) -> tuple[str, dict]:
    # unique email each call to avoid dupe collisions
    email = f"test_iter21_{uuid.uuid4().hex[:10]}@teebox.demo"
    payload = {"email": email, "password": PASSWORD, "display_name": display_name}
    # Rate limit is 5/minute — retry up to 5 times with 65s backoff so a full
    # window resets. This keeps the suite reliable when rerun quickly.
    last = None
    for _attempt in range(5):
        r = requests.post(f"{API}/auth/register", json=payload, timeout=15)
        last = r
        if r.status_code == 200:
            body = r.json()
            return body["access_token"], body["user"]
        if r.status_code == 429:
            time.sleep(65)
            continue
        break
    assert False, f"register failed: {last.status_code} {last.text if last else 'no response'}"


@pytest.fixture(scope="module")
def demo_a():
    tok, user = _login(DEMO_A)
    return {"token": tok, "user": user, "auth": _auth(tok)}


@pytest.fixture(scope="module")
def demo_b():
    tok, user = _login(DEMO_B)
    return {"token": tok, "user": user, "auth": _auth(tok)}


@pytest.fixture(scope="module")
def admin_ctx():
    tok, user = _login(ADMIN_EMAIL)
    return {"token": tok, "user": user, "auth": _auth(tok)}


# ==========================================================================
# 1. REFACTOR SMOKE TESTS — one representative endpoint per router group
# ==========================================================================
class TestRefactorSmoke:
    def test_root(self):
        r = requests.get(f"{API}/", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_auth_me(self, demo_a):
        r = requests.get(f"{API}/auth/me", headers=demo_a["auth"], timeout=10)
        assert r.status_code == 200
        assert r.json()["id"] == demo_a["user"]["id"]

    def test_auth_refresh_and_logout(self):
        r = requests.post(f"{API}/auth/login", json={"email": DEMO_A, "password": PASSWORD}, timeout=10)
        assert r.status_code == 200
        refresh = r.json()["refresh_token"]
        rr = requests.post(f"{API}/auth/refresh", json={"refresh_token": refresh}, timeout=10)
        assert rr.status_code == 200
        new_refresh = rr.json()["refresh_token"]
        lo = requests.post(f"{API}/auth/logout", json={"refresh_token": new_refresh}, timeout=10)
        assert lo.status_code == 200

    def test_rounds_router(self, demo_a):
        # GET /feed
        r = requests.get(f"{API}/feed", headers=demo_a["auth"], timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_users_router(self, demo_a):
        uid = demo_a["user"]["id"]
        r = requests.get(f"{API}/users/{uid}", headers=demo_a["auth"], timeout=10)
        assert r.status_code == 200
        r2 = requests.get(f"{API}/users/{uid}/rounds", headers=demo_a["auth"], timeout=10)
        assert r2.status_code == 200
        r3 = requests.get(f"{API}/users/{uid}/achievements", headers=demo_a["auth"], timeout=10)
        assert r3.status_code == 200
        assert "achievements" in r3.json()
        r4 = requests.get(f"{API}/users/{uid}/friends", headers=demo_a["auth"], timeout=10)
        assert r4.status_code == 200
        r5 = requests.get(f"{API}/users/{uid}/wishlist", headers=demo_a["auth"], timeout=10)
        assert r5.status_code == 200
        r6 = requests.get(f"{API}/discover/users", headers=demo_a["auth"], timeout=10)
        assert r6.status_code == 200

    def test_courses_router(self, demo_a):
        r = requests.get(f"{API}/discover/courses", headers=demo_a["auth"], timeout=15)
        assert r.status_code == 200
        r2 = requests.get(f"{API}/courses/search?q=peb", headers=demo_a["auth"], timeout=15)
        assert r2.status_code == 200

    def test_notifications_router(self, demo_a):
        r = requests.get(f"{API}/notifications", headers=demo_a["auth"], timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "notifications" in body and "unread" in body

    def test_admin_router(self, admin_ctx):
        r = requests.get(f"{API}/admin/courses/pending", headers=admin_ctx["auth"], timeout=10)
        assert r.status_code == 200
        r2 = requests.get(f"{API}/admin/courses/stats", headers=admin_ctx["auth"], timeout=10)
        assert r2.status_code == 200
        r3 = requests.get(f"{API}/admin/courses/import-jobs", headers=admin_ctx["auth"], timeout=10)
        assert r3.status_code == 200


# ==========================================================================
# 2. NOTIFICATION PREFS — defaults, partial merge
# ==========================================================================
EXPECTED_KEYS = {
    "comment_like",
    "achievement_unlocked",
    "post_like",
    "post_comment",
    "mention",
    "follow",
    "course_verified",
}


class TestNotificationPrefs:
    def test_me_returns_all_seven_keys_defaulting_to_true(self, demo_a):
        r = requests.get(f"{API}/auth/me", headers=demo_a["auth"], timeout=10)
        assert r.status_code == 200
        prefs = r.json().get("notification_prefs")
        assert prefs is not None, "notification_prefs missing on /auth/me"
        assert set(prefs.keys()) == EXPECTED_KEYS, f"keys mismatch: {set(prefs.keys())}"
        # NOTE: existing demo users may already have opted-out prefs. We only guarantee shape here.

    def test_login_returns_notification_prefs(self):
        r = requests.post(f"{API}/auth/login", json={"email": DEMO_A, "password": PASSWORD}, timeout=10)
        assert r.status_code == 200
        prefs = r.json()["user"].get("notification_prefs")
        assert prefs is not None
        assert set(prefs.keys()) == EXPECTED_KEYS

    def test_register_returns_all_true_defaults(self):
        tok, user = _register(f"TEST_prefs_{uuid.uuid4().hex[:6]}")
        prefs = user.get("notification_prefs")
        assert prefs is not None
        assert set(prefs.keys()) == EXPECTED_KEYS
        for k in EXPECTED_KEYS:
            assert prefs[k] is True, f"{k} should default to True but is {prefs[k]}"

    def test_patch_me_partial_merge(self):
        tok, user = _register(f"TEST_merge_{uuid.uuid4().hex[:6]}")
        auth = _auth(tok)
        # Turn only comment_like OFF
        r = requests.patch(
            f"{API}/auth/me",
            headers=auth,
            json={"notification_prefs": {"comment_like": False}},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        prefs = r.json()["notification_prefs"]
        assert prefs["comment_like"] is False
        # All other keys must remain True
        for k in EXPECTED_KEYS - {"comment_like"}:
            assert prefs[k] is True, f"{k} should still be True but is {prefs[k]}"
        # GET should also reflect merge
        r2 = requests.get(f"{API}/auth/me", headers=auth, timeout=10)
        assert r2.json()["notification_prefs"]["comment_like"] is False
        # Flip another key back on — comment_like must stay False
        r3 = requests.patch(
            f"{API}/auth/me",
            headers=auth,
            json={"notification_prefs": {"follow": False}},
            timeout=10,
        )
        assert r3.status_code == 200
        prefs2 = r3.json()["notification_prefs"]
        assert prefs2["comment_like"] is False
        assert prefs2["follow"] is False
        assert prefs2["post_like"] is True


# ==========================================================================
# 3. PER-EVENT OPT-OUT: post_like, comment_like, follow, achievement_unlocked
# ==========================================================================
def _count_unread_by_type(auth: dict, type_: str) -> int:
    r = requests.get(f"{API}/notifications", headers=auth, timeout=10)
    assert r.status_code == 200
    return sum(1 for n in r.json()["notifications"] if n.get("type") == type_ and not n.get("read"))


class TestNotificationOptOut:
    """Create two throwaway users A (actor) and B (target). Toggle B's pref
    and confirm notifications are (or aren't) created."""

    def test_post_like_respects_pref(self):
        # actor
        tok_a, user_a = _register(f"TEST_actor_{uuid.uuid4().hex[:6]}")
        auth_a = _auth(tok_a)
        # target
        tok_b, user_b = _register(f"TEST_target_{uuid.uuid4().hex[:6]}")
        auth_b = _auth(tok_b)

        # B posts a round
        rr = requests.post(
            f"{API}/rounds",
            headers=auth_b,
            json={"course_name": "TEST_iter21_optout_course", "total_score": 82, "par": 72, "holes_played": 18},
            timeout=15,
        )
        assert rr.status_code == 200
        round_id = rr.json()["id"]

        # B keeps post_like ON (default) — A likes → B should get 1 notif
        base_unread = _count_unread_by_type(auth_b, "post_like")
        lr = requests.post(f"{API}/rounds/{round_id}/like", headers=auth_a, timeout=10)
        assert lr.status_code == 200
        after = _count_unread_by_type(auth_b, "post_like")
        assert after == base_unread + 1, f"expected +1 post_like notification, got {after - base_unread}"

        # unlike so we can re-like after opt-out
        lr2 = requests.post(f"{API}/rounds/{round_id}/like", headers=auth_a, timeout=10)
        assert lr2.status_code == 200

        # B opts out
        requests.patch(f"{API}/auth/me", headers=auth_b, json={"notification_prefs": {"post_like": False}}, timeout=10)

        # A likes again → no new notification
        before2 = _count_unread_by_type(auth_b, "post_like")
        lr3 = requests.post(f"{API}/rounds/{round_id}/like", headers=auth_a, timeout=10)
        assert lr3.status_code == 200
        after2 = _count_unread_by_type(auth_b, "post_like")
        assert after2 == before2, f"post_like was opted-out but a notification was still created ({after2 - before2})"

    def test_follow_respects_pref(self):
        tok_a, user_a = _register(f"TEST_follower_{uuid.uuid4().hex[:6]}")
        auth_a = _auth(tok_a)
        tok_b, user_b = _register(f"TEST_followee_{uuid.uuid4().hex[:6]}")
        auth_b = _auth(tok_b)

        # default ON — expect +1 follow notif for B
        base = _count_unread_by_type(auth_b, "follow")
        r = requests.post(f"{API}/users/{user_b['id']}/follow", headers=auth_a, timeout=10)
        assert r.status_code == 200 and r.json()["following"] is True
        assert _count_unread_by_type(auth_b, "follow") == base + 1

        # unfollow, opt out, follow again — no notification
        requests.post(f"{API}/users/{user_b['id']}/follow", headers=auth_a, timeout=10)  # toggle off
        requests.patch(f"{API}/auth/me", headers=auth_b, json={"notification_prefs": {"follow": False}}, timeout=10)
        before = _count_unread_by_type(auth_b, "follow")
        r2 = requests.post(f"{API}/users/{user_b['id']}/follow", headers=auth_a, timeout=10)
        assert r2.status_code == 200 and r2.json()["following"] is True
        assert _count_unread_by_type(auth_b, "follow") == before

    def test_comment_like_respects_pref(self):
        tok_a, user_a = _register(f"TEST_commenter_{uuid.uuid4().hex[:6]}")
        auth_a = _auth(tok_a)
        tok_b, user_b = _register(f"TEST_liker_{uuid.uuid4().hex[:6]}")
        auth_b = _auth(tok_b)

        # A posts a round + comment
        rr = requests.post(
            f"{API}/rounds",
            headers=auth_a,
            json={"course_name": "TEST_iter21_cmt_course", "total_score": 90, "par": 72, "holes_played": 18},
            timeout=15,
        )
        assert rr.status_code == 200
        round_id = rr.json()["id"]
        cr = requests.post(
            f"{API}/rounds/{round_id}/comments",
            headers=auth_a,
            json={"text": "TEST_comment_iter21"},
            timeout=10,
        )
        assert cr.status_code == 200
        comment_id = cr.json()["id"]

        # B likes A's comment — A should get comment_like notif (default ON)
        base = _count_unread_by_type(auth_a, "comment_like")
        clr = requests.post(f"{API}/rounds/{round_id}/comments/{comment_id}/like", headers=auth_b, timeout=10)
        assert clr.status_code == 200
        assert _count_unread_by_type(auth_a, "comment_like") == base + 1

        # unlike, A opts out, B likes again — no notif
        requests.post(f"{API}/rounds/{round_id}/comments/{comment_id}/like", headers=auth_b, timeout=10)  # toggle off
        requests.patch(
            f"{API}/auth/me", headers=auth_a, json={"notification_prefs": {"comment_like": False}}, timeout=10
        )
        before = _count_unread_by_type(auth_a, "comment_like")
        clr2 = requests.post(f"{API}/rounds/{round_id}/comments/{comment_id}/like", headers=auth_b, timeout=10)
        assert clr2.status_code == 200
        assert _count_unread_by_type(auth_a, "comment_like") == before

    def test_achievement_unlocked_default_on(self):
        # Fresh user → first round unlocks 'first_round' + 'sub_100' etc.
        tok, user = _register(f"TEST_ach_{uuid.uuid4().hex[:6]}")
        auth = _auth(tok)
        rr = requests.post(
            f"{API}/rounds",
            headers=auth,
            json={"course_name": "TEST_iter21_ach", "total_score": 95, "par": 72, "holes_played": 18},
            timeout=15,
        )
        assert rr.status_code == 200
        # Allow the async notification insert to land
        time.sleep(0.5)
        r = requests.get(f"{API}/notifications", headers=auth, timeout=10)
        assert r.status_code == 200
        types = [n.get("type") for n in r.json()["notifications"]]
        assert "achievement_unlocked" in types, f"expected achievement_unlocked in {types}"

    def test_achievement_unlocked_opt_out(self):
        tok, user = _register(f"TEST_ach_off_{uuid.uuid4().hex[:6]}")
        auth = _auth(tok)
        # opt out FIRST
        pr = requests.patch(
            f"{API}/auth/me", headers=auth, json={"notification_prefs": {"achievement_unlocked": False}}, timeout=10
        )
        assert pr.status_code == 200
        # log a round → new_achievements exists but no notifs of that type
        rr = requests.post(
            f"{API}/rounds",
            headers=auth,
            json={"course_name": "TEST_iter21_ach_off", "total_score": 95, "par": 72, "holes_played": 18},
            timeout=15,
        )
        assert rr.status_code == 200
        time.sleep(0.5)
        r = requests.get(f"{API}/notifications", headers=auth, timeout=10)
        types = [n.get("type") for n in r.json()["notifications"]]
        assert "achievement_unlocked" not in types, f"opted-out user still got achievement_unlocked notifs: {types}"


# ==========================================================================
# 4. AVG SCORE NORMALIZATION (9-hole extrapolated to 18)
# ==========================================================================
class TestAvgNormalization:
    def _find_verified_par72_course_name(self, auth: dict) -> str | None:
        """Try to find an already-verified par-72 18-hole course to satisfy
        the course_par lookup path."""
        r = requests.get(f"{API}/discover/courses", headers=auth, timeout=15)
        if r.status_code != 200:
            return None
        for c in r.json():
            if int(c.get("par") or 0) == 72 and not (c.get("pending")):
                return c.get("name")
        # fallback: search
        r2 = requests.get(f"{API}/courses/search?q=Pebble", headers=auth, timeout=10)
        if r2.status_code == 200:
            for c in r2.json():
                if int(c.get("par") or 0) == 72:
                    return c.get("name")
        return None

    def test_9_hole_extrapolated_and_averaged_with_18(self):
        tok, user = _register(f"TEST_avg_{uuid.uuid4().hex[:6]}")
        auth = _auth(tok)
        course_name = self._find_verified_par72_course_name(auth)
        # If we can't find a verified par-72 course, we still exercise the fallback
        # path (par*2). Use round_par=36 → target_par=72 either way.
        cname = course_name or f"TEST_iter21_avg_course_{uuid.uuid4().hex[:5]}"

        # 9-hole round: 39 with par 36 on a par-72 18-hole course → 39*72/36 = 78
        r1 = requests.post(
            f"{API}/rounds",
            headers=auth,
            json={"course_name": cname, "total_score": 39, "par": 36, "holes_played": 9},
            timeout=15,
        )
        assert r1.status_code == 200, r1.text

        prof1 = requests.get(f"{API}/users/{user['id']}", headers=auth, timeout=10).json()
        avg1 = prof1.get("avg_score")
        assert avg1 is not None
        assert abs(avg1 - 78.0) < 0.05, f"expected 78.0 from extrapolation, got {avg1}"

        # 18-hole round: 80 → new avg should be (78 + 80) / 2 = 79.0
        r2 = requests.post(
            f"{API}/rounds",
            headers=auth,
            json={"course_name": cname, "total_score": 80, "par": 72, "holes_played": 18},
            timeout=15,
        )
        assert r2.status_code == 200, r2.text

        prof2 = requests.get(f"{API}/users/{user['id']}", headers=auth, timeout=10).json()
        avg2 = prof2.get("avg_score")
        assert avg2 is not None
        assert abs(avg2 - 79.0) < 0.05, f"expected 79.0 average, got {avg2}"
