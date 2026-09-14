import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import IdentifiedMixin, ProvenanceMixin


class RelationProvenance(str, enum.Enum):
    """§AI-06 relation provenance. AI-inferred relations stay visually distinct
    in the UI and can never serve as Gate evidence until a human approves them."""

    IMPORTED = "imported"
    RULE_DERIVED = "rule_derived"
    AI_INFERRED = "ai_inferred"
    HUMAN_APPROVED = "human_approved"


class ModelDomain(str, enum.Enum):
    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    CONTROL = "control"
    KANSEI = "kansei"


class TrustState(str, enum.Enum):
    """§AI-03 model trust ladder: Draft → Verified → Validated for Purpose →
    Approved for Reuse → Retired. Promotions are human decisions only."""

    DRAFT = "draft"
    VERIFIED = "verified"
    VALIDATED_FOR_PURPOSE = "validated_for_purpose"
    APPROVED_FOR_REUSE = "approved_for_reuse"
    RETIRED = "retired"


class CausalRelation(Base, IdentifiedMixin, ProvenanceMixin):
    """One edge of a physical causal chain (§AI-06 ontology, lite).

    Nodes are domain-labelled labels ("Metal Dome stiffness"), not foreign
    keys — the same physical quantity can be referenced by several variants'
    chains without inventing an entity per mention. Evidence pins the claim to
    real SimulationRuns/TestRuns (business_ids), never to invented numbers.
    """

    __tablename__ = "causal_relations"

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("variants.id"), index=True)
    source_label: Mapped[str] = mapped_column(String(255))
    source_domain: Mapped[ModelDomain] = mapped_column(Enum(ModelDomain, name="model_domain"))
    target_label: Mapped[str] = mapped_column(String(255))
    target_domain: Mapped[ModelDomain] = mapped_column(Enum(ModelDomain, name="model_domain"))
    relation_type: Mapped[str] = mapped_column(String(64), default="drives")
    mechanism: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{kind: "simulation_run"|"test_run", business_id: "...", note: "..."}]
    evidence: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    provenance: Mapped[RelationProvenance] = mapped_column(
        Enum(RelationProvenance, name="relation_provenance")
    )


class ModelElement(Base, IdentifiedMixin, ProvenanceMixin):
    """A block on the multi-domain Model Canvas (§E02 lite).

    domain colours the block; equation_text renders inside it (display-only —
    the React canvas object is never the engineering ledger, §10.2);
    geometry_component_id is the bidirectional link to the 3D part (§9.3):
    clicking the block highlights the part in S04 and vice versa.
    """

    __tablename__ = "model_elements"

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("variants.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[ModelDomain] = mapped_column(Enum(ModelDomain, name="model_domain"))
    equation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    geometry_component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id"), nullable=True
    )
    # Canvas layout {x, y} in abstract units — the UI scales to fit.
    position: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    links_out: Mapped[list["ModelLink"]] = relationship(
        back_populates="source", foreign_keys="ModelLink.source_element_id"
    )
    links_in: Mapped[list["ModelLink"]] = relationship(
        back_populates="target", foreign_keys="ModelLink.target_element_id"
    )


class ModelLink(Base, IdentifiedMixin, ProvenanceMixin):
    """A directed signal/energy flow between two ModelElements (§E02)."""

    __tablename__ = "model_links"

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("variants.id"), index=True)
    source_element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_elements.id")
    )
    target_element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_elements.id")
    )
    signal: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="signal")
    # Required by SM-01 when a link connects same-dimension but different-unit
    # ports (e.g. mN·m → N·m): the explicit conversion statement, stored.
    unit_conversion: Mapped[str | None] = mapped_column(String(255), nullable=True)

    source: Mapped[ModelElement] = relationship(
        back_populates="links_out", foreign_keys=[source_element_id]
    )
    target: Mapped[ModelElement] = relationship(
        back_populates="links_in", foreign_keys=[target_element_id]
    )


