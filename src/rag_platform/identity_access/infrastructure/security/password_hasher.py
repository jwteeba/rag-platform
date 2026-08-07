"""Bcrypt-backed implementation of `PasswordHasherPort`."""

from __future__ import annotations

from rag_platform.core.security import hash_password, verify_password


class BcryptPasswordHasher:
    """Implements `PasswordHasherPort` using the bcrypt utilities in `core.security`."""

    def hash(self, plain_password: str) -> str:
        return hash_password(plain_password)

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        return verify_password(plain_password, hashed_password)
