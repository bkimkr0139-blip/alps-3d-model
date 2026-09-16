"""ASIC Twin v1.1 domain tables (지시서 v1.1 §6 데이터 모델 확장, R1 P0 slice).

Four verticals, all keyed to an ASIC template id ("cap_afe" | "current_sensor"
| "motor_ripple" | "env_sensor") and optionally to a Variant row — the ASIC
program tab is template-first, but the seed/enterprise flow anchors evidence to
a real Variant so the existing gate/evidence chain can reference it.

    EPIC A  SignalChainModel / CornerStudy      — sensor-ASIC co-design
    EPIC E  MeasurementRun                      — equipment data evidence
    EPIC F  QualificationPlan/Result, SafetyItem, FmedaItem, FaultInjectionRun
    EPIC G  FaCase / FaEvent / AsicEco          — failure-analysis closed loop

    R3 additions:
    EPIC I  AsicAssumption / AsicAssumptionEvent / AsicImpactScan / AsicDeviation
            — concurrent-engineering control panel (가정·영향 탐색·승인 편차)
    EPIC J  AsicCopilotInteraction             — evidence-grounded AI copilot log

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


# ── R2 (지시서 §10) — EPIC B/C/D/H: 양산·공급망 확장 ─────────────────────────


class ManufacturingOption(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC B — FAB·패키지·OSAT 조달 옵션 1건 (§4 EPIC B 구현 범위).

    `nre` JSONB: {component: entry} with components design/ip/mask/
    mpw_shuttle/pkg_tooling/test_dev/reliability; each entry is
    {amount, currency, basis_date, qty_basis, ref} — or {amount_tbd: "<이유>",
    ref} when undecided. TBD entries are never computed as 0: any total over a
    set containing one stays null and names the TBD components
    (수용기준: 미확정 값은 TBD이며 0으로 계산되지 않는다).

    `unit_cost` JSONB: {component: {best, base, worst, unit, currency,
    basis_date, ref}} with components wafer/die_yield/assembly/final_test/
    logistics/scrap (yield·scrap as fractions). Base/Best/Worst bands feed the
    trade study's scenario totals (수용기준: 단일 숫자가 아니라 3-시나리오).

    `schedule` JSONB: [{phase, weeks_best, weeks_base, weeks_worst}] over
    pdk_ip/design/tapeout/wafer/assembly/es_cs/qualification.
    `risks` JSONB: [{kind: supply_single|long_lead|yield_uncertainty|
    thermal_stress|equipment_availability, note, severity}].
    """

    __tablename__ = "asic_manufacturing_options"

    template_id: Mapped[str] = mapped_column(String(32), index=True)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), nullable=True, index=True
    )
    foundry: Mapped[str] = mapped_column(String(64))
    node: Mapped[str] = mapped_column(String(64))
    wafer_size_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    voltage_option: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_option: Mapped[str | None] = mapped_column(String(64), nullable=True)
    temperature_grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    package: Mapped[str] = mapped_column(String(64))
    osat: Mapped[str | None] = mapped_column(String(64), nullable=True)
    moq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tech_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..5, None=TBD
    nre: Mapped[dict] = mapped_column(JSONB)
    unit_cost: Mapped[dict] = mapped_column(JSONB)
    schedule: Mapped[list] = mapped_column(JSONB)
    risks: Mapped[list] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(24), default="draft")  # draft|approved|superseded
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TradeStudy(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC B — 2~5개 옵션의 비용·일정·기술·공급 가중 비교 (§4 EPIC B).

    `result` JSONB is computed synchronously by app/asic_trade.py
    (deterministic arithmetic, no solver): per-option Base/Best/Worst cost
    totals, NRE amortization curve + breakeven vs the cheapest alternative,
    schedule totals, weighted score with TBD axes flagged partial.
    `decision` JSONB records 승인자·판단 근거·잔여 위험 (수용기준) — written
    once via the decision endpoint, reviewer/approver role only.
    """

    __tablename__ = "asic_trade_studies"

    template_id: Mapped[str] = mapped_column(String(32), index=True)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    option_ids: Mapped[list] = mapped_column(JSONB)  # [uuid-str, ...] 2..5
    weights: Mapped[dict] = mapped_column(JSONB)  # {cost, schedule, technology, supply}
    annual_volume: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="draft")  # draft|decided


class ToolRun(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC C — 공통 ToolRun 계약 (지시서 §4 EPIC C): 외부 EDA 실행 1건의
    승인된 메타데이터. The tool itself runs on-premise (라이선스·PDK는 절대
    이 시스템을 통과하지 않는다) — only what the acceptance criteria demand:
    tool, version, runner_class, environment, input/output hash, exit code,
    log URI (§4 EPIC C 구현 범위 1).

    `runner_class` = real_adapter | mock: 목 러너와 실 러너는 UI에서 아이콘·색·
    문구로 분리 렌더링된다 (구현 범위 마지막 항목).

    `lineage_id`: (template, tool, input_hash)가 같은 재실행은 같은 계보 —
    입력 해시가 다르면 절대 같은 계보로 묶이지 않는다 (수용기준: 실패 재시도는
    입력 해시가 동일한 경우에만 동일 런 계보). Rows are append-only; a re-run
    never overwrites an earlier result (수용기준 3).

    `design_revision` is the signal-chain revision the result belongs to — the
    gate policy folds these into MIXED_REVISION_EVIDENCE (수용기준 2).
    """

    __tablename__ = "asic_tool_runs"

    template_id: Mapped[str] = mapped_column(String(32), index=True)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), nullable=True, index=True
    )
    design_revision: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(48))
    # schematic_check|spice|ams|lint|cdc|rdc|synthesis|sta|pr|drc|lvs|erc|signoff
    tool_version: Mapped[str] = mapped_column(String(64))
    runner_class: Mapped[str] = mapped_column(String(24))  # real_adapter|mock
    environment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    command_profile: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exit_code: Mapped[int] = mapped_column(Integer)
    log_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_artifact_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifact_versions.id"), nullable=True
    )
    lineage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(24))  # completed|failed
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TestFlow(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC D — 양산 테스트 프로그램 1개 리비전 (지시서 §4 EPIC D).

    One managed program = 측정 항목·결함 커버리지·테스트 시간·원가·리비전의
    실행 가능한 모델 (EPIC D 목적 — not a file). `target` separates wafer sort
    from final test so the 계보/중복/누락 analysis can compare the two.
    `silicon_revision` + compatible_* form the 리비전 호환성 매트릭스: a
    mismatch blocks execution/approval at the gate (수용기준 3).
    """

    __tablename__ = "asic_test_flows"

    template_id: Mapped[str] = mapped_column(String(32), index=True)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), nullable=True, index=True
    )
    program_revision: Mapped[int] = mapped_column(Integer)
    silicon_revision: Mapped[str] = mapped_column(String(32))
    compatible_mask_rev: Mapped[str | None] = mapped_column(String(32), nullable=True)
    compatible_package_rev: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target: Mapped[str] = mapped_column(String(24))  # wafer_sort|final_test
    cost_rate_per_site_hour: Mapped[float | None] = mapped_column(Float, nullable=True)  # None=TBD
    status: Mapped[str] = mapped_column(String(24), default="draft")  # draft|released|superseded
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["TestFlowItem"]] = relationship(
        back_populates="flow", order_by="TestFlowItem.seq"
    )


class TestFlowItem(Base, IdentifiedMixin, ProvenanceMixin):
    """One test of the flow: limits·unit·temperature·site·pattern·instrument·
    duration, each linked to 요구사항·고장모드·장비 채널 (수용기준 1) and to the
    defect classes it covers — the coverage/time/cost model's raw data."""

    __tablename__ = "asic_test_flow_items"

    test_flow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_test_flows.id"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(24))
    # contact|pre_check|dc|analog|digital|trim_cal|interface|final_bin
    name: Mapped[str] = mapped_column(String(128))
    limits: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {low, high, unit}
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    site_count: Mapped[int] = mapped_column(Integer, default=1)
    pattern: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instrument: Mapped[str | None] = mapped_column(String(64), nullable=True)
    equipment_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expected_duration_s: Mapped[float] = mapped_column(Float)
    requirement_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    failure_mode_refs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    defect_coverage: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # [{defect_class: open|short|leakage|parametric|esd|latchup, coverage_pct}]

    flow: Mapped[TestFlow] = relationship(back_populates="items")


class LimitChange(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC D — 한계값 변경 제안 + 영향 분석 (수용기준 2: 변경 시 영향받는
    로트·제품·인증 증적 자동 표시). A proposal, never a silent edit: applying
    it supersedes the flow into a NEW revision (불변규칙 1) via the apply
    endpoint; until then `status=proposed` rows only inform."""

    __tablename__ = "asic_limit_changes"

    test_flow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_test_flows.id"), index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_test_flow_items.id")
    )
    old_limits: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_limits: Mapped[dict] = mapped_column(JSONB)
    rationale: Mapped[str] = mapped_column(Text)
    impact: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="proposed")  # proposed|applied|rejected
    applied_flow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_test_flows.id"), nullable=True
    )


class WaferMap(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC D — bin/wafer map + site 분석 (구현 범위: bin map·wafer map·site별
    편향·재시험률·오버킬/언더킬 추정).

    `ground_truth` carries the SYNTHETIC fixture's injected bad-die pattern, so
    overkill/underkill are a disclosed confusion-matrix computation against a
    known reference — never presented as production yield data.
    """

    __tablename__ = "asic_wafer_maps"

    template_id: Mapped[str] = mapped_column(String(32), index=True)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), nullable=True, index=True
    )
    lot_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wafer_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    test_flow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_test_flows.id"), nullable=True
    )
    grid: Mapped[dict] = mapped_column(JSONB)  # {rows, cols}
    bins: Mapped[list] = mapped_column(JSONB)  # [{x, y, bin(1=good|2=retest|3+fail), site}]
    ground_truth: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {bad_xy: [[x, y], ...], note} — SYNTHETIC fixture only
    analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_class: Mapped[str] = mapped_column(String(24), default="SYNTHETIC")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AsicPartner(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC H — 파운드리/OSAT 파트너 레지스트리 (포털 격리의 단위).

    The portal shows a partner ONLY rows scoped to its own `partner_id` —
    isolation is enforced in the router via the partner-scoped principal
    (tests exercise it with a mocked principal; no realm changes). Approval
    status gates the supply chain: evidence flowing from a non-approved
    partner raises a gate blocker.
    """

    __tablename__ = "asic_partners"

    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(24))  # foundry|osat|subcon|material
    status: Mapped[str] = mapped_column(String(24), default="conditional")  # approved|conditional|suspended
    approved_scope: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {processes: [...], packages: [...], sites: [...]} — what approval covers
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class LotTraveler(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC H — lot 여행자: lot genealogy + 파트너 간 이동 기록 (append-only
    steps). Gate computes lineage continuity/duplication from `steps`; a lot
    visiting two partners concurrently, or jumping to a partner with no
    preceding handoff, is LINEAGE_BROKEN/DUPLICATE."""

    __tablename__ = "asic_lot_travelers"

    template_id: Mapped[str] = mapped_column(String(32), index=True)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), nullable=True, index=True
    )
    lot_ref: Mapped[str] = mapped_column(String(64), index=True)
    parent_lot_refs: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # genealogy
    silicon_revision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mask_rev: Mapped[str | None] = mapped_column(String(32), nullable=True)
    package_rev: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_partner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_partners.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default="in_process")  # in_process|held|completed|scrapped
    steps: Mapped[list] = mapped_column(JSONB)  # [{partner_id, step, arrived_at, departed_at, result}]
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PartnerArtifact(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC H — 파트너가 포털로 올린 증적 원본 (sha256, artifact_version 승격).
    Partner-scoped: the portal lists only artifacts whose partner_id matches
    the principal; template-side reads are the program team's view."""

    __tablename__ = "asic_partner_artifacts"

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_partners.id"), index=True
    )
    lot_traveler_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_lot_travelers.id"), nullable=True, index=True
    )
    template_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # test_report|wafer_map|ship_doc|cert
    file_hash: Mapped[str] = mapped_column(String(64), unique=True)  # 중복 업로드 차단
    artifact_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artifact_versions.id"), nullable=True
    )
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="submitted")  # submitted|accepted|rejected
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PartnerChange(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC H — PCN (process/site/equipment/material change 통지). 수용기준:
    승인되지 않은 파트너 변경 = gate blocker PARTNER_CHANGE_PENDING. `status`
    moves only through the review endpoint (human decision), never inferred."""

    __tablename__ = "asic_partner_changes"

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_partners.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # process|site_transfer|equipment|material
    description: Mapped[str] = mapped_column(Text)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    affected_template_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="submitted")  # submitted|under_review|approved|rejected
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class QualityAction(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC H — 품질 조치 (hold/quarantine/8D 등). 양산 품질 단계(s9)의
    게이트 입력: an OPEN action on the lot chain blocks release evidence."""

    __tablename__ = "asic_quality_actions"

    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_partners.id"), nullable=True, index=True
    )
    lot_traveler_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_lot_travelers.id"), nullable=True, index=True
    )
    template_id: Mapped[str] = mapped_column(String(32), index=True)
    lot_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(32))  # hold|quarantine|sort|scrap|8d
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="open")  # open|closed
    fa_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_fa_cases.id"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AsicAssumption(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC I (R3) — Concurrent Engineering 가정 (지시서 §4 EPIC I).

    확정 요구사항과 달리 아직 근거가 확정되지 않은 채 병행 설계를 진행하는
    가정을 등록한다. `requirement_id`로 ASSUMPTION_BASED 요구사항과 연결되고
    `downstream`에 영향 받는 회로/레이아웃/패키지/시험/견적을 명시한다 —
    가정 변경 시 이 목록이 AsicImpactScan 생성의 입력이 된다.
    수용기준: 미해결 고위험 가정이 있으면 mask release가 차단된다
    (asic_gate_policy.UNRESOLVED_HIGH_RISK_ASSUMPTION).
    """

    __tablename__ = "asic_assumptions"

    template_id: Mapped[str] = mapped_column(String(32), index=True)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), nullable=True, index=True
    )
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requirements.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="open")  # open|resolved|invalidated|superseded
    risk: Mapped[str] = mapped_column(String(16))  # low|medium|high
    confidence: Mapped[float] = mapped_column(Float, default=0.5)  # 0.0..1.0 owner self-report
    owner: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 영향 대상 [{kind: circuit|layout|package|test|quote, ref, label}]
    downstream: Mapped[list] = mapped_column(JSONB, default=list)
    resolved_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    events: Mapped[list["AsicAssumptionEvent"]] = relationship(back_populates="assumption")
    impact_scans: Mapped[list["AsicImpactScan"]] = relationship(back_populates="assumption")


class AsicAssumptionEvent(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC I — 가정 변경 장부 (append-only, 불변규칙 1과 동일 원칙).

    `payload`는 변경 필드의 old/new를 담는다. 감사 목적상 행을 지우거나
    고치지 않는다 — 가정 이력은 이 장부로 재구성한다.
    """

    __tablename__ = "asic_assumption_events"

    assumption_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_assumptions.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # created|field_changed|resolved|invalidated|superseded
    payload: Mapped[dict] = mapped_column(JSONB)  # {field: {old, new}, ...} or resolution summary

    assumption: Mapped[AsicAssumption] = relationship(back_populates="events")


