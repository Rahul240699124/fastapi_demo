from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.exceptions import HTTPException as StarletteHTTPException

import models
from database import Base, DbSession, engine
from routers import posts, users


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ## Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

# User-uploaded files (profile pictures). media/ is git-ignored, so create it if it's
# missing - StaticFiles refuses to start when its directory doesn't exist.
Path("media/profile_pics").mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

# JSON API routes live in routers/ (prefixes /api/users and /api/posts)
app.include_router(users.router)
app.include_router(posts.router)

templates = Jinja2Templates(directory="templates")


def status_phrase(code) -> str:
    """Turn a status code (e.g. 404 or "404") into its standard name ("Not Found")."""
    try:
        return HTTPStatus(int(code)).phrase
    except ValueError, TypeError:
        return "An Error Occurred"


templates.env.filters["status_phrase"] = status_phrase


# ---------------------------------------------------------------- HTML pages


@app.get("/", response_class=HTMLResponse, include_in_schema=False, name="home")
@app.get("/posts", response_class=HTMLResponse, include_in_schema=False, name="posts")
async def home(request: Request, db: DbSession):
    result = await db.execute(
        select(models.Post).options(selectinload(models.Post.author))
    )
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "home.html",
        {"posts": posts, "title": "🏠 Home"},
    )


@app.get("/posts/{post_id}", response_class=HTMLResponse, include_in_schema=False)
async def get_post_page(request: Request, post_id: int, db: DbSession):
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(models.Post.id == post_id)
    )
    post = result.scalars().first()
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {post_id} not found",
        )
    return templates.TemplateResponse(
        request,
        "post.html",
        {"post": post, "title": post.title},
    )


@app.get("/users/{user_id}/posts", response_class=HTMLResponse, include_in_schema=False)
async def get_user_posts_page(request: Request, user_id: int, db: DbSession):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))  # post_card.html uses post.author
        .where(models.Post.user_id == user_id)
    )
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {"posts": posts, "user": user, "title": f"Posts by User {user.username}"},
    )


# ---------------------------------------------------------------- Error handlers


@app.exception_handler(StarletteHTTPException)
async def common_exception_handler(request: Request, exception: StarletteHTTPException):
    if request.url.path.startswith("/api"):
        # HTTPException (404, 400, ...) -> http_exception_handler, NOT the validation one
        return await http_exception_handler(request, exception)

    massage = (
        exception.detail
        if exception.detail
        else "An error occurred please try again later."
    )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "error": massage,
            "title": exception.status_code,
        },
        status_code=exception.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exception: RequestValidationError
):
    if request.url.path.startswith("/api"):
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
