from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.baseline import Baseline, BaselineStatus
from app.models.component import Component
from app.models.product import Variant
from app.models.requirement import Requirement
from app.schemas.baseline import BaselineCreate, BaselineRead
from app.security import CurrentUser, require_role
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["baselines"])

CAN_MANAGE_BASELINE = require_role("system_architect")


def _build_manifest(db: Session, variant: Variant) -> dict:
    """Freezes the current requirement/component versions for this Variant.

    A Baseline is a Manifest, not a copy (§FR-01) — original rows stay put and
    this JSON just pins the set of IDs that were current at freeze time.
    """
    requirements = db.query(Requirement).filter_by(variant_id=variant.id).all()
    components = db.query(Component).filter_by(variant_id=variant.id).all()
    return {
        "requirements": [
            {"id": str(r.id), "business_id": r.business_id, "status": r.status.value}
            for r in requirements
        ],
        "components": [
            {
                "id": str(c.id),
                "business_id": c.business_id,
                "artifact_version_id": str(c.artifact_version_id) if c.artifact_version_id else None,
            }
            for c in components
        ],
    }


@router.post("/baselines", response_model=BaselineRead, status_code=status.HTTP_201_CREATED)
def create_baseline(
    body: BaselineCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_BASELINE)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    variant = db.get(Variant, body.variant_id)
    if variant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")

    def compute() -> tuple[int, dict]:
        db.query(Baseline).filter_by(variant_id=variant.id, status=BaselineStatus.ACTIVE).update(
            {"status": BaselineStatus.SUPERSEDED}
        )
        baseline = Baseline(
            business_id=body.business_id,
            variant_id=variant.id,
            manifest=_build_manifest(db, variant),
            created_by=user.username,
        )
        db.add(baseline)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="baseline",
            entity_id=baseline.id,
            correlation_id=correlation_id,
            payload={"business_id": baseline.business_id, "variant_id": str(variant.id)},
        )
        return status.HTTP_201_CREATED, BaselineRead.model_validate(baseline).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/variants/{variant_id}/baselines", response_model=list[BaselineRead])
def list_baselines(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(Baseline)
        .filter_by(variant_id=variant_id)
        .order_by(Baseline.created_at.desc())
        .all()
    )
