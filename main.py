"""
main.py - creates the FastAPI app and wires everything together.

REQUEST FLOW (what happens when a request arrives):

    client
      -> middleware  (CORS, then our timing/logging middleware) - runs around EVERY request
      -> routing     (FastAPI finds the matching path + method)
      -> dependencies (get_db, get_current_user, query/body validation)
      -> route function (your code)
      -> response_model filtering (Pydantic schema)
      -> middleware again (adds headers, logs)  -> client
    If anything raises HTTPException / validation errors, the exception handlers at the
    bottom of this file build the response instead.

WHERE THINGS LIVE:
    config.py        settings from .env           database.py   engine, sessions, get_db
    models.py        tables (SQLAlchemy)          schemas.py    request/response shapes
    security.py      hashing + JWT                dependencies.py  get_current_user
    emails.py        background-task emails       routers/      the JSON API (/api/...)
    main.py          app + HTML pages + error handlers
    templates/       Jinja2 pages                 static/js/api.js  the website's API client
    migrations/      Alembic database migrations  tests/        pytest suite
"""

import logging
import math
import time
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.exceptions import HTTPException as StarletteHTTPException

import models
from config import settings
from database import DbSession, engine
from routers import auth, posts, users
from routers.posts import PostSort, query_posts

# =============================================================== Logging
# logging > print(): every line gets a time, level and source, and levels can be
# filtered (DEBUG < INFO < WARNING < ERROR). Other modules just do
# `logger = logging.getLogger(__name__)` and their messages end up here.
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
# Our own debug logs are useful, but third-party DEBUG output (e.g. the MySQL driver)
# is very noisy - keep those at INFO.
for noisy in ("aiomysql", "asyncio", "multipart", "python_multipart"):
    logging.getLogger(noisy).setLevel(logging.INFO)
logger = logging.getLogger("app")


# =============================================================== Lifespan
# Code before `yield` runs ONCE at startup, code after it ONCE at shutdown.
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ---- Startup
    # We USED to call Base.metadata.create_all() here. Now Alembic owns the schema
    # (run `uv run alembic upgrade head`), because create_all can only CREATE missing
    # tables - it never adds a column or changes an existing table.
    logger.info("Starting %s (debug=%s)", settings.app_name, settings.debug)
    yield
    # ---- Shutdown: close every pooled DB connection cleanly.
    await engine.dispose()
    logger.info("Shut down")


app = FastAPI(
    title=settings.app_name,
    description="A blog API built while learning FastAPI. Log in with **Authorize**.",
    version="1.0.0",
    lifespan=lifespan,  # without this argument the lifespan function never runs
)


# =============================================================== Middleware
# Middleware wraps EVERY request/response, like layers of an onion.
# The LAST one added is the OUTERMOST layer (it sees the request first).

# ---- 1) Our own middleware: time each request, log it, add a response header.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)  # passes the request on to the route...
    duration_ms = (time.perf_counter() - start) * 1000  # ...and we're back afterwards
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
    if not request.url.path.startswith(("/static", "/media")):  # skip noisy files
        logger.info(
            "%s %s -> %s (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
    return response


# ---- 2) CORS (Cross-Origin Resource Sharing).
# Browsers BLOCK JavaScript on one origin (e.g. a React app on http://localhost:3000)
# from reading responses from another origin (this API on :8000) unless the API says
# it's allowed via Access-Control-* headers. CORSMiddleware adds those headers for the
# origins listed in settings.cors_origins and answers the browser's "preflight"
# OPTIONS requests. It doesn't affect curl/Postman - CORS is a browser-only rule.
# Added last -> outermost, so even error responses get the CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # never ["*"] together with credentials
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],  # includes "Authorization", needed for our JWT header
)


# =============================================================== Static & media files
app.mount("/static", StaticFiles(directory="static"), name="static")  # CSS, default avatar

# User uploads. media/ is git-ignored, so create it if missing -
# StaticFiles refuses to start when its directory doesn't exist.
Path(settings.media_dir, "profile_pics").mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")


# =============================================================== Routers
# Each router brings its own prefix (/api/auth, /api/users, /api/posts) and /docs tag.
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)


# =============================================================== Templates
templates = Jinja2Templates(directory="templates")


def status_phrase(code) -> str:
    """Turn a status code (e.g. 404 or "404") into its standard name ("Not Found")."""
    try:
        return HTTPStatus(int(code)).phrase
    except ValueError, TypeError:  # Python 3.14: several exceptions without parentheses
        return "An Error Occurred"


# Custom Jinja filter, used in error.html as {{ title | status_phrase }}
templates.env.filters["status_phrase"] = status_phrase


# =============================================================== HTML pages
# These return HTML (not JSON) and are hidden from /docs (include_in_schema=False).
#
# HOW THE WEBSITE AND THE API FIT TOGETHER:
#   * Read-only pages (home, a post, a user's posts) are rendered here on the server.
#   * Anything that needs a login (writing posts, account settings) is a page whose
#     JavaScript calls the JSON API with the user's JWT (see static/js/api.js).
#     So these routes don't check authentication themselves - the API routes do.

HOME_PAGE_SIZE = 5


