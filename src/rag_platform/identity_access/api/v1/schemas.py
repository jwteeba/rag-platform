"""Request and response schemas for the identity_access API.

Distinct from the domain `User` entity and the application-layer DTOs —
these are the wire format, and only these are ever exposed in the OpenAPI
schema or returned to a client. `hashed_password` in particular never
appears here.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from rag_platform.identity_access.domain.roles import Role


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)


class UserProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)


class UserAdminUpdateRequest(BaseModel):
    """Admin-only update of a target user's role and/or active status.

    Both fields optional — omit a field to leave it unchanged. At least one
    must be provided (enforced by the route, see `users_router.py`).
    """

    role: Role | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    items: list[UserResponse]
    has_more: bool
    next_cursor: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int = Field(description="Seconds until the access token expires.")


class RefreshTokenRequest(BaseModel):
    refresh_token: str
