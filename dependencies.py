"""
dependencies.py - reusable FastAPI dependencies for AUTHENTICATION.

A dependency is a function FastAPI runs BEFORE your route. Its return value is passed
into the route. Dependencies can depend on other dependencies, so they form a chain:

    route(current_user: CurrentUser)
        -> get_current_user(token, db)
               -> oauth2_scheme(request)  reads "Authorization: Bearer <token>"
               -> get_db()                opens a DB session

If any step raises HTTPException, the route never runs and the client gets the error.
That's how ONE line in a route signature (`current_user: CurrentUser`) protects it.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

import models
from database import DbSession
from security import decode_access_token

# OAuth2PasswordBearer does two jobs:
#   1. At request time: reads the "Authorization: Bearer <token>" header and returns
#      the token string. If the header is missing it raises 401 automatically.
#   2. In /docs: adds the green "Authorize" button. tokenUrl tells Swagger where to
#      POST the username/password to get a token (our login route in routers/auth.py).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DbSession,
) -> models.User:
    # 401 = "who are you?" (not logged in / bad token).
    # The WWW-Authenticate header is required by the HTTP spec for 401 responses
    # and tells the client which auth scheme to use.
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_id = decode_access_token(token)  # checks signature + expiry
    if user_id is None:
        raise credentials_error

    # Load the user fresh from the DB on every request. A token stays valid until it
    # expires, but if the account was deleted in the meantime, this lookup fails and
    # the old token stops working.
    user = await db.get(models.User, user_id)  # db.get = lookup by primary key
    if user is None:
        raise credentials_error
    return user


# Use in a route:   async def create_post(..., current_user: CurrentUser):
CurrentUser = Annotated[models.User, Depends(get_current_user)]
