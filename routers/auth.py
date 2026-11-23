"""
routers/auth.py - logging in, and the forgot/reset-password flow.

    POST /api/auth/token            username (or email) + password -> JWT access token
    POST /api/auth/forgot-password  email -> a reset token is emailed (background task)
    POST /api/auth/reset-password   reset token + new password -> password changed

Signing UP is POST /api/users (routers/users.py).

HOW A CLIENT USES THE TOKEN:
    1. POST /api/auth/token  (form fields: username, password)
       <- {"access_token": "eyJhbGciOi...", "token_type": "bearer"}
    2. Send it on every protected request as a header:
           Authorization: Bearer eyJhbGciOi...
    In /docs, click "Authorize", enter username + password, and Swagger does this for you.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, or_, select

import models
from config import settings
from database import DbSession
from emails import send_password_reset_email
from schemas import ForgotPasswordRequest, MessageResponse, ResetPasswordRequest, Token
from security import (
    create_access_token,
    generate_reset_token,
    hash_password,
    hash_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/token", response_model=Token)
async def login(
    # OAuth2PasswordRequestForm reads FORM fields (not JSON!) named "username" and
    # "password" - that's what the OAuth2 "password flow" standard requires, and what
    # the /docs Authorize button sends. Forms need the python-multipart package,
    # which fastapi[standard] already includes.
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
):
    # Let people log in with their username OR their email.
    result = await db.execute(
        select(models.User).where(
            or_(
                models.User.username == form_data.username,
                models.User.email == form_data.username,
            )
        )
    )
    user = result.scalars().first()

    # Same error whether the user doesn't exist or the password is wrong. Different
    # messages would tell an attacker which usernames/emails are registered.
    if user is None or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Token(access_token=create_access_token(user.id))


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,  # 202 = "accepted, work continues in background"
)
async def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,  # FastAPI injects this automatically
    db: DbSession,
):
    # Always return the SAME response, whether or not the email exists.
    # Otherwise this endpoint would reveal who has an account.
    response = MessageResponse(
        message="If that email is registered, a reset token has been sent."
    )

    result = await db.execute(
        select(models.User).where(models.User.email == body.email)
    )
    user = result.scalars().first()
    if user is None:
        return response

    raw_token = generate_reset_token()
    db.add(
        models.PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),  # store only the hash
            expires_at=datetime.now(UTC)
            + timedelta(minutes=settings.reset_token_expire_minutes),
        )
    )
    await db.commit()

    # Queue the email. It runs AFTER the response has been sent, so the client
    # doesn't wait for the (possibly slow) mail server.
    background_tasks.add_task(send_password_reset_email, user.email, raw_token)
    return response


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(body: ResetPasswordRequest, db: DbSession):
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset token",
    )

    # We stored only hashes, so hash what the user sent and look THAT up.
    result = await db.execute(
        select(models.PasswordResetToken).where(
            models.PasswordResetToken.token_hash == hash_token(body.token)
        )
    )
    reset_token = result.scalars().first()
    if reset_token is None:
        raise invalid

    # MySQL DATETIME columns don't store a timezone, so the value comes back "naive".
    # We saved it in UTC, so mark it as UTC before comparing with an aware datetime.
    expires_at = reset_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise invalid

    user = await db.get(models.User, reset_token.user_id)
    if user is None:
        raise invalid
    user.password_hash = hash_password(body.new_password)

    # A reset token must work only ONCE: delete every reset token of this user
    # (this one and any older ones). This is a bulk DELETE statement, run in SQL.
    await db.execute(
        delete(models.PasswordResetToken).where(
            models.PasswordResetToken.user_id == user.id
        )
    )
    await db.commit()  # password change + token deletion succeed or fail TOGETHER
    return MessageResponse(message="Password has been reset. You can log in now.")