def page(request: Request, template: str, title: str, **context) -> HTMLResponse:
    """Render a template. Every variable the template uses goes in the context dict.
    (In TemplateResponse(request, name, context) the 4th positional arg is status_code!)"""
    return templates.TemplateResponse(request, template, {"title": title, **context})


@app.get("/", response_class=HTMLResponse, include_in_schema=False, name="home")
@app.get("/posts", response_class=HTMLResponse, include_in_schema=False, name="posts")
async def home(
    request: Request,
    db: DbSession,
    # Read from the URL:  /?page=2&search=fastapi&sort=rating
    page_number: Annotated[int, Query(alias="page", ge=1)] = 1,
    search: Annotated[str | None, Query(max_length=100)] = None,
    sort: PostSort = "newest",
):
    search = (search or "").strip() or None  # an empty search box means "no search"
    # SAME function as GET /api/posts -> identical search / sort / paging rules.
    # (It also loads post.author, which the post cards display.)
    total, posts_on_page = await query_posts(
        db,
        skip=(page_number - 1) * HOME_PAGE_SIZE,  # page 1 -> skip 0, page 2 -> skip 5...
        limit=HOME_PAGE_SIZE,
        search=search,
        sort=sort,
    )
    return page(
        request,
        "home.html",
        "🏠 Home",
        posts=posts_on_page,
        total=total,
        page=page_number,
        pages=max(1, math.ceil(total / HOME_PAGE_SIZE)),  # ceil: 11 posts / 5 = 3 pages
        search=search,
        sort=sort,
    )


# ---- Pages driven by JavaScript + the JSON API (the server only sends the shell)


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    return page(request, "login.html", "Log in")


@app.get("/register", response_class=HTMLResponse, include_in_schema=False)
async def register_page(request: Request):
    return page(request, "register.html", "Sign up")


@app.get("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
async def forgot_password_page(request: Request):
    return page(request, "forgot_password.html", "Forgot password")


@app.get("/reset-password", response_class=HTMLResponse, include_in_schema=False)
async def reset_password_page(request: Request):
    return page(request, "reset_password.html", "Reset password")


@app.get("/account", response_class=HTMLResponse, include_in_schema=False)
async def account_page(request: Request):
    return page(request, "account.html", "My Account")


# "/posts/new" MUST come before "/posts/{post_id}": routes are matched in order, and
# "/posts/{post_id}" would otherwise catch "new" and fail to turn it into an int (422).
@app.get("/posts/new", response_class=HTMLResponse, include_in_schema=False)
async def new_post_page(request: Request):
    return page(request, "post_form.html", "New Post", post=None)


@app.get("/posts/{post_id}/edit", response_class=HTMLResponse, include_in_schema=False)
async def edit_post_page(request: Request, post_id: int, db: DbSession):
    post = await db.get(models.Post, post_id)  # the template only needs plain columns
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {post_id} not found",
        )
    return page(request, "post_form.html", f"Edit: {post.title}", post=post)


# ---- Server-rendered read-only pages


@app.get("/posts/{post_id}", response_class=HTMLResponse, include_in_schema=False)
async def get_post_page(request: Request, post_id: int, db: DbSession):
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id)
    )
    post = result.scalars().first()
    if post is None:
        # Not an /api path -> the handler below renders error.html instead of JSON.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {post_id} not found",
        )
    return templates.TemplateResponse(
        request, "post.html", {"post": post, "title": post.title}
    )


@app.get("/users/{user_id}/posts", response_class=HTMLResponse, include_in_schema=False)
async def get_user_posts_page(request: Request, user_id: int, db: DbSession):
    user = await db.get(models.User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))  # post_card.html uses post.author
        .where(models.Post.user_id == user_id)
        .order_by(models.Post.date_posted.desc())
    )
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {"posts": posts, "user": user, "title": f"Posts by User {user.username}"},
    )


# =============================================================== Error handlers
# ONE app, TWO kinds of clients: /api/... callers want JSON, browsers want a page.
# So each handler checks the URL and picks the format.
# (Only one handler per exception class can exist - registering a second one for
# the same class silently replaces the first.)


@app.exception_handler(StarletteHTTPException)  # 404, 401, 403, 400... (HTTPException)
async def common_exception_handler(request: Request, exception: StarletteHTTPException):
    if request.url.path.startswith("/api"):
        # FastAPI's default -> JSON {"detail": ...}, keeping headers such as
        # WWW-Authenticate on 401 responses.
        return await http_exception_handler(request, exception)

    message = exception.detail or "An error occurred please try again later."
    return templates.TemplateResponse(
        request,
        "error.html",
        {"error": message, "title": exception.status_code},
        status_code=exception.status_code,
    )


@app.exception_handler(RequestValidationError)  # 422: bad body / path / query values
async def validation_exception_handler(
    request: Request, exception: RequestValidationError
):
    if request.url.path.startswith("/api"):
        # FastAPI's default -> 422 JSON {"detail": [ {loc, msg, type}, ... ]}
        return await request_validation_exception_handler(request, exception)
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "error": "Unprocessable Entity: unable to be followed due to semantic errors.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
