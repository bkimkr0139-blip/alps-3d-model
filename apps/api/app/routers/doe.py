"""AN-04 DOE / optimization (지시서 §7 AN-04, base-spec FR-06 lite): a
synchronous response-surface regression + ranked candidate comparison over
already-persisted ProcessRun parameters (`ProcessRun.actual[parameter]`) and
CTQ inspection data (same `_ctq_value` extraction as `/cavities/compare`).

No new DOE-design/experiment-plan machinery here — the regression runs over
process data that already exists (§AN-04 reuses P1's process_runs/검사
데이터). See `app/doe.py` for the compute (kept pure/DB-free, same split as
`app/correlation.py`), and AGENTS.md's "AN-04" section for the full scope
notes and deferred items (Bayesian Optimization, multi-objective Pareto)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.doe import candidate_grid, fit_response_surface, rank_candidates
from app.models.doe import DoeStudy
from app.models.process_twin import Lot, ProcessOperation, ProcessRun
from app.models.product import Variant
from app.models.test import TestRun
from app.routers.process_twin import _ctq_value
from app.schemas.doe import DoeStudyCreate, DoeStudyRead
from app.security import CurrentUser, require_role
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["doe"])

# Manufacturing engineering owns process-parameter/DOE work (§4); mechanical
# engineer/system architect can also run it, mirroring CAN_MANAGE_PROCESS in
# app/routers/process_twin.py (kept as a separate constant here on purpose —
# not imported — to avoid coupling this router's RBAC to edits elsewhere).
CAN_RUN_DOE = require_role("manufacturing_engineer", "mechanical_engineer", "system_architect")


def _gather_observations(
    db: Session, variant_id: uuid.UUID | str, operation_id: uuid.UUID | str, parameter: str, metric: str
) -> tuple[list[dict], str | None]:
    """Every ProcessRun for this operation, scoped to lots of this variant,
    that recorded `parameter` in `actual` AND has at least one inspection
    (TestRun) to derive a CTQ value from. Returns (observations, metric_unit)
    — metric_unit comes from the measurement rows themselves, never invented.
    A lot with more than one inspection run contributes the mean of its CTQ
    values (still real data, just averaged per lot)."""
    observations: list[dict] = []
    metric_unit: str | None = None

    runs = (
        db.query(ProcessRun)
        .join(Lot, ProcessRun.lot_id == Lot.id)
        .filter(Lot.variant_id == variant_id, ProcessRun.operation_id == operation_id)
        .all()
    )
    for run in runs:
        if not run.actual or parameter not in run.actual:
            continue
        value = run.actual[parameter]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue

        test_runs = db.query(TestRun).filter_by(lot_id=run.lot_id).all()
        ctq_values = []
        for tr in test_runs:
            v = _ctq_value(tr.measurements, metric)
            if v is None:
                continue
            ctq_values.append(v)
            if metric_unit is None and tr.measurements:
                metric_unit = tr.measurements[0].y_unit
        if not ctq_values:
            continue

        finding = next((f for f in (run.window_findings or []) if f.get("parameter") == parameter), None)
        observations.append(
            {
                "lot_business_id": run.lot.business_id,
                "process_run_business_id": run.business_id,
                "parameter_value": float(value),
                "ctq_value": sum(ctq_values) / len(ctq_values),
                "out_of_window": finding is not None,
                "window_findings": [finding] if finding else None,
            }
        )

    return observations, metric_unit


@router.post("/doe-studies", response_model=DoeStudyRead, status_code=status.HTTP_201_CREATED)
def create_doe_study(
    body: DoeStudyCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_RUN_DOE)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    if db.get(Variant, body.variant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")
    operation = db.get(ProcessOperation, body.operation_id)
    if operation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "process operation not found")

    observations, metric_unit = _gather_observations(
        db, body.variant_id, body.operation_id, body.parameter, body.metric
    )
    xs = [o["parameter_value"] for o in observations]
    ys = [o["ctq_value"] for o in observations]
    try:
        fit = fit_response_surface(xs, ys)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    window_bound = next((w for w in (operation.window or []) if w.get("parameter") == body.parameter), None)
    window_min = window_bound["min"] if window_bound else None
    window_max = window_bound["max"] if window_bound else None
    parameter_unit = window_bound.get("unit") if window_bound else None

    # Candidate settings: every distinct observed value (real data) plus an
    # evenly spaced grid across the approved process window (or the observed
    # range, if the operation has no declared window for this parameter).
    observed_xs = sorted(set(xs))
    grid_lo = window_min if window_min is not None else min(xs)
    grid_hi = window_max if window_max is not None else max(xs)
    grid_xs = candidate_grid(grid_lo, grid_hi, body.candidate_grid_size)

    seen = {round(x, 9) for x in observed_xs}
    candidates_in = [{"parameter_value": x, "source": "observed"} for x in observed_xs]
    candidates_in += [
        {"parameter_value": x, "source": "grid"} for x in grid_xs if round(x, 9) not in seen
    ]

    target = body.target_band
    ranked = rank_candidates(
        fit,
        candidates_in,
        window_min=window_min,
        window_max=window_max,
        target_min=target.min if target else None,
        target_max=target.max if target else None,
    )

    constraint_violations = [o for o in observations if o["out_of_window"]]

    def compute() -> tuple[int, dict]:
        study = DoeStudy(
            business_id=body.business_id,
            variant_id=body.variant_id,
            operation_id=body.operation_id,
            parameter=body.parameter,
            parameter_unit=parameter_unit,
            metric=body.metric,
            metric_unit=metric_unit,
            target_band=target.model_dump(mode="json") if target else None,
            observations=observations,
            fit=fit,
            candidates=ranked,
            constraint_violations=constraint_violations,
            created_by=user.username,
        )
        db.add(study)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="run",
            entity_type="doe_study",
            entity_id=study.id,
            correlation_id=correlation_id,
            payload={
                "business_id": study.business_id,
                "parameter": body.parameter,
                "metric": body.metric,
                "n_observations": fit["n_observations"],
            },
        )
        return status.HTTP_201_CREATED, DoeStudyRead.model_validate(study).model_dump(mode="json")

    result = idempotent_write(db, request=request, idempotency_key=idempotency_key, user=user, compute=compute)
    db.commit()
    return result


@router.get("/doe-studies/{study_id}", response_model=DoeStudyRead)
def get_doe_study(study_id: str, db: Annotated[Session, Depends(get_db)]):
    study = db.get(DoeStudy, study_id)
    if study is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "DOE study not found")
    return study


@router.get("/twins/{variant_id}/doe-studies", response_model=list[DoeStudyRead])
def list_doe_studies(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(DoeStudy)
        .filter(DoeStudy.variant_id == variant_id)
        .order_by(DoeStudy.created_at.desc())
        .all()
    )
