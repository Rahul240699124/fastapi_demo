"""Sign-up, login, JWT protection and the forgot/reset-password flow.

A test = arrange (set up data) -> act (call the API) -> assert (check the result).
`assert` fails the test when the expression is False.
"""

from datetime import timedelta
from pathlib import Path

import jwt

from config import settings
from security import create_access_token

from .helpers import PASSWORD, auth_headers


def test_register_returns_user_without_password(client):
    r = client.post(
        "/api/users",
        json={"username": "alice", "email": "alice@example.com", "password": PASSWORD},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == "alice"
    assert body["image_path"] == "/static/profile_pics/default.png"
    # response_model=UserResponse filters these out
    assert "password" not in body and "password_hash" not in body


def test_register_sends_welcome_email_in_background(client, create_user):
    create_user("alice")
    # TestClient runs background tasks before returning, so the email is already "sent".
    outbox = Path(settings.email_outbox_file).read_text(encoding="utf-8")
    assert "To: alice@example.com" in outbox
    assert "Welcome" in outbox


def test_register_duplicate_username_and_email(client, create_user):
    create_user("alice")
    same_username = {"username": "alice", "email": "new@example.com", "password": PASSWORD}
    same_email = {"username": "other", "email": "alice@example.com", "password": PASSWORD}
    assert client.post("/api/users", json=same_username).status_code == 400
    assert client.post("/api/users", json=same_email).status_code == 400


def test_register_validation(client):
    r = client.post(
        "/api/users", json={"username": "al", "email": "nope", "password": "123"}
    )
    assert r.status_code == 422
    bad_fields = {error["loc"][-1] for error in r.json()["detail"]}
    assert bad_fields == {"username", "email", "password"}


def test_login_with_username_or_email(client, create_user):
    create_user("alice")
    for login_name in ("alice", "alice@example.com"):
        r = client.post(
            "/api/auth/token", data={"username": login_name, "password": PASSWORD}
        )
        assert r.status_code == 200
        assert r.json()["token_type"] == "bearer"


def test_login_wrong_password(client, create_user):
    create_user("alice")
    r = client.post("/api/auth/token", data={"username": "alice", "password": "wrong-pass"})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_me_requires_a_valid_token(client, create_user):
    user, headers = create_user("alice")

    assert client.get("/api/users/me").status_code == 401  # no header at all
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/api/users/me", headers=bad).status_code == 401

    r = client.get("/api/users/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == user["id"]


def test_expired_token_is_rejected(client, create_user, monkeypatch):
    user, _ = create_user("alice")
    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)  # already expired
    expired = create_access_token(user["id"])
    r = client.get("/api/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_token_signed_with_another_key_is_rejected(client, create_user):
    user, _ = create_user("alice")
    forged = jwt.encode(
        {"sub": str(user["id"]), "type": "access"},
        "an-attacker-guessed-key-that-is-long-enough",  # not our secret_key
        algorithm="HS256",
    )
    r = client.get("/api/users/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_token_of_deleted_user_stops_working(client, create_user):
    user, headers = create_user("alice")
    assert client.delete(f"/api/users/{user['id']}", headers=headers).status_code == 200
    assert client.get("/api/users/me", headers=headers).status_code == 401


# ---------------------------------------------------------------- password reset


def read_reset_token() -> str:
    """Pull the token out of the last "sent" reset email."""
    outbox = Path(settings.email_outbox_file).read_text(encoding="utf-8")
    email = outbox.rsplit("Subject: Reset your password", 1)[1]
    # The token is on its own line after "...minutes):"
    return email.split("):\n\n", 1)[1].split("\n", 1)[0].strip()


def test_forgot_password_does_not_reveal_unknown_emails(client, create_user):
    create_user("alice")
    known = client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "ghost@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()  # identical answers


def test_reset_password_full_flow(client, create_user):
    create_user("alice")
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    token = read_reset_token()

    r = client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "brand-new-pass"}
    )
    assert r.status_code == 200

    # old password no longer works, new one does
    old = client.post("/api/auth/token", data={"username": "alice", "password": PASSWORD})
    assert old.status_code == 401
    assert auth_headers(client, "alice", "brand-new-pass")

    # a reset token works only once
    again = client.post(
        "/api/auth/reset-password", json={"token": token, "new_password": "another-pass1"}
    )
    assert again.status_code == 400


def test_reset_password_with_expired_token(client, create_user, monkeypatch):
    create_user("alice")
    monkeypatch.setattr(settings, "reset_token_expire_minutes", -1)
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    r = client.post(
        "/api/auth/reset-password",
        json={"token": read_reset_token(), "new_password": "brand-new-pass"},
    )
    assert r.status_code == 400


def test_access_token_expiry_setting_is_used():
    token = create_access_token(1)
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    lifetime = timedelta(seconds=payload["exp"] - payload["iat"])
    assert lifetime == timedelta(minutes=settings.access_token_expire_minutes)
