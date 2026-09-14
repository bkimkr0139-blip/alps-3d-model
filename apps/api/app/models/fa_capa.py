"""Defect → FailureAnalysis(FA) → CAPA workflow (지시서 §3.1/§9.1 품질:
Defect/NCR/FA/CAPA, TS10 Defect & FA Workspace, HANDOFF §5 item 4).

New module on purpose (see AGENTS.md "FA/CAPA workflow" section) rather than
appending to `process_twin.py` — keeps this vertical slice's diff isolated
from parallel work on the existing Process Twin trio.

Two "AI never concludes" boundaries apply here, and they are DIFFERENT from
each other — keep them distinct:
  - `FailureAnalysis.root_cause`/`root_cause_confirmed` are filled by a human
    analyst (§7 domain rule). The app never computes or infers them; there is
    no `confidence="check_required"` field on this model because this is not
    an AI output at all — it is a human's investigation record. (Compare
    `RootCauseCandidate` in `schemas/process_twin.py`, which *is* AI output
    and *does* carry `confidence`.)
  - `CAPA` state transitions are all human actions (submit/approve/reject/
    implement/verify/close) gated by RBAC — never auto-advanced by the app.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import IdentifiedMixin, ProvenanceMixin


class CapaActionType(str, enum.Enum):
    CORRECTIVE = "corrective"
    PREVENTIVE = "preventive"
    BOTH = "both"


class CapaStatus(str, enum.Enum):
    """Mirrors Gate's draft→pending_review→approved/rejected, extended with
    CAPA's own post-approval lifecycle (§12 12~14주 "Defect/FA/CAPA, Model
    trust, Gate"): approved → implemented → effectiveness_verified → closed.
    REJECTED and CLOSED are terminal."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    EFFECTIVENESS_VERIFIED = "effectiveness_verified"
    CLOSED = "closed"


class CapaEventType(str, enum.Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    EFFECTIVENESS_VERIFIED = "effectiveness_verified"
    CLOSED = "closed"


class CapaDecisionType(str, enum.Enum):
    """Just the two legal `POST /capas/{id}/decisions` outcomes — kept
    separate from `CapaEventType` (which also names non-decision events),
    mirroring `GateDecisionType` vs `GateStatus` in `models/gate.py`."""

    APPROVED = "approved"
    REJECTED = "rejected"


class FailureAnalysis(Base, IdentifiedMixin, ProvenanceMixin):
    """불량분석 (FA, TS10). One investigation record tied to a Defect.

    `evidence` uses the same shape as `RootCauseCandidate.evidence`
    ([{kind, business_id, note}]) so an analyst can cite the same real
    entities (process_run/lot/cavity business ids) the rule-based root-cause
    hypotheses already point at — but nothing here is computed by the app.
    """

    __tablename__ = "failure_analyses"

    defect_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("defects.id"), index=True)
    method: Mapped[str] = mapped_column(String(128))
    findings: Mapped[str] = mapped_column(Text)
    analyst: Mapped[str] = mapped_column(String(255))
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Human-entered, evidence-based, never AI-derived (§7). Nullable/False
    # until an analyst actually confirms a cause — "insufficient data yet" is
    # a legitimate, representable state.
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_confirmed: Mapped[bool] = mapped_column(default=False)
    evidence: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    defect: Mapped["Defect"] = relationship()  # noqa: F821 - resolved via models/__init__.py registry
    capas: Mapped[list["CAPA"]] = relationship(back_populates="failure_analysis")


class CAPA(Base, IdentifiedMixin, ProvenanceMixin):
    """시정·예방조치 (Corrective And Preventive Action, TS10/TS12).

    `verification_test_run_id` is the "재검증 → 근거 연결" anchor (HANDOFF §5
    item 5, scoped to CAPA closure only per this task): effectiveness is
    never a free-text claim, it points at a real TestRun (a retest run on the
    affected lot/variant)."""

    __tablename__ = "capas"

    failure_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("failure_analyses.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    capa_type: Mapped[CapaActionType] = mapped_column(Enum(CapaActionType, name="capa_action_type"))
    description: Mapped[str] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(255))
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[CapaStatus] = mapped_column(Enum(CapaStatus, name="capa_status"), default=CapaStatus.DRAFT)
    submitted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_test_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_runs.id"), nullable=True
    )
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    failure_analysis: Mapped[FailureAnalysis] = relationship(back_populates="capas")
    verification_test_run: Mapped["TestRun | None"] = relationship()  # noqa: F821
    events: Mapped[list["CapaEvent"]] = relationship(back_populates="capa", order_by="CapaEvent.occurred_at")


class CapaEvent(Base, IdentifiedMixin, ProvenanceMixin):
    """Append-only CAPA transition ledger — mirrors `GateDecision`: a changed
    status is always a NEW row here, `CAPA.status` only ever reflects the
    latest one. Every transition gets a row (submit/decide/implement/verify/
    close), which is broader than Gate (Gate only journals decisions/
    comments, not submit) — CAPA's own lifecycle is longer and §12's UAT
    wants the full trail."""

    __tablename__ = "capa_events"

    capa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("capas.id"), index=True)
    event_type: Mapped[CapaEventType] = mapped_column(Enum(CapaEventType, name="capa_event_type"))
    actor: Mapped[str] = mapped_column(String(255))
    actor_roles: Mapped[list] = mapped_column(JSONB)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # e.g. {"test_run_id": "...", "test_run_business_id": "..."} on the
    # EFFECTIVENESS_VERIFIED event — real-entity evidence, not free text.
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    capa: Mapped[CAPA] = relationship(back_populates="events")
