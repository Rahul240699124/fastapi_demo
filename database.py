from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Format: mysql+pymysql://<user>:<password>@<host>:<port>/<database>
# User "root" with no password -> nothing after the colon.
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://root:@localhost:3306/fastapi_demo?charset=utf8mb4"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,  # reconnect if MySQL closed an idle connection
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    # WAMP's MySQL defaults to MyISAM, which silently ignores foreign keys
    # (no ON DELETE CASCADE) and transactions. Force InnoDB for every table.
    __table_args__ = {"mysql_engine": "InnoDB"}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
