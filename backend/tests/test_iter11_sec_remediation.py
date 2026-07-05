"""Iter11 backend tests: verify iter10 remediation gaps are closed.

Focus:
  SEC-102 display_name null / empty / whitespace / whitespace-padded / omitted.
  SEC-108 concurrent refresh race — 10 consecutive iterations. Each iteration:
     fresh login → 2 simultaneous /auth/refresh with same token → [200,401] →
     retry with winner's new refresh → must be 200 (clean) OR 401 (compromised);
     never leave a compromised family with a usable token.
  Regression: run selected iter10 tests inline for a smoke pass.
"""
import os
import asyncio
import uuid
import pytest
import requests
import httpx
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL"))
assert BASE_URL, "backend URL missing"
BASE_URL = BASE_URL.rstrip("/")

PASS = "password123"

SEED_REESE = {
    "display_name": "Reese Callahan",
    "home_course": "Pebble Meadows GC",
    "handicap": 8.4,
    "bio": "Weekend warrior. Always chasing the sunrise tee time.",
    "avatar": None,
}


def _login(email: str) -> dict:
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": PASS}, timeout=20)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return r.json()


def _hdr(auth):
    return {"Authorization": f"Bearer {auth['access_token']}",
            "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def reese():
    return _login("reese@teebox.demo")


@pytest.fixture(scope="module")
def jordan():
    return _login("jordan@teebox.demo")


@pytest.fixture(autouse=True)
def _restore_reese(reese):
    yield
    try:
        requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese),
                       json=SEED_REESE, timeout=10)
    except Exception:
        pass


# ============================================================================
# SEC-102: display_name hardening
# ============================================================================
class TestSEC102DisplayName:

    def test_null_returns_422_and_unchanged(self, reese):
        before = requests.get(f"{BASE_URL}/api/auth/me",
                              headers=_hdr(reese)).json()["display_name"]
        r = requests.patch(f"{BASE_URL}/api/auth/me",
                           headers=_hdr(reese),
                           json={"display_name": None})
        assert r.status_code == 422, f"expected 422 got {r.status_code} {r.text}"
        # detail should mention 'display_name cannot be empty' per spec
        detail = r.json().get("detail", "")
        assert "display_name" in str(detail).lower() and \
               ("empty" in str(detail).lower() or "cannot" in str(detail).lower()), \
               f"unexpected detail: {detail!r}"
        after = requests.get(f"{BASE_URL}/api/auth/me",
                             headers=_hdr(reese)).json()["display_name"]
        assert after == before, f"display_name changed: {before!r} -> {after!r}"

    def test_empty_string_returns_422(self, reese):
        before = requests.get(f"{BASE_URL}/api/auth/me",
                              headers=_hdr(reese)).json()["display_name"]
        r = requests.patch(f"{BASE_URL}/api/auth/me",
                           headers=_hdr(reese),
                           json={"display_name": ""})
        assert r.status_code == 422, f"expected 422 got {r.status_code} {r.text}"
        after = requests.get(f"{BASE_URL}/api/auth/me",
                             headers=_hdr(reese)).json()["display_name"]
        assert after == before

    def test_whitespace_only_returns_422(self, reese):
        before = requests.get(f"{BASE_URL}/api/auth/me",
                              headers=_hdr(reese)).json()["display_name"]
        r = requests.patch(f"{BASE_URL}/api/auth/me",
                           headers=_hdr(reese),
                           json={"display_name": "   "})
        assert r.status_code == 422, f"expected 422 got {r.status_code} {r.text}"
        after = requests.get(f"{BASE_URL}/api/auth/me",
                             headers=_hdr(reese)).json()["display_name"]
        assert after == before

    def test_whitespace_padded_is_trimmed(self, reese):
        r = requests.patch(f"{BASE_URL}/api/auth/me",
                           headers=_hdr(reese),
                           json={"display_name": "  Reese Callahan  "})
        assert r.status_code == 200, f"expected 200 got {r.status_code} {r.text}"
        assert r.json()["display_name"] == "Reese Callahan"
        g = requests.get(f"{BASE_URL}/api/auth/me",
                         headers=_hdr(reese)).json()
        assert g["display_name"] == "Reese Callahan"

    def test_omit_key_does_not_touch(self, reese):
        # set to a known value first
        r0 = requests.patch(f"{BASE_URL}/api/auth/me",
                            headers=_hdr(reese),
                            json={"display_name": "Reese Callahan"})
        assert r0.status_code == 200
        # now PATCH without display_name at all — must not change it
        r = requests.patch(f"{BASE_URL}/api/auth/me",
                           headers=_hdr(reese),
                           json={"bio": "iter11 probe bio"})
        assert r.status_code == 200
        assert r.json()["display_name"] == "Reese Callahan"
        assert r.json()["bio"] == "iter11 probe bio"

    def test_valid_new_name_ok(self, reese):
        r = requests.patch(f"{BASE_URL}/api/auth/me",
                           headers=_hdr(reese),
                           json={"display_name": "Reese C."})
        assert r.status_code == 200
        assert r.json()["display_name"] == "Reese C."


