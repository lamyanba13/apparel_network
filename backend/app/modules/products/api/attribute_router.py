from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.products.api.attribute_schemas import (
    AttributeCreateRequest,
    AttributeResponse,
    AttributeUpdateRequest,
    AttributeValueCreateRequest,
    AttributeValueResponse,
    AttributeValueUpdateRequest,
    VariantAttributeAssignmentRequest,
    VariantAttributeAssignmentResponse,
    VariantAttributeValueResponse,
)
from app.modules.products.api.dependencies import (
    AttributeServiceDependency,
    VariantAttributeServiceDependency,
)
from app.modules.products.application.attribute_schemas import (
    AttributeAssignment,
    AttributeCreate,
    AttributeUpdate,
    AttributeValueCreate,
    AttributeValueUpdate,
)

attribute_router = APIRouter(prefix="/attributes", tags=["Product Attributes"])
attribute_value_router = APIRouter(
    prefix="/attribute-values", tags=["Product Attributes"]
)
variant_attribute_router = APIRouter(prefix="/variants", tags=["Variant Attributes"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required Attribute permission"},
    404: {"description": "Resource not found or belongs to another Store"},
}


def _attribute(value: Any) -> AttributeResponse:
    return AttributeResponse.model_validate(value, from_attributes=True)


@attribute_router.post(
    "",
    response_model=AttributeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("attribute:create")],
    responses={**_RESPONSES, 409: {"description": "Attribute conflict"}},
)
async def create_attribute(
    payload: AttributeCreateRequest,
    identity: CurrentIdentity,
    service: AttributeServiceDependency,
    response: Response,
) -> AttributeResponse:
    attribute = await service.create(
        AttributeCreate(
            store_id=payload.store_id,
            name=payload.name,
            slug=payload.slug,
            attribute_type=payload.attribute_type,
            description=payload.description,
            required=payload.required,
            filterable=payload.filterable,
            searchable=payload.searchable,
            sort_order=payload.sort_order,
            status=payload.status,
            actor_id=identity.user.id,
        )
    )
    response.headers["Location"] = f"/api/v1/attributes/{attribute.id}"
    return _attribute(attribute)


@attribute_router.get(
    "",
    response_model=list[AttributeResponse],
    dependencies=[require_permission("attribute:view")],
    responses=_RESPONSES,
)
async def list_attributes(
    identity: CurrentIdentity,
    service: AttributeServiceDependency,
    store_id: UUID | None = None,
) -> list[AttributeResponse]:
    return [
        _attribute(item)
        for item in await service.list_owned(identity.user.id, store_id=store_id)
    ]


@attribute_router.patch(
    "/{attribute_id}",
    response_model=AttributeResponse,
    dependencies=[require_permission("attribute:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def update_attribute(
    attribute_id: UUID,
    payload: AttributeUpdateRequest,
    identity: CurrentIdentity,
    service: AttributeServiceDependency,
) -> AttributeResponse:
    return _attribute(
        await service.update_owned(
            attribute_id,
            identity.user.id,
            AttributeUpdate(
                values=payload.model_dump(exclude={"version"}, exclude_unset=True),
                expected_version=payload.version,
                actor_id=identity.user.id,
            ),
        )
    )


@attribute_router.delete(
    "/{attribute_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("attribute:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def delete_attribute(
    attribute_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: AttributeServiceDependency,
) -> Response:
    await service.delete_owned(attribute_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@attribute_router.post(
    "/{attribute_id}/values",
    response_model=AttributeValueResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("attribute:update")],
    responses={**_RESPONSES, 409: {"description": "Attribute Value conflict"}},
)
async def create_attribute_value(
    attribute_id: UUID,
    payload: AttributeValueCreateRequest,
    identity: CurrentIdentity,
    service: AttributeServiceDependency,
) -> AttributeValueResponse:
    value = await service.create_value(
        attribute_id,
        identity.user.id,
        AttributeValueCreate(
            value=payload.value,
            slug=payload.slug,
            sort_order=payload.sort_order,
            actor_id=identity.user.id,
        ),
    )
    return AttributeValueResponse.model_validate(value, from_attributes=True)


@attribute_value_router.patch(
    "/{value_id}",
    response_model=AttributeValueResponse,
    dependencies=[require_permission("attribute:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def update_attribute_value(
    value_id: UUID,
    payload: AttributeValueUpdateRequest,
    identity: CurrentIdentity,
    service: AttributeServiceDependency,
) -> AttributeValueResponse:
    value = await service.update_value(
        value_id,
        identity.user.id,
        AttributeValueUpdate(
            values=payload.model_dump(exclude={"version"}, exclude_unset=True),
            expected_version=payload.version,
            actor_id=identity.user.id,
        ),
    )
    return AttributeValueResponse.model_validate(value, from_attributes=True)


@attribute_value_router.delete(
    "/{value_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("attribute:update")],
    responses={**_RESPONSES, 409: {"description": "Optimistic or assignment conflict"}},
)
async def delete_attribute_value(
    value_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: AttributeServiceDependency,
) -> Response:
    await service.delete_value(value_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@variant_attribute_router.post(
    "/{variant_id}/attributes",
    response_model=VariantAttributeAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("attribute:assign")],
    responses={**_RESPONSES, 409: {"description": "Assignment conflict"}},
)
async def assign_variant_attribute(
    variant_id: UUID,
    payload: VariantAttributeAssignmentRequest,
    identity: CurrentIdentity,
    service: VariantAttributeServiceDependency,
) -> VariantAttributeAssignmentResponse:
    assignment = await service.assign(
        variant_id,
        identity.user.id,
        AttributeAssignment(
            attribute_value_id=payload.attribute_value_id,
            expected_version=payload.version,
            actor_id=identity.user.id,
        ),
    )
    return VariantAttributeAssignmentResponse.model_validate(
        assignment, from_attributes=True
    )


@variant_attribute_router.get(
    "/{variant_id}/attributes",
    response_model=list[VariantAttributeValueResponse],
    dependencies=[require_permission("attribute:view")],
    responses=_RESPONSES,
)
async def list_variant_attributes(
    variant_id: UUID,
    identity: CurrentIdentity,
    service: VariantAttributeServiceDependency,
) -> list[VariantAttributeValueResponse]:
    return [
        VariantAttributeValueResponse.model_validate(item, from_attributes=True)
        for item in await service.list_owned(variant_id, identity.user.id)
    ]


@variant_attribute_router.delete(
    "/{variant_id}/attributes/{value_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("attribute:assign")],
    responses={**_RESPONSES, 409: {"description": "Optimistic version conflict"}},
)
async def remove_variant_attribute(
    variant_id: UUID,
    value_id: UUID,
    version: Annotated[int, Query(ge=1)],
    identity: CurrentIdentity,
    service: VariantAttributeServiceDependency,
) -> Response:
    await service.remove(variant_id, value_id, identity.user.id, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
