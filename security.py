"""
security.py - passwords, JWT access tokens and password-reset tokens.

Nothing here touches the database or FastAPI; these are plain functions, which
makes them easy to understand and to test on their own.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt  # the PyJWT library
from pwdlib import PasswordHash

from config import settings

# =============================================================== 1. PASSWORDS
# We never store the password itself, only a HASH: a one-way scrambled version.
# On login we hash what the user typed and compare it with the stored hash.
# Argon2 is deliberately SLOW and uses lots of memory, which makes brute-forcing
# stolen hashes very expensive. PasswordHash.recommended() picks Argon2 for us.
password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    # Each call adds a random "salt", so hashing the same password twice gives
    # DIFFERENT strings - two users with password "secret123" have different hashes.
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Re-hashes plain_password with the salt stored inside hashed_password and compares.
    return password_hasher.verify(plain_password, hashed_password)


# =============================================================== 2. JWT ACCESS TOKENS
# A JWT (JSON Web Token) is a string with 3 parts: header.payload.signature
#   - payload: JSON "claims", e.g. {"sub": "7", "exp": 1765000000}
#   - signature: HMAC of header+payload made with settings.secret_key
#
# The payload is only base64-encoded, NOT encrypted - anyone can read it (try jwt.io),
# so never put secrets in it. What the signature guarantees is that nobody can CHANGE
# it: editing "sub" to another user's id breaks the signature without the secret key.
#
# Flow:  login -> server creates a token -> client stores it -> client sends
#        "Authorization: Bearer <token>" on every request -> server verifies the
#        signature + expiry and knows who is calling. No server-side session needed.


def create_access_token(user_id: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),  # "subject" = who the token is about (JWT spec wants a string)
        "iat": now,  # "issued at"
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),  # expiry
        "type": "access",  # our own claim, so a different kind of token can't be reused here
    }
    # PyJWT converts the datetimes to Unix timestamps and signs the result.
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """Return the user id inside a valid token, or None if it's invalid or expired."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            # ALWAYS pass the allowed algorithms explicitly. Otherwise an attacker could
            # send a token whose header says "alg": "none" (no signature at all).
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.InvalidTokenError:
        # Base class of every PyJWT error: bad signature, malformed token,
        # ExpiredSignatureError (PyJWT checks "exp" automatically), ...
        return None

    if payload.get("type") != "access":
        return None
    try:
        return int(payload["sub"])
    except KeyError, ValueError:  # Python 3.14: several exceptions without parentheses
        return None


# =============================================================== 3. PASSWORD RESET TOKENS
# A reset link must contain an unguessable random value. We email the RAW token to the
# user but store only its SHA-256 hash, so someone who reads the database still can't
# use the tokens in it (same idea as password hashing).
#
# SHA-256 (fast) is fine here instead of Argon2 (slow): the token is 32 random bytes,
# far too many possibilities to brute-force, unlike a human-chosen password.


def generate_reset_token() -> str:
    # secrets = cryptographically secure randomness. NEVER use `random` for security.
    return secrets.token_urlsafe(32)  # ~43 URL-safe characters


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()  # 64 hex chars -> String(64) column
