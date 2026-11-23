"""
routers/users.py - the /api/users endpoints.

    GET    /api/users                  public  list users (paginated)
    POST   /api/users                  public  sign up (+ welcome email in background)
    GET    /api/users/me               login   the logged-in user
    PUT    /api/users/me/picture       login   upload a profile picture (UploadFile)
    DELETE /api/users/me/picture       login   go back to the default picture
    GET    /api/users/{user_id}        public  one user
    PATCH  /api/users/{user_id}        owner   update your own account
    DELETE /api/users/{user_id}        owner   delete your own account (+ posts)
    GET    /api/users/{user_id}/posts  public  a user's posts

"login" = needs a valid JWT (else 401). "owner" = logged in AND it must be your own
account (else 403).

ROUTE ORDER MATTERS: "/me" is declared BEFORE "/{user_id}". FastAPI checks routes in
the order they were added; if "/{user_id}" came first, GET /api/users/me would match
it, try to turn "me" into an int, and answer 422.
"""

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import models
from config import settings
from database import DbSession
from dependencies import CurrentUser
from emails import send_welcome_email
from schemas import PostResponse, UserCreate, UserResponse, UserUpdate
from security import hash_password

# prefix: every path below is relative to it ("/{user_id}" -> "/api/users/{user_id}").
# tags: groups these routes under "users" in /docs.
router = APIRouter(prefix="/api/users", tags=["users"])


# =============================================================== helpers
# Small functions reused by several routes, so each route stays short (DRY).


async def get_user_or_404(db: AsyncSession, user_id: int) -> models.User:
    user = await db.get(models.User, user_id)  # primary-key lookup
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )
    return user


def ensure_is_self(current_user: models.User, user_id: int) -> None:
    # 401 = not logged in (handled by CurrentUser).  403 = logged in, but NOT ALLOWED.
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only modify your own account",
        )


async def ensure_unique(
    db: AsyncSession, *, username: str | None = None, email: str | None = None
) -> None:
    """400 if the username or email is already taken."""
    if username is not None:
        result = await db.execute(
            select(models.User).where(models.User.username == username)
        )
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with username {username} already exists",
            )
    if email is not None:
        result = await db.execute(select(models.User).where(models.User.email == email))
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with email {email} already exists",
            )


def profile_pics_dir() -> Path:
    # Read from settings at call time (not import time) so tests can point it elsewhere.
    return Path(settings.media_dir) / "profile_pics"


def delete_picture_file(filename: str | None) -> None:
    if filename:
        # .name strips any folder part, so a weird value can't delete files elsewhere.
        (profile_pics_dir() / Path(filename).name).unlink(missing_ok=True)


# =============================================================== routes


@router.get("", response_model=list[UserResponse])
async def get_users(
    db: DbSession,
    # Annotated[TYPE, Query(rules)] = default -> a ?query parameter with validation,
    # e.g. /api/users?skip=20&limit=10
    skip: Annotated[int, Query(ge=0, description="How many users to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Max users to return")] = 20,
):
    result = await db.execute(
        select(models.User).order_by(models.User.id).offset(skip).limit(limit)
    )
    # An empty page is still a valid answer -> return [] (200), not a 404.
    return result.scalars().all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def add_user(user: UserCreate, db: DbSession, background_tasks: BackgroundTasks):
    await ensure_unique(db, username=user.username, email=user.email)

    new_user = models.User(
        username=user.username,
        email=user.email,
        password_hash=hash_password(user.password),  # never store the plain password
    )
    db.add(new_user)  # stage the object (no await - nothing is sent to the DB yet)
    await db.commit()  # INSERT happens here
    await db.refresh(new_user)  # reload DB-generated values (id, dates)

    # Runs AFTER the 201 response is sent - the client doesn't wait for the email.
    background_tasks.add_task(send_welcome_email, new_user.email, new_user.username)
    return new_user


@router.get("/me", response_model=UserResponse)
async def read_me(current_user: CurrentUser):
    # get_current_user (dependencies.py) already verified the token and loaded the
    # user. If the token was missing/invalid, this function never even runs (401).
    return current_user


