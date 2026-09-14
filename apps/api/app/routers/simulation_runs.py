from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.artifact import ArtifactVersion, ArtifactVersionStatus
from app.models.idempotency import IdempotencyRecord
from app.models.model_canvas import ModelCard
from app.models.product import Variant
from app.models.simulation import RunStatus, RunType, SimulationRun
from app.schemas.simulation import SimulationRunCreate, SimulationRunRead
from app.security import CurrentUser, require_role
from app.temporal_client import get_temporal_client
from app.write_support import get_correlation_id, get_idempotency_key, record_audit

router = APIRouter(prefix="/api/v1", tags=["simulation-runs"])

CAN_RUN_SIMULATION = require_role("mechanical_engineer", "electrical_asic_engineer", "system_architect")

# (workflow name, Temporal task queue) per run type — each worker process
# only registers the workflow(s)/activities for its own task queue.
_WORKFLOW_BY_RUN_TYPE = {
    RunType.CAD_CONVERT: ("ConvertStepToGltfWorkflow", "cad-converter"),
    RunType.SPICE_ANALYSIS: ("RunSpiceAnalysisWorkflow", "spice-worker"),
    RunType.MECH_MODEL: ("RunMechModelWorkflow", "mech-model"),
}


@router.post("/simulation-runs", response_model=SimulationRunRead, status_code=status.HTTP_201_CREATED)
async def create_simulation_run(
    body: SimulationRunCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_RUN_SIMULATION)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Deliberately not using `idempotent_write` (see AGENTS.md): starting the
    Temporal workflow is an async side effect that must fire exactly once, so
    this checks for a prior identical request BEFORE creating the DB row and
    only starts the workflow on the branch that actually creates one.
    """
    endpoint = request.scope["route"].path

    if idempotency_key:
        existing = (
            db.query(IdempotencyRecord)
            .filter_by(key=idempotency_key, endpoint=endpoint, actor=user.username)
            .one_or_none()
        )
        if existing is not None:
            return db.get(SimulationRun, existing.response_body["id"])

    if db.get(Variant, body.variant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")
    if body.run_type not in _WORKFLOW_BY_RUN_TYPE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported run_type: {body.run_type}")

    # MV-04 — block mech runs outside the model card's validity envelope.
    # A card-less variant is unaffected; out-of-envelope parameters return
    # 422 with every violated bound listed (no silent out-of-range prediction).
    if body.run_type == RunType.MECH_MODEL and body.parameters:
        card = (
            db.query(ModelCard)
            .filter_by(variant_id=body.variant_id)
            .first()
        )
        if card is not None and card.validity_envelope:
            violations = []
            for bound in card.validity_envelope:
                value = body.parameters.get(bound.get("parameter"))
                if isinstance(value, (int, float)) and not (
                    float(bound["min"]) <= float(value) <= float(bound["max"])
                ):
                    violations.append(
                        f"{bound['parameter']}={value} 가 유효 범위 "
                        f"[{bound['min']}, {bound['max']}] {bound.get('unit', '')}을 벗어납니다"
                    )
            if violations:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    {"detail": "parameters outside the model card validity envelope (MV-04)",
                     "violations": violations, "model_card": card.business_id},
                )

    if body.input_artifact_version_id is not None:
        input_version = db.get(ArtifactVersion, body.input_artifact_version_id)
        if input_version is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "input artifact version not found")
        if input_version.status != ArtifactVersionStatus.PROMOTED:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "input artifact version is not promoted yet")

    run = SimulationRun(
        business_id=body.business_id,
        variant_id=body.variant_id,
        run_type=body.run_type,
        status=RunStatus.QUEUED,
        input_artifact_version_id=body.input_artifact_version_id,
        parameters=body.parameters,
        created_by=user.username,
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"business_id '{body.business_id}' already exists") from exc

    workflow_id = f"{body.run_type.value}-{run.id}"
    run.temporal_workflow_id = workflow_id

    record_audit(
        db,
        user=user,
        action="create",
        entity_type="simulation_run",
        entity_id=run.id,
        correlation_id=correlation_id,
        payload={"run_type": body.run_type.value, "variant_id": str(body.variant_id)},
    )

    if idempotency_key:
        db.add(
            IdempotencyRecord(
                key=idempotency_key,
                endpoint=endpoint,
                actor=user.username,
                status_code=status.HTTP_201_CREATED,
                response_body={"id": str(run.id)},
            )
        )

    db.commit()
    db.refresh(run)

    workflow_name, task_queue = _WORKFLOW_BY_RUN_TYPE[body.run_type]
    temporal = await get_temporal_client()
    await temporal.start_workflow(
        workflow_name,
        args=[str(run.id)],
        id=workflow_id,
        task_queue=task_queue,
    )
    return run


@router.get("/simulation-runs/{run_id}", response_model=SimulationRunRead)
def get_simulation_run(run_id: str, db: Annotated[Session, Depends(get_db)]):
    run = db.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "simulation run not found")
    return run


@router.get("/variants/{variant_id}/simulation-runs", response_model=list[SimulationRunRead])
def list_simulation_runs(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(SimulationRun)
        .filter_by(variant_id=variant_id)
        .order_by(SimulationRun.created_at.desc())
        .all()
    )
