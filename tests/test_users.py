"""User endpoints: listing, ownership rules (401 vs 403), deleting, picture uploads."""

from pathlib import Path

from config import settings

from .helpers import PNG_BYTES, make_post


def test_list_users_is_paginated(client, create_user):
    for name in ("alice", "bob", "carol"):
        create_user(name)

    page = client.get("/api/users", params={"skip": 1, "limit": 1}).json()
    assert [u["username"] for u in page] == ["bob"]

    assert client.get("/api/users", params={"limit": 500}).status_code == 422  # le=100


def test_get_unknown_user(client):
    assert client.get("/api/users/999").status_code == 404


def test_update_own_account(client, create_user):
    user, headers = create_user("alice")
    r = client.patch(
        f"/api/users/{user['id']}", json={"username": "alice2"}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["username"] == "alice2"
    assert r.json()["email"] == "alice@example.com"  # untouched (exclude_unset)


def test_update_rules(client, create_user):
    alice, alice_headers = create_user("alice")
    bob, _ = create_user("bob")

    # 401: not logged in
    assert client.patch(f"/api/users/{alice['id']}", json={}).status_code == 401
    # 403: logged in as alice, trying to change bob
    r = client.patch(
        f"/api/users/{bob['id']}", json={"username": "hacked"}, headers=alice_headers
    )
    assert r.status_code == 403
    # 400: username already taken
    r = client.patch(
        f"/api/users/{alice['id']}", json={"username": "bob"}, headers=alice_headers
    )
    assert r.status_code == 400


def test_delete_account_also_deletes_posts(client, create_user):
    alice, headers = create_user("alice")
    post = make_post(client, headers)

    assert client.delete(f"/api/users/{alice['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/users/{alice['id']}").status_code == 404
    assert client.get(f"/api/posts/{post['id']}").status_code == 404  # cascade


def test_cannot_delete_someone_else(client, create_user):
    _, alice_headers = create_user("alice")
    bob, _ = create_user("bob")
    assert client.delete(f"/api/users/{bob['id']}", headers=alice_headers).status_code == 403


def test_user_posts_list(client, create_user):
    alice, headers = create_user("alice")
    assert client.get(f"/api/users/{alice['id']}/posts").json() == []  # empty, not 404
    make_post(client, headers, title="Alice's post")
    posts = client.get(f"/api/users/{alice['id']}/posts").json()
    assert [p["title"] for p in posts] == ["Alice's post"]
    assert client.get("/api/users/999/posts").status_code == 404


# ---------------------------------------------------------------- picture upload


def upload(client, headers, content=PNG_BYTES, filename="me.png", content_type="image/png"):
    # files={field_name: (filename, bytes, content_type)} -> multipart/form-data
    return client.put(
        "/api/users/me/picture",
        files={"file": (filename, content, content_type)},
        headers=headers,
    )


def test_upload_picture(client, create_user):
    _, headers = create_user("alice")
    r = upload(client, headers)
    assert r.status_code == 200
    body = r.json()
    assert body["image_path"].startswith("/media/profile_pics/")
    assert body["image_file"] != "me.png"  # we never keep the client's filename
    saved = Path(settings.media_dir, "profile_pics", body["image_file"])
    assert saved.read_bytes() == PNG_BYTES


def test_new_picture_replaces_old_file(client, create_user):
    _, headers = create_user("alice")
    first = upload(client, headers).json()["image_file"]
    second = upload(client, headers).json()["image_file"]
    folder = Path(settings.media_dir, "profile_pics")
    assert not (folder / first).exists()
    assert (folder / second).exists()


def test_delete_picture_goes_back_to_default(client, create_user):
    _, headers = create_user("alice")
    upload(client, headers)
    r = client.delete("/api/users/me/picture", headers=headers)
    assert r.json()["image_path"] == "/static/profile_pics/default.png"


def test_upload_rejects_bad_files(client, create_user, monkeypatch):
    _, headers = create_user("alice")
    # wrong declared type
    assert upload(client, headers, b"hello", "a.txt", "text/plain").status_code == 415
    # says PNG, but the bytes aren't an image
    assert upload(client, headers, b"not really a png", "a.png").status_code == 400
    # too big
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)
    assert upload(client, headers).status_code == 413
    # not logged in
    assert upload(client, {}).status_code == 401
