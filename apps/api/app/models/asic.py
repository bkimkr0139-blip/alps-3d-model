"""ASIC Twin v1.1 domain tables (지시서 v1.1 §6 데이터 모델 확장, R1 P0 slice).

Four verticals, all keyed to an ASIC template id ("cap_afe" | "current_sensor"
| "motor_ripple" | "env_sensor") and optionally to a Variant row — the ASIC
program tab is template-first, but the seed/enterprise flow anchors evidence to
a real Variant so the existing gate/evidence chain can reference it.

    EPIC A  SignalChainModel / CornerStudy      — sensor-ASIC co-design
    EPIC E  MeasurementRun                      — equipment data evidence
    EPIC F  QualificationPlan/Result, SafetyItem, FmedaItem, FaultInjectionRun
    EPIC G  FaCase / FaEvent / AsicEco          — failure-analysis closed loop

Conventions:
  - Status/class fields are String + pydantic Literal (NOT pg Enum) — greenfield
    tables keep the migration free of ENUM-copy gotchas (HANDOFF §8).
  - Append-only rule (지시서 §6 불변규칙 1): approved evidence is superseded by a
    new revision, never edited — hence `supersedes_id` / revision columns and
    the FaEvent ledger instead of in-place mutation.
  - "AI never concludes" (§7 도메인 금지): FaCase.root_cause is human-only, the
    same boundary as failure_analyses.root_cause; nothing here computes it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import IdentifiedMixin, ProvenanceMixin


class SignalChainModel(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC A — sensor→AFE→ADC→digital→output mixed-signal chain, versioned.

    `blocks` JSONB (지시서 §4 EPIC A 구현범위 1): ordered
    [{key, kind(sensor|analog|mixed|digital|io|power), label, params{},
      error_budget{offset, gain_error, inl, dnl, noise, drift, latency, saturation}}],
    each block optionally carrying `requirement_ids` so results trace back
    (수용기준: 결과가 요구사항 ID + 모델 리비전을 포함).
    """

    __tablename__ = "asic_signal_chains"

    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), nullable=True, index=True
    )
    template_id: Mapped[str] = mapped_column(String(32), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="draft")  # draft|approved|superseded
    blocks: Mapped[list] = mapped_column(JSONB)
    source_class: Mapped[str] = mapped_column(String(24), default="SYNTHETIC")
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_signal_chains.id"), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    corner_studies: Mapped[list["CornerStudy"]] = relationship(back_populates="signal_chain")


class CornerStudy(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC A — Corner / Monte-Carlo / temperature sweep over one chain revision.

    Computed synchronously in the router (deterministic seeded draw, <100 ms —
    지시서 §9 sends only long-running jobs to Temporal) and stored with its
    seed so the run is reproducible (§12 회귀: 결정론적 시드).

    `spec` JSONB: [{output, min, max, unit}] — spec-limit coverage per output.
    `result` JSONB: {per_output: [{output, p50, p95, p99, violation_rate,
    corners: [{corner, mean, sd}]}], model_ood: bool, ood_reason}.
    """

    __tablename__ = "asic_corner_studies"

    signal_chain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_signal_chains.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(24))  # corner|monte_carlo|temp_sweep
    n_draws: Mapped[int] = mapped_column(Integer, default=2000)
    seed: Mapped[int] = mapped_column(Integer)
    spec: Mapped[list] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tool_version: Mapped[str] = mapped_column(String(64), default="asic-signal-chain-v1")
    source_class: Mapped[str] = mapped_column(String(24), default="SYNTHETIC")
    status: Mapped[str] = mapped_column(String(24), default="queued")  # queued|succeeded|failed

    signal_chain: Mapped[SignalChainModel] = relationship(back_populates="corner_studies")


class MeasurementRun(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC E — equipment measurement evidence (지시서 §4 EPIC E).

    The raw file is kept twice: as an immutable promoted artifact (sha256 in
    artifact_versions) and as `file_hash` here — a UNIQUE column so the same
    file re-uploaded can never create a duplicate run (수용기준 1).
    `points` keeps raw AND converted values per point (구현범위: 단위 원본 보존).
    `findings` records partial-file / time-reversal / duplicate-block facts —
    findings, never silent fixes (§7 도메인 금지: 무음 변환 금지).
    """

    __tablename__ = "asic_measurement_runs"

    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), nullable=True, index=True
    )
    template_id: Mapped[str] = mapped_column(String(32), index=True)
    equipment_id: Mapped[str] = mapped_column(String(128))
    equipment_type: Mapped[str] = mapped_column(String(32))  # sem_tester|wafer_prober|handler
    equipment_model: Mapped[str | None] = mapped_column(String(128), nullable=True)  # T2000, V93000…
    firmware: Mapped[str | None] = mapped_column(String(64), nullable=True)
    calibration_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    program_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_artifact_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifact_versions.id"), nullable=True
    )
    file_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="parsed")  # parsed|verified_ingest|rejected
    points: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    findings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    lot_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

    raw_artifact_version: Mapped["ArtifactVersion | None"] = relationship()  # noqa: F821


