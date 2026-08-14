"""Authentication endpoints.

Thin per the architecture rules: each route parses its request, calls one
application service method, and maps the result to a response schema. No
business logic lives here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from rag_platform.identity_access.api.v1.dependencies import get_auth_service
from rag_platform.identity_access.api.v1.schemas import (
    RefreshTokenRequest,
    TokenResponse,
    UserCreateRequest,
    UserResponse,
)
from rag_platform.identity_access.application.dto.auth_dto import LoginInput, RegisterUserInput
from rag_platform.identity_access.application.services.auth_service import AuthenticationService

router = APIRouter(prefix="/auth", tags=["auth"])

AuthServiceDep = Annotated[AuthenticationService, Depends(get_auth_service)]


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(request: UserCreateRequest, auth_service: AuthServiceDep) -> UserResponse:
    user = await auth_service.register(
        RegisterUserInput(
            email=request.email, password=request.password, full_name=request.full_name
        )
    )
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in with email and password (OAuth2 password flow)",
    description=(
        "Standard OAuth2 password grant: submit `username` (the user's email) "
        "and `password` as form fields, not JSON."
    ),
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: AuthServiceDep,
) -> TokenResponse:
    user = await auth_service.authenticate(
        LoginInput(email=form_data.username, password=form_data.password)
    )
    pair = await auth_service.issue_tokens(user)
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        expires_in=pair.expires_in,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange a refresh token for a new access/refresh pair",
    description=(
        "Rotates the refresh token: the one submitted here is revoked and " "cannot be reused."
    ),
)
async def refresh(request: RefreshTokenRequest, auth_service: AuthServiceDep) -> TokenResponse:
    pair = await auth_service.refresh(request.refresh_token)
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        expires_in=pair.expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Revoke a refresh token",
)
async def logout(request: RefreshTokenRequest, auth_service: AuthServiceDep) -> None:
    await auth_service.logout(request.refresh_token)
