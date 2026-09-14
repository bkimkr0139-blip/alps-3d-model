import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.model_canvas import (
    FindingSeverity,
    FindingStatus,
    ModelDomain,
    PortDirection,
    RelationProvenance,
    TrustState,
)


class EvidenceRef(BaseModel):
    kind: str = Field(pattern="^(simulation_run|test_run)$")
    business_id: str
    note: str | None = None


class ValidityBound(BaseModel):
    parameter: str
    unit: str | None = None
    min: float
    max: float


class CausalRelationCreate(BaseModel):
    business_id: str
    source_label: str
    source_domain: ModelDomain
    target_label: str
    target_domain: ModelDomain
    relation_type: str = "drives"
    mechanism: str | None = None
    evidence: list[EvidenceRef] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: RelationProvenance


class CausalRelationRead(CausalRelationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    variant_id: uuid.UUID
    created_by: str
    created_at: datetime


class ModelElementCreate(BaseModel):
    business_id: str
    name: str
    domain: ModelDomain
    equation_text: str | None = None
    description: str | None = None
    unit: str | None = None
    geometry_component_id: uuid.UUID | None = None
    position: dict | None = None


class ModelElementRead(ModelElementCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    variant_id: uuid.UUID
    created_by: str
    created_at: datetime


class ModelLinkCreate(BaseModel):
    business_id: str
    source_element_id: uuid.UUID
    target_element_id: uuid.UUID
    signal: str
    unit: str | None = None
    kind: str = "signal"
    # SM-01: required when endpoint units differ within one dimension
    unit_conversion: str | None = None


class ModelLinkRead(ModelLinkCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    variant_id: uuid.UUID
    created_by: str
    created_at: datetime


class ModelCardCreate(BaseModel):
    business_id: str
    title: str
    purpose: str
    equation_text: str | None = None
    assumptions: list[str] | None = None
    evidence: list[EvidenceRef] | None = None
    validity_envelope: list[ValidityBound] | None = None
    trust_state: TrustState = TrustState.DRAFT
    notes: str | None = None


class ModelCardRead(ModelCardCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    variant_id: uuid.UUID
    created_by: str
    created_at: datetime


# -- port contracts (지시서 ⑤ SM-03 lite) -------------------------------------


class PortContractCreate(BaseModel):
    business_id: str
    name: str
    direction: PortDirection
    quantity: str
    unit: str
    range_min: float | None = None
    range_max: float | None = None
    timing_semantics: str | None = None


class PortContractRead(PortContractCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    element_id: uuid.UUID
    created_by: str
    created_at: datetime


# -- rule-based model review (지시서 ⑥ AI-02 / MV-01..05 lite) -----------------


class ReviewFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    run_no: int
    category: str
    severity: FindingSeverity
    title: str
    detail: str | None = None
    evidence: list | None = None
    resolution: str | None = None
    status: FindingStatus
    provenance: RelationProvenance
    created_by: str
    created_at: datetime


class ReviewRunRead(BaseModel):
    variant_id: uuid.UUID
    run_no: int
    findings: list[ReviewFindingRead]


# -- uncertainty quantification (지시서 ⑦ SL-03 lite) --------------------------


class UQInput(BaseModel):
    name: str
    distribution: str = Field(pattern="^(uniform|triangular|normal)$")
    params: dict
    unit: str | None = None
    # Where the distribution came from — anything not measured must say
    # "assumed" (금지: no invented engineering numbers presented as fact).
    source: str = "assumed"


class UQTargetBand(BaseModel):
    min: float
    max: float
    unit: str | None = None
    source: str | None = None


class UQCreate(BaseModel):
    business_id: str
    model_type: str = Field(pattern="^(fs_dome|detent_torque|bridge_transfer)$")
    n_samples: int = Field(default=2000, ge=200, le=20000)
    seed: int = Field(default=42, ge=0)
    inputs: list[UQInput] = Field(min_length=1, max_length=8)
    target_band: UQTargetBand


class UQRead(UQCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    variant_id: uuid.UUID
    metric_name: str
    metric_unit: str
    results: dict
    created_by: str
    created_at: datetime
