from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request, status, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse
from schemas import PostCreate, PostResponse, UserCreate, UserResponse
from typing import Annotated
from sqlalchemy import Select
from sqlalchemy.orm import Session

import models
from database import Base, engine, get_db
from security import hash_password

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

# app.mount("/media", StaticFiles(directory="media"), name="media")

templates = Jinja2Templates(directory="templates")


def status_phrase(code) -> str:
    """Turn a status code (e.g. 404 or "404") into its standard name ("Not Found")."""
    try:
        return HTTPStatus(int(code)).phrase
    except (ValueError, TypeError):
        return "An Error Occurred"


# Makes it usable in templates as: {{ some_code | status_phrase }}
templates.env.filters["status_phrase"] = status_phrase

# response_class=HTMLResponse is used for reaturing the end point of an api in html formate.
# include_in_schema=False is used for not to show html responces in docs and redoc pages for separation from json responces apis

@app.get("/", response_class=HTMLResponse, include_in_schema=False, name="home")
@app.get("/posts", include_in_schema=False, name="posts")
# def home():
# return f"<h1>{posts[0]['title']}</h1></br><p>{posts[0]['content']}</p>"
def home(request: Request, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(Select(models.Post))
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request, 
        "home.html", 
        {"posts": posts, "title": "🏠 Home"},
    )

@app.get("/posts/{post_id}", response_class=HTMLResponse, include_in_schema=False)
def get_post_page(request: Request, post_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(Select(models.Post).where(models.Post.id == post_id))
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
def get_user_posts(request: Request, user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(Select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )
    result = db.execute(Select(models.Post).where(models.Post.user_id == user_id))
    posts = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {"posts": posts, "title": f"Posts by User {user.username}"},
    )

@app.get("/api/users", response_model=list[UserResponse])
def get_users(db: Annotated[Session, Depends(get_db)]):
    result = db.execute(Select(models.User))
    users = result.scalars().all()
    if not users:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No users found",
        )
    return users

@app.post(
    "/api/users", 
    response_model=UserResponse, 
    status_code=status.HTTP_201_CREATED)
def add_user(user: UserCreate, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(Select(models.User).where(models.User.email == user.email))
    existing_email = result.scalars().first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email {user.email} already exists",
        )
    result = db.execute(Select(models.User).where(models.User.username == user.username))
    existing_username = result.scalars().first()
    if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with username {user.username} already exists",
            )
    new_user = models.User(
        username=user.username,
        email=user.email,
        image_file=user.image_file,
        password_hash=hash_password(user.password),  # never store the plain password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.get("/api/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(Select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )
    return user

@app.get("/api/posts", response_model=list[PostResponse])
def get_posts(db: Annotated[Session, Depends(get_db)]):
    result = db.execute(Select(models.Post))
    posts = result.scalars().all()
    return posts

@app.get("/api/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(Select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id {post_id} not found",
        )
    return post

@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse])
def get_user_posts(user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(Select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id {user_id} not found",
        )
    result = db.execute(Select(models.Post).where(models.Post.user_id == user_id))
    posts = result.scalars().all()
    return posts


@app.exception_handler(StarletteHTTPException)
def common_exception_handler(request: Request, exception:StarletteHTTPException):
    massage = (
        exception.detail
        if exception.detail
        else "An error occurred please try again later."
    )
    # := and = are different, := is used for assignment and comparison in the same line. and = is used for assignment only.
    if url := request.url.path:
        if url.startswith("/api"):
            return JSONResponse(
                status_code=exception.status_code,
                content={"detail": massage},
            )
            # return templates.TemplateResponse(
            #     request,
            #     "error.html",
            #     {
            #         "error": massage,
            #         "title": exception.status_code,
            #     },
            # )
            
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "error": massage,
            "title": exception.status_code,
        },
    status_code=exception.status_code
    );

@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exception: RequestValidationError):
    urlPath = request.url.path
    if urlPath.startswith("/api"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exception.errors()},
        )
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "error": "Unprocessable Entity: unable to be followed due to semantic errors.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
    )

## Create A Post
@app.post(
    "/api/posts", 
    response_model=PostResponse, 
    status_code=status.HTTP_201_CREATED)
def create_post(post: PostCreate, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(Select(models.User).where(models.User.id == post.user_id))
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
    db.commit()
    db.refresh(new_post) 
    return new_post
