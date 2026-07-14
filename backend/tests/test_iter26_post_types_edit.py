"""Iter-26 backend tests: post_type discriminator, edit/delete rounds+comments,
   courses-played endpoint.
"""
import os
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://tee-social-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ---- Fixtures --------------------------------------------------------------
def _login(email: str, password: str = "password123") -> dict:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def reese():
    d = _login("reese@teebox.demo")
    return {"token": d["access_token"], "user": d["user"], "headers": {"Authorization": f"Bearer {d['access_token']}"}}


@pytest.fixture(scope="module")
def jordan():
    d = _login("jordan@teebox.demo")
    return {"token": d["access_token"], "user": d["user"], "headers": {"Authorization": f"Bearer {d['access_token']}"}}


# ---- Post-type discriminator ----------------------------------------------
class TestPostTypes:
    def test_round_post_still_works_and_returns_new_achievements(self, reese):
        payload = {
            "post_type": "round",
            "course_name": f"TEST_iter26_course_{uuid.uuid4().hex[:8]}",
            "total_score": 82,
            "par": 72,
            "holes_played": 18,
            "notes": "TEST_iter26 round",
        }
        r = requests.post(f"{API}/rounds", json=payload, headers=reese["headers"], timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["post_type"] == "round"
        assert body["course_name"] == payload["course_name"]
        assert body["total_score"] == 82
        assert "new_achievements" in body and isinstance(body["new_achievements"], list)
        # cleanup
        requests.delete(f"{API}/rounds/{body['id']}", headers=reese["headers"], timeout=15)

    def test_round_missing_score_returns_422(self, reese):
        payload = {"post_type": "round", "course_name": "TEST_iter26_no_score"}
        r = requests.post(f"{API}/rounds", json=payload, headers=reese["headers"], timeout=15)
        assert r.status_code == 422

    def test_round_missing_course_returns_422(self, reese):
        payload = {"post_type": "round", "total_score": 82}
        r = requests.post(f"{API}/rounds", json=payload, headers=reese["headers"], timeout=15)
        assert r.status_code == 422

    def test_text_post_with_notes_only(self, reese):
        payload = {"post_type": "text", "notes": "TEST_iter26 hello world text post"}
        r = requests.post(f"{API}/rounds", json=payload, headers=reese["headers"], timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["post_type"] == "text"
        assert body["notes"] == "TEST_iter26 hello world text post"
        assert body.get("new_achievements") == []
        assert body.get("course_name") == ""
        assert body.get("total_score") is None
        requests.delete(f"{API}/rounds/{body['id']}", headers=reese["headers"], timeout=15)

    def test_text_post_empty_returns_422(self, reese):
        payload = {"post_type": "text", "notes": "  ", "photos": []}
        r = requests.post(f"{API}/rounds", json=payload, headers=reese["headers"], timeout=15)
        assert r.status_code == 422

    def test_lfg_post_preserves_fields_on_get(self, reese):
        payload = {
            "post_type": "lfg",
            "course_name": "TEST_iter26_LFG_course",
            "notes": "TEST_iter26 need one",
            "meetup_date": "Sat 8:30 AM",
            "looking_for_count": 2,
        }
        r = requests.post(f"{API}/rounds", json=payload, headers=reese["headers"], timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        rid = body["id"]
        assert body["post_type"] == "lfg"
        assert body["meetup_date"] == "Sat 8:30 AM"
        assert body["looking_for_count"] == 2
        # GET single round preserves the fields
        r2 = requests.get(f"{API}/rounds/{rid}", headers=reese["headers"], timeout=15)
        assert r2.status_code == 200
        assert r2.json()["meetup_date"] == "Sat 8:30 AM"
        assert r2.json()["looking_for_count"] == 2
        requests.delete(f"{API}/rounds/{rid}", headers=reese["headers"], timeout=15)


# ---- Edit / Delete rounds --------------------------------------------------
class TestRoundEdit:
    def _make_round(self, actor):
        payload = {
            "post_type": "round",
            "course_name": f"TEST_iter26_edit_{uuid.uuid4().hex[:8]}",
            "total_score": 90,
            "par": 72,
            "holes_played": 18,
        }
        r = requests.post(f"{API}/rounds", json=payload, headers=actor["headers"], timeout=15)
        assert r.status_code == 200, r.text
        return r.json()

    def test_author_can_edit_notes_course_score(self, reese):
        rnd = self._make_round(reese)
        rid = rnd["id"]
        upd = {"notes": "TEST_iter26 edited", "course_name": "TEST_iter26_edited_course", "total_score": 85}
        r = requests.patch(f"{API}/rounds/{rid}", json=upd, headers=reese["headers"], timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["notes"] == "TEST_iter26 edited"
        assert body["course_name"] == "TEST_iter26_edited_course"
        assert body["total_score"] == 85
        assert body.get("edited_at")
        # cleanup
        requests.delete(f"{API}/rounds/{rid}", headers=reese["headers"], timeout=15)

    def test_non_author_cannot_edit(self, reese, jordan):
        rnd = self._make_round(reese)
        rid = rnd["id"]
        r = requests.patch(f"{API}/rounds/{rid}", json={"notes": "hax"}, headers=jordan["headers"], timeout=15)
        assert r.status_code == 403
        requests.delete(f"{API}/rounds/{rid}", headers=reese["headers"], timeout=15)

    def test_unknown_round_404(self, reese):
        r = requests.patch(f"{API}/rounds/nonexistent-id-xyz", json={"notes": "x"}, headers=reese["headers"], timeout=15)
        assert r.status_code == 404


# ---- Edit / Delete comments -----------------------------------------------
class TestCommentEdit:
    def _make_round_with_comment(self, author, commenter):
        rnd = requests.post(
            f"{API}/rounds",
            json={"post_type": "text", "notes": "TEST_iter26 comment host"},
            headers=author["headers"], timeout=15,
        ).json()
        c = requests.post(
            f"{API}/rounds/{rnd['id']}/comments",
            json={"text": "TEST_iter26 original comment"},
            headers=commenter["headers"], timeout=15,
        ).json()
        return rnd, c

    def test_author_can_edit_comment(self, reese):
        rnd, c = self._make_round_with_comment(reese, reese)
        r = requests.patch(
            f"{API}/rounds/{rnd['id']}/comments/{c['id']}",
            json={"text": "TEST_iter26 edited comment"},
            headers=reese["headers"], timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["text"] == "TEST_iter26 edited comment"
        assert body.get("edited_at")
        assert "like_count" in body and "liked_by_me" in body
        requests.delete(f"{API}/rounds/{rnd['id']}", headers=reese["headers"], timeout=15)

    def test_non_author_cannot_edit_comment(self, reese, jordan):
        rnd, c = self._make_round_with_comment(reese, jordan)  # jordan commented
        r = requests.patch(
            f"{API}/rounds/{rnd['id']}/comments/{c['id']}",
            json={"text": "hax"},
            headers=reese["headers"], timeout=15,  # reese tries to edit jordan's comment
        )
        assert r.status_code == 403
        requests.delete(f"{API}/rounds/{rnd['id']}", headers=reese["headers"], timeout=15)

    def test_author_can_delete_comment_non_author_cannot(self, reese, jordan):
        rnd, c = self._make_round_with_comment(reese, jordan)
        # reese can't delete jordan's comment
        r = requests.delete(
            f"{API}/rounds/{rnd['id']}/comments/{c['id']}",
            headers=reese["headers"], timeout=15,
        )
        assert r.status_code == 403
        # jordan can
        r2 = requests.delete(
            f"{API}/rounds/{rnd['id']}/comments/{c['id']}",
            headers=jordan["headers"], timeout=15,
        )
        assert r2.status_code == 200
        assert r2.json().get("ok") is True
        # confirm deleted
        comments = requests.get(f"{API}/rounds/{rnd['id']}/comments", headers=reese["headers"], timeout=15).json()
        assert all(cc["id"] != c["id"] for cc in comments)
        requests.delete(f"{API}/rounds/{rnd['id']}", headers=reese["headers"], timeout=15)


# ---- Courses-played endpoint ----------------------------------------------
class TestCoursesPlayed:
    def test_courses_played_shape_and_sort(self, reese):
        # create 2 rounds at course A, 1 at course B, and 1 text post (should NOT be counted)
        cA = f"TEST_iter26_CP_A_{uuid.uuid4().hex[:6]}"
        cB = f"TEST_iter26_CP_B_{uuid.uuid4().hex[:6]}"
        made = []
        for score in (85, 79):
            r = requests.post(f"{API}/rounds", json={
                "post_type": "round", "course_name": cA, "total_score": score,
            }, headers=reese["headers"], timeout=15)
            assert r.status_code == 200, r.text
            made.append(r.json()["id"])
        r = requests.post(f"{API}/rounds", json={
            "post_type": "round", "course_name": cB, "total_score": 92,
        }, headers=reese["headers"], timeout=15)
        assert r.status_code == 200
        made.append(r.json()["id"])
        # text post — should NOT bump any count
        rt = requests.post(f"{API}/rounds", json={
            "post_type": "text", "notes": "TEST_iter26 CP text — do not count",
        }, headers=reese["headers"], timeout=15)
        made.append(rt.json()["id"])

        res = requests.get(f"{API}/users/{reese['user']['id']}/courses-played", headers=reese["headers"], timeout=15)
        assert res.status_code == 200, res.text
        rows = res.json()
        assert isinstance(rows, list)
        rowA = next((r for r in rows if r["course_name"] == cA), None)
        rowB = next((r for r in rows if r["course_name"] == cB), None)
        assert rowA is not None and rowB is not None
        assert rowA["play_count"] == 2
        assert rowB["play_count"] == 1
        assert rowA["best_score"] == 79
        assert rowB["best_score"] == 92
        assert rowA["avg_score"] == 82.0
        # shape check
        for k in ("course_name", "play_count", "best_score", "avg_score", "last_played", "city", "region", "country"):
            assert k in rowA, f"missing key {k}"
        # sort: cA (play_count=2) should appear before cB (play_count=1) in the returned list
        idx_a = next(i for i, r in enumerate(rows) if r["course_name"] == cA)
        idx_b = next(i for i, r in enumerate(rows) if r["course_name"] == cB)
        assert idx_a < idx_b, f"expected {cA} before {cB} (play_count sort desc)"

        # cleanup
        for rid in made:
            requests.delete(f"{API}/rounds/{rid}", headers=reese["headers"], timeout=15)

    def test_courses_played_empty_for_fresh_user(self, reese):
        # register a brand-new user with 0 rounds
        email = f"TEST_iter26_empty_{uuid.uuid4().hex[:8]}@teebox.demo"
        reg = requests.post(f"{API}/auth/register", json={
            "email": email, "password": "password123", "display_name": f"TEST_iter26_{uuid.uuid4().hex[:5]}"
        }, timeout=15)
        assert reg.status_code == 200, reg.text
        uid = reg.json()["user"]["id"]
        res = requests.get(f"{API}/users/{uid}/courses-played", headers=reese["headers"], timeout=15)
        assert res.status_code == 200
        assert res.json() == []

    def test_user_courses_played_count_excludes_non_round_posts(self, reese):
        # Snapshot current courses_played, add a text + LFG post, ensure it stayed the same
        before = requests.get(f"{API}/users/{reese['user']['id']}", headers=reese["headers"], timeout=15).json()
        cp_before = before["courses_played"]
        text = requests.post(f"{API}/rounds", json={
            "post_type": "text", "notes": "TEST_iter26 exclude-text",
        }, headers=reese["headers"], timeout=15).json()
        lfg = requests.post(f"{API}/rounds", json={
            "post_type": "lfg", "course_name": "TEST_iter26_LFG_should_not_count",
            "notes": "TEST_iter26 lfg body",
        }, headers=reese["headers"], timeout=15).json()
        after = requests.get(f"{API}/users/{reese['user']['id']}", headers=reese["headers"], timeout=15).json()
        cp_after = after["courses_played"]
        # cleanup
        requests.delete(f"{API}/rounds/{text['id']}", headers=reese["headers"], timeout=15)
        requests.delete(f"{API}/rounds/{lfg['id']}", headers=reese["headers"], timeout=15)
        # Note: current /users/{id} implementation groups on all rounds — flag if it changed.
        assert cp_after == cp_before or cp_after == cp_before, (
            f"courses_played changed after text/lfg posts: {cp_before} -> {cp_after}. "
            "Expected round-type-only aggregation."
        )


# ---- Regression: legacy endpoints still work ------------------------------
class TestRegression:
    def test_feed_still_works(self, reese):
        r = requests.get(f"{API}/feed?scope=followers", headers=reese["headers"], timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_me_endpoint(self, reese):
        r = requests.get(f"{API}/auth/me", headers=reese["headers"], timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == "reese@teebox.demo"

    def test_notifications_endpoint(self, reese):
        r = requests.get(f"{API}/notifications", headers=reese["headers"], timeout=15)
        assert r.status_code == 200
        assert "notifications" in r.json()
