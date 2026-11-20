from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

import models
from database import DbSession
from schemas import PostCreate, PostResponse, PostUpdate

# Every path below is relative to this prefix, e.g. "/{post_id}" -> "/api/posts/{post_id}".
router = APIRouter(prefix="/api/posts", tags=["posts"])


@router.get("", response_model=list[PostResponse])
async def get_posts(db: DbSession):
    result = await db.execute(select(models.Post))
    posts = result.scalars().all()
    return posts


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(post: PostCreate, db: DbSession):
    result = await db.execute(select(models.User).where(models.User.id == post.user_id))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {post.user_id} not found",
        )
    new_post = models.Post(
        title=post.title,
        content=post.content,
        published=post.published,
        rating=post.rating,
        user_id=post.user_id,
    )
    db.add(new_post)
    await db.commit()
    await db.refresh(new_post, attribute_names=["author"])
    return new_post


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: int, db: DbSession):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {post_id} not found",
        )
    return post


@router.patch("/{post_id}", response_model=PostResponse)
async def update_post(post_id: int, post_update: PostUpdate, db: DbSession):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {post_id} not found",
        )
    for field, value in post_update.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    await db.commit()
    await db.refresh(post, attribute_names=["author"])
    return post


@router.delete("/{post_id}", response_model=PostResponse)
async def delete_post(post_id: int, db: DbSession):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {post_id} not found",
        )
    await db.delete(post)
    await db.commit()
    return post
