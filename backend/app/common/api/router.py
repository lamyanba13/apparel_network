from fastapi import APIRouter

from app.modules.identity.api.account_router import router as identity_account_router
from app.modules.identity.api.router import router as identity_auth_router
from app.modules.identity.api.session_router import router as identity_session_router
from app.modules.stores.api.media_router import router as store_media_router
from app.modules.stores.api.membership_router import router as store_membership_router
from app.modules.stores.api.router import router as stores_router
from app.modules.stores.api.verification_router import (
    router as store_verification_router,
)

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(identity_auth_router)
v1_router.include_router(identity_session_router)
v1_router.include_router(identity_account_router)
v1_router.include_router(stores_router)
v1_router.include_router(store_verification_router)
v1_router.include_router(store_membership_router)
v1_router.include_router(store_media_router)
