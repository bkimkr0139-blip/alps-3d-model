"""Defect → FailureAnalysis → CAPA workflow (지시서 TS10 Defect & FA
Workspace / TS12 Review & Release Gate lite, HANDOFF §5 item 4).

New router file on purpose — see `app/models/fa_capa.py` module docstring and
AGENTS.md "FA/CAPA workflow" section. Does not modify `routers/process_twin.py`.

State machine (CAPA.status), each transition an append-only `CapaEvent` row
(mirrors `GateDecision`'s append-only pattern — never an edit, never just an
overwritten status field with no trail):

    draft --submit--> pending_review --decide(approved)--> approved
                                      \\-decide(rejected)--> rejected [terminal]
    approved --implement--> implemented
    implemented --verify_effectiveness(test_run)--> effectiveness_verified
    effectiveness_verified --close--> closed [terminal]

RBAC mirrors Gate (`app/routers/gates.py`): creating/submitting/implementing/
verifying is `quality_engineer`/`manufacturing_engineer`/`system_architect`
work; APPROVE/REJECT and the final CLOSE both require `reviewer_approver`
(`require_role`) — closing a CAPA is the quality sign-off that the corrective
action actually worked, so it gets the same independent-reviewer gate as the
original approval, not just whoever implemented it.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.fa_capa import CAPA, CapaDecisionType, CapaEvent, CapaEventType, CapaStatus, FailureAnalysis
from app.models.process_twin import Defect
from app.models.test import TestRun
from app.schemas.fa_capa import (
    CapaCloseRequest,
    CapaCreate,
    CapaDecisionRequest,
    CapaEventRead,
    CapaImplementRequest,
    CapaRead,
    CapaSubmitRequest,
    CapaVerifyRequest,
    FailureAnalysisCreate,
    FailureAnalysisRead,
)
from app.schemas.process_twin import DefectRead
from app.security import CurrentUser, require_role
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["fa-capa"])

# Quality/manufacturing (plus architect, per the existing CAN_MANAGE_PROCESS
# precedent in routers/process_twin.py) own FA authoring and CAPA execution.
CAN_MANAGE_QUALITY = require_role("quality_engineer", "manufacturing_engineer", "system_architect")
# Approve/reject and final close require the independent reviewer role,
# exactly like Gate (app/routers/gates.py CAN_DECIDE_GATE).
CAN_DECIDE_CAPA = require_role("reviewer_approver")


def _flush_conflict(e: IntegrityError, business_id: str) -> tuple[int, dict]:
    return status.HTTP_409_CONFLICT, {"detail": f"business_id '{business_id}' already exists"}


def _record_event(
    db: Session,
    *,
    capa: CAPA,
    event_type: CapaEventType,
    business_id: str,
    user: CurrentUser,
    comment: str | None,
    evidence: dict | None = None,
) -> CapaEvent:
    event = CapaEvent(
        business_id=business_id,
        capa_id=capa.id,
        event_type=event_type,
        actor=user.username,
        actor_roles=sorted(user.roles),
        comment=comment,
        evidence=evidence,
        occurred_at=datetime.now(timezone.utc),
        created_by=user.username,
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"business_id '{business_id}' already exists") from exc
    return event


# -- failure analyses -------------------------------------------------------


@router.post(
    "/defects/{defect_id}/failure-analyses",
    response_model=FailureAnalysisRead,
    status_code=status.HTTP_201_CREATED,
)
def create_failure_analysis(
    defect_id: str,
    body: FailureAnalysisCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_QUALITY)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    defect = db.get(Defect, defect_id)
    if defect is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "defect not found")

    def compute() -> tuple[int, dict]:
        fa = FailureAnalysis(
            business_id=body.business_id,
            defect_id=defect.id,
            method=body.method,
            findings=body.findings,
            analyst=body.analyst,
            analyzed_at=body.analyzed_at,
            root_cause=body.root_cause,
            root_cause_confirmed=body.root_cause_confirmed,
            evidence=[e.model_dump() for e in body.evidence] if body.evidence else None,
            created_by=user.username,
        )
        db.add(fa)
        try:
            db.flush()
        except IntegrityError as exc:
            return _flush_conflict(exc, body.business_id)
        record_audit(
            db, user=user, action="create", entity_type="failure_analysis", entity_id=fa.id,
            correlation_id=correlation_id,
            payload={"business_id": fa.business_id, "defect_id": str(defect.id)},
        )
        return status.HTTP_201_CREATED, FailureAnalysisRead.model_validate(fa).model_dump(mode="json")

    result = idempotent_write(db, request=request, idempotency_key=idempotency_key, user=user, compute=compute)
    db.commit()
    return result


@router.get("/defects/{defect_id}/failure-analyses", response_model=list[FailureAnalysisRead])
def list_failure_analyses(defect_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(FailureAnalysis)
        .filter_by(defect_id=defect_id)
        .order_by(FailureAnalysis.analyzed_at.desc())
        .all()
    )


@router.get("/failure-analyses/{fa_id}", response_model=FailureAnalysisRead)
def get_failure_analysis(fa_id: str, db: Annotated[Session, Depends(get_db)]):
    fa = db.get(FailureAnalysis, fa_id)
    if fa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "failure analysis not found")
    return fa


# Convenience read for the frontend: the Process Twin genealogy's
# `GenealogyDefect` intentionally omits the UUID (display-only shape), so the
# FA/CAPA panel resolves real defect ids for a lot through this endpoint
# instead of the other agent's process_twin.py schema having to grow one.
@router.get("/lots/{lot_id}/defects", response_model=list[DefectRead])
def list_lot_defects(lot_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(Defect).filter_by(lot_id=lot_id).order_by(Defect.created_at).all()


# -- CAPAs --------------------------------------------------------------------


@router.post(
    "/failure-analyses/{fa_id}/capas",
    response_model=CapaRead,
    status_code=status.HTTP_201_CREATED,
)
def create_capa(
    fa_id: str,
    body: CapaCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_QUALITY)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    fa = db.get(FailureAnalysis, fa_id)
    if fa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "failure analysis not found")

    def compute() -> tuple[int, dict]:
        capa = CAPA(
            business_id=body.business_id,
            failure_analysis_id=fa.id,
            title=body.title,
            capa_type=body.capa_type,
            description=body.description,
            owner=body.owner,
            due_date=body.due_date,
            created_by=user.username,
        )
        db.add(capa)
        try:
            db.flush()
        except IntegrityError as exc:
            return _flush_conflict(exc, body.business_id)
        record_audit(
            db, user=user, action="create", entity_type="capa", entity_id=capa.id,
            correlation_id=correlation_id,
            payload={"business_id": capa.business_id, "failure_analysis_id": str(fa.id)},
        )
        return status.HTTP_201_CREATED, CapaRead.model_validate(capa).model_dump(mode="json")

    result = idempotent_write(db, request=request, idempotency_key=idempotency_key, user=user, compute=compute)
    db.commit()
    return result


@router.get("/failure-analyses/{fa_id}/capas", response_model=list[CapaRead])
def list_capas_for_fa(fa_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(CAPA).filter_by(failure_analysis_id=fa_id).order_by(CAPA.created_at.desc()).all()


@router.get("/capas", response_model=list[CapaRead])
def list_capas(
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[CapaStatus | None, Query(alias="status")] = None,
):
    query = db.query(CAPA)
    if status_filter is not None:
        query = query.filter_by(status=status_filter)
    return query.order_by(CAPA.created_at.desc()).all()


@router.get("/capas/{capa_id}", response_model=CapaRead)
def get_capa(capa_id: str, db: Annotated[Session, Depends(get_db)]):
    capa = db.get(CAPA, capa_id)
    if capa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CAPA not found")
    return capa


@router.get("/capas/{capa_id}/events", response_model=list[CapaEventRead])
def list_capa_events(capa_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(CapaEvent).filter_by(capa_id=capa_id).order_by(CapaEvent.occurred_at).all()


def _require_capa(db: Session, capa_id: str) -> CAPA:
    capa = db.get(CAPA, capa_id)
    if capa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CAPA not found")
    return capa


def _require_status(capa: CAPA, expected: CapaStatus) -> None:
    if capa.status != expected:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"CAPA is not in '{expected.value}' status (current: {capa.status.value})",
        )


@router.post("/capas/{capa_id}/submit", response_model=CapaRead)
def submit_capa(
    capa_id: str,
    body: CapaSubmitRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_QUALITY)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
):
    capa = _require_capa(db, capa_id)
    _require_status(capa, CapaStatus.DRAFT)

    capa.status = CapaStatus.PENDING_REVIEW
    capa.submitted_by = user.username
    capa.submitted_at = datetime.now(timezone.utc)
    _record_event(
        db, capa=capa, event_type=CapaEventType.SUBMITTED, business_id=body.business_id,
        user=user, comment=body.comment,
    )
    record_audit(
        db, user=user, action="submit", entity_type="capa", entity_id=capa.id,
        correlation_id=correlation_id, payload={"business_id": capa.business_id},
    )
    db.commit()
    db.refresh(capa)
    return capa


@router.post("/capas/{capa_id}/decisions", response_model=CapaRead)
def decide_capa(
    capa_id: str,
    body: CapaDecisionRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DECIDE_CAPA)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
):
    capa = _require_capa(db, capa_id)
    _require_status(capa, CapaStatus.PENDING_REVIEW)

    new_status = CapaStatus.APPROVED if body.decision == CapaDecisionType.APPROVED else CapaStatus.REJECTED
    event_type = CapaEventType.APPROVED if body.decision == CapaDecisionType.APPROVED else CapaEventType.REJECTED
    capa.status = new_status
    _record_event(
        db, capa=capa, event_type=event_type, business_id=body.business_id,
        user=user, comment=body.comment,
    )
    record_audit(
        db, user=user, action="decide", entity_type="capa", entity_id=capa.id,
        correlation_id=correlation_id, payload={"decision": body.decision.value, "comment": body.comment},
    )
    db.commit()
    db.refresh(capa)
    return capa


@router.post("/capas/{capa_id}/implement", response_model=CapaRead)
def implement_capa(
    capa_id: str,
    body: CapaImplementRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_QUALITY)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
):
    capa = _require_capa(db, capa_id)
    _require_status(capa, CapaStatus.APPROVED)

    capa.status = CapaStatus.IMPLEMENTED
    _record_event(
        db, capa=capa, event_type=CapaEventType.IMPLEMENTED, business_id=body.business_id,
        user=user, comment=body.comment,
    )
    record_audit(
        db, user=user, action="implement", entity_type="capa", entity_id=capa.id,
        correlation_id=correlation_id, payload={"business_id": capa.business_id},
    )
    db.commit()
    db.refresh(capa)
    return capa


@router.post("/capas/{capa_id}/verify-effectiveness", response_model=CapaRead)
def verify_capa_effectiveness(
    capa_id: str,
    body: CapaVerifyRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_QUALITY)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
):
    """§5 item 5 재검증→근거 연결, scoped to CAPA closure: effectiveness must
    point at a real TestRun (a retest), never a free-text claim of "fixed"."""
    capa = _require_capa(db, capa_id)
    _require_status(capa, CapaStatus.IMPLEMENTED)

    test_run = db.get(TestRun, body.test_run_id)
    if test_run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test run not found")

    capa.status = CapaStatus.EFFECTIVENESS_VERIFIED
    capa.verification_test_run_id = test_run.id
    capa.verification_note = body.comment
    _record_event(
        db, capa=capa, event_type=CapaEventType.EFFECTIVENESS_VERIFIED, business_id=body.business_id,
        user=user, comment=body.comment,
        evidence={"test_run_id": str(test_run.id), "test_run_business_id": test_run.business_id},
    )
    record_audit(
        db, user=user, action="verify_effectiveness", entity_type="capa", entity_id=capa.id,
        correlation_id=correlation_id,
        payload={"business_id": capa.business_id, "test_run_id": str(test_run.id)},
    )
    db.commit()
    db.refresh(capa)
    return capa


@router.post("/capas/{capa_id}/close", response_model=CapaRead)
def close_capa(
    capa_id: str,
    body: CapaCloseRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DECIDE_CAPA)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
):
    capa = _require_capa(db, capa_id)
    _require_status(capa, CapaStatus.EFFECTIVENESS_VERIFIED)

    capa.status = CapaStatus.CLOSED
    capa.closed_at = datetime.now(timezone.utc)
    _record_event(
        db, capa=capa, event_type=CapaEventType.CLOSED, business_id=body.business_id,
        user=user, comment=body.comment,
    )
    record_audit(
        db, user=user, action="close", entity_type="capa", entity_id=capa.id,
        correlation_id=correlation_id, payload={"business_id": capa.business_id},
    )
    db.commit()
    db.refresh(capa)
    return capa
