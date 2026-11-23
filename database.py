"""
database.py - how the app talks to MySQL.

THE THREE PIECES:
    engine            -> manages a POOL of real connections to MySQL (created once).
    AsyncSessionLocal -> a factory that makes Session objects. A session is your
                         "unit of work": you query, add, change objects through it,
                         then commit() writes everything to the DB in one transaction.
    get_db()          -> a FastAPI *dependency* that gives each request its own
                         session and always closes it afterwards.

WHY ASYNC?
    A DB query spends most of its time waiting for MySQL. With `await db.execute(...)`
    the server can handle OTHER requests during that wait instead of blocking a thread.
    That needs an async driver (aiomysql) and the async SQLAlchemy API (AsyncSession).
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

# create_async_engine does NOT connect yet - it connects lazily on the first query.
engine = create_async_engine(
    settings.database_url,  # comes from .env (see config.py), never hard-coded
    # Before handing out a pooled connection, check it's still alive.
    # Prevents "MySQL server has gone away" after the app sits idle for a while.
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    # autoflush=False: SQLAlchemy won't silently send pending changes to the DB
    # before every query - changes go out when WE call commit()/flush().
    autoflush=False,
    # expire_on_commit=False: after commit(), keep the loaded attribute values.
    # With the default (True), reading user.username after commit would trigger a
    # new lazy query - which is NOT allowed in async code (MissingGreenlet error).
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Parent class of every model in models.py.

    Base.metadata collects all tables, which Alembic (migrations/) and the tests use.
    """

    # WAMP's MySQL defaults to the MyISAM engine, which silently ignores foreign keys
    # (no ON DELETE CASCADE) and transactions. Force InnoDB for every table.
    # (Other databases, e.g. SQLite in the tests, simply ignore "mysql_*" options.)
    __table_args__ = {"mysql_engine": "InnoDB"}


async def get_db():
    """Dependency: one session per request.

    FLOW for a request that uses `db: DbSession`:
        1. FastAPI calls get_db() and runs it up to `yield`.
        2. The yielded session is passed into the route function as `db`.
        3. The route runs (queries, commit, ...).
        4. After the response is ready, FastAPI resumes get_db() after `yield`
           -> leaving the `async with` block closes the session and returns the
           connection to the pool - even if the route raised an exception.
           (Same effect as try: yield db  finally: await db.close())
    """
    async with AsyncSessionLocal() as db:  # `async with` closes the session for us
        yield db


# Shorthand so routes can write `db: DbSession` instead of the long version.
# Annotated[TYPE, Depends(fn)] = "this parameter is of TYPE and its value comes from fn".
DbSession = Annotated[AsyncSession, Depends(get_db)]
