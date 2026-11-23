"""tests/helpers.py - small helper functions and constants shared by the test files.

(Fixtures live in conftest.py; plain helpers live here, because importing from
conftest.py directly is discouraged by pytest.)
"""

from fastapi.testclient import TestClient

PASSWORD = "secret123"
# The smallest thing our upload route accepts as a PNG: the 8-byte PNG signature.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def auth_headers(client: TestClient, username: str, password: str = PASSWORD) -> dict:
    """Log in and return the Authorization header for later requests."""
    # The login route expects FORM data (data=...), not JSON (json=...).
    r = client.post("/api/auth/token", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_post(client: TestClient, headers: dict, **fields) -> dict:
    """Create a post as the user behind `headers`; extra fields override the defaults."""
    body = {"title": "Hello world", "content": "Some interesting content here."}
    body.update(fields)
    r = client.post("/api/posts", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()
