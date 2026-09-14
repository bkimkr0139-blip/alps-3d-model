from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.correlation import compute_correlation, extract_predicted_curve
from app.db import get_db
from app.models.simulation import RunStatus, SimulationRun
from app.models.test import CorrelationRecord, Measurement, TestRun
from app.schemas.test import CorrelationCreate, CorrelationRead
from app.security import CurrentUser, require_role
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["correlations"])

CAN_MANAGE_TEST = require_role("test_emc_engineer", "mechanical_engineer", "electrical_asic_engineer")


@router.post("/correlations", response_model=CorrelationRead, status_code=status.HTTP_201_CREATED)
def create_correlation(
    body: CorrelationCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_TEST)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    sim_run = db.get(SimulationRun, body.simulation_run_id)
    if sim_run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "simulation run not found")
    if sim_run.status != RunStatus.SUCCEEDED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "simulation run has not succeeded")

    test_run = db.get(TestRun, body.test_run_id)
    if test_run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test run not found")
    measurements = db.query(Measurement).filter_by(test_run_id=test_run.id).all()
    if not measurements:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "test run has no measurements uploaded yet")

    try:
        pred_x, pred_y, x_unit, y_unit = extract_predicted_curve(sim_run.metrics)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if any(m.x_unit != x_unit or m.y_unit != y_unit for m in measurements):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"measurements must be in {x_unit}/{y_unit} to match the predicted "
            f"curve's units (§5.3 unit normalization)",
        )

    try:
        meas_x = np.array([m.x_value for m in measurements])
        meas_y = np.array([m.y_value for m in measurements])
        result = compute_correlation(pred_x, pred_y, meas_x, meas_y)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    def compute() -> tuple[int, dict]:
        record = CorrelationRecord(
            business_id=body.business_id,
            simulation_run_id=sim_run.id,
            test_run_id=test_run.id,
            created_by=user.username,
            **result,
        )
        db.add(record)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="correlation_record",
            entity_id=record.id,
            correlation_id=correlation_id,
            payload=result,
        )
        return status.HTTP_201_CREATED, CorrelationRead.model_validate(record).model_dump(mode="json")

    resp = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return resp


@router.get("/correlations/{correlation_id}", response_model=CorrelationRead)
def get_correlation(correlation_id: str, db: Annotated[Session, Depends(get_db)]):
    record = db.get(CorrelationRecord, correlation_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "correlation record not found")
    return record


