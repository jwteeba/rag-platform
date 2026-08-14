"""SQLAlchemy ORM models for the identity_access context.

These are Infrastructure-layer artifacts — the domain (`domain/entities.py`)
knows nothing about them. `postgres_user_repository.py` and
`postgres_refresh_token_store.py` translate between `UserModel`/
`RefreshTokenModel` here and the framework-free `User`/`IssuedRefreshToken`
the rest of the application works with.

No `workspace_id` column on `users`: per `docs/architecture.md`, workspace
scoping applies to workspace-*owned* resources (documents, conversations,
etc., introduced in later phases), not to user accounts themselves — a
user's relationship to a workspace is membership, not ownership, and no
membership concept exists yet. Revisit this if/when workspace membership is
introduced.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from rag_platform.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

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

    # The JWT's own `jti` claim is the primary key — no separate surrogate
    # id. A refresh token row's entire purpose is "is this jti valid",
    # looked up by jti; a UUIDv7 `id` column would only ever be dead weight.
    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