class QualificationPlan(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC F — AEC-Q100 qualification matrix header (제품·패키지·Grade별)."""

    __tablename__ = "asic_qual_plans"

    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), nullable=True, index=True
    )
    template_id: Mapped[str] = mapped_column(String(32), index=True)
    grade: Mapped[str] = mapped_column(String(8))  # G0|G1|G2
    policy_version: Mapped[str] = mapped_column(String(32), default="alps-asic-v1.0")
    standard_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="draft")  # draft|in_progress|passed|failed
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    results: Mapped[list["QualificationResult"]] = relationship(back_populates="plan")


class QualificationResult(Base, IdentifiedMixin, ProvenanceMixin):
    """One stress-test row of the matrix — 시험조건·샘플·로트·전후측정·웨이버.

    `status` is NEVER set to pass by free-text claim alone: the gate policy
    (asic_gate_policy) recomputes QUAL_PASS from rows + open failures +
    waivers (지시서 §6 불변규칙 4: 준수 상태는 매트릭스에서 계산).
    """

    __tablename__ = "asic_qual_results"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_qual_plans.id"), index=True
    )
    group: Mapped[str] = mapped_column(String(24))  # TC|TH|HTSL|HAST|ESD|LU|PTC|…
    method: Mapped[str] = mapped_column(String(255))
    condition: Mapped[dict] = mapped_column(JSONB)  # {temp_c, rh, bias, duration_h, cycles…}
    samples: Mapped[str] = mapped_column(String(64))  # "3 lot × 77"
    lots: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    pre_electrical_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_measurement_runs.id"), nullable=True
    )
    post_electrical_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_measurement_runs.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default="pending")  # pending|pass|fail
    failed_param: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fa_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_fa_cases.id"), nullable=True
    )
    waiver_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    waiver_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped[QualificationPlan] = relationship(back_populates="results")


class SafetyItem(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC F — functional-safety trace: Safety Goal → FSR → TSR → HW req.

    Self-referencing `parent_id` tree (지시서 §4 EPIC F 구현범위 2). A "compliant"
    claim is never stored — the UI derives it from FMEDA rows + fault-injection
    evidence linked under each leaf (수용기준 1).
    """

    __tablename__ = "asic_safety_items"

    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), nullable=True, index=True
    )
    template_id: Mapped[str] = mapped_column(String(32), index=True)
    level: Mapped[str] = mapped_column(String(16))  # safety_goal|fsr|tsr|hw_req
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_safety_items.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text)
    asil: Mapped[str | None] = mapped_column(String(8), nullable=True)  # QM|A|B|C|D
    safety_mechanism: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnostic_coverage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    safe_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    children: Mapped[list["SafetyItem"]] = relationship()
    fmeda_rows: Mapped[list["FmedaItem"]] = relationship(back_populates="safety_item")
    fault_injections: Mapped[list["FaultInjectionRun"]] = relationship(back_populates="safety_item")


