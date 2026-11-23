"""
config.py - ONE place for every setting the app needs.

WHY:
    Values like the database password or the JWT secret key must NOT be hard-coded
    in source files: they'd end up on GitHub, and you couldn't use different values
    on your laptop, in tests and in production.

HOW IT WORKS (pydantic-settings):
    `Settings` looks like a Pydantic model. When you create it, each field is filled
    from (highest priority first):
        1. a real environment variable   (e.g.  set DATABASE_URL=...  /  Docker `environment:`)
        2. the `.env` file in the project root
        3. the default value written below
    Field names are matched case-insensitively: field `database_url` <- env var `DATABASE_URL`.
    Values are also *validated and converted*: "30" in .env becomes the int 30.

USAGE anywhere in the project:
    from config import settings
    settings.database_url
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Tell pydantic-settings where to read values from.
    model_config = SettingsConfigDict(
        env_file=".env",  # read KEY=value lines from this file
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unknown keys in .env instead of crashing
    )

    # ---------------------------------------------------------------- App
    app_name: str = "FastAPI Demo Blog"
    debug: bool = False

    # ---------------------------------------------------------------- Database
    # Format: mysql+aiomysql://<user>:<password>@<host>:<port>/<database>
    #   "+aiomysql" = the async MySQL driver (we use AsyncSession everywhere).
    database_url: str = (
        "mysql+aiomysql://root:@localhost:3306/fastapi_demo?charset=utf8mb4"
    )

    # ---------------------------------------------------------------- JWT auth
    # The secret used to SIGN tokens. Anyone who knows it can forge a token for any
    # user, so the real value lives only in .env. The default is deliberately
    # obviously-fake so you notice if .env is missing.
    secret_key: str = "CHANGE-ME-in-.env"
    jwt_algorithm: str = "HS256"  # HMAC + SHA-256: one shared secret signs & verifies
    access_token_expire_minutes: int = 30

    # ---------------------------------------------------------------- Password reset
    reset_token_expire_minutes: int = 15

    # ---------------------------------------------------------------- Uploads
    media_dir: str = "media"  # where user uploads are stored (git-ignored)
    max_upload_size_mb: int = 2

    # ---------------------------------------------------------------- CORS
    # Which *browser origins* (scheme + host + port) may call this API from JavaScript.
    # In .env write it as JSON:  CORS_ORIGINS=["http://localhost:3000"]
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # ---------------------------------------------------------------- Emails
    # We don't have a real mail server, so "sent" emails are appended to this file.
    email_outbox_file: str = "logs/emails.log"


# Create ONE shared instance when this module is first imported.
# Every other module does `from config import settings` and gets this same object.
settings = Settings()
