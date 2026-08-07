"""User management endpoints.

Split into two access levels, both enforced declaratively at the route
decorator via `require_permission` / the `CurrentUser` dependency — never by
branching inside a route body:

- Self-service (`/users/me`): any authenticated user, own record only.
- Admin (`/users`, `/users/{user_id}`): requires `USERS_READ` /
  `USERS_MANAGE`, see `identity_access/domain/roles.py`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from rag_platform.core.exceptions import ValidationError
from rag_platform.identity_access.api.v1.dependencies import (
    CurrentUser,
    get_user_service,
    require_permission,
)
from rag_platform.identity_access.api.v1.schemas import (
    UserAdminUpdateRequest,
    UserListResponse,
    UserProfileUpdateRequest,
    UserResponse,
)
from rag_platform.identity_access.application.services.user_service import UserService
from rag_platform.identity_access.domain.roles import Permission

router = APIRouter(prefix="/users", tags=["users"])

UserServiceDep = Annotated[UserService, Depends(get_user_service)]


@router.get("/me", response_model=UserResponse, summary="Get the current user's profile")
async def get_my_profile(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse, summary="Update the current user's profile")
async def update_my_profile(
    request: UserProfileUpdateRequest,
    current_user: CurrentUser,
    user_service: UserServiceDep,
) -> UserResponse:
    updated = await user_service.update_profile(current_user.id, full_name=request.full_name)
    return UserResponse.model_validate(updated)


@router.get(
    "",
    response_model=UserListResponse,
    summary="List users",
    dependencies=[Depends(require_permission(Permission.USERS_READ))],
)
async def list_users(
    user_service: UserServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query()] = None,
) -> UserListResponse:
    page = await user_service.list_users(limit=limit, cursor=cursor)
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in page.items],
        has_more=page.has_more,
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get a user by id",
    dependencies=[Depends(require_permission(Permission.USERS_READ))],
)
async def get_user(user_id: uuid.UUID, user_service: UserServiceDep) -> UserResponse:
    user = await user_service.get_by_id(user_id)
    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update a user's role and/or active status",
    dependencies=[Depends(require_permission(Permission.USERS_MANAGE))],
)
async def update_user(
    user_id: uuid.UUID, request: UserAdminUpdateRequest, user_service: UserServiceDep
) -> UserResponse:
    if request.role is None and request.is_active is None:
        raise ValidationError("At least one of `role` or `is_active` must be provided.")
    updated = await user_service.update_role_and_status(
        user_id, role=request.role, is_active=request.is_active
    )
    return UserResponse.model_validate(updated)