@router.get("/simulation-runs/{simulation_run_id}/correlations", response_model=list[CorrelationRead])
def list_correlations_for_run(simulation_run_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(CorrelationRecord).filter_by(simulation_run_id=simulation_run_id).all()


@router.get("/correlations/{correlation_id}/gap-analysis")
def get_gap_analysis(correlation_id: str, db: Annotated[Session, Depends(get_db)]):
    """Residual-cause candidates over stored correlation data (§AI-05 lite).

    Pure read-side computation on the stored predicted/measured curves —
    nothing is persisted, nothing is fed to an LLM, and the output is
    explicitly "확인 필요" candidates, never a verdict (§10.2).
    """
    record = db.get(CorrelationRecord, correlation_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "correlation record not found")
    sim_run = db.get(SimulationRun, record.simulation_run_id)
    test_run = db.get(TestRun, record.test_run_id)
    if sim_run is None or test_run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "correlation inputs missing")

    try:
        pred_x, pred_y, x_unit, y_unit = extract_predicted_curve(sim_run.metrics)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    measurements = (
        db.query(Measurement)
        .filter_by(test_run_id=test_run.id)
        .order_by(Measurement.x_value)
        .all()
    )
    if not measurements:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "test run has no measurements")

    meas_x = np.array([m.x_value for m in measurements])
    meas_y = np.array([m.y_value for m in measurements])
    overlap_min = max(pred_x.min(), meas_x.min())
    overlap_max = min(pred_x.max(), meas_x.max())
    mask = (pred_x >= overlap_min) & (pred_x <= overlap_max)
    eval_x = pred_x[mask]
    pred_at_x = pred_y[mask]
    meas_at_x = np.interp(eval_x, meas_x, meas_y)
    residuals = pred_at_x - meas_at_x  # predicted − measured

    n = len(residuals)
    mean_res = float(np.mean(residuals))
    sd_res = float(np.std(residuals, ddof=1)) if n > 1 else 0.0
    # slope of residuals over x: persistent x-dependent structure
    if n >= 2 and float(np.ptp(eval_x)) > 0:
        slope = float(np.polyfit(eval_x, residuals, 1)[0])
        span = float(np.ptp(eval_x))
    else:
        slope, span = 0.0, 0.0

    stats = {
        "n_points": int(n),
        "x_unit": x_unit,
        "y_unit": y_unit,
        "mean": mean_res,
        "sd": sd_res,
        "min": float(np.min(residuals)),
        "max": float(np.max(residuals)),
        "slope_per_x_unit": slope,
        "x_span": span,
    }

    candidates = []
    # offset-like: consistent bias independent of x (a perfectly constant
    # offset has sd ≈ 0, so the epsilon keeps the test meaningful)
    if abs(mean_res) > 2 * sd_res + 1e-12:
        candidates.append({
            "cause": "parameter_offset",
            "confidence": "check_required",
            "title": "일정 오프셋 형태의 잔차 — 파라미터 편차 가능성",
            "detail": (
                f"잔차 평균 {mean_res:.3f}{y_unit} 가 표준편차 {sd_res:.3f}{y_unit}의 2배를 넘습니다. "
                "모델 파라미터(예: 물성·치수)가 실측 대비 일정하게 치우쳤을 가능성이 있습니다."
            ),
            "evidence": [{"kind": "correlation_record", "business_id": record.business_id}],
        })
    # x-dependent trend: scale/structure issue
    if n >= 2 and span > 0 and abs(slope) * span > max(2 * sd_res, 1e-12):
        candidates.append({
            "cause": "scale_or_structure",
            "confidence": "check_required",
            "title": "입력에 따라 증가하는 잔차 — 스케일/구조 오차 가능성",
            "detail": (
                f"잔차 기울기 {slope:.4f}{y_unit}/{x_unit} 로 x에 따라 체계적으로 변합니다. "
                "선형 스케일 계수 미적합 또는 구조(형상) 단순화의 영향일 수 있습니다."
            ),
            "evidence": [{"kind": "correlation_record", "business_id": record.business_id}],
        })
    # noise-dominated: no structure — suspect test side or alignment
    noise_ratio = sd_res / (abs(mean_res) + abs(slope) * span + 1e-12)
    if noise_ratio > 2.0:
        candidates.append({
            "cause": "noise_or_alignment",
            "confidence": "check_required",
            "title": "잔차가 무작위 노이즈에 가까움 — 시험/정렬 확인 필요",
            "detail": (
                f"체계적 성분 대비 변동이 {noise_ratio:.1f}배 큽니다. 측정 노이즈, "
                "커서 정렬(x축 보간), 시험 셋업 반복성을 먼저 확인하세요."
            ),
            "evidence": [{"kind": "test_run", "business_id": test_run.business_id}],
        })
    if record.extrapolation_warning:
        candidates.append({
            "cause": "extrapolation",
            "confidence": "check_required",
            "title": "실측 커버 밖 예측 구간 포함 — 검증 범위 확인 필요",
            "detail": (
                f"실측이 x=[{record.overlap_x_min}, {record.overlap_x_max}] {x_unit}만 커버합니다. "
                "그 밖의 예측 구간은 검증된 것이 아니므로 상관 지표 해석에 주의하세요."
            ),
            "evidence": [{"kind": "correlation_record", "business_id": record.business_id}],
        })

    return {
        "correlation_id": correlation_id,
        "residuals": {
            "x": [float(v) for v in eval_x],
            "residual": [float(v) for v in residuals],
            "measured": [float(v) for v in meas_at_x],
            "predicted": [float(v) for v in pred_at_x],
        },
        "stats": stats,
        "candidates": candidates,
    }
