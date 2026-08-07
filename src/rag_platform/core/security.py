"""Low-level password-hashing and JWT utility functions.

These are pure functions with no knowledge of the domain (no `User`, no
ports) — they take primitives in and return primitives out. Framework-free
beyond the crypto libraries themselves.

`identity_access/infrastructure/security/` wraps these functions in classes
that implement the domain's `PasswordHasherPort` and `TokenServicePort`
interfaces. Keeping the raw crypto here and the port-adapter wiring there
mirrors the Phase 0 decision to keep `core/` as shared, framework-light
utilities that any bounded context's infrastructure layer can build on.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import bcrypt
import jwt

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt, returning a storable string."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a bcrypt hash.

    Returns False (rather than raising) for a malformed stored hash, so a
    corrupt record fails closed as "wrong password" instead of crashing the
    request.
    """
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


class TokenType(StrEnum):
    """Distinguishes access from refresh tokens inside the JWT `type` claim.

    Without this, a stolen refresh token (long-lived) could be replayed
    directly as an access token, or vice versa. Every decode call must check
    this claim matches what it expected.
    """

    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Decoded, validated claims from a JWT issued by this service."""

    subject: str  # user id, as a string
    token_type: TokenType
    jti: str  # unique token id, used for refresh-token revocation
    issued_at: datetime
    expires_at: datetime


class TokenError(Exception):
    """Raised for any malformed, expired, or otherwise invalid JWT.

    Deliberately a plain exception, not an `ApplicationError` subclass —
    this module is framework- and domain-agnostic. The infrastructure layer
    that calls these functions is responsible for translating this into the
    appropriate domain exception (see
    `identity_access/infrastructure/security/jwt_token_service.py`).
    """


def encode_token(
    *,
    subject: str,
    token_type: TokenType,
    expires_in: timedelta,
    secret_key: str,
    algorithm: str,
) -> tuple[str, TokenClaims]:
    """Create a signed JWT and return it alongside the claims it encodes."""
    now = datetime.now(UTC)
    expires_at = now + expires_in
    jti = str(uuid.uuid4())

    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "jti": jti,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, secret_key, algorithm=algorithm)
    claims = TokenClaims(
        subject=subject, token_type=token_type, jti=jti, issued_at=now, expires_at=expires_at
    )
    return token, claims


def decode_token(
    token: str,
    *,
    expected_type: TokenType,
    secret_key: str,
    algorithm: str,
) -> TokenClaims:
    """Decode and validate a JWT, raising `TokenError` on any problem.

    Validates signature, expiry (handled by `pyjwt` from the `exp` claim),
    and that the token's `type` claim matches `expected_type` — this is what
    prevents a refresh token from being usable as an access token.
    """
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid.") from exc

    try:
        token_type = TokenType(payload["type"])
        subject = str(payload["sub"])
        jti = str(payload["jti"])
        issued_at = datetime.fromtimestamp(payload["iat"], tz=UTC)
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    except (KeyError, ValueError) as exc:
        raise TokenError("Token payload is malformed.") from exc

    if token_type is not expected_type:
        raise TokenError(f"Expected a {expected_type.value} token, got {token_type.value}.")

    return TokenClaims(
        subject=subject,
        token_type=token_type,
        jti=jti,
        issued_at=issued_at,
        expires_at=expires_at,
    )
