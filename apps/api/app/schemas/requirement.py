import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.requirement import (
    RequirementStatus,
    SafetyClass,
    TraceTargetType,
    VerificationMethod,
)


class RequirementCreate(BaseModel):
    business_id: str
    variant_id: uuid.UUID
    text: str
    source: str | None = None
    priority: str = "medium"
    verification_method: VerificationMethod
    safety_class: SafetyClass = SafetyClass.QM
    owner: str


class RequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    variant_id: uuid.UUID
    text: str
    source: str | None
    priority: str
    verification_method: VerificationMethod
    safety_class: SafetyClass
    owner: str
    status: RequirementStatus
    created_by: str
    created_at: datetime


class TraceLinkCreate(BaseModel):
    business_id: str
    target_type: TraceTargetType
    target_id: uuid.UUID


class TraceLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    requirement_id: uuid.UUID
    target_type: TraceTargetType
    target_id: uuid.UUID
    created_by: str
    created_at: datetime
