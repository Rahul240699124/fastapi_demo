"""
emails.py - "sending" emails, used as BACKGROUND TASKS.

WHY BACKGROUND TASKS?
    Talking to a real mail server can take a few seconds. If a route sent the email
    itself, the user would wait for it. With FastAPI's BackgroundTasks:

        @router.post("/register")
        async def register(..., background_tasks: BackgroundTasks):
            ...save user...
            background_tasks.add_task(send_welcome_email, user.email, user.username)
            return user          # <- response is sent to the client FIRST
                                 # <- THEN FastAPI runs send_welcome_email(...)

    Good for small "fire and forget" jobs (emails, logging, thumbnails). For heavy
    or must-not-be-lost jobs you'd use a real task queue (Celery, ARQ, RQ...).

HERE:
    There's no mail server in this project, so a "sent" email is appended to the file
    in settings.email_outbox_file (logs/emails.log) and logged. Swap the body of
    send_email() for real SMTP (smtplib / aiosmtplib) and nothing else has to change.

These are plain `def` functions on purpose: FastAPI runs sync background tasks in a
thread pool, so slow file or network I/O here never blocks the async event loop.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)  # logger named "emails"


def send_email(to: str, subject: str, body: str) -> None:
    outbox = Path(settings.email_outbox_file)
    outbox.parent.mkdir(parents=True, exist_ok=True)  # create logs/ if missing
    with outbox.open("a", encoding="utf-8") as f:
        f.write(
            f"--- {datetime.now(UTC):%Y-%m-%d %H:%M:%S} UTC\n"
            f"To: {to}\nSubject: {subject}\n\n{body}\n\n"
        )
    logger.info("Email sent to %s: %s", to, subject)


def send_welcome_email(email: str, username: str) -> None:
    send_email(
        to=email,
        subject="Welcome to FastAPI Demo Blog!",
        body=f"Hi {username},\n\nYour account was created. Happy posting!",
    )


def send_password_reset_email(email: str, token: str) -> None:
    # A real app would email a link to a frontend page, e.g.
    #   https://myblog.com/reset-password?token=<token>
    # and that page would POST the token + new password to /api/auth/reset-password.
    send_email(
        to=email,
        subject="Reset your password",
        body=(
            f"Use this token to reset your password "
            f"(valid for {settings.reset_token_expire_minutes} minutes):\n\n{token}\n\n"
            "If you didn't ask for this, ignore this email."
        ),
    )