class FmedaItem(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC F — FMEDA row: every number carries its source file hash and the
    calculation-formula version (수용기준: FMEDA 수치는 출처·산식 버전을 가진다)."""

    __tablename__ = "asic_fmeda_items"

    safety_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_safety_items.id"), index=True
    )
    failure_mode: Mapped[str] = mapped_column(String(255))
    distribution_pct: Mapped[float] = mapped_column(Float)
    dc_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    fit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    formula_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    safety_item: Mapped[SafetyItem] = relationship(back_populates="fmeda_rows")


class FaultInjectionRun(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC F — 고장 주입 시험: expected vs observed, human-judged pass/fail."""

    __tablename__ = "asic_fault_injections"

    safety_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_safety_items.id"), index=True
    )
    method: Mapped[str] = mapped_column(String(128))
    stimulus: Mapped[str] = mapped_column(Text)
    expected: Mapped[str] = mapped_column(Text)
    observed: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))  # pass|fail|pending
    simulation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_runs.id"), nullable=True
    )
    executed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    safety_item: Mapped[SafetyItem] = relationship(back_populates="fault_injections")


class FaCase(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC G — failure-analysis case (ASIC domain, separate from the process
    side's failure_analyses which hang off Defect rows).

    `observations` are FACTS (지시서 §7: 실측/실제 기록은 FACT), `hypotheses` are
    the analyst's working tree with confirm tests + exclusion basis. The final
    `root_cause` is human-approved only (rca_approved transition, RBAC-gated)
    and `cause_class` is one of the fixed taxonomy values or `unknown` —
    `unknown` is a legitimate terminal state when evidence is insufficient.
    """

    __tablename__ = "asic_fa_cases"

    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), nullable=True, index=True
    )
    template_id: Mapped[str] = mapped_column(String(32), index=True)
    scope: Mapped[str] = mapped_column(String(24))  # lot|wafer|die|package|field_return
    lot_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wafer_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    die_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    symptom: Mapped[str] = mapped_column(Text)
    repro_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open")
    # open|analyzing|rca_approved|eco_open|verified|closed
    observations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    hypotheses: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_confirmed: Mapped[bool] = mapped_column(default=False)
    cause_class: Mapped[str | None] = mapped_column(String(24), nullable=True)
    location: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {x,y,z,ref} for 3D overlay
    analysts: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # [{role, actor, at}]
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    events: Mapped[list["FaEvent"]] = relationship(back_populates="case", order_by="FaEvent.occurred_at")
    ecos: Mapped[list["AsicEco"]] = relationship(back_populates="fa_case")


class FaEvent(Base, IdentifiedMixin, ProvenanceMixin):
    """Append-only FA transition ledger (mirrors CapaEvent): 접수→분석→RCA 승인→
    ECO→효과검증→종결, every transition a NEW row with actor roles."""

    __tablename__ = "asic_fa_events"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_fa_cases.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(255))
    actor_roles: Mapped[list] = mapped_column(JSONB)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    case: Mapped[FaCase] = relationship(back_populates="events")


class AsicEco(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC G — design ECO closing the FA loop: trigger→impact→revision bump→
    regression→close. Closing requires re-verification evidence (수용기준: ECO
    완료만으로 FA를 닫을 수 없음) — the router enforces regression results +
    a follow-up verification reference before `closed`."""

    __tablename__ = "asic_ecos"

    fa_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_fa_cases.id"), nullable=True, index=True
    )
    template_id: Mapped[str] = mapped_column(String(32), index=True)
    trigger: Mapped[str] = mapped_column(String(24))  # fa_case|limit_change|improvement
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    design_rev_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    design_rev_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mask_revision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    test_program_revision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    impact: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open")
    # open|analyzed|regression_pending|closed
    regression_run_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_measurement_runs.id"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    fa_case: Mapped[FaCase | None] = relationship(back_populates="ecos")
