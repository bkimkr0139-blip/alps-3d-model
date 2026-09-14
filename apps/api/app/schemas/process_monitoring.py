"""Schemas for process monitoring (TACT 지시서 AN-03 관리도 + AI-03 이상 설명)."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ProcessParameterInfo(BaseModel):
    parameter: str
    unit: str | None
    n_points: int
    operation_business_ids: list[str]


class ControlChartPoint(BaseModel):
    lot_business_id: str
    process_run_business_id: str
    operation: str
    seq_no: int
    cavity_label: str
    started_at: datetime
    value: float
    # Points excluded from the limit basis (with the audit-visible reason):
    # the exclusion is derived from the immutable out_of_window flag that P1
    # already stored — AN-03's "제외 사유를 감사 가능하게" without new writes.
    excluded_from_limits: bool
    exclusion_reason: str | None = None
    violations: list[str] = []


class ControlChart(BaseModel):
    variant_id: uuid.UUID
    parameter: str
    unit: str | None
    n_points: int
    n_basis: int
    center_line: float | None
    sigma: float | None
    lcl: float | None
    ucl: float | None
    points: list[ControlChartPoint]
    rule_hits: list[str]
    # AN-03: control limits come from the measured stable process and must
    # never be confused with spec limits — the UI prints this verbatim.
    note: str


class AnomalyExplanation(BaseModel):
    variant_id: uuid.UUID
    parameter: str
    # Always a 조사 가설 (investigation hypothesis) — AI-03: 데이터가
    # 충분하지 않으면 원인 대신 조사 가설로 표시한다.
    hypothesis: str
    facts_used: list[str]
    model: str
    disclaimer: str
    generated_at: datetime
