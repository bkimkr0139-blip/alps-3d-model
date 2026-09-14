import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import IdentifiedMixin, ProvenanceMixin


class TestPlan(Base, IdentifiedMixin, ProvenanceMixin):
    __tablename__ = "test_plans"

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("variants.id"))
    name: Mapped[str] = mapped_column(String(255))

    test_runs: Mapped[list["TestRun"]] = relationship(back_populates="test_plan")


class TestRun(Base, IdentifiedMixin, ProvenanceMixin):
    """A single execution of a TestPlan (§9.1 TestPlan/TestRun/Measurement).

    `raw_artifact_version_id` points at the untouched uploaded CSV — FR-07
    requires the original file preserved, not just the parsed rows.
    """

    __tablename__ = "test_runs"

    test_plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("test_plans.id"))
    # Optional lot link (P1): inspections join the process-twin genealogy
    # through the lot that was sampled.
    lot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lots.id"), nullable=True, index=True
    )
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    equipment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    environment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_artifact_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifact_versions.id"), nullable=True
    )

    test_plan: Mapped[TestPlan] = relationship(back_populates="test_runs")
    measurements: Mapped[list["Measurement"]] = relationship(back_populates="test_run")


class Measurement(Base, IdentifiedMixin, ProvenanceMixin):
    __tablename__ = "measurements"

    test_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("test_runs.id"))
    x_value: Mapped[float] = mapped_column(Float)
    y_value: Mapped[float] = mapped_column(Float)
    x_unit: Mapped[str] = mapped_column(String(32))
    y_unit: Mapped[str] = mapped_column(String(32))

    test_run: Mapped[TestRun] = relationship(back_populates="measurements")


class CorrelationRecord(Base, IdentifiedMixin, ProvenanceMixin):
    """Predicted-vs-measured alignment result (§5.3, §9.1). Raw data on both
    sides is untouched — this only stores the computed comparison."""

    __tablename__ = "correlation_records"

    simulation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_runs.id")
    )
    test_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("test_runs.id"))
    rmse: Mapped[float] = mapped_column(Float)
    mae: Mapped[float] = mapped_column(Float)
    max_error: Mapped[float] = mapped_column(Float)
    correlation_coefficient: Mapped[float] = mapped_column(Float)
    extrapolation_warning: Mapped[bool] = mapped_column(default=False)
    overlap_x_min: Mapped[float] = mapped_column(Float)
    overlap_x_max: Mapped[float] = mapped_column(Float)
