"""SQLAlchemy ORM models for the identity_access context."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from rag_platform.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__: Any = {"schema": "rag_platform"}  # noqa: RUF012

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Stored as the `Role` enum's string value (e.g. "admin", "member") —
    # plain `String` rather than a Postgres native ENUM type, so adding a
    # role later is a data migration, not a schema-altering `ALTER TYPE`.
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"
    __table_args__: Any = {"schema": "rag_platform"}  # noqa: RUF012

    # The JWT's own `jti` claim is the primary key — no separate surrogate
    # id. A refresh token row's entire purpose is "is this jti valid",
    # looked up by jti; a UUIDv7 `id` column would only ever be dead weight.
    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
