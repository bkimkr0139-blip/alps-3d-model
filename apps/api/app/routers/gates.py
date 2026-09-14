from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.gate_readiness import check_gate_readiness
from app.models.audit import AuditEvent
from app.models.baseline import Baseline
from app.models.gate import Gate, GateComment, GateDecision, GateStatus
from app.models.product import Variant
from app.schemas.audit import AuditEventRead
from app.schemas.baseline import BaselineRead
from app.schemas.gate import (
    GateCommentCreate,
    GateCommentRead,
    GateCreate,
    GateDecisionCreate,
    GateDecisionRead,
    GateRead,
)
from app.security import CurrentUser, get_current_user, require_role
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["gates"])

CAN_MANAGE_GATE = require_role("program_manager", "system_architect")
CAN_DECIDE_GATE = require_role("reviewer_approver")


@router.post("/gates", response_model=GateRead, status_code=status.HTTP_201_CREATED)
def create_gate(
    body: GateCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_GATE)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    if db.get(Variant, body.variant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")
    baseline = db.get(Baseline, body.baseline_id)
    if baseline is None or str(baseline.variant_id) != str(body.variant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "baseline not found for this variant")

    def compute() -> tuple[int, dict]:
        gate = Gate(
            business_id=body.business_id,
            variant_id=body.variant_id,
            baseline_id=body.baseline_id,
            name=body.name,
            required_roles=body.required_roles,
            created_by=user.username,
        )
        db.add(gate)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db, user=user, action="create", entity_type="gate", entity_id=gate.id,
            correlation_id=correlation_id,
            payload={"business_id": gate.business_id, "variant_id": str(body.variant_id)},
        )
        return status.HTTP_201_CREATED, GateRead.model_validate(gate).model_dump(mode="json")

    result = idempotent_write(db, request=request, idempotency_key=idempotency_key, user=user, compute=compute)
    db.commit()
    return result


@router.get("/gates/{gate_id}", response_model=GateRead)
def get_gate(gate_id: str, db: Annotated[Session, Depends(get_db)]):
    gate = db.get(Gate, gate_id)
    if gate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "gate not found")
    return gate


@router.get("/variants/{variant_id}/gates", response_model=list[GateRead])
def list_gates(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(Gate).filter_by(variant_id=variant_id).order_by(Gate.created_at.desc()).all()


@router.post("/gates/{gate_id}/submit", response_model=GateRead)
def submit_gate(
    gate_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_GATE)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
):
    """§12.2: "승인 전 필수 증적 누락 시 Gate 차단" — blocked here, at submit
    time, not at decision time, so the submitter sees exactly what's missing.
    """
    gate = db.get(Gate, gate_id)
    if gate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "gate not found")
    if gate.status != GateStatus.DRAFT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"gate is not in draft status (current: {gate.status.value})")

    readiness = check_gate_readiness(db, variant_id=gate.variant_id, baseline_id=gate.baseline_id)
    gate.evidence_checklist = readiness
    if not readiness["passed"]:
        db.commit()
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            {"detail": "required evidence missing", "missing": readiness["missing"]},
        )

    gate.status = GateStatus.PENDING_REVIEW
    gate.submitted_by = user.username
    gate.submitted_at = datetime.now(timezone.utc)
    record_audit(
        db, user=user, action="submit", entity_type="gate", entity_id=gate.id,
        correlation_id=correlation_id, payload={"evidence_checklist": readiness},
    )
    db.commit()
    db.refresh(gate)
    return gate


@router.post("/gates/{gate_id}/comments", response_model=GateCommentRead, status_code=status.HTTP_201_CREATED)
def add_comment(
    gate_id: str,
    body: GateCommentCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
):
    gate = db.get(Gate, gate_id)
    if gate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "gate not found")

    comment = GateComment(
        business_id=body.business_id, gate_id=gate.id, author=user.username, text=body.text,
        created_by=user.username,
    )
    db.add(comment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"business_id '{body.business_id}' already exists") from exc
    record_audit(
        db, user=user, action="comment", entity_type="gate", entity_id=gate.id,
        correlation_id=correlation_id, payload={"comment_id": str(comment.id)},
    )
    db.commit()
    db.refresh(comment)
    return comment


@router.get("/gates/{gate_id}/comments", response_model=list[GateCommentRead])
def list_comments(gate_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(GateComment).filter_by(gate_id=gate_id).order_by(GateComment.created_at).all()


@router.post("/gates/{gate_id}/decisions", response_model=GateDecisionRead, status_code=status.HTTP_201_CREATED)
def decide_gate(
    gate_id: str,
    body: GateDecisionCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DECIDE_GATE)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
):
    gate = db.get(Gate, gate_id)
    if gate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "gate not found")
    if gate.status != GateStatus.PENDING_REVIEW:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"gate is not pending review (current: {gate.status.value})")
    if gate.submitted_by == user.username and "platform_admin" not in user.roles:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "reviewer must be independent of the submitter (§4 independence)"
        )

    decision = GateDecision(
        business_id=body.business_id,
        gate_id=gate.id,
        decision=body.decision,
        actor=user.username,
        actor_roles=sorted(user.roles),
        comment=body.comment,
        condition_expiry=body.condition_expiry,
        decided_at=datetime.now(timezone.utc),
        created_by=user.username,
    )
    db.add(decision)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"business_id '{body.business_id}' already exists") from exc

    gate.status = GateStatus(body.decision.value)
    record_audit(
        db, user=user, action="decide", entity_type="gate", entity_id=gate.id,
        correlation_id=correlation_id,
        payload={"decision": body.decision.value, "comment": body.comment},
    )
    db.commit()
    db.refresh(decision)
    return decision


@router.get("/gates/{gate_id}/decisions", response_model=list[GateDecisionRead])
def list_decisions(gate_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(GateDecision).filter_by(gate_id=gate_id).order_by(GateDecision.decided_at).all()


@router.get("/gates/{gate_id}/evidence-package")
def get_evidence_package(gate_id: str, db: Annotated[Session, Depends(get_db)]):
    """§FR-09 "Export 가능한 증적 패키지" — everything a reviewer or auditor
    needs to reconstruct why this Gate ended up in its current state, in one
    document: the frozen Baseline manifest, every comment and decision, and
    the append-only audit trail for this Gate."""
    gate = db.get(Gate, gate_id)
    if gate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "gate not found")
    baseline = db.get(Baseline, gate.baseline_id)
    comments = db.query(GateComment).filter_by(gate_id=gate_id).order_by(GateComment.created_at).all()
    decisions = db.query(GateDecision).filter_by(gate_id=gate_id).order_by(GateDecision.decided_at).all()
    audit_events = (
        db.query(AuditEvent)
        .filter_by(entity_type="gate", entity_id=gate_id)
        .order_by(AuditEvent.created_at)
        .all()
    )
    return {
        "gate": GateRead.model_validate(gate).model_dump(mode="json"),
        "baseline": BaselineRead.model_validate(baseline).model_dump(mode="json") if baseline else None,
        "comments": [GateCommentRead.model_validate(c).model_dump(mode="json") for c in comments],
        "decisions": [GateDecisionRead.model_validate(d).model_dump(mode="json") for d in decisions],
        "audit_trail": [AuditEventRead.model_validate(a).model_dump(mode="json") for a in audit_events],
    }
