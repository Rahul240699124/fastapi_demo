# fastapi_demo

A blog application built while learning **FastAPI**. Users sign up, log in with JWT, upload a profile picture and write posts. Posts can be browsed as server-rendered HTML pages or used through a JSON API. Data is stored in **MySQL** with **async SQLAlchemy 2.x**, and the schema is managed with **Alembic**.

Every source file has comments explaining *why* the code is written that way, so the project also works as a study reference.

## Features

- JSON REST API with automatic docs (Swagger UI and ReDoc)
- HTML pages rendered with **Jinja2** and **Bootstrap 5**
- **JWT authentication** (OAuth2 password flow), with ownership checks on create, update and delete
- Passwords hashed with **Argon2**, never stored or returned in plain text
- Forgot / reset password using single-use, expiring, hashed tokens
- **Profile picture upload** with type, size and real-content checks
- **Pagination, search, filtering and sorting** for posts
- **Background tasks** for emails (written to a local outbox file)
- **CORS** and a custom request-timing / logging middleware
- Settings loaded from **`.env`** with `pydantic-settings`
- **Alembic** migrations
- **pytest** suite running on an in-memory SQLite database
- **Docker** and docker-compose setup (app + MySQL)

## Tech stack

| Area | Tool |
| --- | --- |
| Web framework | FastAPI |
| Templates | Jinja2 + Bootstrap 5.3 |
| ORM | SQLAlchemy 2.x (async) |
| Database | MySQL 8 (aiomysql driver) |
| Migrations | Alembic |
| Validation / settings | Pydantic v2, pydantic-settings |
| Auth | PyJWT, pwdlib (Argon2) |
| Tests | pytest, aiosqlite |
| Package manager | uv |

## Getting started

### 1. Install dependencies

```bash
uv sync
```

### 2. Create your `.env`

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Then edit `.env`. At minimum, set `DATABASE_URL` and a random `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Create the database and its tables

```sql
CREATE DATABASE fastapi_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

```bash
uv run alembic upgrade head
```

If your database already has the tables from an older version of this project, run `uv run alembic stamp head` instead. It records the current version without changing anything.

### 4. Run the development server

```bash
uv run fastapi dev main.py
```

- App: <http://127.0.0.1:8000>
- Swagger UI: <http://127.0.0.1:8000/docs>. Click **Authorize** and log in to try the protected routes.
- ReDoc: <http://127.0.0.1:8000/redoc>

## Running with Docker

```bash
docker compose up --build
```

This starts MySQL and the app together, applies the migrations, and serves the app at <http://localhost:8080>.

## Running the tests

```bash
uv run pytest           # all tests
uv run pytest -v        # one line per test
uv run pytest tests/test_posts.py::test_pagination   # a single test
```

The tests use a fresh in-memory SQLite database for each test, so they never touch MySQL.

## API overview

"Login" means the route needs an `Authorization: Bearer <token>` header. "Owner" means you must also be the account or post owner.

### Auth

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| POST | `/api/auth/token` | public | Log in with username or email + password (form data) and get a JWT |
| POST | `/api/auth/forgot-password` | public | Email a reset token |
| POST | `/api/auth/reset-password` | public | Set a new password using the token |

### Users

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| GET | `/api/users?skip=&limit=` | public | List users |
| POST | `/api/users` | public | Sign up |
| GET | `/api/users/me` | login | The logged-in user |
| PUT | `/api/users/me/picture` | login | Upload a profile picture (JPEG/PNG/WebP, max 2 MB) |
| DELETE | `/api/users/me/picture` | login | Go back to the default picture |
| GET | `/api/users/{id}` | public | One user |
| PATCH | `/api/users/{id}` | owner | Update your account |
| DELETE | `/api/users/{id}` | owner | Delete your account and its posts |
| GET | `/api/users/{id}/posts` | public | A user's posts |

### Posts

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| GET | `/api/posts` | public | List posts, paginated (see query parameters below) |
| POST | `/api/posts` | login | Create a post; you are the author |
| GET | `/api/posts/{id}` | public | One post |
| PATCH | `/api/posts/{id}` | owner | Edit your post |
| DELETE | `/api/posts/{id}` | owner | Delete your post |

Query parameters for `GET /api/posts`: `skip`, `limit` (1–100), `search` (title or content), `published` (true/false), `author_id`, `sort` (`newest`, `oldest` or `rating`). The response looks like `{"total": 42, "skip": 0, "limit": 10, "items": [...]}`.

### Website pages

| Page | What it does |
| --- | --- |
| `/` or `/posts` | All posts, with search, sorting and pagination (`?search=&sort=&page=`) |
| `/posts/{id}` | One post. Its author also sees **Edit** and **Delete** buttons. |
| `/users/{id}/posts` | A user's posts |
| `/login`, `/register` | Log in or sign up |
| `/forgot-password`, `/reset-password` | Password reset flow |
| `/account` | Your profile: upload or remove your picture, edit details, delete your account |
| `/posts/new`, `/posts/{id}/edit` | Write or edit a post |

Pages that need a login use JavaScript (`static/js/api.js`) to call the JSON API with your JWT, which is stored in the browser's `localStorage`. The website is simply another client of the API. The read-only pages are rendered on the server.

### Example

```bash
# sign up, then log in
curl -X POST http://127.0.0.1:8000/api/users -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com", "password": "secret123"}'

TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/token \
  -d "username=alice&password=secret123" | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# create a post as alice
curl -X POST http://127.0.0.1:8000/api/posts -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Hello", "content": "My first post on FastAPI!", "rating": 5}'
```

## Project structure

```text
fastapi_demo/
├── main.py            # App setup: middleware, routers, HTML pages, error handlers
├── config.py          # Settings loaded from .env (pydantic-settings)
├── database.py        # Async engine, sessions, get_db dependency
├── models.py          # SQLAlchemy models: User, Post, PasswordResetToken
├── schemas.py         # Pydantic request/response schemas
├── security.py        # Password hashing, JWT, reset tokens
├── dependencies.py    # get_current_user (authentication)
├── emails.py          # Emails sent as background tasks
├── routers/           # JSON API: auth.py, users.py, posts.py
├── migrations/        # Alembic migrations
├── tests/             # pytest suite
├── templates/         # Jinja2 templates (layout, pages, partials/)
├── static/            # CSS, js/api.js (browser API client), default profile picture
├── media/             # Uploaded files (git-ignored)
├── Dockerfile
└── docker-compose.yml
```

## Notes

- **Changing a model:** run `uv run alembic revision --autogenerate -m "..."`, read the generated file, then run `uv run alembic upgrade head`.
- **Emails** aren't really sent. They're appended to `logs/emails.log`, so you can read the password-reset token there.
- **MySQL storage engine:** all tables use **InnoDB**, so foreign keys and transactions work even where the server's default is MyISAM (as in WAMP).
