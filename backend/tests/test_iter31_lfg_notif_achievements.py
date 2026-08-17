"""Iteration 31 tests: LFG interest flow, notif tap-to-navigate helpers, achievements crash fix."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://course-crew-3.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str = "password123") -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    j = r.json()
    return j.get("access_token") or j["token"]


def _headers(token: str):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def reese_token():
    return _login("reese@teebox.demo")


@pytest.fixture(scope="module")
def second_user():
    """Register a fresh second user for the LFG join flow."""
    email = f"TEST_lfg2_{uuid.uuid4().hex[:8]}@teebox.demo"
    payload = {
        "email": email,
        "password": "password123",
        "display_name": f"TEST LFG {uuid.uuid4().hex[:4]}",
    }
    r = requests.post(f"{API}/auth/register", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token") or _login(email)
    me = requests.get(f"{API}/auth/me", headers=_headers(token), timeout=15).json()
    return {"email": email, "token": token, "user": me}


# ---------- Health / auth ----------
class TestAuth:
    def test_login_reese(self, reese_token):
        assert isinstance(reese_token, str) and len(reese_token) > 20

    def test_me_returns_reese(self, reese_token):
        r = requests.get(f"{API}/auth/me", headers=_headers(reese_token), timeout=15)
        assert r.status_code == 200
        assert r.json().get("email") == "reese@teebox.demo"


# ---------- Achievements 500 fix ----------
class TestAchievements:
    def test_achievements_ok_for_reese(self, reese_token):
        me = requests.get(f"{API}/auth/me", headers=_headers(reese_token), timeout=15).json()
        r = requests.get(f"{API}/users/{me['id']}/achievements", headers=_headers(reese_token), timeout=30)
        assert r.status_code == 200, f"achievements crashed: {r.status_code} {r.text}"
        data = r.json()
        # Response is either list or dict — accept both shapes
        if isinstance(data, dict):
            defs = data.get("achievements") or data.get("defs") or []
        else:
            defs = data
        assert isinstance(defs, list) and len(defs) == 14, f"Expected 14 achievements, got {len(defs)}"
        keys = {d.get("key") for d in defs}
        assert "first_round" in keys

    def test_achievements_ok_after_lfg_post(self, reese_token):
        """Create an lfg post (no total_score) and verify achievements still 200."""
        payload = {
            "post_type": "lfg",
            "notes": "TEST_lfg post for achievements check",
            "course_name": "Pebble Meadows GC",
            "looking_for_count": 2,
            "tee_time": "2026-06-01T15:00:00Z",
        }
        cr = requests.post(f"{API}/rounds", json=payload, headers=_headers(reese_token), timeout=30)
        assert cr.status_code in (200, 201), f"lfg create: {cr.status_code} {cr.text}"
        me = requests.get(f"{API}/auth/me", headers=_headers(reese_token), timeout=15).json()
        r = requests.get(f"{API}/users/{me['id']}/achievements", headers=_headers(reese_token), timeout=30)
        assert r.status_code == 200, f"achievements after lfg post crashed: {r.status_code} {r.text}"


# ---------- Notifications endpoints ----------
class TestNotifications:
    def test_list_notifications_ok(self, reese_token):
        r = requests.get(f"{API}/notifications", headers=_headers(reese_token), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "notifications" in j and "unread" in j
        assert isinstance(j["notifications"], list)

    def test_mark_notif_read_no_row_is_still_ok(self, reese_token):
        # Marking a non-existent id should be idempotent (200 with ok:true, since update_one matches 0)
        r = requests.post(f"{API}/notifications/does-not-exist/read", headers=_headers(reese_token), timeout=15)
        assert r.status_code in (200, 404)


# ---------- LFG interest / accept / decline flow ----------
class TestLfgFlow:
    _state: dict = {}

    def test_1_reese_creates_lfg_post(self, reese_token):
        payload = {
            "post_type": "lfg",
            "notes": "TEST_lfg looking for a partner",
            "course_name": "Pebble Meadows GC",
            "looking_for_count": 2,
            "tee_time": "2026-07-15T15:00:00Z",
        }
        r = requests.post(f"{API}/rounds", json=payload, headers=_headers(reese_token), timeout=30)
        assert r.status_code in (200, 201), f"create lfg: {r.status_code} {r.text}"
        body = r.json()
        rid = body.get("id") or body.get("round_id")
        assert rid, f"no id in create response: {body}"
        TestLfgFlow._state["round_id"] = rid
        TestLfgFlow._state["looking_for_count"] = 2

    def test_2_owner_cannot_join_own(self, reese_token):
        rid = TestLfgFlow._state["round_id"]
        r = requests.post(f"{API}/rounds/{rid}/lfg/interest", headers=_headers(reese_token), timeout=15)
        assert r.status_code == 400

    def test_3_second_user_expresses_interest(self, second_user):
        rid = TestLfgFlow._state["round_id"]
        r = requests.post(f"{API}/rounds/{rid}/lfg/interest", headers=_headers(second_user["token"]), timeout=15)
        assert r.status_code == 200, f"interest failed: {r.status_code} {r.text}"
        j = r.json()
        assert j["status"] == "pending"
        assert j["lfg_pending_count"] == 1
        assert j["lfg_spots_remaining"] == 2
        assert j.get("interest_id")
        TestLfgFlow._state["interest_id"] = j["interest_id"]

    def test_4_second_join_toggle_withdraws(self, second_user):
        """Tapping join again should withdraw request (per backend logic)."""
        rid = TestLfgFlow._state["round_id"]
        r = requests.post(f"{API}/rounds/{rid}/lfg/interest", headers=_headers(second_user["token"]), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["status"] is None, f"expected withdrawal, got {j}"
        assert j["lfg_pending_count"] == 0

    def test_5_resend_interest_then_check_poster_can_list(self, second_user, reese_token):
        rid = TestLfgFlow._state["round_id"]
        # Re-request
        r = requests.post(f"{API}/rounds/{rid}/lfg/interest", headers=_headers(second_user["token"]), timeout=15)
        assert r.status_code == 200 and r.json()["status"] == "pending"
        TestLfgFlow._state["interest_id"] = r.json()["interest_id"]
        # Non-organizer cannot list
        r2 = requests.get(f"{API}/rounds/{rid}/lfg/interests", headers=_headers(second_user["token"]), timeout=15)
        assert r2.status_code == 403
        # Poster can list
        r3 = requests.get(f"{API}/rounds/{rid}/lfg/interests", headers=_headers(reese_token), timeout=15)
        assert r3.status_code == 200
        lst = r3.json()
        assert any(it["id"] == TestLfgFlow._state["interest_id"] for it in lst)
        # The requester should also appear in the enclosed .user
        assert any(it.get("user") and it["user"].get("id") == second_user["user"]["id"] for it in lst)

    def test_6_poster_receives_lfg_interest_notification(self, reese_token):
        r = requests.get(f"{API}/notifications", headers=_headers(reese_token), timeout=15)
        assert r.status_code == 200
        types = [n["type"] for n in r.json()["notifications"]]
        assert "lfg_interest" in types, f"expected lfg_interest notif, got types={set(types)}"

    def test_7_poster_accepts_request(self, reese_token, second_user):
        rid = TestLfgFlow._state["round_id"]
        iid = TestLfgFlow._state["interest_id"]
        r = requests.post(
            f"{API}/rounds/{rid}/lfg/interests/{iid}/accept",
            headers=_headers(reese_token),
            timeout=15,
        )
        assert r.status_code == 200, f"accept failed: {r.status_code} {r.text}"
        j = r.json()
        assert j["status"] == "accepted"
        assert j["lfg_accepted_count"] == 1
        assert j["lfg_spots_remaining"] == 1  # started 2, one accepted

    def test_8_requester_gets_lfg_response_notification(self, second_user):
        r = requests.get(f"{API}/notifications", headers=_headers(second_user["token"]), timeout=15)
        assert r.status_code == 200
        types = [n["type"] for n in r.json()["notifications"]]
        assert "lfg_response" in types, f"expected lfg_response notif, got types={set(types)}"

    def test_9_accepted_user_cannot_re_join(self, second_user):
        rid = TestLfgFlow._state["round_id"]
        r = requests.post(f"{API}/rounds/{rid}/lfg/interest", headers=_headers(second_user["token"]), timeout=15)
        assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text}"

    def test_10_feed_reflects_lfg_counts(self, reese_token):
        rid = TestLfgFlow._state["round_id"]
        r = requests.get(f"{API}/rounds/{rid}", headers=_headers(reese_token), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j.get("lfg_accepted_count") == 1
        assert j.get("lfg_spots_remaining") == 1

    def test_11_decline_flow_with_third_user(self, reese_token):
        # Register a third user, request, then decline
        email = f"TEST_lfg3_{uuid.uuid4().hex[:8]}@teebox.demo"
        rr = requests.post(f"{API}/auth/register", json={
            "email": email, "password": "password123",
            "display_name": f"TEST L3 {uuid.uuid4().hex[:4]}",
        }, timeout=30)
        assert rr.status_code in (200, 201)
        third_token = rr.json().get("access_token") or rr.json().get("token") or _login(email)

        rid = TestLfgFlow._state["round_id"]
        r = requests.post(f"{API}/rounds/{rid}/lfg/interest", headers=_headers(third_token), timeout=15)
        assert r.status_code == 200
        iid3 = r.json()["interest_id"]

        dec = requests.post(
            f"{API}/rounds/{rid}/lfg/interests/{iid3}/decline",
            headers=_headers(reese_token), timeout=15,
        )
        assert dec.status_code == 200
        assert dec.json()["status"] == "declined"

        # Third user should get lfg_response notif
        notes = requests.get(f"{API}/notifications", headers=_headers(third_token), timeout=15).json()
        types = [n["type"] for n in notes["notifications"]]
        assert "lfg_response" in types

    def test_12_cleanup_delete_lfg_post(self, reese_token):
        rid = TestLfgFlow._state.get("round_id")
        if not rid:
            return
        r = requests.delete(f"{API}/rounds/{rid}", headers=_headers(reese_token), timeout=15)
        assert r.status_code in (200, 204, 404)
