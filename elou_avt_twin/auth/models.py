"""
models.py
=========
Pydantic contracts for the RBAC layer: the in-memory authorization
principal, API request/response models and admin-facing views.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Principal(BaseModel):
    """Authenticated identity resolved by the auth dependencies.

    Permissions authorize operations. Scheme editing additionally requires
    the administrator role, as enforced by require_permission.
    """

    username: str
    full_name: str = ""
    roles: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    is_system: bool = False

    def has_permission(self, code: str) -> bool:
        return code in self.permissions


class UserView(BaseModel):
    id: int
    username: str
    full_name: str = ""
    is_active: bool = True
    roles: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)


class RoleView(BaseModel):
    code: str
    name: str
    description: str = ""
    permissions: List[str] = Field(default_factory=list)


class PermissionView(BaseModel):
    code: str
    description: str


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserView


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(..., min_length=4, max_length=256)
    full_name: str = Field("", max_length=128)
    role_codes: List[str] = Field(default_factory=list)


class RoleAssign(BaseModel):
    role_codes: List[str] = Field(default_factory=list)


class RoleCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field("", max_length=512)
    permission_codes: List[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class RolePermissions(BaseModel):
    permission_codes: List[str] = Field(default_factory=list)
