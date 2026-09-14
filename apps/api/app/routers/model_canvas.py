from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.model_canvas import (
    CausalRelation,
    FindingSeverity,
    FindingStatus,
    ModelCard,
    ModelElement,
    ModelLink,
    ModelReviewFinding,
    PortContract,
    PortDirection,
    RelationProvenance,
    UQAnalysis,
)
from app.model_review import run_model_review
from app.models.product import Variant
from app.schemas.model_canvas import (
    CausalRelationCreate,
    CausalRelationRead,
    ModelCardCreate,
    ModelCardRead,
    ModelElementCreate,
    ModelElementRead,
    ModelLinkCreate,
    ModelLinkRead,
    PortContractCreate,
    PortContractRead,
    ReviewFindingRead,
    ReviewRunRead,
    UQCreate,
    UQRead,
)
from app.security import CurrentUser, require_role
from app.unitcheck import check_link_units
from app.uq import metric_for, run_lhs_monte_carlo
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["model-canvas"])

CAN_MANAGE_MODEL = require_role("system_architect")

# Impact-path strip order (left → right in the UI).
_DOMAIN_ORDER = {"mechanical": 0, "electrical": 1, "control": 2, "kansei": 3}


def _get_variant(db: Session, variant_id: str) -> Variant:
    variant = db.get(Variant, variant_id)
    if variant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")
    return variant


# -- causal relations / impact paths (지시서 ① DT-03 / AI-06) -----------------


@router.post(
    "/variants/{variant_id}/causal-relations",
    response_model=CausalRelationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_causal_relation(
    variant_id: str,
    body: CausalRelationCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_MODEL)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    _get_variant(db, variant_id)

    def compute() -> tuple[int, dict]:
        relation = CausalRelation(
            business_id=body.business_id,
            variant_id=variant_id,
            source_label=body.source_label,
            source_domain=body.source_domain,
            target_label=body.target_label,
            target_domain=body.target_domain,
            relation_type=body.relation_type,
            mechanism=body.mechanism,
            evidence=[e.model_dump(mode="json") for e in body.evidence] if body.evidence else None,
            confidence=body.confidence,
            provenance=body.provenance,
            created_by=user.username,
        )
        db.add(relation)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="causal_relation",
            entity_id=relation.id,
            correlation_id=correlation_id,
            payload={"business_id": relation.business_id, "variant_id": variant_id},
        )
        return status.HTTP_201_CREATED, CausalRelationRead.model_validate(relation).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/twins/{variant_id}/impact-paths")