# ============================================================================
# SEC-108: concurrent refresh race — 10 iterations
# ============================================================================
class TestSEC108Concurrent:

    @pytest.mark.parametrize("iteration", list(range(10)))
    def test_concurrent_refresh_no_orphan(self, iteration):
        # Rotate across the 3 demo accounts, spaced to stay under 10/min login limit.
        accts = ["reese@teebox.demo", "jordan@teebox.demo", "sam@teebox.demo"]
        import time
        # 8s spacer × 10 iters = 80s total → ~7.5 logins/min < 10/min limit.
        time.sleep(8)
        auth = _login(accts[iteration % len(accts)])
        refresh_token = auth["refresh_token"]

        async def _hit():
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=20) as c:
                return await c.post("/api/auth/refresh",
                                    json={"refresh_token": refresh_token})

        async def _run_both():
            return await asyncio.gather(_hit(), _hit(),
                                        return_exceptions=True)

        results = asyncio.run(_run_both())
        statuses = sorted([r.status_code for r in results
                           if hasattr(r, "status_code")])
        assert len(statuses) == 2, f"iter{iteration}: {results}"

        # Both 200 = ok (no contention detected). Both 401 = both saw reuse.
        # [200,401] = winner+loser split (expected).
        assert statuses in ([200, 401], [200, 200], [401, 401]), \
            f"iter{iteration}: unexpected statuses {statuses}"

        winners = [r for r in results if r.status_code == 200]
        if not winners:
            # both 401 — nothing to spend, family is dead, OK
            return

        # Take the winner's new refresh token and try one more refresh.
        # Requirement:
        #   - if statuses == [200,401] (race detected): family MUST be revoked
        #     so 3rd refresh -> 401.
        #   - if statuses == [200,200] (no race): winner should still be usable
        #     -> 200 (either winner's token could work; both are new).
        new_refresh = winners[-1].json()["refresh_token"]
        r3 = requests.post(f"{BASE_URL}/api/auth/refresh",
                           json={"refresh_token": new_refresh}, timeout=20)

        if statuses == [200, 401]:
            assert r3.status_code == 401, (
                f"iter{iteration}: family compromised but winner's new token "
                f"still valid (got {r3.status_code}) — SEC-108 race NOT closed"
            )
        elif statuses == [200, 200]:
            # Both refresh calls succeeded — no reuse-detection triggered.
            # The last winner's token should still be usable.
            assert r3.status_code == 200, (
                f"iter{iteration}: clean double-refresh but 3rd call failed "
                f"({r3.status_code}) — spec says winner must remain usable"
            )


# ============================================================================
# Regression smoke — quick pass to ensure iter10 fixes did not break anything
# ============================================================================
class TestRegressions:
    def test_register_login(self):
        # register limit is 5/minute — wait to clear budget from any earlier calls
        import time
        time.sleep(20)
        email = f"TEST_iter11_reg_{uuid.uuid4().hex[:8]}@teebox.dev"
        r = requests.post(f"{BASE_URL}/api/auth/register",
                          json={"email": email, "password": PASS,
                                "display_name": "TEST Reg"})
        assert r.status_code == 200 and "access_token" in r.json()
        # login limit also 10/min — small extra pause
        time.sleep(8)
        r2 = requests.post(f"{BASE_URL}/api/auth/login",
                           json={"email": email, "password": PASS})
        assert r2.status_code == 200

    def test_refresh_happy_path(self, jordan):
        r = requests.post(f"{BASE_URL}/api/auth/refresh",
                          json={"refresh_token": jordan["refresh_token"]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["access_token"] and body["refresh_token"] != jordan["refresh_token"]
        jordan["access_token"] = body["access_token"]
        jordan["refresh_token"] = body["refresh_token"]

    def test_logout_revokes_refresh(self):
        # use module sam if available; else login (guarded by spacing above)
        import time
        time.sleep(8)
        auth = _login("sam@teebox.demo")
        r2 = requests.post(f"{BASE_URL}/api/auth/logout",
                           json={"refresh_token": auth["refresh_token"]})
        assert r2.status_code == 200 and r2.json()["ok"] is True
        r3 = requests.post(f"{BASE_URL}/api/auth/refresh",
                           json={"refresh_token": auth["refresh_token"]})
        assert r3.status_code == 401

    def test_null_clear_handicap_bio(self, reese):
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese),
                           json={"handicap": None, "bio": None,
                                 "home_course": None, "avatar": None})
        assert r.status_code == 200
        body = r.json()
        assert body["handicap"] is None
        assert body["bio"] is None
        assert body["home_course"] is None
        assert body.get("avatar") is None

    def test_avatar_oversize_413(self, reese):
        big = "data:image/png;base64," + ("A" * 900_000)
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(reese),
                           json={"avatar": big})
        assert r.status_code == 413

    def test_friends_shape(self, reese):
        me = requests.get(f"{BASE_URL}/api/auth/me",
                          headers=_hdr(reese)).json()
        r = requests.get(f"{BASE_URL}/api/users/{me['id']}/friends",
                         headers=_hdr(reese))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for f in data:
            for k in ("id", "display_name", "is_friend", "is_following",
                      "round_count"):
                assert k in f, f"friend missing key {k}: {f}"

    def test_wishlist_add_dup_delete(self, jordan):
        course = f"TEST_iter11_wl_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{BASE_URL}/api/wishlist", headers=_hdr(jordan),
                          json={"course_name": course})
        assert r.status_code == 200 and r.json()["added"] is True
        r2 = requests.post(f"{BASE_URL}/api/wishlist", headers=_hdr(jordan),
                           json={"course_name": course})
        assert r2.status_code == 200 and r2.json()["added"] is False
        r3 = requests.delete(f"{BASE_URL}/api/wishlist/{course}",
                             headers=_hdr(jordan))
        assert r3.status_code == 200 and r3.json()["removed"] is True


# ============================================================================
# Final cleanup — restore reese seed
# ============================================================================
def test_zz_final_restore_reese():
    import time
    time.sleep(8)
    auth = _login("reese@teebox.demo")
    r = requests.patch(f"{BASE_URL}/api/auth/me", headers=_hdr(auth),
                       json=SEED_REESE)
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "Reese Callahan"
    assert body["handicap"] == 8.4
    assert body["home_course"] == "Pebble Meadows GC"
