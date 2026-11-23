"""HTML pages, the JSON-vs-HTML error handlers, and the middleware (timing + CORS)."""

from .helpers import make_post


def test_home_page_lists_posts(client, create_user):
    _, headers = create_user("alice")
    make_post(client, headers, title="Visible on the home page")
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Visible on the home page" in r.text
    assert "alice" in r.text  # author loaded with selectinload


def test_post_and_user_pages(client, create_user):
    alice, headers = create_user("alice")
    post = make_post(client, headers)
    assert client.get(f"/posts/{post['id']}").status_code == 200
    assert client.get(f"/users/{alice['id']}/posts").status_code == 200


def test_errors_are_html_for_pages_and_json_for_api(client):
    page = client.get("/posts/999")
    assert page.status_code == 404
    assert page.headers["content-type"].startswith("text/html")
    assert "Not Found" in page.text  # the status_phrase filter in error.html

    api = client.get("/api/posts/999")
    assert api.status_code == 404
    assert api.json() == {"detail": "Post with id 999 not found"}

    assert client.get("/posts/abc").headers["content-type"].startswith("text/html")  # 422 page


def test_timing_middleware_adds_header(client):
    r = client.get("/api/posts")
    assert float(r.headers["x-process-time-ms"]) >= 0


def test_cors_preflight(client):
    # A browser sends this OPTIONS "preflight" before a cross-origin request with
    # an Authorization header.
    allowed = client.options(
        "/api/posts",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"

    blocked = client.options(
        "/api/posts",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in blocked.headers


# ---------------------------------------------------------------- frontend pages


def test_frontend_pages_render(client):
    pages = ["/login", "/register", "/forgot-password", "/reset-password", "/account", "/posts/new"]
    for path in pages:
        r = client.get(path)
        assert r.status_code == 200, path
        assert "/static/js/api.js" in r.text  # every page loads the API client


def test_posts_new_is_not_caught_by_post_id_route(client):
    # If /posts/{post_id} were declared first, "new" would fail int conversion -> 422.
    assert "Write a new post" in client.get("/posts/new").text


def test_edit_page_prefills_the_form(client, create_user):
    _, headers = create_user("alice")
    post = make_post(client, headers, title="Editable title", rating=3)
    r = client.get(f"/posts/{post['id']}/edit")
    assert r.status_code == 200
    assert 'value="Editable title"' in r.text
    assert client.get("/posts/999/edit").status_code == 404


def test_post_page_has_hidden_owner_actions(client, create_user):
    alice, headers = create_user("alice")
    post = make_post(client, headers)
    html = client.get(f"/posts/{post['id']}").text
    assert f'data-author-id="{alice["id"]}"' in html  # JS compares it with /api/users/me


def test_user_page_does_not_show_email(client, create_user):
    alice, _ = create_user("alice")
    html = client.get(f"/users/{alice['id']}/posts").text
    assert "alice@example.com" not in html
    assert "Joined" in html


def test_home_search_sort_and_pagination(client, create_user):
    _, headers = create_user("alice")
    for i in range(7):
        make_post(client, headers, title=f"Post number {i}", rating=(i % 5) + 1)
    make_post(client, headers, title="Special FastAPI guide")

    first = client.get("/").text
    assert "8 Posts" in first  # total badge
    assert first.count('class="post-card p-4"') == 5  # HOME_PAGE_SIZE
    assert 'aria-label="Posts pages"' in first  # pagination shown

    second = client.get("/", params={"page": 2}).text
    assert second.count('class="post-card p-4"') == 3

    found = client.get("/", params={"search": "fastapi"}).text
    assert "Special FastAPI guide" in found and "Post number" not in found
    assert 'value="fastapi"' in found  # search box keeps the term

    assert client.get("/", params={"sort": "bogus"}).status_code == 422
    assert client.get("/", params={"page": 0}).status_code == 422
    assert client.get("/", params={"search": ""}).status_code == 200  # empty box = no filter
