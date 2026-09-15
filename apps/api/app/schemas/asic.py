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
