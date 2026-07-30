"""Shared API composition and dependency utilities."""

from app.common.api.dependencies import (
    current_user_dependency,
    cursor_pagination_dependency,
    idempotency_key_dependency,
    offset_pagination_dependency,
    request_context_dependency,
)
from app.common.api.deprecation import DeprecationPolicy, apply_deprecation_headers
from app.common.api.exceptions import register_exception_handlers
from app.common.api.openapi import install_custom_openapi
from app.common.api.router import v1_router

__all__ = [
    "DeprecationPolicy",
    "apply_deprecation_headers",
    "current_user_dependency",
    "cursor_pagination_dependency",
    "idempotency_key_dependency",
    "install_custom_openapi",
    "offset_pagination_dependency",
    "register_exception_handlers",
    "request_context_dependency",
    "v1_router",
]
