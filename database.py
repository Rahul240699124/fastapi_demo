from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Format: mysql+aiomysql://<user>:<password>@<host>:<port>/<database>
# User "root" with no password -> nothing after the colon.
# command for use Async uv add aiomysql
SQLALCHEMY_DATABASE_URL = (
    "mysql+aiomysql://root:@localhost:3306/fastapi_demo?charset=utf8mb4"
)

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    __table_args__ = {"mysql_engine": "InnoDB"}


async def get_db():
    db = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()


DbSession = Annotated[AsyncSession, Depends(get_db)]
