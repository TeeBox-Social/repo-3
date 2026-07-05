"""Iter8 backend tests: profile editor, new stat row, pin round, friends screen."""
import os
import base64
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL missing"
BASE_URL = BASE_URL.rstrip("/")

PASS = "password123"


def _login(email: str) -> dict:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PASS}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def reese():
    return _login("reese@teebox.demo")


@pytest.fixture(scope="module")
def jordan():
    return _login("jordan@teebox.demo")


@pytest.fixture(scope="module")
def sam():
    return _login("sam@teebox.demo")


def _hdr(auth):
    return {"Authorization": f"Bearer {auth['access_token']}", "Content-Type": "application/json"}


# --------- 1. Profile editor: PATCH /api/auth/me ---------
class TestProfileEditor:
    def test_patch_me_updates_fields(self, reese):
        h = _hdr(reese)
        # snapshot original
        orig = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        payload = {
            "display_name": orig["display_name"],  # keep name to preserve seed
            "bio": "TEST_bio_iter8",
            "home_course": "TEST_Home_iter8",
            "handicap": 7.7,
        }
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["bio"] == "TEST_bio_iter8"
        assert d["home_course"] == "TEST_Home_iter8"
        assert d["handicap"] == 7.7

        # GET verifies persistence
        g = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        assert g["bio"] == "TEST_bio_iter8"
        assert g["handicap"] == 7.7

        # restore
        requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={
            "display_name": orig["display_name"],
            "bio": orig.get("bio") or "",
            "home_course": orig.get("home_course") or "",
            "handicap": orig.get("handicap"),
        }, timeout=15)

    def test_patch_me_handicap_null_clears(self, reese):
        """Review request states: 'Handicap can be set to null to clear.'"""
        h = _hdr(reese)
        orig = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        # set a non-null first
        requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"handicap": 9.9}, timeout=15)
        # now clear
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"handicap": None}, timeout=15)
        assert r.status_code == 200, r.text
        g = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        # restore first so we don't corrupt state on failure
        requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"handicap": orig.get("handicap")}, timeout=15)
        assert g.get("handicap") in (None,), f"handicap should be cleared to null, got {g.get('handicap')!r}"

    def test_patch_me_oversized_avatar_returns_413(self, reese):
        h = _hdr(reese)
        # >600KB decoded => >800_000 b64 chars
        raw = b"a" * 900_000
        big_b64 = "data:image/png;base64," + base64.b64encode(raw).decode()
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"avatar": big_b64}, timeout=30)
        assert r.status_code == 413, f"expected 413, got {r.status_code}: {r.text[:200]}"


# --------- 2. Pin/Unpin round ---------
class TestPinRound:
    def test_pin_own_round_and_reflect_in_profile(self, reese):
        h = _hdr(reese)
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        rounds = requests.get(f"{BASE_URL}/api/users/{me['id']}/rounds", headers=h, timeout=15).json()
        assert len(rounds) >= 1
        rid = rounds[0]["id"]
        p = requests.post(f"{BASE_URL}/api/rounds/{rid}/pin", headers=h, timeout=15)
        assert p.status_code == 200, p.text
        assert p.json().get("pinned") is True

        prof = requests.get(f"{BASE_URL}/api/users/{me['id']}", headers=h, timeout=15).json()
        assert prof.get("pinned_round") is not None, "pinned_round should be enriched"
        assert prof["pinned_round"]["id"] == rid

        # unpin
        u = requests.delete(f"{BASE_URL}/api/users/me/pin", headers=h, timeout=15)
        assert u.status_code == 200
        prof2 = requests.get(f"{BASE_URL}/api/users/{me['id']}", headers=h, timeout=15).json()
        assert prof2.get("pinned_round") is None

    def test_pin_non_owner_returns_403(self, reese, jordan):
        # jordan tries to pin one of reese's rounds
        hr = _hdr(reese)
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=hr, timeout=15).json()
        rounds = requests.get(f"{BASE_URL}/api/users/{me['id']}/rounds", headers=hr, timeout=15).json()
        rid = rounds[0]["id"]
        r = requests.post(f"{BASE_URL}/api/rounds/{rid}/pin", headers=_hdr(jordan), timeout=15)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_pin_nonexistent_round_returns_404(self, reese):
        r = requests.post(f"{BASE_URL}/api/rounds/does-not-exist-uuid/pin", headers=_hdr(reese), timeout=15)
        assert r.status_code == 404, r.text