def get_impact_paths(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    """Causal chain for the impact-path strip (§AI-06 lite). provenance rides
    on every edge — the UI renders AI-inferred edges distinctly and they may
    never back a Gate decision until a human approves them."""
    _get_variant(db, variant_id)
    relations = (
        db.query(CausalRelation)
        .filter_by(variant_id=variant_id)
        .order_by(CausalRelation.created_at)
        .all()
    )
    nodes: dict[tuple[str, str], dict] = {}
    edges = []
    for r in relations:
        nodes.setdefault(
            (r.source_label, r.source_domain.value),
            {"label": r.source_label, "domain": r.source_domain.value},
        )
        nodes.setdefault(
            (r.target_label, r.target_domain.value),
            {"label": r.target_label, "domain": r.target_domain.value},
        )
        edges.append(
            {
                "id": str(r.id),
                "business_id": r.business_id,
                "source": r.source_label,
                "source_domain": r.source_domain.value,
                "target": r.target_label,
                "target_domain": r.target_domain.value,
                "relation_type": r.relation_type,
                "mechanism": r.mechanism,
                "evidence": r.evidence or [],
                "confidence": r.confidence,
                "provenance": r.provenance.value,
            }
        )
    ordered = sorted(nodes.values(), key=lambda n: (_DOMAIN_ORDER.get(n["domain"], 9), n["label"]))
    return {"variant_id": variant_id, "nodes": ordered, "edges": edges}


# -- multi-domain model canvas (지시서 ② SM-01 / E02 lite) --------------------


@router.post(
    "/variants/{variant_id}/model-elements",
    response_model=ModelElementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_model_element(
    variant_id: str,
    body: ModelElementCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_MODEL)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    _get_variant(db, variant_id)

    def compute() -> tuple[int, dict]:
        element = ModelElement(
            business_id=body.business_id,
            variant_id=variant_id,
            name=body.name,
            domain=body.domain,
            equation_text=body.equation_text,
            description=body.description,
            unit=body.unit,
            geometry_component_id=body.geometry_component_id,
            position=body.position,
            created_by=user.username,
        )
        db.add(element)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="model_element",
            entity_id=element.id,
            correlation_id=correlation_id,
            payload={"business_id": element.business_id, "variant_id": variant_id},
        )
        return status.HTTP_201_CREATED, ModelElementRead.model_validate(element).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post(
    "/variants/{variant_id}/model-links",
    response_model=ModelLinkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_model_link(
    variant_id: str,
    body: ModelLinkCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_MODEL)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    _get_variant(db, variant_id)
    elements: dict[str, ModelElement] = {}
    for element_id in (body.source_element_id, body.target_element_id):
        element = db.get(ModelElement, element_id)
        if element is None or str(element.variant_id) != variant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"model element {element_id} not found")
        elements[str(element.id)] = element

    # SM-01/MV-02 — unit check against port contracts (fallback: element unit).
    # Runs before write: dimension conflicts and conversion-less mixed units
    # are rejected outright (422), so links that exist always carry checked units.
    src = elements[str(body.source_element_id)]
    dst = elements[str(body.target_element_id)]
    ports = (
        db.query(PortContract)
        .filter(PortContract.element_id.in_([src.id, dst.id]))
        .all()
    )
    src_out = next(
        (p for p in ports if p.element_id == src.id and p.direction in (PortDirection.OUT, PortDirection.INOUT)),
        None,
    )
    dst_in = next(
        (p for p in ports if p.element_id == dst.id and p.direction in (PortDirection.IN, PortDirection.INOUT)),
        None,
    )
    check = check_link_units(
        body.unit,
        src_out.unit if src_out else src.unit,
        dst_in.unit if dst_in else dst.unit,
        src.name,
        dst.name,
        has_conversion=bool(body.unit_conversion),
    )
    if check.level in ("error", "conversion_required"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, check.message)

    def compute() -> tuple[int, dict]:
        link = ModelLink(
            business_id=body.business_id,
            variant_id=variant_id,
            source_element_id=body.source_element_id,
            target_element_id=body.target_element_id,
            signal=body.signal,
            unit=body.unit,
            kind=body.kind,
            unit_conversion=body.unit_conversion,
            created_by=user.username,
        )
        db.add(link)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="model_link",
            entity_id=link.id,
            correlation_id=correlation_id,
            payload={"business_id": link.business_id, "variant_id": variant_id},
        )
        return status.HTTP_201_CREATED, ModelLinkRead.model_validate(link).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/twins/{variant_id}/system-model")
