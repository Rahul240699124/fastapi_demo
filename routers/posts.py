"""
routers/posts.py - the /api/posts endpoints.

    GET    /api/posts            public  list posts: pagination + search + filters + sort
    POST   /api/posts            login   create a post (author = the logged-in user)
    GET    /api/posts/{post_id}  public  one post
    PATCH  /api/posts/{post_id}  owner   edit your own post
    DELETE /api/posts/{post_id}  owner   delete your own post

Every response includes the nested author (PostResponse.author), so every query here
loads it with selectinload(models.Post.author) - async sessions can't lazy-load.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import models
from database import DbSession
from dependencies import CurrentUser
from schemas import PostCreate, PostListResponse, PostResponse, PostUpdate

router = APIRouter(prefix="/api/posts", tags=["posts"])


async def get_post_or_404(db: AsyncSession, post_id: int) -> models.Post:
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
    return post


def ensure_is_author(post: models.Post, current_user: models.User) -> None:
    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only modify your own posts",
        )


PostSort = Literal["newest", "oldest", "rating"]


async def query_posts(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 10,
    search: str | None = None,
    published: bool | None = None,
    author_id: int | None = None,
    sort: PostSort = "newest",
) -> tuple[int, list[models.Post]]:
    """Filter + sort + paginate posts. Returns (total_matching, posts_on_this_page).

    Shared by the JSON API below AND the HTML home page (main.py), so the search /
    filter / sort rules exist in ONE place and both always behave the same.
    """
    # 1) Build the WHERE conditions one by one, only for filters that were given.
    #    A query is just an object until it's executed, so we can build it in steps.
    conditions = []
    if search:
        pattern = f"%{search}%"  # % = "any characters" in SQL LIKE
        # ilike = case-insensitive LIKE. SQLAlchemy passes `pattern` as a bound
        # parameter, so user input can never inject SQL.
        conditions.append(
            or_(models.Post.title.ilike(pattern), models.Post.content.ilike(pattern))
        )
    if published is not None:
        conditions.append(models.Post.published == published)
    if author_id is not None:
        conditions.append(models.Post.user_id == author_id)

    # 2) TOTAL count with the same filters (for "page 2 of 7" in a UI).
    #    SELECT count(*) FROM posts WHERE ...
    total = await db.scalar(
        select(func.count()).select_from(models.Post).where(*conditions)
    )

    # 3) The page itself: same filters + ORDER BY + OFFSET/LIMIT.
    order_by = {
        "newest": models.Post.date_posted.desc(),
        "oldest": models.Post.date_posted.asc(),
        # nulls (unrated) sort last in MySQL for DESC; id as a stable tie-breaker
        "rating": models.Post.rating.desc(),
    }[sort]
    result = await db.execute(
        select(models.Post)
        .options(selectinload(models.Post.author))
        .where(*conditions)
        .order_by(order_by, models.Post.id.desc())
        .offset(skip)
        .limit(limit)
    )

    return total or 0, list(result.scalars().all())


@router.get("", response_model=PostListResponse)
async def get_posts(
    db: DbSession,
    # Annotated[TYPE, Query(rules)] = default  -> a ?query parameter with validation.
    # (Recommended style: the default value stays a plain Python default.)
    # ---- pagination: /api/posts?skip=20&limit=10  -> items 21..30
    skip: Annotated[int, Query(ge=0, description="How many posts to skip (offset)")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size (max 100)")] = 10,
    # ---- search & filters (all optional - None means "don't filter")
    search: Annotated[
        str | None,
        Query(min_length=1, max_length=100, description="Text in title or content"),
    ] = None,
    published: Annotated[
        bool | None, Query(description="true = published, false = drafts")
    ] = None,
    author_id: Annotated[int | None, Query(description="Only posts by this user")] = None,
    # ---- sorting: Literal restricts the value to these options (anything else -> 422)
    sort: PostSort = "newest",
):
    # The route only VALIDATES the query parameters; query_posts does the work.
    total, items = await query_posts(
        db,
        skip=skip,
        limit=limit,
        search=search,
        published=published,
        author_id=author_id,
        sort=sort,
    )
    return PostListResponse(total=total, skip=skip, limit=limit, items=items)


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(post: PostCreate, db: DbSession, current_user: CurrentUser):
    new_post = models.Post(
        # model_dump() -> {"title": ..., "content": ..., "published": ..., "rating": ...}
        # ** unpacks it into keyword arguments.
        **post.model_dump(),
        user_id=current_user.id,  # the author comes from the JWT, never from the body
    )
    db.add(new_post)
    await db.commit()
    # Reload DB defaults (date_posted, likes) AND the author relationship, because
    # PostResponse needs post.author and we can't lazy-load it later in async code.
    await db.refresh(new_post, attribute_names=["date_posted", "likes", "author"])
    return new_post


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: int, db: DbSession):
    return await get_post_or_404(db, post_id)


@router.patch("/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: int, post_update: PostUpdate, db: DbSession, current_user: CurrentUser
):
    post = await get_post_or_404(db, post_id)  # 404 first...
    ensure_is_author(post, current_user)  # ...then 403 if it's not yours

    # Only the fields the client sent (see UserUpdate in routers/users.py).
    for field, value in post_update.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    await db.commit()
    return post  # author is still loaded (expire_on_commit=False)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: DbSession, current_user: CurrentUser):
    post = await get_post_or_404(db, post_id)
    ensure_is_author(post, current_user)
    await db.delete(post)
    await db.commit()
    # 204 No Content = success with an empty body (the usual answer for DELETE).
