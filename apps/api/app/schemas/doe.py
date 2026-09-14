"""Schemas for AN-04 DOE/optimization (지시서 §7 AN-04, FR-06 lite)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DoeTargetBand(BaseModel):
    min: float
    max: float
    unit: str | None = None
    # §7: any demo spec band must be labelled as such — never presented as a
    # real customer spec.
    source: str = "데모 사양·합성 데이터"


class DoeStudyCreate(BaseModel):
    business_id: str
    variant_id: uuid.UUID
    operation_id: uuid.UUID
    parameter: str
    metric: str = Field(default="peak", pattern="^(peak|mean)$")
    target_band: DoeTargetBand | None = None
    candidate_grid_size: int = Field(default=5, ge=3, le=20)


class DoeObservation(BaseModel):
    lot_business_id: str
    process_run_business_id: str
    parameter_value: float
    ctq_value: float
    out_of_window: bool
    window_findings: list[dict] | None = None


class DoeFit(BaseModel):
    slope: float
    intercept: float
    r_squared: float
    direction: str
    n_observations: int


class DoeCandidate(BaseModel):
    parameter_value: float
    predicted_ctq: float
    in_window: bool
    meets_target: bool | None
    distance_to_target_center: float | None
    rank: int | None
    source: str


class DoeStudyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    variant_id: uuid.UUID
    operation_id: uuid.UUID
    parameter: str
    parameter_unit: str | None
    metric: str
    metric_unit: str | None
    target_band: DoeTargetBand | None
    observations: list[DoeObservation]
    fit: DoeFit
    candidates: list[DoeCandidate]
    constraint_violations: list[DoeObservation]
    disclaimer: str = (
        "회귀·후보 비교는 확인 필요 정보이며, AI/최적화가 최종 해를 임의로 확정하지 않습니다. "
        "후보 실행은 담당 엔지니어 승인 후 진행하세요."
    )
    created_by: str
    created_at: datetime
