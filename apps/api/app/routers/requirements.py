from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.product import Variant
from app.models.requirement import Requirement, RequirementTraceLink
from app.schemas.requirement import (
    RequirementCreate,
    RequirementRead,
    TraceLinkCreate,
    TraceLinkRead,
)
from app.security import CurrentUser, require_role
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["requirements"])

CAN_MANAGE_REQUIREMENT = require_role("system_architect", "program_manager")


@router.post("/requirements", response_model=RequirementRead, status_code=status.HTTP_201_CREATED)
def create_requirement(
    body: RequirementCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_REQUIREMENT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    if db.get(Variant, body.variant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")

    def compute() -> tuple[int, dict]:
        requirement = Requirement(
            business_id=body.business_id,
            variant_id=body.variant_id,
            text=body.text,
            source=body.source,
            priority=body.priority,
            verification_method=body.verification_method,
            safety_class=body.safety_class,
            owner=body.owner,
            created_by=user.username,
        )
        db.add(requirement)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="requirement",
            entity_id=requirement.id,
            correlation_id=correlation_id,
            payload={"business_id": requirement.business_id, "variant_id": str(body.variant_id)},
        )
        return status.HTTP_201_CREATED, RequirementRead.model_validate(requirement).model_dump(
            mode="json"
        )

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/variants/{variant_id}/requirements", response_model=list[RequirementRead])
def list_requirements(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(Requirement).filter_by(variant_id=variant_id).all()


@router.post(
    "/requirements/{requirement_id}/trace-links",
    response_model=TraceLinkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_trace_link(
    requirement_id: str,
    body: TraceLinkCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_REQUIREMENT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    requirement = db.get(Requirement, requirement_id)
    if requirement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "requirement not found")

    def compute() -> tuple[int, dict]:
        link = RequirementTraceLink(
            business_id=body.business_id,
            requirement_id=requirement.id,
            target_type=body.target_type,
            target_id=body.target_id,
            created_by=user.username,
        )
        db.add(link)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="requirement_trace_link",
            entity_id=link.id,
            correlation_id=correlation_id,
            payload={
                "requirement_id": str(requirement.id),
                "target_type": body.target_type.value,
                "target_id": str(body.target_id),
            },
        )
        return status.HTTP_201_CREATED, TraceLinkRead.model_validate(link).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/requirements/{requirement_id}/trace-links", response_model=list[TraceLinkRead])
def list_trace_links(requirement_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(RequirementTraceLink).filter_by(requirement_id=requirement_id).all()
