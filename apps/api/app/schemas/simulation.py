import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.simulation import RunStatus, RunType


class SimulationRunCreate(BaseModel):
    business_id: str
    variant_id: uuid.UUID
    run_type: RunType
    input_artifact_version_id: uuid.UUID | None = None
    parameters: dict | None = None


class ResultMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    value: float
    unit: str | None


class SimulationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    variant_id: uuid.UUID
    run_type: RunType
    status: RunStatus
    input_artifact_version_id: uuid.UUID | None
    output_artifact_version_id: uuid.UUID | None
    tool_version: str | None
    parameters: dict | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_by: str
    created_at: datetime
    metrics: list[ResultMetricRead] = []