def get_system_model(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    """Blocks + flows for the Model Canvas. geometry_component_id is the
    §9.3 bidirectional link to the 3D part — the canvas and S04 highlight
    each other through it."""
    _get_variant(db, variant_id)
    elements = (
        db.query(ModelElement).filter_by(variant_id=variant_id).order_by(ModelElement.created_at).all()
    )
    links = db.query(ModelLink).filter_by(variant_id=variant_id).order_by(ModelLink.created_at).all()
    ports = (
        db.query(PortContract)
        .join(ModelElement, PortContract.element_id == ModelElement.id)
        .filter(ModelElement.variant_id == variant_id)
        .order_by(PortContract.created_at)
        .all()
    )
    return {
        "variant_id": variant_id,
        "elements": [ModelElementRead.model_validate(e).model_dump(mode="json") for e in elements],
        "links": [ModelLinkRead.model_validate(l).model_dump(mode="json") for l in links],
        "ports": [PortContractRead.model_validate(p).model_dump(mode="json") for p in ports],
    }


# -- model card (지시서 ④ TC-03 / E10 lite) -----------------------------------


@router.post(
    "/variants/{variant_id}/model-card",
    response_model=ModelCardRead,
    status_code=status.HTTP_201_CREATED,
)
def create_model_card(
    variant_id: str,
    body: ModelCardCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_MODEL)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    _get_variant(db, variant_id)

    def compute() -> tuple[int, dict]:
        # Inside compute(): on a reseed the Idempotency-Key match returns the
        # cached 201 before this runs — an existence check outside would 409
        # first and break idempotent replays.
        existing = db.query(ModelCard).filter_by(variant_id=variant_id).first()
        if existing is not None:
            return status.HTTP_409_CONFLICT, {"detail": "model card already exists for this variant"}
        card = ModelCard(
            business_id=body.business_id,
            variant_id=variant_id,
            title=body.title,
            purpose=body.purpose,
            equation_text=body.equation_text,
            assumptions=body.assumptions,
            evidence=[e.model_dump(mode="json") for e in body.evidence] if body.evidence else None,
            validity_envelope=[v.model_dump(mode="json") for v in body.validity_envelope]
            if body.validity_envelope
            else None,
            trust_state=body.trust_state,
            notes=body.notes,
            created_by=user.username,
        )
        db.add(card)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="model_card",
            entity_id=card.id,
            correlation_id=correlation_id,
            payload={"business_id": card.business_id, "variant_id": variant_id},
        )
        return status.HTTP_201_CREATED, ModelCardRead.model_validate(card).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/twins/{variant_id}/model-card", response_model=ModelCardRead | None)
def get_model_card(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    _get_variant(db, variant_id)
    return db.query(ModelCard).filter_by(variant_id=variant_id).first()


# -- port contracts (지시서 ⑤ SM-03 lite) -------------------------------------


@router.post(
    "/model-elements/{element_id}/ports",
    response_model=PortContractRead,
    status_code=status.HTTP_201_CREATED,
)
def create_port_contract(
    element_id: str,
    body: PortContractCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_MODEL)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    element = db.get(ModelElement, element_id)
    if element is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "model element not found")

    def compute() -> tuple[int, dict]:
        port = PortContract(
            business_id=body.business_id,
            element_id=element.id,
            name=body.name,
            direction=body.direction,
            quantity=body.quantity,
            unit=body.unit,
            range_min=body.range_min,
            range_max=body.range_max,
            timing_semantics=body.timing_semantics,
            created_by=user.username,
        )
        db.add(port)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="port_contract",
            entity_id=port.id,
            correlation_id=correlation_id,
            payload={"business_id": port.business_id, "element_id": str(element.id)},
        )
        return status.HTTP_201_CREATED, PortContractRead.model_validate(port).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


# -- rule-based model review (지시서 ⑥ AI-02 / MV-01..05 lite) -----------------