class AsicImpactScan(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC I — 가정 변경 영향 탐색 결과 (수용기준 2).

    가정의 내용/신뢰도/리스크가 바뀌면 자동 생성되고, `downstream` 각 항목에
    `action: rerun|review` 상태로 매핑된다. findings가 모두 done이 되기 전까지
    scan은 open — open scan이 남아 있으면 해당 가정은 resolved로 닫을 수 없다.
    """

    __tablename__ = "asic_impact_scans"

    assumption_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("asic_assumptions.id"), index=True
    )
    trigger: Mapped[str] = mapped_column(String(32))  # assumption_changed|created|manual
    # [{kind, ref, label, action: rerun|review, status: pending|done, reason}]
    findings: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(24), default="open")  # open|cleared
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    assumption: Mapped[AsicAssumption] = relationship(back_populates="impact_scans")


class AsicDeviation(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC I — CS 공정 단축/변형의 승인 편차 (수용기준 3).

    일정 단축으로 생략·병행한 활동을 숨기지 않고 문서로 남긴다.
    독립성 규칙 (FA/CAPA 게이트와 동일): `requested_by != decided_by` —
    승인 엔드포인트가 강제한다. 잔여 위험(`residual_risk`)은 승인 조건의 일부.
    """

    __tablename__ = "asic_deviations"

    template_id: Mapped[str] = mapped_column(String(32), index=True)
    # 생략·병행 활동 [{ref, label, stage, reason}]
    skipped: Mapped[list] = mapped_column(JSONB, default=list)
    rationale: Mapped[str] = mapped_column(Text)
    residual_risk: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="submitted")  # submitted|approved|rejected|superseded
    requested_by: Mapped[str] = mapped_column(String(255))
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AsicCopilotInteraction(Base, IdentifiedMixin, ProvenanceMixin):
    """EPIC J (R3) — 근거 중심 AI Copilot 상호작록 (지시서 §4 EPIC J).

    한 번의 질의 = 한 행. 감사 재현 수용기준을 위해 `input_snapshot`(입력 +
    검색 스냅샷)과 그 sha256(`input_hash`)을 남긴다 — 같은 입력·엔진 버전이면
    result가 결정론적으로 재현된다(룰 엔진은 DB 상태에서만 팩트를 수집).
    `result.evidence`의 근거 링크 없는 제안은 게이트 증적으로 첨부될 수
    없다(구조적으로: copilot은 gate/evidence 테이블에 절대 쓰지 않는다).
    `result.abstain`은 OOD·근거 부족·충돌 시 답변 대신 보류를 기록한다.
    """

    __tablename__ = "asic_copilot_interactions"

    template_id: Mapped[str] = mapped_column(String(32), index=True)
    usecase: Mapped[str] = mapped_column(String(32))  # req_draft|similar_fa|corner_sensitivity|wafer_anomaly|fa_hypothesis|test_efficiency|gate_gap
    input_snapshot: Mapped[dict] = mapped_column(JSONB)  # 입력 + 검색된 근거 ref 목록
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    result: Mapped[dict] = mapped_column(JSONB)
    # {summary, facts: [...], evidence: [{kind, ref, label}], proposals: [...],
    #  confidence: float, abstain: bool, abstain_reason}
    engine_version: Mapped[str] = mapped_column(String(64))  # asic-copilot-rules-v1
    accepted_proposals: Mapped[list] = mapped_column(JSONB, default=list)
    # 수락 기록 [{pid, accepted_by, accepted_at, diff_sha256, applied_ref}]
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
