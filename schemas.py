"""
schemas.py - Pydantic models = the SHAPE of data going in and out of the API.

models.py vs schemas.py (easy to mix up):
    models.py  (SQLAlchemy) -> how data is stored in MySQL tables.
    schemas.py (Pydantic)   -> what a client may SEND (request body) and what it
                               RECEIVES (response). FastAPI uses them to:
        * validate input  -> wrong types / too short / bad email -> automatic 422 error
        * filter output   -> `response_model=UserResponse` drops any field not listed,
                             so password_hash can never leak into a response
        * document the API -> every schema appears in /docs

NAMING PATTERN used below:
    XxxBase     -> fields shared by the other schemas
    XxxCreate   -> body for POST (create)
    XxxUpdate   -> body for PATCH: every field optional, send only what changes
    XxxResponse -> what the API returns
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# =============================================================== Users


class UserBase(BaseModel):
    # Field(...) adds validation rules; they also show up in /docs.
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr = Field(max_length=120)  # EmailStr rejects "not-an-email"


class UserCreate(UserBase):
    # The plain password only exists in the request. The route hashes it immediately.
    password: str = Field(min_length=8, max_length=128)
    # NOTE: no image_file here. A client must not be able to invent a filename;
    # pictures are uploaded through PUT /api/users/me/picture instead.


class UserUpdate(BaseModel):
    # All optional (default None) so a PATCH can change just one field.
    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: EmailStr | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserResponse(UserBase):
    # from_attributes=True lets Pydantic read values from an ORM object's ATTRIBUTES
    # (user.username) instead of requiring a dict. That's why routes can simply
    # `return user` (a models.User) and FastAPI converts it using this schema.
    model_config = ConfigDict(from_attributes=True)

    id: int
    image_file: str | None = None
    image_path: str  # a @property on models.User - computed, not a DB column
    date_created: datetime
    date_updated: datetime


class AuthorResponse(BaseModel):
    """The PUBLIC part of a user, embedded inside every post (no email!)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    image_path: str


# =============================================================== Posts


class PostBase(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    content: str = Field(min_length=10, max_length=1000)
    published: bool = True
    rating: int | None = Field(default=None, ge=1, le=5)  # ge/le = greater/less or equal


class PostCreate(PostBase):
    # NOTE: no user_id. The author is ALWAYS the logged-in user (taken from the JWT).
    # Accepting user_id from the body would let anyone post in someone else's name.
    pass


class PostUpdate(BaseModel):
    # Same rules as PostBase, but optional. (Without the rules here, a PATCH
    # could set an empty title that POST would have rejected.)
    title: str | None = Field(default=None, min_length=3, max_length=100)
    content: str | None = Field(default=None, min_length=10, max_length=1000)
    published: bool | None = None
    rating: int | None = Field(default=None, ge=1, le=5)


class PostResponse(PostBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date_posted: datetime
    likes: int
    # A NESTED schema: Pydantic reads post.author (a models.User) and converts it
    # with AuthorResponse. In async code post.author must be loaded in the query
    # (selectinload) - see routers/posts.py.
    author: AuthorResponse


class PostListResponse(BaseModel):
    """One PAGE of posts plus what a client needs to build pagination controls."""

    total: int  # how many posts match the filters in total (all pages)
    skip: int  # how many were skipped (the offset)
    limit: int  # page size that was asked for
    items: list[PostResponse]  # the posts on this page


# =============================================================== Auth


class Token(BaseModel):
    """Response of POST /api/auth/token. This exact shape (access_token + token_type)
    is what the OAuth2 standard and the /docs "Authorize" button expect."""

    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    message: str
