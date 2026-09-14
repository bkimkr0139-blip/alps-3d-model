import enum
import uuid

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import IdentifiedMixin, ProvenanceMixin


class LotDisposition(str, enum.Enum):
    """Lot 판정 (§6.3 Quality.disposition). AI never sets this — it arrives
    from the quality workflow / seed, and quarantine is the safe default for
    suspect lots."""

    OK = "ok"
    QUARANTINE = "quarantine"
    REJECT = "reject"


class DefectSeverity(str, enum.Enum):
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class Mold(Base, IdentifiedMixin, ProvenanceMixin):
    """금형 (§PT-02 lite): one tool revision, its cavities, and the lots it
    produced. Cavity-level quality tracking hangs off this."""

    __tablename__ = "molds"

    name: Mapped[str] = mapped_column(String(255))
    tool_revision: Mapped[str] = mapped_column(String(64), default="A")
    # e.g. "metal dome stamping" — which process this tool serves
    process: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    cavities: Mapped[list["Cavity"]] = relationship(back_populates="mold")


class Cavity(Base, IdentifiedMixin, ProvenanceMixin):
    __tablename__ = "cavities"

    mold_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("molds.id"), index=True)
    cavity_no: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    mold: Mapped[Mold] = relationship(back_populates="cavities")
    lots: Mapped[list["Lot"]] = relationship(back_populates="cavity")


class ProcessOperation(Base, IdentifiedMixin, ProvenanceMixin):
    """One route step (§PT-03) with its approved process window.

    The window is versioned by row (a changed window is a new operation row);
    ProcessRun.out_of_window is evaluated against the window that was current
    when the run was recorded, and both are kept — never rewritten."""

    __tablename__ = "process_operations"

    name: Mapped[str] = mapped_column(String(255))
    seq_no: Mapped[int] = mapped_column(Integer)
    equipment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{parameter, unit, min, max}] — approved window (Process window)
    window: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    runs: Mapped[list["ProcessRun"]] = relationship(back_populates="operation")


class Lot(Base, IdentifiedMixin, ProvenanceMixin):
    """생산 Lot (§6.3 Production): the genealogy pivot tying variant design,
    mold/cavity, material, process runs, inspections and defects together."""

    __tablename__ = "lots"

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("variants.id"), index=True)
    mold_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("molds.id"))
    cavity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cavities.id"), index=True)
    material_lot_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    produced_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disposition: Mapped[LotDisposition] = mapped_column(
        Enum(LotDisposition, name="lot_disposition"), default=LotDisposition.OK
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    cavity: Mapped[Cavity] = relationship(back_populates="lots")
    process_runs: Mapped[list["ProcessRun"]] = relationship(back_populates="lot")
    defects: Mapped[list["Defect"]] = relationship(back_populates="lot")


class ProcessRun(Base, IdentifiedMixin, ProvenanceMixin):
    """One execution of an operation for a Lot (§PT-03): setpoint and actual
    are stored separately, and `out_of_window` is a recorded FACT about the
    actual values — real production data is never rejected at the door, it is
    flagged (Raw data 불변성; the MV-04 blocking rule is for simulations)."""

    __tablename__ = "process_runs"

    lot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lots.id"), index=True)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("process_operations.id"))
    # {"param": value, ...} — intended vs measured, kept apart per PT-03
    setpoint: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    actual: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    operator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    out_of_window: Mapped[bool] = mapped_column(default=False)
    # [{parameter, actual, min, max}] — which parameters left the window
    window_findings: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    lot: Mapped[Lot] = relationship(back_populates="process_runs")
    operation: Mapped[ProcessOperation] = relationship(back_populates="runs")


class Defect(Base, IdentifiedMixin, ProvenanceMixin):
    """불량 (§6.3 Quality): class + severity + quantity on a Lot; unit_id
    pins single-unit defects when serial tracking exists."""

    __tablename__ = "defects"

    lot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lots.id"), index=True)
    defect_class: Mapped[str] = mapped_column(String(64))
    severity: Mapped[DefectSeverity] = mapped_column(Enum(DefectSeverity, name="defect_severity"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    lot: Mapped[Lot] = relationship(back_populates="defects")