class ModelCard(Base, IdentifiedMixin, ProvenanceMixin):
    """Model Card (§TC-03/E10 lite): what the model is for, what it assumes,
    which real runs back it, where it is valid — and its trust state.

    trust_state starts at DRAFT and only humans move it up (spec §10.2: no AI
    final approvals). Validity envelope blocks out-of-envelope predictions from
    being presented as normal results (지시서 금지 #4)."""

    __tablename__ = "model_cards"

    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("variants.id"), index=True, unique=True
    )
    title: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str] = mapped_column(Text)
    equation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [str, ...]
    assumptions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # [{kind, business_id, note}]
    evidence: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # [{parameter, unit, min, max}]
    validity_envelope: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    trust_state: Mapped[TrustState] = mapped_column(
        Enum(TrustState, name="trust_state"), default=TrustState.DRAFT
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PortDirection(str, enum.Enum):
    IN = "in"
    OUT = "out"
    INOUT = "inout"


class PortContract(Base, IdentifiedMixin, ProvenanceMixin):
    """Typed interface of a ModelElement (§SM-03 lite): name, direction,
    physical quantity, unit, allowed range and timing semantics. Link creation
    validates units against these contracts (§SM-01: same quantity in
    different units → warn + require an explicit conversion; different
    quantity → reject)."""

    __tablename__ = "port_contracts"

    element_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_elements.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    direction: Mapped[PortDirection] = mapped_column(Enum(PortDirection, name="port_direction"))
    # Physical quantity ("force", "displacement", "voltage", ...) — the
    # dimension identity used for compatibility checks.
    quantity: Mapped[str] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(32))
    range_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    # e.g. "continuous", "sampled@1kHz", "static"
    timing_semantics: Mapped[str | None] = mapped_column(String(64), nullable=True)


class FindingSeverity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class FindingStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    ACCEPTED = "accepted"


class ModelReviewFinding(Base, IdentifiedMixin, ProvenanceMixin):
    """One deterministic Model-Review finding (§AI-02 lite, MV-01..05).

    Findings are append-only per review run (run_no increments); a new review
    never edits or deletes earlier rows — the ledger, not the latest view, is
    the record. provenance is rule_derived: these are machine checks, and a
    human resolves or accepts each finding."""

    __tablename__ = "model_review_findings"

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("variants.id"), index=True)
    run_no: Mapped[int] = mapped_column(index=True)
    category: Mapped[str] = mapped_column(String(64))
    severity: Mapped[FindingSeverity] = mapped_column(Enum(FindingSeverity, name="finding_severity"))
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{kind, business_id, note}] — always real entities, never invented
    evidence: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[FindingStatus] = mapped_column(
        Enum(FindingStatus, name="finding_status"), default=FindingStatus.OPEN
    )
    provenance: Mapped[RelationProvenance] = mapped_column(
        Enum(RelationProvenance, name="relation_provenance"), default=RelationProvenance.RULE_DERIVED
    )


class UQAnalysis(Base, IdentifiedMixin, ProvenanceMixin):
    """Uncertainty quantification run (§SL-03 lite): seeded LHS Monte Carlo
    over the variant's prediction-model inputs, producing the output-metric
    distribution and the probability of violating a target band.

    Same seed + inputs ⇒ bit-identical results (MV-05 reproducibility). Input
    distributions carry a `source` label — anything not measured is stored as
    "assumed" and rendered as such in the UI (지시서 금지: no invented
    engineering numbers presented as fact)."""

    __tablename__ = "uq_analyses"

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("variants.id"), index=True)
    model_type: Mapped[str] = mapped_column(String(64))
    n_samples: Mapped[int] = mapped_column()
    seed: Mapped[int] = mapped_column()
    # [{name, distribution, params, unit, source}]
    inputs: Mapped[list] = mapped_column(JSONB)
    metric_name: Mapped[str] = mapped_column(String(64))
    metric_unit: Mapped[str] = mapped_column(String(32))
    # {min, max, unit, source}
    target_band: Mapped[dict] = mapped_column(JSONB)
    # {mean, sd, p05, p50, p95, hist: {bin_edges, counts}, violation_prob,
    #  violation_count, out_of_envelope: bool}
    results: Mapped[dict] = mapped_column(JSONB)
