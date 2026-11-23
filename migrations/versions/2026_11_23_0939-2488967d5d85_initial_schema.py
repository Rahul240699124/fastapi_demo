"""initial schema: users, posts, password_reset_tokens

The BASELINE migration: builds the whole schema on an EMPTY database.

    Fresh database (Docker, new developer):  uv run alembic upgrade head
    Database that already has these tables:  uv run alembic stamp head
        ("stamp" only records "this DB is at this revision" - it runs no SQL)

Revision ID: 2488967d5d85
Revises:
Create Date: 2026-11-23 09:39:09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Alembic links migrations into a chain using these ids.
revision: str = "2488967d5d85"
down_revision: str | Sequence[str] | None = None  # None = first migration
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Move the schema FORWARD: create the three tables."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column("image_file", sa.String(length=200), nullable=True),
        sa.Column(
            "date_created",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "date_updated",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
        mysql_engine="InnoDB",  # foreign keys + transactions (see database.py)
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"])

    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("published", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "date_posted",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("likes", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
    )
    op.create_index(op.f("ix_posts_id"), "posts", ["id"])
    op.create_index(op.f("ix_posts_user_id"), "posts", ["user_id"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_password_reset_tokens_id"), "password_reset_tokens", ["id"]
    )
    op.create_index(
        op.f("ix_password_reset_tokens_user_id"), "password_reset_tokens", ["user_id"]
    )


def downgrade() -> None:
    """Move the schema BACKWARD: undo upgrade() in reverse order
    (child tables first, because they reference users)."""
    op.drop_index(op.f("ix_password_reset_tokens_user_id"), table_name="password_reset_tokens")
    op.drop_index(op.f("ix_password_reset_tokens_id"), table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index(op.f("ix_posts_user_id"), table_name="posts")
    op.drop_index(op.f("ix_posts_id"), table_name="posts")
    op.drop_table("posts")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
