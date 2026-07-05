"""Iter9 backend tests: verify PATCH /api/auth/me now allows explicit-null clears
after fix (data.dict(exclude_unset=True)) while still ignoring omitted keys."""
import os
import base64
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL"))
assert BASE_URL, "backend URL missing"
BASE_URL = BASE_URL.rstrip("/")

PASS = "password123"


def _login(email: str) -> dict:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PASS}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def reese():
    return _login("reese@teebox.demo")


def _hdr(auth):
    return {"Authorization": f"Bearer {auth['access_token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def restore_reese_after(reese):
    """Ensure reese ends the test run with seed handicap=8.4 and canonical bio."""
    yield
    h = _hdr(reese)
    requests.patch(
        f"{BASE_URL}/api/auth/me",
        headers=h,
        json={
            "handicap": 8.4,
            "bio": "Weekend warrior. Always chasing the sunrise tee time.",
            "home_course": "Pebble Meadows GC",
            "avatar": None,
        },
        timeout=15,
    )


class TestPrimaryFixNullClear:
    def test_null_handicap_clears_and_reset_restores(self, reese):
        h = _hdr(reese)
        # ensure non-null starting handicap
        r1 = requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"handicap": 8.4}, timeout=15)
        assert r1.status_code == 200
        assert r1.json().get("handicap") == 8.4

        # clear via explicit null
        r2 = requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"handicap": None}, timeout=15)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body.get("handicap") is None, body

        # GET verifies persistence
        g = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        assert g.get("handicap") is None, g

        # restore to 8.4
        r3 = requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"handicap": 8.4}, timeout=15)
        assert r3.status_code == 200
        assert r3.json().get("handicap") == 8.4

    def test_omit_handicap_does_not_touch_it(self, reese):
        h = _hdr(reese)
        # baseline
        requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"handicap": 8.4}, timeout=15)
        # send unrelated field only
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"bio": "TEST_iter9_touch"}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("handicap") == 8.4, "handicap must be preserved when key is omitted"
        g = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        assert g.get("handicap") == 8.4
        assert g.get("bio") == "TEST_iter9_touch"

    def test_null_bio_clears(self, reese):
        h = _hdr(reese)
        requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"bio": "TEST_iter9_bio"}, timeout=15)
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"bio": None}, timeout=15)
        assert r.status_code == 200
        g = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        assert g.get("bio") is None, g

    def test_null_home_course_clears(self, reese):
        h = _hdr(reese)
        requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"home_course": "TEST_iter9_home"}, timeout=15)
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"home_course": None}, timeout=15)
        assert r.status_code == 200
        g = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        assert g.get("home_course") is None, g

    def test_null_avatar_clears(self, reese):
        h = _hdr(reese)
        # set a tiny valid data URI first
        tiny = "data:image/png;base64," + base64.b64encode(b"x" * 100).decode()
        requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"avatar": tiny}, timeout=15)
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"avatar": None}, timeout=15)
        assert r.status_code == 200
        g = requests.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15).json()
        assert g.get("avatar") is None, g

    def test_oversized_avatar_still_413(self, reese):
        h = _hdr(reese)
        raw = b"a" * 900_000
        big = "data:image/png;base64," + base64.b64encode(raw).decode()
        r = requests.patch(f"{BASE_URL}/api/auth/me", headers=h, json={"avatar": big}, timeout=30)
        assert r.status_code == 413, f"expected 413, got {r.status_code}: {r.text[:200]}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
