from fastapi import APIRouter

from app.modules.identity.api.router import router as identity_auth_router
from app.modules.identity.api.session_router import router as identity_session_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(identity_auth_router)
v1_router.include_router(identity_session_router)
