import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.gate import GateDecisionType, GateStatus


class GateCreate(BaseModel):
    business_id: str
    variant_id: uuid.UUID
    baseline_id: uuid.UUID
    name: str
    required_roles: list[str] = ["reviewer_approver"]


class GateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    variant_id: uuid.UUID
    baseline_id: uuid.UUID
    name: str
    status: GateStatus
    required_roles: list[str]
    evidence_checklist: dict | None
    submitted_by: str | None
    submitted_at: datetime | None
    created_by: str
    created_at: datetime


class GateCommentCreate(BaseModel):
    business_id: str
    text: str


class GateCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    gate_id: uuid.UUID
    author: str
    text: str
    created_at: datetime


class GateDecisionCreate(BaseModel):
    business_id: str
    decision: GateDecisionType
    comment: str
    condition_expiry: datetime | None = None


class GateDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    gate_id: uuid.UUID
    decision: GateDecisionType
    actor: str
    actor_roles: list[str]
    comment: str
    condition_expiry: datetime | None
    decided_at: datetime
