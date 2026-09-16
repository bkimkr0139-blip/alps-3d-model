"""Schemas for the ASIC Twin v1.1 R1 P0 slice (지시서 v1.1 §6/§7).

`*Create`/`*Read` split per the house pattern. Status/class fields are
Literal-validated here (the DB columns are plain strings — see
models/asic.py for why no pg ENUM). New Read fields all default None so
idempotency-cache replays of older creation responses can't 500 (HANDOFF §8).
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TEMPLATE_IDS = ("cap_afe", "current_sensor", "motor_ripple", "env_sensor")
TemplateId = Literal["cap_afe", "current_sensor", "motor_ripple", "env_sensor"]

SourceClass = Literal["REAL_MEASURED", "REAL_SIMULATION", "SURROGATE", "SYNTHETIC", "MANUAL"]


class ChainBlock(BaseModel):
    """One signal-chain block (EPIC A): sensor→AFE→ADC→digital→output."""

    key: str
    kind: Literal["sensor", "analog", "mixed", "digital", "io", "power"]
    label: str
    params: dict = Field(default_factory=dict)
    error_budget: dict = Field(default_factory=dict)  # offset/gain_error/inl/dnl/noise/drift/latency/saturation
    requirement_ids: list[str] = Field(default_factory=list)


class SignalChainCreate(BaseModel):
    business_id: str
    template_id: TemplateId
    variant_id: uuid.UUID | None = None
    blocks: list[ChainBlock]
    source_class: SourceClass = "SYNTHETIC"
    note: str | None = None


class SignalChainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    variant_id: uuid.UUID | None
    revision: int
    status: str
    blocks: list[dict]
    source_class: str
    supersedes_id: uuid.UUID | None
    content_hash: str
    note: str | None
    created_by: str
    created_at: datetime


class CornerSpecLimit(BaseModel):
    output: str
    nominal: float | None = None  # expected center value for this output
    min: float | None = None
    max: float | None = None
    unit: str | None = None


class CornerStudyCreate(BaseModel):
    business_id: str
    signal_chain_id: uuid.UUID
    kind: Literal["corner", "monte_carlo", "temp_sweep"] = "monte_carlo"
    n_draws: int = Field(default=2000, ge=100, le=20000)
    # bounded to PostgreSQL INTEGER — None → deterministic from business_id
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    spec: list[CornerSpecLimit]


class CornerStudyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    signal_chain_id: uuid.UUID
    kind: str
    n_draws: int
    seed: int
    spec: list[dict]
    result: dict | None
    tool_version: str
    source_class: str
    status: str
    created_by: str
    created_at: datetime


class MeasurementRunImportMeta(BaseModel):
    """Form-fields metadata for the multipart import (EPIC E)."""

    business_id: str
    template_id: TemplateId
    variant_id: uuid.UUID | None = None
    equipment_id: str
    equipment_type: Literal["sem_tester", "wafer_prober", "handler"]
    equipment_model: str | None = None
    firmware: str | None = None
    calibration_expires_at: datetime | None = None
    program_revision: str | None = None
    operator: str | None = None
    executed_at: datetime | None = None
    lot_ref: str | None = None


class MeasurementPointRead(BaseModel):
    name: str
    value: float
    unit: str | None = None
    raw_value: float | None = None
    raw_unit: str | None = None
    site: int | None = None
    temperature_c: float | None = None


class MeasurementRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    variant_id: uuid.UUID | None
    equipment_id: str
    equipment_type: str
    equipment_model: str | None
    firmware: str | None
    calibration_expires_at: datetime | None
    program_revision: str | None
    operator: str | None
    executed_at: datetime | None
    raw_artifact_version_id: uuid.UUID | None
    file_hash: str
    status: str
    points: list[dict] | None
    findings: list[dict] | None
    lot_ref: str | None
    created_by: str
    created_at: datetime


class QualificationPlanCreate(BaseModel):
    business_id: str
    template_id: TemplateId
    variant_id: uuid.UUID | None = None
    grade: Literal["G0", "G1", "G2"]
    standard_version: str | None = None
    note: str | None = None


class QualificationPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    variant_id: uuid.UUID | None
    grade: str
    policy_version: str
    standard_version: str | None
    status: str
    note: str | None
    results: list["QualificationResultRead"] = []
    created_by: str
    created_at: datetime


class QualificationResultCreate(BaseModel):
    business_id: str
    group: str
    method: str
    condition: dict
    samples: str
    lots: list[str] | None = None
    pre_electrical_run_id: uuid.UUID | None = None
    post_electrical_run_id: uuid.UUID | None = None
    status: Literal["pending", "pass", "fail"] = "pending"
    failed_param: str | None = None
    fa_case_id: uuid.UUID | None = None
    waiver_ref: str | None = None
    waiver_expires_at: datetime | None = None


class QualificationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    plan_id: uuid.UUID
    group: str
    method: str
    condition: dict
    samples: str
    lots: list | None
    pre_electrical_run_id: uuid.UUID | None
    post_electrical_run_id: uuid.UUID | None
    status: str
    failed_param: str | None
    fa_case_id: uuid.UUID | None
    waiver_ref: str | None
    waiver_expires_at: datetime | None
    created_at: datetime


class SafetyItemCreate(BaseModel):
    business_id: str
    template_id: TemplateId
    variant_id: uuid.UUID | None = None
    level: Literal["safety_goal", "fsr", "tsr", "hw_req"]
    parent_business_id: str | None = None
    title: str
    asil: Literal["QM", "A", "B", "C", "D"] | None = None
    safety_mechanism: str | None = None
    diagnostic_coverage_pct: float | None = None
    safe_state: str | None = None
    response_time_ms: float | None = None


class SafetyItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    variant_id: uuid.UUID | None
    level: str
    parent_id: uuid.UUID | None
    title: str
    asil: str | None
    safety_mechanism: str | None
    diagnostic_coverage_pct: float | None
    safe_state: str | None
    response_time_ms: float | None
    created_by: str
    created_at: datetime


class FmedaItemCreate(BaseModel):
    business_id: str
    safety_item_business_id: str
    failure_mode: str
    distribution_pct: float
    dc_pct: float | None = None
    fit_rate: float | None = None
    source_ref: str | None = None
    source_hash: str | None = None
    formula_version: str | None = None
    note: str | None = None


class FmedaItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    safety_item_id: uuid.UUID
    failure_mode: str
    distribution_pct: float
    dc_pct: float | None
    fit_rate: float | None
    source_ref: str | None
    source_hash: str | None
    formula_version: str | None
    note: str | None
    created_at: datetime


class FaultInjectionCreate(BaseModel):
    business_id: str
    safety_item_business_id: str
    method: str
    stimulus: str
    expected: str
    observed: str
    status: Literal["pass", "fail", "pending"] = "pending"
    executed_by: str | None = None
    executed_at: datetime | None = None


class FaultInjectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    safety_item_id: uuid.UUID
    method: str
    stimulus: str
    expected: str
    observed: str
    status: str
    simulation_run_id: uuid.UUID | None
    executed_by: str | None
    executed_at: datetime | None
    created_at: datetime


class FaObservation(BaseModel):
    fact: str
    source: str | None = None  # measurement_run business_id / analysis method


class FaHypothesis(BaseModel):
    text: str
    confirm_tests: list[str] = Field(default_factory=list)
    excluded: bool = False
    exclusion_basis: str | None = None


class FaCaseCreate(BaseModel):
    business_id: str
    template_id: TemplateId
    variant_id: uuid.UUID | None = None
    scope: Literal["lot", "wafer", "die", "package", "field_return"]
    lot_ref: str | None = None
    wafer_ref: str | None = None
    die_ref: str | None = None
    symptom: str
    repro_condition: str | None = None
    location: dict | None = None
    observations: list[FaObservation] = Field(default_factory=list)


class FaCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    variant_id: uuid.UUID | None
    scope: str
    lot_ref: str | None
    wafer_ref: str | None
    die_ref: str | None
    symptom: str
    repro_condition: str | None
    status: str
    observations: list[dict] | None
    hypotheses: list[dict] | None
    root_cause: str | None
    root_cause_confirmed: bool
    cause_class: str | None
    location: dict | None
    analysts: list | None
    closed_at: datetime | None
    created_by: str
    created_at: datetime


class FaCaseUpdate(BaseModel):
    """Investigation progress: observations/hypotheses/location/status. The
    root-cause approval is a SEPARATE endpoint (role-gated) — you cannot
    approve an RCA by patching the row."""

    observations: list[FaObservation] | None = None
    hypotheses: list[FaHypothesis] | None = None
    location: dict | None = None
    status: Literal["open", "analyzing", "rca_approved", "eco_open", "verified", "closed"] | None = None


class FaRootCauseRequest(BaseModel):
    root_cause: str
    cause_class: Literal[
        "design", "process", "package", "test", "handling", "application", "unknown"
    ]
    comment: str | None = None
    # 지시서 §4 EPIC G 수용기준 1: 최종 원인은 관찰 사실 + 확인 증적 없이 승인 불가
    evidence_business_ids: list[str]


class FaEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    case_id: uuid.UUID
    event_type: str
    actor: str
    actor_roles: list[str]
    comment: str | None
    evidence: dict | None
    occurred_at: datetime


class AsicEcoCreate(BaseModel):
    business_id: str
    template_id: TemplateId
    fa_case_business_id: str | None = None
    trigger: Literal["fa_case", "limit_change", "improvement"]
    title: str
    description: str | None = None
    design_rev_from: str | None = None
    design_rev_to: str | None = None
    mask_revision: str | None = None
    test_program_revision: str | None = None
    impact: list[dict] | None = None


class AsicEcoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    fa_case_id: uuid.UUID | None
    template_id: str
    trigger: str
    title: str
    description: str | None
    design_rev_from: str | None
    design_rev_to: str | None
    mask_revision: str | None
    test_program_revision: str | None
    impact: list[dict] | None
    status: str
    regression_run_ids: list | None
    verification_note: str | None
    verification_run_id: uuid.UUID | None
    closed_at: datetime | None
    created_by: str
    created_at: datetime


class AsicEcoAnalyzeRequest(BaseModel):
    design_rev_from: str | None = None
    design_rev_to: str | None = None
    mask_revision: str | None = None
    test_program_revision: str | None = None
    impact: list[dict] | None = None
    comment: str | None = None


class AsicEcoRegressionRequest(BaseModel):
    regression_run_ids: list[str]
    comment: str | None = None


class AsicEcoCloseRequest(BaseModel):
    verification_run_business_id: str
    verification_note: str
    comment: str | None = None


class GateBlocker(BaseModel):
    code: str
    detail: str
    evidence: list[str] = Field(default_factory=list)


class AsicGateReport(BaseModel):
    """POST-free GET report per template: computed blockers + readiness rung
    (지시서 §8 게이트 정책 확장 + Readiness Ladder 개편). The frontend ASIC tab
    renders this verbatim — blockers are never hand-authored in the UI."""

    template_id: str
    gate_id: str
    policy_version: str = "alps-asic-v1.1"
    status: Literal["pass", "blocked"]
    blockers: list[GateBlocker]
    readiness: Literal[
        "education_only",
        "connected_nonvalidated",
        "validated_shadow",
        "controlled_pilot",
        "production_candidate",
        "released",
    ]
    readiness_reachable: bool
    checks: list[dict]
    evaluated_at: datetime


QualificationPlanRead.model_rebuild()


# ── R2 — EPIC B: FAB·패키지·원가·납기 (지시서 §4 EPIC B) ─────────────────────

NreComponent = Literal[
    "design", "ip", "mask", "mpw_shuttle", "pkg_tooling", "test_dev", "reliability"
]
UnitComponent = Literal["wafer", "die_yield", "assembly", "final_test", "logistics", "scrap"]
RiskKind = Literal[
    "supply_single", "long_lead", "yield_uncertainty", "thermal_stress", "equipment_availability"
]


class NreEntry(BaseModel):
    """One NRE component — decided ({amount,...}) or TBD ({amount_tbd})."""

    amount: float | None = None
    amount_tbd: str | None = None  # 이유 — TBD는 0으로 계산되지 않는다
    currency: Literal["KRW", "USD", "JPY", "EUR"] = "KRW"
    basis_date: str | None = None
    qty_basis: int | None = None
    ref: str | None = None  # 근거 문서 (지시서: 모든 숫자에 근거 문서 연결)


class UnitCostEntry(BaseModel):
    """One unit-cost component with Base/Best/Worst bands."""

    base: float | None = None
    best: float | None = None
    worst: float | None = None
    base_tbd: str | None = None
    unit: str | None = None
    currency: Literal["KRW", "USD", "JPY", "EUR"] = "KRW"
    basis_date: str | None = None
    dies_per_wafer: float | None = None  # wafer entry only
    ref: str | None = None


class SchedulePhase(BaseModel):
    phase: Literal[
        "pdk_ip", "design", "tapeout", "wafer", "assembly", "es_cs", "qualification"
    ]
    weeks_best: float
    weeks_base: float
    weeks_worst: float


class RiskEntry(BaseModel):
    kind: RiskKind
    note: str
    severity: Literal["high", "medium", "low"]


class ManufacturingOptionCreate(BaseModel):
    business_id: str = Field(min_length=3, max_length=64)
    template_id: TemplateId
    variant_id: uuid.UUID | None = None
    foundry: str = Field(min_length=1, max_length=64)
    node: str = Field(min_length=1, max_length=64)
    wafer_size_mm: float | None = None
    voltage_option: str | None = None
    device_option: str | None = None
    temperature_grade: str | None = None
    package: str = Field(min_length=1, max_length=64)
    osat: str | None = None
    moq: int | None = None
    tech_score: int | None = Field(default=None, ge=1, le=5)
    nre: dict[NreComponent, NreEntry]
    unit_cost: dict[UnitComponent, UnitCostEntry]
    schedule: list[SchedulePhase]
    risks: list[RiskEntry] = Field(default_factory=list)
    status: Literal["draft", "approved"] = "draft"
    note: str | None = None


class ManufacturingOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    variant_id: uuid.UUID | None
    foundry: str
    node: str
    wafer_size_mm: float | None
    voltage_option: str | None
    device_option: str | None
    temperature_grade: str | None
    package: str
    osat: str | None
    moq: int | None
    tech_score: int | None
    # cost fields are role-restricted (수용기준: 내부 단가 데이터는 열람 범위 제한) —
    # unauthenticated/limited callers get cost_restricted=true with these None.
    nre: dict | None
    unit_cost: dict | None
    schedule: list | None
    risks: list | None
    status: str
    note: str | None
    created_by: str
    created_at: datetime
    cost_restricted: bool = False


class TradeStudyCreate(BaseModel):
    business_id: str = Field(min_length=3, max_length=64)
    template_id: TemplateId
    variant_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    option_ids: list[uuid.UUID] = Field(min_length=2, max_length=5)
    weights: dict[Literal["cost", "schedule", "technology", "supply"], float]
    annual_volume: int = Field(ge=1)


class TradeStudyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    variant_id: uuid.UUID | None
    title: str
    option_ids: list
    weights: dict
    annual_volume: int
    result: dict | None
    decision: dict | None
    status: str
    created_by: str
    created_at: datetime


class TradeStudyDecision(BaseModel):
    """옵션 선택 기록 (수용기준: 승인자·판단 근거·잔여 위험을 기록한다)."""

    option_id: uuid.UUID
    rationale: str = Field(min_length=1)
    residual_risks: list[str] = Field(default_factory=list)


# ── R2 — EPIC C: EDA 실행·검증 오케스트레이션 (지시서 §4 EPIC C) ──────────────

ToolName = Literal[
    "schematic_check", "spice", "ams", "lint", "cdc", "rdc",
    "synthesis", "sta", "pr", "drc", "lvs", "erc", "signoff",
]
RunnerClass = Literal["real_adapter", "mock"]


class ToolRunCreate(BaseModel):
    """One external EDA execution's approved metadata (도구 자체는 온프레미스
    실행 — 이 API는 메타데이터·해시·로그 위치만 수집한다)."""

    business_id: str = Field(min_length=3, max_length=64)
    template_id: TemplateId
    variant_id: uuid.UUID | None = None
    design_revision: int = Field(ge=1)
    tool: ToolName
    tool_version: str = Field(min_length=1, max_length=64)
    runner_class: RunnerClass
    environment: dict | None = None  # {image_digest | host, os, ...}
    command_profile: str | None = None
    input_hash: str = Field(min_length=64, max_length=64, pattern="^[0-9a-f]{64}$")
    output_hash: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    exit_code: int
    log_uri: str | None = None
    report_artifact_version_id: uuid.UUID | None = None
    metrics: dict | None = None
    note: str | None = None


class ToolRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    variant_id: uuid.UUID | None
    design_revision: int
    tool: str
    tool_version: str
    runner_class: str
    environment: dict | None
    command_profile: str | None
    input_hash: str
    output_hash: str | None
    exit_code: int
    log_uri: str | None
    report_artifact_version_id: uuid.UUID | None
    lineage_id: uuid.UUID
    metrics: dict | None
    status: str
    note: str | None
    created_by: str
    created_at: datetime


# ---------------------------------------------------------------------------
# EPIC D — DFT·양산 테스트 프로그램 트윈 (지시서 §4)
# ---------------------------------------------------------------------------

TestFlowTarget = Literal["wafer_sort", "final_test"]
TestStage = Literal[
    "contact", "pre_check", "dc", "analog", "digital", "trim_cal", "interface", "final_bin",
]


class Limits(BaseModel):
    low: float | None = None
    high: float | None = None
    unit: str | None = None


class DefectCoverageEntry(BaseModel):
    defect_class: Literal["open", "short", "leakage", "parametric", "esd", "latchup"]
    coverage_pct: float = Field(ge=0, le=100)


class TestFlowItemIn(BaseModel):
    seq: int = Field(ge=1)
    stage: TestStage
    name: str = Field(min_length=1, max_length=128)
    limits: Limits | None = None
    temperature_c: float | None = None
    site_count: int = Field(default=1, ge=1)
    pattern: str | None = Field(default=None, max_length=64)
    instrument: str | None = Field(default=None, max_length=64)
    equipment_channel: str | None = Field(default=None, max_length=32)
    expected_duration_s: float = Field(gt=0)
    requirement_ids: list[str] | None = None
    failure_mode_refs: list[str] | None = None
    defect_coverage: list[DefectCoverageEntry] | None = None


class TestFlowCreate(BaseModel):
    business_id: str = Field(min_length=3, max_length=64)
    template_id: TemplateId
    variant_id: uuid.UUID | None = None
    program_revision: int = Field(ge=1)
    silicon_revision: str = Field(min_length=1, max_length=32)
    compatible_mask_rev: str | None = Field(default=None, max_length=32)
    compatible_package_rev: str | None = Field(default=None, max_length=32)
    target: TestFlowTarget
    cost_rate_per_site_hour: float | None = None  # None = TBD
    status: Literal["draft", "released"] = "draft"
    note: str | None = None
    items: list[TestFlowItemIn] = Field(min_length=1)


class TestFlowItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    test_flow_id: uuid.UUID
    seq: int
    stage: str
    name: str
    limits: dict | None
    temperature_c: float | None
    site_count: int
    pattern: str | None
    instrument: str | None
    equipment_channel: str | None
    expected_duration_s: float
    requirement_ids: list | None
    failure_mode_refs: list | None
    defect_coverage: list | None


class TestFlowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    variant_id: uuid.UUID | None
    program_revision: int
    silicon_revision: str
    compatible_mask_rev: str | None
    compatible_package_rev: str | None
    target: str
    cost_rate_per_site_hour: float | None
    status: str
    note: str | None
    created_by: str
    created_at: datetime
    items: list[TestFlowItemRead] = []


class LimitChangeCreate(BaseModel):
    item_id: uuid.UUID
    new_limits: Limits
    rationale: str = Field(min_length=1)


class LimitChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    test_flow_id: uuid.UUID
    item_id: uuid.UUID
    old_limits: dict | None
    new_limits: dict
    rationale: str
    impact: dict | None
    status: str
    applied_flow_id: uuid.UUID | None
    created_by: str
    created_at: datetime


class WaferMapCreate(BaseModel):
    business_id: str = Field(min_length=3, max_length=64)
    template_id: TemplateId
    variant_id: uuid.UUID | None = None
    lot_ref: str | None = Field(default=None, max_length=64)
    wafer_ref: str | None = Field(default=None, max_length=64)
    test_flow_id: uuid.UUID | None = None
    grid: dict  # {rows, cols}
    bins: list[dict] = Field(min_length=1)  # [{x, y, bin, site}]
    ground_truth: dict | None = None  # SYNTHETIC fixture only — {bad_xy, note}
    source_class: SourceClass = "SYNTHETIC"
    note: str | None = None


class WaferMapRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    variant_id: uuid.UUID | None
    lot_ref: str | None
    wafer_ref: str | None
    test_flow_id: uuid.UUID | None
    grid: dict
    bins: list
    ground_truth: dict | None
    analysis: dict | None
    source_class: str
    note: str | None
    created_by: str
    created_at: datetime


# ---------------------------------------------------------------------------
# EPIC H — 파운드리·OSAT 포털·lot genealogy (지시서 §4)
# ---------------------------------------------------------------------------

PartnerKind = Literal["foundry", "osat", "subcon", "material"]


class AsicPartnerCreate(BaseModel):
    business_id: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    kind: PartnerKind
    status: Literal["approved", "conditional", "suspended"] = "conditional"
    approved_scope: dict | None = None
    note: str | None = None


class AsicPartnerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    name: str
    kind: str
    status: str
    approved_scope: dict | None
    approved_at: datetime | None
    note: str | None
    created_by: str
    created_at: datetime


class LotStep(BaseModel):
    partner_business_id: str
    step: str = Field(min_length=1, max_length=64)
    result: str | None = None


class LotTravelerCreate(BaseModel):
    business_id: str = Field(min_length=3, max_length=64)
    template_id: TemplateId
    variant_id: uuid.UUID | None = None
    lot_ref: str = Field(min_length=1, max_length=64)
    parent_lot_refs: list[str] | None = None
    silicon_revision: str | None = Field(default=None, max_length=32)
    mask_rev: str | None = Field(default=None, max_length=32)
    package_rev: str | None = Field(default=None, max_length=32)
    note: str | None = None
    steps: list[LotStep] = Field(min_length=1)


class LotTravelerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    variant_id: uuid.UUID | None
    lot_ref: str
    parent_lot_refs: list | None
    silicon_revision: str | None
    mask_rev: str | None
    package_rev: str | None
    current_partner_id: uuid.UUID | None
    status: str
    steps: list
    note: str | None
    created_by: str
    created_at: datetime


class PartnerArtifactCreate(BaseModel):
    business_id: str = Field(min_length=3, max_length=64)
    partner_business_id: str = Field(min_length=3, max_length=64)  # portal principal mapping
    template_id: TemplateId
    lot_traveler_id: uuid.UUID | None = None
    kind: Literal["test_report", "wafer_map", "ship_doc", "cert"]
    file_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    meta: dict | None = None
    note: str | None = None


class PartnerArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    partner_id: uuid.UUID
    lot_traveler_id: uuid.UUID | None
    template_id: str
    kind: str
    file_hash: str
    artifact_version_id: uuid.UUID | None
    meta: dict | None
    status: str
    note: str | None
    created_by: str
    created_at: datetime


class PartnerChangeCreate(BaseModel):
    business_id: str = Field(min_length=3, max_length=64)
    partner_business_id: str = Field(min_length=3, max_length=64)  # portal principal mapping
    kind: Literal["process", "site_transfer", "equipment", "material"]
    description: str = Field(min_length=1)
    effective_at: datetime | None = None
    affected_template_ids: list[TemplateId] | None = None
    note: str | None = None


class PartnerChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    partner_id: uuid.UUID
    kind: str
    description: str
    effective_at: datetime | None
    affected_template_ids: list | None
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    note: str | None
    created_by: str
    created_at: datetime


class PartnerChangeReview(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = None


class QualityActionCreate(BaseModel):
    business_id: str = Field(min_length=3, max_length=64)
    template_id: TemplateId
    lot_traveler_id: uuid.UUID | None = None
    lot_ref: str | None = Field(default=None, max_length=64)
    action: Literal["hold", "quarantine", "sort", "scrap", "8d"]
    reason: str = Field(min_length=1)
    fa_case_id: uuid.UUID | None = None
    note: str | None = None


class QualityActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    partner_id: uuid.UUID | None
    lot_traveler_id: uuid.UUID | None
    template_id: str
    lot_ref: str | None
    action: str
    reason: str
    status: str
    fa_case_id: uuid.UUID | None
    closed_at: datetime | None
    note: str | None
    created_by: str
    created_at: datetime


class QualityActionClose(BaseModel):
    note: str | None = None


# ── R3 EPIC I: concurrent-engineering control panel ──────────────────────────

DownstreamKind = Literal["circuit", "layout", "package", "test", "quote"]


class DownstreamRef(BaseModel):
    """가정이 변경될 때 영향을 받는 대상 한 건 (§4 EPIC I 구현범위 3)."""

    kind: DownstreamKind
    ref: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=255)


class AssumptionCreate(BaseModel):
    business_id: str = Field(min_length=3, max_length=64)
    template_id: TemplateId
    variant_id: uuid.UUID | None = None
    requirement_id: uuid.UUID | None = None
    title: str = Field(min_length=3, max_length=255)
    detail: str = Field(min_length=1)
    risk: Literal["low", "medium", "high"] = "medium"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    owner: str = Field(min_length=1, max_length=255)
    due_at: datetime | None = None
    downstream: list[DownstreamRef] = Field(default_factory=list)
    note: str | None = None


class AssumptionUpdate(BaseModel):
    """부분 수정 — 변경된 필드만 old/new로 장부에 남고, 내용·신뢰도·리스크가
    바뀌면 영향 탐색이 자동 생성된다 (수용기준 2)."""

    title: str | None = Field(default=None, min_length=3, max_length=255)
    detail: str | None = None
    risk: Literal["low", "medium", "high"] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    owner: str | None = Field(default=None, max_length=255)
    due_at: datetime | None = None
    downstream: list[DownstreamRef] | None = None
    note: str | None = None


class AssumptionResolve(BaseModel):
    decision: Literal["resolved", "invalidated"]
    evidence: dict = Field(default_factory=dict)  # {ref, label, summary} 근거 링크
    note: str | None = None


class AssumptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    variant_id: uuid.UUID | None
    requirement_id: uuid.UUID | None
    title: str
    detail: str
    status: str
    risk: str
    confidence: float
    owner: str
    due_at: datetime | None
    downstream: list[dict]
    resolved_evidence: dict | None
    resolved_at: datetime | None
    note: str | None
    created_by: str
    created_at: datetime


class AssumptionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    assumption_id: uuid.UUID
    kind: str
    payload: dict
    created_by: str
    created_at: datetime


class ImpactFindingRead(BaseModel):
    kind: DownstreamKind
    ref: str
    label: str
    action: Literal["rerun", "review"]
    status: Literal["pending", "done"]
    reason: str | None = None


class ImpactScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    assumption_id: uuid.UUID
    trigger: str
    findings: list[dict]
    status: str
    note: str | None
    created_by: str
    created_at: datetime


class FindingDone(BaseModel):
    ref: str = Field(min_length=1, max_length=128)
    note: str | None = None


class SkippedRef(BaseModel):
    """생략·병행된 활동 한 건 (§4 EPIC I 구현범위 5) — 활동은 스테이지로 읽는다."""

    stage: str = Field(min_length=1, max_length=64)
    ref: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=255)


class DeviationCreate(BaseModel):
    business_id: str = Field(min_length=3, max_length=64)
    template_id: TemplateId
    skipped: list[SkippedRef] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    residual_risk: str = Field(min_length=1)
    note: str | None = None


class DeviationDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = None


class DeviationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    skipped: list[dict]
    rationale: str
    residual_risk: str
    status: str
    requested_by: str
    decided_by: str | None
    decided_at: datetime | None
    note: str | None
    created_by: str
    created_at: datetime


# ── R3 EPIC J: evidence-grounded AI copilot ─────────────────────────────────

CopilotUsecase = Literal[
    "req_draft",
    "similar_fa",
    "corner_sensitivity",
    "wafer_anomaly",
    "fa_hypothesis",
    "test_efficiency",
    "gate_gap",
]


class CopilotRun(BaseModel):
    usecase: CopilotUsecase
    text: str | None = Field(default=None, max_length=4000)  # req_draft/similar_fa 질의문
    fa_case_id: uuid.UUID | None = None  # fa_hypothesis 대상


class CopilotEvidence(BaseModel):
    kind: str  # fa_case|corner_study|wafer_map|test_flow|gate_report|measurement_run|requirement
    ref: str  # business_id 또는 gate-report/{template_id} 형태 링크
    label: str


class CopilotProposal(BaseModel):
    pid: str
    kind: str  # requirement_draft|fa_hypothesis|confirm_test|review_candidate
    text: str
    diff_base: str | None = None  # 원문(대상 문서) 대비 diff를 UI가 강제 표시
    evidence: list[CopilotEvidence]


class CopilotResult(BaseModel):
    summary: str
    facts: list[str] = Field(default_factory=list)
    evidence: list[CopilotEvidence] = Field(default_factory=list)
    proposals: list[CopilotProposal] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    abstain: bool = False
    abstain_reason: str | None = None


class CopilotInteractionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    template_id: str
    usecase: str
    input_snapshot: dict
    input_hash: str
    result: dict
    engine_version: str
    accepted_proposals: list[dict]
    note: str | None
    created_by: str
    created_at: datetime


class ProposalAccept(BaseModel):
    """수용기준: 사용자가 AI 제안 수락 전 원문 대비 diff를 확인한다 —
    `diff_sha256`은 UI가 표시한 diff 본문의 해시로, 서버가 재계산해 대조한다."""

    pid: str
    diff_sha256: str = Field(min_length=64, max_length=64)
    note: str | None = None
