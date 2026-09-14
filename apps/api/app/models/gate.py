import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import IdentifiedMixin, ProvenanceMixin


class GateStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONDITIONALLY_APPROVED = "conditionally_approved"


class GateDecisionType(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CONDITIONALLY_APPROVED = "conditionally_approved"


class Gate(Base, IdentifiedMixin, ProvenanceMixin):
    """One §FR-09 Gate instance (e.g. "Virtual Verification Complete") for a
    Variant. `required_roles` names who must decide; `evidence_checklist`
    records what §12.2's readiness check found at submit time — both are
    frozen once submitted so a later definition change can't retroactively
    rewrite what this Gate demanded.
    """

    __tablename__ = "gates"

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("variants.id"))
    baseline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("baselines.id"))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[GateStatus] = mapped_column(Enum(GateStatus, name="gate_status"), default=GateStatus.DRAFT)
    required_roles: Mapped[list] = mapped_column(JSONB)
    evidence_checklist: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    comments: Mapped[list["GateComment"]] = relationship(back_populates="gate")
    decisions: Mapped[list["GateDecision"]] = relationship(back_populates="gate")


class GateComment(Base, IdentifiedMixin, ProvenanceMixin):
    __tablename__ = "gate_comments"

    gate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gates.id"))
    author: Mapped[str] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(String(4000))

    gate: Mapped[Gate] = relationship(back_populates="comments")


class GateDecision(Base, IdentifiedMixin, ProvenanceMixin):
    """Append-only e-signature record (§FR-09). Never updated or deleted —
    a changed mind is a NEW decision row, and the Gate's `status` moves to
    reflect only the latest one."""

    __tablename__ = "gate_decisions"

    gate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gates.id"))
    decision: Mapped[GateDecisionType] = mapped_column(Enum(GateDecisionType, name="gate_decision_type"))
    actor: Mapped[str] = mapped_column(String(255))
    actor_roles: Mapped[list] = mapped_column(JSONB)
    comment: Mapped[str] = mapped_column(String(4000))
    condition_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    gate: Mapped[Gate] = relationship(back_populates="decisions")
