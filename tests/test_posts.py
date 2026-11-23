"""Post endpoints: auth & ownership, plus pagination / search / filters / sorting."""

from .helpers import make_post


def test_create_post_requires_login(client):
    r = client.post("/api/posts", json={"title": "Hello", "content": "Some content here"})
    assert r.status_code == 401


def test_create_post_author_comes_from_token(client, create_user):
    alice, headers = create_user("alice")
    post = make_post(client, headers, rating=4)
    assert post["user_id"] == alice["id"]
    assert post["author"] == {
        "id": alice["id"],
        "username": "alice",
        "image_path": "/static/profile_pics/default.png",
    }
    assert post["likes"] == 0


def test_create_post_ignores_user_id_in_body(client, create_user):
    alice, alice_headers = create_user("alice")
    bob, _ = create_user("bob")
    # Trying to post "as bob": the extra field is ignored, author is still alice.
    post = make_post(client, alice_headers, user_id=bob["id"])
    assert post["user_id"] == alice["id"]


def test_get_post(client, create_user):
    _, headers = create_user("alice")
    post = make_post(client, headers)
    assert client.get(f"/api/posts/{post['id']}").json()["title"] == post["title"]
    assert client.get("/api/posts/999").status_code == 404
    assert client.get("/api/posts/abc").status_code == 422


def test_update_and_delete_own_post(client, create_user):
    _, headers = create_user("alice")
    post = make_post(client, headers)

    r = client.patch(f"/api/posts/{post['id']}", json={"rating": 5}, headers=headers)
    assert r.status_code == 200
    assert r.json()["rating"] == 5
    assert r.json()["title"] == post["title"]  # untouched

    assert client.delete(f"/api/posts/{post['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/posts/{post['id']}").status_code == 404


def test_cannot_change_someone_elses_post(client, create_user):
    _, alice_headers = create_user("alice")
    _, bob_headers = create_user("bob")
    post = make_post(client, alice_headers)

    r = client.patch(f"/api/posts/{post['id']}", json={"rating": 1}, headers=bob_headers)
    assert r.status_code == 403
    assert client.delete(f"/api/posts/{post['id']}", headers=bob_headers).status_code == 403


def test_update_validation(client, create_user):
    _, headers = create_user("alice")
    post = make_post(client, headers)
    r = client.patch(f"/api/posts/{post['id']}", json={"title": ""}, headers=headers)
    assert r.status_code == 422  # same rules as on create


# ---------------------------------------------------------------- listing


def test_pagination(client, create_user):
    _, headers = create_user("alice")
    for i in range(5):
        make_post(client, headers, title=f"Post number {i}")

    page = client.get("/api/posts", params={"skip": 2, "limit": 2}).json()
    assert page["total"] == 5  # all matching posts, not just this page
    assert page["skip"] == 2 and page["limit"] == 2
    assert len(page["items"]) == 2

    assert client.get("/api/posts", params={"limit": 0}).status_code == 422
    assert client.get("/api/posts", params={"limit": 101}).status_code == 422


def test_search_filters_and_sort(client, create_user):
    alice, alice_headers = create_user("alice")
    _, bob_headers = create_user("bob")
    make_post(client, alice_headers, title="FastAPI tips", rating=3)
    make_post(client, alice_headers, title="Draft idea", published=False, rating=5)
    make_post(client, bob_headers, title="Cooking", content="Nothing about fastapi here")

    def titles(**params):
        return [p["title"] for p in client.get("/api/posts", params=params).json()["items"]]

    # search is case-insensitive and looks in title AND content
    assert sorted(titles(search="FASTAPI")) == ["Cooking", "FastAPI tips"]
    assert titles(published=False) == ["Draft idea"]
    assert sorted(titles(author_id=alice["id"])) == ["Draft idea", "FastAPI tips"]
    assert titles(sort="rating")[:2] == ["Draft idea", "FastAPI tips"]  # 5, then 3
    assert client.get("/api/posts", params={"sort": "random"}).status_code == 422
