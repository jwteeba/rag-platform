"""DTOs crossing the API → Application boundary for authentication use cases.

Kept separate from both the domain entities (`User`) and the API schemas
(`identity_access/api/v1/schemas.py`) — the API layer maps its Pydantic
request models to these before calling an application service, and maps the
service's return value to a Pydantic response model on the way out. This is
what keeps a route function's body to "parse, call, map" with no business
logic of its own.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegisterUserInput:
    email: str
    password: str
    full_name: str


@dataclass(frozen=True, slots=True)
class LoginInput:
    email: str
    password: str