@router.put("/me/picture", response_model=UserResponse)
async def upload_profile_picture(
    current_user: CurrentUser,
    db: DbSession,
    # UploadFile = a file sent as multipart/form-data (field name "file").
    # It's "spooled": small files stay in memory, big ones go to a temp file on disk.
    file: UploadFile,
):
    allowed_types = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPEG, PNG or WebP images are allowed",
        )

    # Read at most max+1 bytes: if we got more than max, the file is too big.
    # (Reading everything first would let someone upload a 5 GB file into memory.)
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File is larger than {settings.max_upload_size_mb} MB",
        )

    # content_type is just a claim made by the client - NEVER trust it alone.
    # Check the file's first bytes ("magic numbers") to confirm it really is an image.
    jpeg_or_png_signatures = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")
    is_real_image = data.startswith(jpeg_or_png_signatures) or (  # startswith(tuple) = any of them
        data[:4] == b"RIFF" and data[8:12] == b"WEBP"  # WebP
    )
    if not is_real_image:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The file content is not a valid image",
        )

    # NEVER use the client's filename (file.filename) on disk: it could contain
    # "../" tricks or clash with another user's file. Generate our own unique name.
    filename = f"{uuid.uuid4().hex}{allowed_types[file.content_type]}"
    folder = profile_pics_dir()
    folder.mkdir(parents=True, exist_ok=True)

    # Writing a file is BLOCKING I/O. run_in_threadpool runs it in a worker thread,
    # so the async event loop keeps serving other requests meanwhile.
    await run_in_threadpool((folder / filename).write_bytes, data)

    old_file = current_user.image_file
    current_user.image_file = filename
    await db.commit()
    await db.refresh(current_user)

    # Delete the old picture only AFTER the DB update succeeded.
    await run_in_threadpool(delete_picture_file, old_file)
    return current_user


@router.delete("/me/picture", response_model=UserResponse)
async def delete_profile_picture(current_user: CurrentUser, db: DbSession):
    old_file = current_user.image_file
    current_user.image_file = None  # image_path falls back to the default picture
    await db.commit()
    await db.refresh(current_user)
    await run_in_threadpool(delete_picture_file, old_file)
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: DbSession):
    return await get_user_or_404(db, user_id)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int, user_update: UserUpdate, db: DbSession, current_user: CurrentUser
):
    ensure_is_self(current_user, user_id)
    user = current_user  # it's the same account, already loaded by the dependency

    if user_update.username is not None and user_update.username != user.username:
        await ensure_unique(db, username=user_update.username)
    if user_update.email is not None and user_update.email != user.email:
        await ensure_unique(db, email=user_update.email)

    if user_update.password is not None:
        user.password_hash = hash_password(user_update.password)

    # exclude_unset=True -> only fields the client actually SENT. Without it, every
    # field they left out would be None and would overwrite real values.
    # "password" is skipped: it isn't a column, it was handled above.
    for field, value in user_update.model_dump(
        exclude_unset=True, exclude={"password"}
    ).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=UserResponse)
async def delete_user(user_id: int, db: DbSession, current_user: CurrentUser):
    ensure_is_self(current_user, user_id)

    # The User -> posts / reset_tokens cascade must LOAD those rows to delete them,
    # and async code can't lazy-load -> load them up front with selectinload.
    result = await db.execute(
        select(models.User)
        .options(
            selectinload(models.User.posts),
            selectinload(models.User.reset_tokens),
        )
        .where(models.User.id == user_id)
    )
    user = result.scalars().one()
    picture = user.image_file

    await db.delete(user)  # delete() IS awaited on AsyncSession (add() is not)
    await db.commit()
    await run_in_threadpool(delete_picture_file, picture)
    return user


@router.get("/{user_id}/posts", response_model=list[PostResponse])
async def get_user_posts(user_id: int, db: DbSession):
    await get_user_or_404(db, user_id)  # 404 if the user doesn't exist
    result = await db.execute(
        select(models.Post)
        # PostResponse includes the nested author -> load it now (no lazy loading in async)
        .options(selectinload(models.Post.author))
        .where(models.Post.user_id == user_id)
        .order_by(models.Post.date_posted.desc())
    )
    return result.scalars().all()  # [] if the user has no posts yet