@router.post("/twins/{variant_id}/model-review", response_model=ReviewRunRead, status_code=status.HTTP_201_CREATED)
def run_review(variant_id: str, request: Request, db: Annotated[Session, Depends(get_db)],
               user: Annotated[CurrentUser, Depends(require_role("mechanical_engineer", "system_architect"))],
               correlation_id: Annotated[str, Depends(get_correlation_id)]):
    """Append-only review run: rule findings over stored entities. No
    Idempotency-Key replay cache — a re-POST intentionally produces a NEW
    run_no snapshot (the ledger appends, it never replays)."""
    _get_variant(db, variant_id)
    latest = (
        db.query(ModelReviewFinding.run_no)
        .filter(ModelReviewFinding.variant_id == variant_id)
        .order_by(ModelReviewFinding.run_no.desc())
        .first()
    )
    run_no = (latest[0] + 1) if latest else 1

    findings = run_model_review(db, variant_id)
    rows = []
    for i, f in enumerate(findings):
        row = ModelReviewFinding(
            business_id=f"MV-{variant_id[:8]}-R{run_no:02d}-{i:02d}",
            variant_id=variant_id,
            run_no=run_no,
            category=f["category"],
            severity=FindingSeverity(f["severity"]),
            title=f["title"],
            detail=f["detail"],
            evidence=f["evidence"],
            resolution=f["resolution"],
            status=FindingStatus.OPEN,
            created_by=user.username,
        )
        db.add(row)
        rows.append(row)
    # server_default gen_random_uuid() — flush so row.id exists for the audit trail
    db.flush()
    for row in rows:
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="model_review_finding",
            entity_id=row.id,
            correlation_id=correlation_id,
            payload={"business_id": row.business_id, "run_no": run_no, "category": row.category},
        )
    db.commit()
    return ReviewRunRead(
        variant_id=variant_id,
        run_no=run_no,
        findings=[ReviewFindingRead.model_validate(r) for r in rows],
    )


@router.get("/twins/{variant_id}/model-review", response_model=ReviewRunRead | None)
def get_latest_review(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    _get_variant(db, variant_id)
    latest = (
        db.query(ModelReviewFinding)
        .filter(ModelReviewFinding.variant_id == variant_id)
        .order_by(ModelReviewFinding.run_no.desc())
        .first()
    )
    if latest is None:
        return None
    rows = (
        db.query(ModelReviewFinding)
        .filter(ModelReviewFinding.variant_id == variant_id, ModelReviewFinding.run_no == latest.run_no)
        .order_by(ModelReviewFinding.created_at)
        .all()
    )
    return ReviewRunRead(
        variant_id=variant_id,
        run_no=latest.run_no,
        findings=[ReviewFindingRead.model_validate(r) for r in rows],
    )


# -- uncertainty quantification (지시서 ⑦ SL-03 lite) --------------------------


@router.post("/variants/{variant_id}/uq", response_model=UQRead, status_code=status.HTTP_201_CREATED)
def create_uq_analysis(
    variant_id: str,
    body: UQCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("mechanical_engineer", "system_architect"))],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    _get_variant(db, variant_id)

    def compute() -> tuple[int, dict]:
        metric_name, metric_unit = metric_for(body.model_type)
        try:
            results = run_lhs_monte_carlo(
                body.model_type,
                [i.model_dump() for i in body.inputs],
                body.n_samples,
                body.seed,
                body.target_band.model_dump(),
            )
        except (KeyError, ValueError) as exc:
            db.rollback()
            return status.HTTP_422_UNPROCESSABLE_ENTITY, {
                "detail": f"invalid UQ input: {exc}",
            }
        analysis = UQAnalysis(
            business_id=body.business_id,
            variant_id=variant_id,
            model_type=body.model_type,
            n_samples=body.n_samples,
            seed=body.seed,
            inputs=[i.model_dump(mode="json") for i in body.inputs],
            metric_name=metric_name,
            metric_unit=metric_unit,
            target_band=body.target_band.model_dump(mode="json"),
            results=results,
            created_by=user.username,
        )
        db.add(analysis)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="run",
            entity_type="uq_analysis",
            entity_id=analysis.id,
            correlation_id=correlation_id,
            payload={"business_id": analysis.business_id, "seed": body.seed, "n_samples": body.n_samples},
        )
        return status.HTTP_201_CREATED, UQRead.model_validate(analysis).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/twins/{variant_id}/uq", response_model=UQRead | None)
def get_latest_uq(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    _get_variant(db, variant_id)
    return (
        db.query(UQAnalysis)
        .filter(UQAnalysis.variant_id == variant_id)
        .order_by(UQAnalysis.created_at.desc())
        .first()
    )
