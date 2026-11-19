from pydantic import BaseModel, ConfigDict, EmailStr, Field
from datetime import datetime

class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr = Field(max_length=120)
    image_file: str | None = None

class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)

class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    image_file: str | None = None
    image_path: str
    date_created: datetime
    date_updated: datetime
    date_deleted: datetime | None = None

class PostBase(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    content: str = Field(min_length=10, max_length=1000)
    published: bool = True
    rating: int | None = Field(default=None, ge=1, le=5)

class PostCreate(PostBase):
    user_id: int

class PostResponse(PostBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date_posted: datetime
    
