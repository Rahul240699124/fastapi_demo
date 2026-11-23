"""
models.py - SQLAlchemy ORM models: each class = one database TABLE,
each `Mapped[...] = mapped_column(...)` attribute = one COLUMN.

    User 1 ──< many Post                 (a user writes many posts)
    User 1 ──< many PasswordResetToken   (forgot-password tokens)

The type hint decides the column's Python type and whether it may be NULL:
    Mapped[str]         -> NOT NULL         Mapped[str | None] -> NULL allowed

default vs server_default:
    default=...         -> Python fills the value when SQLAlchemy INSERTs the row.
    server_default=...  -> written into the table definition (CREATE TABLE ... DEFAULT),
                           so rows inserted OUTSIDE the app (phpMyAdmin, SQL) get it too.

CHANGING A MODEL? The database doesn't update itself. Create a migration:
    uv run alembic revision --autogenerate -m "describe the change"
    uv run alembic upgrade head
"""

# Lets classes refer to each other before they're defined
# (User mentions Post in a type hint, but Post is defined further down).
from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # unique=True -> MySQL creates a UNIQUE index: duplicates are impossible,
    # even if two sign-up requests arrive at the same moment.
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)  # never the password
    # Just the FILENAME of the uploaded picture (the file lives in media/profile_pics/).
    image_file: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        default=None,
    )
    # timezone=True has no effect on MySQL (DATETIME stores no timezone), so we always
    # save UTC and treat values read back as UTC.
    date_created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),  # lambda -> evaluated per INSERT, not once
        server_default=func.now(),
        nullable=False,
    )
    date_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),  # refreshed automatically on every UPDATE
        server_default=func.now(),
        nullable=False,
    )

    # ---- Relationships: Python-only shortcuts, NOT columns.
    # user.posts -> list of this user's Post objects (SQLAlchemy uses posts.user_id).
    # back_populates="author" pairs it with Post.author, keeping both sides in sync.
    posts: Mapped[list[Post]] = relationship(
        back_populates="author",
        # When the user is deleted through SQLAlchemy, delete their posts too, and
        # delete a post that's removed from user.posts ("orphan").
        cascade="all, delete-orphan",
    )

    reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # @property = a computed attribute: user.image_path (no parentheses).
    # Not stored in the DB; UserResponse/AuthorResponse include it in API responses.
    @property
    def image_path(self) -> str:
        if self.image_file:
            # Uploaded pictures are served from /media (mounted in main.py).
            # quote() makes the name URL-safe, e.g. "my pic.jpg" -> "my%20pic.jpg"
            return f"/media/profile_pics/{quote(self.image_file)}"
        return "/static/profile_pics/default.png"  # bundled with the app


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # Text = no length limit
    published: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    # The FOREIGN KEY: the real link to users.id, stored in the posts table.
    # ondelete="CASCADE" -> MySQL itself deletes the posts if the user row is deleted
    # (even outside the app). index=True speeds up "all posts of user X" queries.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date_posted: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    likes: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )

    # post.author -> the User object whose id == post.user_id.
    # (post.user_id is the number; post.author is the whole object.)
    # In async code it must be loaded in the query: .options(selectinload(Post.author))
    author: Mapped[User] = relationship(back_populates="posts")


class PasswordResetToken(Base):
    """One row per "forgot password" request (see routers/auth.py)."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SHA-256 of the emailed token (64 hex chars). The raw token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="reset_tokens")
