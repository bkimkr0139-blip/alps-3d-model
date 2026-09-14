import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import IdentifiedMixin, ProvenanceMixin


class VerificationMethod(str, enum.Enum):
    TEST = "test"
    ANALYSIS = "analysis"
    INSPECTION = "inspection"
    DEMONSTRATION = "demonstration"


class SafetyClass(str, enum.Enum):
    QM = "QM"
    ASIL_A = "ASIL_A"
    ASIL_B = "ASIL_B"
    ASIL_C = "ASIL_C"
    ASIL_D = "ASIL_D"


class RequirementStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    OBSOLETE = "obsolete"


class TraceTargetType(str, enum.Enum):
    COMPONENT = "component"
    ARTIFACT_VERSION = "artifact_version"
    SIMULATION_RUN = "simulation_run"
    TEST_RUN = "test_run"


class Requirement(Base, IdentifiedMixin, ProvenanceMixin):
    __tablename__ = "requirements"

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("variants.id"))
    text: Mapped[str] = mapped_column(String(4000))
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[str] = mapped_column(String(32), default="medium")
    verification_method: Mapped[VerificationMethod] = mapped_column(
        Enum(VerificationMethod, name="verification_method")
    )
    safety_class: Mapped[SafetyClass] = mapped_column(
        Enum(SafetyClass, name="safety_class"), default=SafetyClass.QM
    )
    owner: Mapped[str] = mapped_column(String(255))
    status: Mapped[RequirementStatus] = mapped_column(
        Enum(RequirementStatus, name="requirement_status"), default=RequirementStatus.DRAFT
    )

    variant: Mapped["Variant"] = relationship(back_populates="requirements")  # noqa: F821
    trace_links: Mapped[list["RequirementTraceLink"]] = relationship(back_populates="requirement")


class RequirementTraceLink(Base, IdentifiedMixin, ProvenanceMixin):
    __tablename__ = "requirement_trace_links"

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requirements.id")
    )
    target_type: Mapped[TraceTargetType] = mapped_column(Enum(TraceTargetType, name="trace_target_type"))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))

    requirement: Mapped[Requirement] = relationship(back_populates="trace_links")