# --------- 3. GET /api/users/{id} new fields ---------
class TestUserProfileStats:
    def test_reese_stats(self, reese):
        h = _hdr(reese)
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        p = requests.get(f"{BASE_URL}/api/users/{me['id']}", headers=h, timeout=15)
        assert p.status_code == 200
        d = p.json()
        assert d["round_count"] == 2, d
        assert d["courses_played"] == 2, d
        assert d["avg_score"] == 80.5, d
        assert d["friends_count"] == 2, d
        # 'best_score' need not be included; if present, ok — UI doesn't display it
        # Verify friends_count matches actual friends list length
        fl = requests.get(f"{BASE_URL}/api/users/{me['id']}/friends", headers=h, timeout=15).json()
        assert len(fl) == d["friends_count"]


# --------- 4. GET /api/users/{id}/friends ---------
class TestFriendsEndpoint:
    def test_reese_friends_content_and_sort(self, reese):
        h = _hdr(reese)
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        r = requests.get(f"{BASE_URL}/api/users/{me['id']}/friends", headers=h, timeout=15)
        assert r.status_code == 200
        friends = r.json()
        assert len(friends) == 2
        # from reese's own perspective, everyone in her friends list must be mutual (is_friend=True)
        for f in friends:
            assert set(["id", "display_name", "avatar", "handicap", "round_count", "is_following", "is_friend", "is_me"]).issubset(f.keys()), f
            assert f["is_friend"] is True, f
            assert f["is_me"] is False
        # Sorted: friends first (all here), then alphabetical
        names = [f["display_name"].lower() for f in friends]
        assert names == sorted(names), names

    def test_friends_viewed_by_other(self, reese, jordan):
        # sam views reese's friends — reese has {jordan, sam}
        hr = _hdr(reese)
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=hr, timeout=15).json()
        # from jordan's POV: jordan sees reese's friends (jordan+sam)
        r = requests.get(f"{BASE_URL}/api/users/{me['id']}/friends", headers=_hdr(jordan), timeout=15)
        assert r.status_code == 200
        friends = r.json()
        assert len(friends) == 2
        # jordan sees themselves in the list => is_me true for jordan entry
        me_flags = [f for f in friends if f["is_me"]]
        assert len(me_flags) == 1


# --------- 5. Stale pinned_round auto-clear ---------
class TestPinAutoClear:
    def test_deleted_pinned_round_autoclears(self, reese):
        h = _hdr(reese)
        # create a new round, pin it, delete it, then GET /users/{id}
        payload = {
            "course_name": "TEST_iter8_temp_course",
            "total_score": 82,
            "par": 72,
            "holes_played": 18,
            "notes": "",
        }
        c = requests.post(f"{BASE_URL}/api/rounds", headers=h, json=payload, timeout=15)
        assert c.status_code == 200, c.text
        rid = c.json()["id"]
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        pn = requests.post(f"{BASE_URL}/api/rounds/{rid}/pin", headers=h, timeout=15)
        assert pn.status_code == 200

        # sanity: profile shows the pin
        prof = requests.get(f"{BASE_URL}/api/users/{me['id']}", headers=h, timeout=15).json()
        assert prof.get("pinned_round") and prof["pinned_round"]["id"] == rid

        # delete the round
        d = requests.delete(f"{BASE_URL}/api/rounds/{rid}", headers=h, timeout=15)
        assert d.status_code == 200, d.text

        # GET /users/{id} — should auto-clear
        prof2 = requests.get(f"{BASE_URL}/api/users/{me['id']}", headers=h, timeout=15).json()
        assert prof2.get("pinned_round") is None, prof2
        # And no orphan pinned_round_id leaked into the top-level (public_user drops it, but be defensive)
        assert "pinned_round_id" not in prof2, "orphan pinned_round_id leaked in response"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
