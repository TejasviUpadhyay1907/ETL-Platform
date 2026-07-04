"""
API Key management router.

POST   /api/v1/api-keys                  — create key (api_keys:create)
GET    /api/v1/api-keys                  — list my keys (api_keys:read)
DELETE /api/v1/api-keys/{key_id}         — revoke key (api_keys:revoke)
POST   /api/v1/api-keys/{key_id}/rotate  — rotate key (api_keys:rotate)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.dependencies import DbSession, require_permission
from app.api.schemas.auth_schemas import (
    APIKeyCreateRequest,
    APIKeyCreatedResponse,
    APIKeyResponse,
    APIKeyRotateResponse,
)
from app.api.schemas.base_schemas import APIResponse
from app.auth.rbac import Perm
from app.logging.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.post(
    "",
    response_model=APIResponse[APIKeyCreatedResponse],
    status_code=201,
    summary="Create a new API key",
    description="Creates a new API key. The raw key is returned **once** — store it securely.",
)
def create_api_key(
    payload: APIKeyCreateRequest,
    db: DbSession,
    current_user: dict = Depends(require_permission(Perm.API_KEYS_CREATE)),
) -> APIResponse[APIKeyCreatedResponse]:
    from app.auth.api_key_manager import create_api_key as _create

    api_key, raw_key = _create(
        session=db,
        user_id=uuid.UUID(current_user["user_id"]),
        name=payload.name,
        scope=payload.scope,
        description=payload.description,
        expires_at=payload.expires_at,
    )
    response_data = APIKeyCreatedResponse(
        **APIKeyResponse.from_api_key(api_key).model_dump(),
        raw_key=raw_key,
    )
    return APIResponse[APIKeyCreatedResponse].ok(data=response_data)


@router.get("", response_model=APIResponse[list[APIKeyResponse]], summary="List my API keys")
def list_api_keys(
    db: DbSession,
    current_user: dict = Depends(require_permission(Perm.API_KEYS_READ)),
) -> APIResponse[list[APIKeyResponse]]:
    from sqlalchemy import select
    from app.database.models.auth.api_key import APIKey

    keys = list(db.execute(
        select(APIKey).where(
            APIKey.user_id == uuid.UUID(current_user["user_id"]),
            APIKey.is_active == True,  # noqa: E712
        ).order_by(APIKey.created_at.desc())
    ).scalars().all())
    return APIResponse[list[APIKeyResponse]].ok(data=[APIKeyResponse.from_api_key(k) for k in keys])


@router.delete("/{key_id}", response_model=APIResponse[dict], summary="Revoke an API key")
def revoke_api_key(
    key_id: uuid.UUID,
    db: DbSession,
    current_user: dict = Depends(require_permission(Perm.API_KEYS_REVOKE)),
) -> APIResponse[dict]:
    from app.auth.api_key_manager import revoke_api_key as _revoke

    _revoke(db, key_id, uuid.UUID(current_user["user_id"]))
    return APIResponse[dict].ok(data={"revoked": True, "key_id": str(key_id)})


@router.post(
    "/{key_id}/rotate",
    response_model=APIResponse[APIKeyRotateResponse],
    summary="Rotate an API key",
    description="Revokes the existing key and creates a replacement. Returns the new raw key — store it immediately.",
)
def rotate_api_key(
    key_id: uuid.UUID,
    db: DbSession,
    current_user: dict = Depends(require_permission(Perm.API_KEYS_ROTATE)),
) -> APIResponse[APIKeyRotateResponse]:
    from app.auth.api_key_manager import rotate_api_key as _rotate

    new_key, raw = _rotate(db, key_id, uuid.UUID(current_user["user_id"]))
    result = APIKeyRotateResponse(
        old_key_id=key_id,
        new_key=APIKeyCreatedResponse(
            **APIKeyResponse.from_api_key(new_key).model_dump(),
            raw_key=raw,
        ),
    )
    return APIResponse[APIKeyRotateResponse].ok(data=result)
