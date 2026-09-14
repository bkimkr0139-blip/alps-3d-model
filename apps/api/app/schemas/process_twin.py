"""Schemas for the TACT Product–Process Twin vertical slice (지시서 §9.1 lite)."""

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.process_twin import DefectSeverity, LotDisposition


class MoldCreate(BaseModel):
    business_id: str
    name: str
    tool_revision: str = "A"
    process: str | None = None
    notes: str | None = None


class MoldRead(MoldCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_by: str
    created_at: datetime


class CavityCreate(BaseModel):
    business_id: str
    cavity_no: int = Field(ge=1)
    label: str
    notes: str | None = None


class CavityRead(CavityCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mold_id: uuid.UUID
    created_by: str
    created_at: datetime


class WindowBound(BaseModel):
    parameter: str
    unit: str | None = None
    min: float
    max: float


class ProcessOperationCreate(BaseModel):
    business_id: str
    name: str
    seq_no: int
    equipment: str | None = None
    description: str | None = None
    window: list[WindowBound] | None = None


class ProcessOperationRead(ProcessOperationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_by: str
    created_at: datetime


class LotCreate(BaseModel):
    business_id: str
    variant_id: uuid.UUID
    mold_id: uuid.UUID
    cavity_id: uuid.UUID
    material_lot_id: str | None = None
    work_order_id: str | None = None
    produced_at: datetime
    quantity: int | None = None
    disposition: LotDisposition = LotDisposition.OK
    notes: str | None = None


class LotRead(LotCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_by: str
    created_at: datetime


class ProcessRunCreate(BaseModel):
    business_id: str
    lot_id: uuid.UUID
    operation_id: uuid.UUID
    setpoint: dict | None = None
    actual: dict | None = None
    started_at: datetime
    operator: str | None = None


class ProcessRunRead(ProcessRunCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    out_of_window: bool
    window_findings: list | None
    created_by: str
    created_at: datetime


class DefectCreate(BaseModel):
    business_id: str
    lot_id: uuid.UUID
    defect_class: str
    severity: DefectSeverity
    quantity: int = Field(default=1, ge=1)
    unit_id: str | None = None
    note: str | None = None


class DefectRead(DefectCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_by: str
    created_at: datetime


# -- genealogy (지시서 TS05 / AC-02) -------------------------------------------


class GenealogyProcessRun(BaseModel):
    business_id: str
    operation: str
    operation_business_id: str
    seq_no: int
    equipment: str | None
    setpoint: dict | None
    actual: dict | None
    out_of_window: bool
    window_findings: list | None
    started_at: datetime


class GenealogyTestRun(BaseModel):
    id: uuid.UUID
    business_id: str
    executed_at: datetime
    measurement_count: int
    y_unit: str | None


class GenealogyDefect(BaseModel):
    business_id: str
    defect_class: str
    severity: DefectSeverity
    quantity: int
    note: str | None


class LotGenealogy(BaseModel):
    lot: LotRead
    mold: MoldRead
    cavity: CavityRead
    process_runs: list[GenealogyProcessRun]
    test_runs: list[GenealogyTestRun]
    defects: list[GenealogyDefect]


# -- cavity comparison (지시서 AN-02 / AC-03) -----------------------------------


class CavityCtqStats(BaseModel):
    cavity_id: uuid.UUID
    cavity_label: str
    lot_count: int
    n_values: int
    mean: float | None
    sd: float | None
    # Cp/Cpk per AN-03 — only computed when spec limits are supplied
    cp: float | None = None
    cpk: float | None = None


class CavityComparison(BaseModel):
    variant_id: uuid.UUID
    metric: str
    unit: str
    cavities: list[CavityCtqStats]
    # Drift flag between cavities — a check-required hint (AN-02: 이상 탐지는
    # 원인 확정이 아니라 조사 우선순위), never a verdict.
    drift_suspected: bool
    check_note: str | None = None


# -- rule-based root-cause hypotheses (지시서 AI-01 lite) ------------------------


class RootCauseCause(str, Enum):
    PROCESS_OUT_OF_WINDOW = "process_out_of_window"
    CAVITY_BIAS = "cavity_bias"
    MATERIAL_LOT = "material_lot"
    INSUFFICIENT_DATA = "insufficient_data"


class RootCauseCandidate(BaseModel):
    cause: RootCauseCause
    title: str
    # Always "check_required": the API proposes investigation priorities, it
    # never settles a root cause (AI-04: 상관을 인과로 단정 금지).
    confidence: str = "check_required"
    detail: str
    # [{kind, business_id, note}] — every claim pins a real entity
    evidence: list[dict]


class RootCauseHypothesis(BaseModel):
    lot_id: uuid.UUID
    lot_business_id: str
    candidates: list[RootCauseCandidate]
    disclaimer: str
