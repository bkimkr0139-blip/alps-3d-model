from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.component import Component
from app.models.product import Variant
from app.models.requirement import Requirement, RequirementTraceLink

router = APIRouter(prefix="/api/v1", tags=["twins"])


@router.get("/twins/{variant_id}/graph")
def get_twin_graph(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    """Requirement <-> Component/Artifact/SimulationRun/TestRun trace graph (§6.1 S03).

    Returned as {nodes, edges} so the frontend can feed it straight into
    React Flow without re-deriving structure client-side.
    """
    variant = db.get(Variant, variant_id)
    if variant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")

    requirements = db.query(Requirement).filter_by(variant_id=variant_id).all()
    components = db.query(Component).filter_by(variant_id=variant_id).all()
    req_ids = [r.id for r in requirements]
    links = (
        db.query(RequirementTraceLink).filter(RequirementTraceLink.requirement_id.in_(req_ids)).all()
        if req_ids
        else []
    )

    nodes = [
        {"id": str(r.id), "type": "requirement", "business_id": r.business_id, "label": r.text[:60]}
        for r in requirements
    ] + [
        {"id": str(c.id), "type": "component", "business_id": c.business_id, "label": c.name}
        for c in components
    ]
    edges = [
        {
            "id": str(link.id),
            "source": str(link.requirement_id),
            "target": str(link.target_id),
            "target_type": link.target_type.value,
        }
        for link in links
    ]
    return {"variant_id": str(variant.id), "nodes": nodes, "edges": edges}
