"""Schemas for the Defect → FailureAnalysis → CAPA workflow (HANDOFF §5 item
4). Follows the exact `*Create`/`*Read` split used throughout
`schemas/gate.py` and `schemas/process_twin.py`."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.fa_capa import CapaActionType, CapaDecisionType, CapaEventType, CapaStatus


class EvidenceRef(BaseModel):
    """Same shape as `RootCauseCandidate.evidence` entries — every claim
    pins a real entity, never a bare assertion."""

    kind: str
    business_id: str
    note: str | None = None


class FailureAnalysisCreate(BaseModel):
    business_id: str
    method: str
    findings: str
    analyst: str
    analyzed_at: datetime
    root_cause: str | None = None
    root_cause_confirmed: bool = False
    evidence: list[EvidenceRef] | None = None


class FailureAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    defect_id: uuid.UUID
    method: str
    findings: str
    analyst: str
    analyzed_at: datetime
    root_cause: str | None
    root_cause_confirmed: bool
    evidence: list[dict] | None
    created_by: str
    created_at: datetime


class CapaCreate(BaseModel):
    business_id: str
    title: str
    capa_type: CapaActionType
    description: str
    owner: str
    due_date: datetime | None = None


class CapaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    failure_analysis_id: uuid.UUID
    title: str
    capa_type: CapaActionType
    description: str
    owner: str
    due_date: datetime | None
    status: CapaStatus
    submitted_by: str | None
    submitted_at: datetime | None
    verification_test_run_id: uuid.UUID | None
    verification_note: str | None
    closed_at: datetime | None
    created_by: str
    created_at: datetime


class CapaSubmitRequest(BaseModel):
    business_id: str
    comment: str | None = None


class CapaDecisionRequest(BaseModel):
    business_id: str
    decision: CapaDecisionType
    comment: str


class CapaImplementRequest(BaseModel):
    business_id: str
    comment: str | None = None


class CapaVerifyRequest(BaseModel):
    business_id: str
    test_run_id: uuid.UUID
    comment: str | None = None


class CapaCloseRequest(BaseModel):
    business_id: str
    comment: str | None = None


class CapaEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    capa_id: uuid.UUID
    event_type: CapaEventType
    actor: str
    actor_roles: list[str]
    comment: str | None
    evidence: dict | None
    occurred_at: datetime
