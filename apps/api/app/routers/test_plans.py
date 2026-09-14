from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.product import Variant
from app.models.test import TestPlan
from app.schemas.test import TestPlanCreate, TestPlanRead
from app.security import CurrentUser, require_role
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["test-plans"])

CAN_MANAGE_TEST = require_role("test_emc_engineer", "mechanical_engineer", "electrical_asic_engineer")


@router.post("/test-plans", response_model=TestPlanRead, status_code=status.HTTP_201_CREATED)
def create_test_plan(
    body: TestPlanCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_TEST)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    if db.get(Variant, body.variant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")

    def compute() -> tuple[int, dict]:
        plan = TestPlan(
            business_id=body.business_id, variant_id=body.variant_id, name=body.name, created_by=user.username
        )
        db.add(plan)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="test_plan",
            entity_id=plan.id,
            correlation_id=correlation_id,
            payload={"business_id": plan.business_id, "variant_id": str(body.variant_id)},
        )
        return status.HTTP_201_CREATED, TestPlanRead.model_validate(plan).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/variants/{variant_id}/test-plans", response_model=list[TestPlanRead])
def list_test_plans(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(TestPlan).filter_by(variant_id=variant_id).all()
