"""
tests/conftest.py - shared pytest FIXTURES (setup code that tests ask for by name).

    def test_something(client, create_user): ...
                       ^^^^^^  ^^^^^^^^^^^  pytest sees these parameter names, runs the
                                            matching fixtures below and passes the results.

THE TEST DATABASE:
    Tests must NOT touch your real MySQL data. Each test gets a brand-new, empty
    SQLite database that lives only in memory and disappears afterwards. That keeps
    tests fast, independent of each other, and runnable anywhere (no MySQL needed).

    The trick is FastAPI's `app.dependency_overrides`: we tell the app
    "whenever a route asks for get_db, call override_get_db instead".
    The route code doesn't change at all - that's the power of dependency injection.

RUN:   uv run pytest            (all tests)
       uv run pytest -v         (one line per test)
       uv run pytest tests/test_posts.py::test_create_post_requires_login   (one test)
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from config import settings
from database import Base, get_db
from main import app

from .helpers import PASSWORD, auth_headers


@pytest.fixture
def client(tmp_path, monkeypatch):
    # ---- Send uploads and "emails" to a temporary folder instead of the real ones.
    # monkeypatch undoes these changes automatically after the test.
    monkeypatch.setattr(settings, "media_dir", str(tmp_path / "media"))
    monkeypatch.setattr(settings, "email_outbox_file", str(tmp_path / "emails.log"))

    # ---- An in-memory SQLite database. StaticPool = always reuse ONE connection;
    # otherwise each new connection would see a different, empty in-memory database.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    TestSession = async_sessionmaker(engine, autoflush=False, expire_on_commit=False)

    async def override_get_db():
        async with TestSession() as session:
            yield session

    async def create_tables():
        async with engine.begin() as conn:
            # Tests build tables straight from the models (fast) instead of Alembic.
            await conn.run_sync(Base.metadata.create_all)

    app.dependency_overrides[get_db] = override_get_db

    # `with TestClient(app)` runs the app's lifespan (startup/shutdown) and gives us
    # c.portal: a way to run async code inside the app's own event loop.
    with TestClient(app) as c:
        c.portal.call(create_tables)
        yield c  # <- the test runs here
        c.portal.call(engine.dispose)

    app.dependency_overrides.clear()  # leave the app as we found it


@pytest.fixture
def create_user(client):
    """A FACTORY fixture: returns a function, so one test can create several users.

    Returns (user_json, auth_headers) - the headers are ready to send:
        user, headers = create_user("alice")
        client.post("/api/posts", json=..., headers=headers)
    """

    def _create(username: str = "alice", password: str = PASSWORD):
        r = client.post(
            "/api/users",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": password,
            },
        )
        assert r.status_code == 201, r.text
        return r.json(), auth_headers(client, username, password)

    return _create
