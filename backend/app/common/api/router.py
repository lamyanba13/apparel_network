from fastapi import APIRouter

from app.modules.cart.api.router import router as cart_router
from app.modules.catalogs.api.router import router as catalogs_router
from app.modules.catalogs.api.taxonomy_router import router as taxonomy_router
from app.modules.checkout.api.router import router as checkout_router
from app.modules.identity.api.account_router import router as identity_account_router
from app.modules.identity.api.router import router as identity_auth_router
from app.modules.identity.api.session_router import router as identity_session_router
from app.modules.inventory.api.router import router as inventory_router
from app.modules.orders.api.router import router as orders_router
from app.modules.pricing.api.price_list_router import (
    price_list_router,
    resolver_router,
)
from app.modules.pricing.api.router import router as pricing_router
from app.modules.products.api.attribute_router import (
    attribute_router,
    attribute_value_router,
    variant_attribute_router,
)
from app.modules.products.api.media_router import router as product_media_router
from app.modules.products.api.router import router as products_router
from app.modules.products.api.variant_router import router as product_variant_router
from app.modules.stores.api.analytics_router import router as store_analytics_router
from app.modules.stores.api.media_router import router as store_media_router
from app.modules.stores.api.membership_router import router as store_membership_router
from app.modules.stores.api.operating_hours_router import (
    router as store_operating_hours_router,
)
from app.modules.stores.api.router import router as stores_router
from app.modules.stores.api.search_router import router as store_search_router
from app.modules.stores.api.verification_router import (
    router as store_verification_router,
)

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(identity_auth_router)
v1_router.include_router(identity_session_router)
v1_router.include_router(identity_account_router)
v1_router.include_router(catalogs_router)
v1_router.include_router(taxonomy_router)
v1_router.include_router(products_router)
v1_router.include_router(product_variant_router)
v1_router.include_router(attribute_router)
v1_router.include_router(attribute_value_router)
v1_router.include_router(variant_attribute_router)
v1_router.include_router(inventory_router)
v1_router.include_router(pricing_router)
v1_router.include_router(price_list_router)
v1_router.include_router(resolver_router)
v1_router.include_router(cart_router)
v1_router.include_router(checkout_router)
v1_router.include_router(orders_router)
v1_router.include_router(product_media_router)
v1_router.include_router(store_search_router)
v1_router.include_router(stores_router)
v1_router.include_router(store_verification_router)
v1_router.include_router(store_membership_router)
v1_router.include_router(store_media_router)
v1_router.include_router(store_operating_hours_router)
v1_router.include_router(store_analytics_router)
