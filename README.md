# fastapi_demo


A small blog application built while learning **FastAPI**. Users write posts, which can be browsed as server-rendered HTML pages or accessed through a JSON API. Data is stored in **MySQL** through **SQLAlchemy 2.x**.

## Features

- HTML pages rendered with **Jinja2** and styled with **Bootstrap 5**
- JSON REST API with automatic docs (Swagger UI and ReDoc)
- Users and posts stored in MySQL; each post belongs to a user
- Passwords hashed with **Argon2** (via `pwdlib`), never stored or returned in plain text
- Request validation with **Pydantic**
- Custom error pages for HTML routes and JSON errors for `/api` routes
- Default profile picture for users without one

## Tech stack

| Area | Tool |
| --- | --- |
| Web framework | FastAPI |
| Templates | Jinja2 + Bootstrap 5.3 |
| ORM | SQLAlchemy 2.x |
| Database | MySQL 8 (PyMySQL driver) |
| Validation | Pydantic |
| Password hashing | pwdlib (Argon2) |
| Package manager | uv |

## Requirements

- Python **3.14+**
- [uv](https://docs.astral.sh/uv/)
- A running MySQL server (for example from WAMP or XAMPP)

## Getting started

### 1. Install dependencies

```bash
uv sync
```

### 2. Create the database

```sql
CREATE DATABASE fastapi_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

The app connects as user `root` with no password on `localhost:3306`. To use different credentials, edit `SQLALCHEMY_DATABASE_URL` in `database.py`:

```python
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://<user>:<password>@<host>:<port>/fastapi_demo?charset=utf8mb4"
```

The tables are created automatically the first time the app starts.

### 3. Run the development server

```bash
uv run fastapi dev main.py
```

Then open:

- App: <http://127.0.0.1:8000>
- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>

## Routes

### HTML pages

| Method | Path | Description |
| --- | --- | --- |
| GET | `/` or `/posts` | All posts |
| GET | `/posts/{post_id}` | A single post |
| GET | `/users/{user_id}/posts` | All posts by one user |

### JSON API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/users` | List users |
| POST | `/api/users` | Create a user |
| GET | `/api/users/{user_id}` | Get one user |
| GET | `/api/users/{user_id}/posts` | List one user's posts |
| GET | `/api/posts` | List posts |
| POST | `/api/posts` | Create a post |
| GET | `/api/posts/{post_id}` | Get one post |

### Example: create a user, then a post

```bash
curl -X POST http://127.0.0.1:8000/api/users \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com", "password": "secret123"}'

curl -X POST http://127.0.0.1:8000/api/posts \
  -H "Content-Type: application/json" \
  -d '{"title": "Hello", "content": "My first post on FastAPI!", "rating": 5, "user_id": 1}'
```

Validation rules:

- **User:** username 3–50 characters, a valid email, password 8–128 characters
- **Post:** title 3–100 characters, content 10–1000 characters, rating 1–5 (optional), and `user_id` must belong to an existing user

## Project structure

```text
fastapi_demo/
├── main.py          # App setup, routes, exception handlers
├── database.py      # Database connection, session, Base model
├── models.py        # SQLAlchemy models: User, Post, PasswordResetToken
├── schemas.py       # Pydantic request/response schemas
├── security.py      # Password hashing helpers
├── templates/       # Jinja2 templates (layout, pages, partials/)
└── static/          # CSS and profile pictures
```

## Notes

- **MySQL storage engine:** all tables are created with the **InnoDB** engine, so foreign keys and transactions work even when the server's default is MyISAM (as it is in WAMP).
- **Schema changes:** the app uses `create_all()`, which only creates missing tables. After changing a model, update the existing table yourself with `ALTER TABLE`, or drop and recreate it.
