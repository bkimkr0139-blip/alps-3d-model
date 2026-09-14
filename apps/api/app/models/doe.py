"""AN-04 DOE·최적화 (지시서 §7 AN-04, base-spec FR-06 lite): a persisted
response-surface regression + ranked candidate comparison over one process
parameter (ProcessRun.actual[parameter]) and one CTQ metric (the lot's own
TestRun/Measurement rows, same _ctq_value extraction as cavity compare).

Deliberate scope cuts vs. the full FR-06 (documented in AGENTS.md "AN-04"
section): Grid/Random/Latin-Hypercube DOE *designs* are not implemented —
there is no live DOE execution here, only regression + candidate ranking
over process data that already exists (real production runs are the design
points, not a generated experiment plan). Bayesian Optimization is
explicitly optional per FR-06 and not built. Multi-objective Pareto fronts
are not implemented — the available data has one CTQ objective per study.

Same precedent as CorrelationRecord/UQAnalysis: the computation itself is
cheap synchronous numpy arithmetic (§8.3 PoC 과설계 방지, no Temporal
workflow), but the *result* is persisted as a durable, re-fetchable evidence
row (§6.2 근거/버전/승인 트레일)."""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import IdentifiedMixin, ProvenanceMixin


class DoeStudy(Base, IdentifiedMixin, ProvenanceMixin):
    __tablename__ = "doe_studies"

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("variants.id"), index=True)
    operation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("process_operations.id"))
    # key into ProcessRun.actual, e.g. "dome_thickness_mm"
    parameter: Mapped[str] = mapped_column(String(128))
    parameter_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # CTQ metric name — same vocabulary as /cavities/compare ("peak" | "mean")
    metric: Mapped[str] = mapped_column(String(32))
    metric_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # {min, max, unit, source} — CTQ acceptance band; source labels demo data (§7)
    target_band: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # [{lot_business_id, process_run_business_id, parameter_value, ctq_value,
    #   out_of_window, window_findings}] — every regression point traces to a
    # real persisted ProcessRun + TestRun/Measurement (§7: no fabricated numbers)
    observations: Mapped[list] = mapped_column(JSONB)
    # {slope, intercept, r_squared, direction, n_observations}
    fit: Mapped[dict] = mapped_column(JSONB)
    # [{parameter_value, predicted_ctq, in_window, meets_target,
    #   distance_to_target_center, rank, source: "observed"|"grid"}]
    candidates: Mapped[list] = mapped_column(JSONB)
    # subset of `observations` whose actual parameter value left the approved
    # process window (mirrors ProcessRun.out_of_window/window_findings)
    constraint_violations: Mapped[list] = mapped_column(JSONB)
