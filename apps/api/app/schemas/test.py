import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TestPlanCreate(BaseModel):
    business_id: str
    variant_id: uuid.UUID
    name: str


class TestPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    variant_id: uuid.UUID
    name: str
    created_by: str
    created_at: datetime


class TestRunCreate(BaseModel):
    business_id: str
    test_plan_id: uuid.UUID
    # Process-twin link (P1): the lot this inspection sampled.
    lot_id: uuid.UUID | None = None
    executed_at: datetime
    equipment_id: str | None = None
    environment: dict | None = None


class TestRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    test_plan_id: uuid.UUID
    # default None: idempotent_write replays the cached creation-time body,
    # and bodies cached before P1 have no lot_id (M8 lesson).
    lot_id: uuid.UUID | None = None
    executed_at: datetime
    equipment_id: str | None
    environment: dict | None
    raw_artifact_version_id: uuid.UUID | None
    created_by: str
    created_at: datetime


class MeasurementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    test_run_id: uuid.UUID
    x_value: float
    y_value: float
    x_unit: str
    y_unit: str


class CorrelationCreate(BaseModel):
    business_id: str
    simulation_run_id: uuid.UUID
    test_run_id: uuid.UUID


class CorrelationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    simulation_run_id: uuid.UUID
    test_run_id: uuid.UUID
    rmse: float
    mae: float
    max_error: float
    correlation_coefficient: float
    extrapolation_warning: bool
    overlap_x_min: float
    overlap_x_max: float
    created_by: str
    created_at: datetime
