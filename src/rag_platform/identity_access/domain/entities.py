"""IdentityAccess domain entities.

Plain, framework-free Python — no FastAPI, no SQLAlchemy, no Pydantic. See
`rag_platform.identity_access.domain.roles` for the role/permission model
these entities use.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from rag_platform.identity_access.domain.roles import Role


@dataclass(slots=True)
class User:
    """A registered user of the platform.

    `hashed_password` is always a bcrypt hash — the domain never holds a
    plaintext password. Hashing happens in the infrastructure layer, behind
    `PasswordHasherPort`, before a `User` is ever constructed.
    """

    id: uuid.UUID
    email: str
    hashed_password: str
    full_name: str
    role: Role
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(cls, *, email: str, hashed_password: str, full_name: str, role: Role) -> User:
        """Construct a new `User` with a freshly generated id and timestamps."""
        now = datetime.now(UTC)
        return cls(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    def touch(self) -> None:
        """Update `updated_at` to now. Call this from any mutating method."""
        self.updated_at = datetime.now(UTC)

    def rename(self, full_name: str) -> None:
        self.full_name = full_name
        self.touch()

    def change_role(self, role: Role) -> None:
        self.role = role
        self.touch()

    def deactivate(self) -> None:
        self.is_active = False
        self.touch()

    def activate(self) -> None:
        self.is_active = True
        self.touch()
