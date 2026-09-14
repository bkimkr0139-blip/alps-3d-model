from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.artifact import ArtifactVersion, ArtifactVersionStatus
from app.models.component import Component
from app.models.product import Variant
from app.schemas.component import ComponentCreate, ComponentLink, ComponentRead
from app.security import CurrentUser, require_role
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["components"])

CAN_MANAGE_COMPONENT = require_role(
    "mechanical_engineer", "electrical_asic_engineer", "system_architect"
)


@router.post("/components", response_model=ComponentRead, status_code=status.HTTP_201_CREATED)
def create_component(
    body: ComponentCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_COMPONENT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    if db.get(Variant, body.variant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")

    def compute() -> tuple[int, dict]:
        component = Component(
            business_id=body.business_id,
            variant_id=body.variant_id,
            name=body.name,
            artifact_version_id=body.artifact_version_id,
            created_by=user.username,
        )
        db.add(component)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="component",
            entity_id=component.id,
            correlation_id=correlation_id,
            payload={"business_id": component.business_id, "variant_id": str(body.variant_id)},
        )
        return status.HTTP_201_CREATED, ComponentRead.model_validate(component).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/variants/{variant_id}/components", response_model=list[ComponentRead])
def list_components(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(Component).filter_by(variant_id=variant_id).all()


@router.patch("/components/{component_id}/link-artifact", response_model=ComponentRead)
def link_artifact(
    component_id: str,
    body: ComponentLink,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_COMPONENT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
):
    """Attaches a promoted 3D artifact to an existing Component (§FR-03:
    "승인된 파라미터 변경 요청" — not full CAD editing, just re-pointing which
    derived geometry represents this part)."""
    component = db.get(Component, component_id)
    if component is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "component not found")
    artifact_version = db.get(ArtifactVersion, body.artifact_version_id)
    if artifact_version is None or artifact_version.status != ArtifactVersionStatus.PROMOTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "artifact version not found or not promoted")

    component.artifact_version_id = artifact_version.id
    record_audit(
        db,
        user=user,
        action="link_artifact",
        entity_type="component",
        entity_id=component.id,
        correlation_id=correlation_id,
        payload={"artifact_version_id": str(artifact_version.id)},
    )
    db.commit()
    db.refresh(component)
    return component
