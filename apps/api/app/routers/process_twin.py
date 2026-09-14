"""TACT Product–Process Twin vertical slice (지시서 §PT-02/PT-03, AN-02/03,
AI-01, TS05, §9.2 lite): molds/cavities, process route with setpoint/actual
separation, lot genealogy, cavity comparison and rule-based root-cause
hypotheses.

Ground rules carried over from the AI-modeling 지시서 and re-stated here:
real production records are facts and never rejected (out-of-window runs are
FLAGGED, not refused — the MV-04 blocking rule is for simulations); every AI
candidate is a check-required investigation hint with evidence pointing at
real entities; nothing here ever writes to MES/QMS or approves anything.
"""

import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.process_twin import (
    Cavity,
    Defect,
    Lot,
    Mold,
    ProcessOperation,
    ProcessRun,
)
from app.models.product import Variant
from app.models.test import Measurement, TestRun
from app.schemas.process_twin import (
    CavityComparison,
    CavityCtqStats,
    CavityCreate,
    CavityRead,
    DefectCreate,
    DefectRead,
    GenealogyDefect,
    GenealogyProcessRun,
    GenealogyTestRun,
    LotCreate,
    LotGenealogy,
    LotRead,
    MoldCreate,
    MoldRead,
    ProcessOperationCreate,
    ProcessOperationRead,
    ProcessRunCreate,
    ProcessRunRead,
    RootCauseCandidate,
    RootCauseCause,
    RootCauseHypothesis,
)
from app.security import CurrentUser, require_role
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["process-twin"])

# Process/quality engineering owns molds, routes and lots; architects too.
CAN_MANAGE_PROCESS = require_role("mechanical_engineer", "system_architect")


def _flush_conflict(e: IntegrityError, business_id: str) -> tuple[int, dict]:
    db.rollback()
    return status.HTTP_409_CONFLICT, {"detail": f"business_id '{business_id}' already exists"}


def _evaluate_window(window: list[dict] | None, actual: dict | None) -> tuple[bool, list[dict]]:
    """Which actual parameters left the approved window. Returns
    (out_of_window, findings) — a *flag*, never a rejection."""
    if not window or not actual:
        return False, []
    findings = []
    for bound in window:
        value = actual.get(bound.get("parameter", ""))
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value < bound["min"] or value > bound["max"]:
            findings.append(
                {
                    "parameter": bound.get("parameter"),
                    "actual": value,
                    "min": bound["min"],
                    "max": bound["max"],
                    "unit": bound.get("unit"),
                }
            )
    return bool(findings), findings


# -- molds / cavities (§PT-02) --------------------------------------------------


@router.post("/molds", response_model=MoldRead, status_code=status.HTTP_201_CREATED)
def create_mold(
    body: MoldCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_PROCESS)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    def compute() -> tuple[int, dict]:
        mold = Mold(
            business_id=body.business_id,
            name=body.name,
            tool_revision=body.tool_revision,
            process=body.process,
            notes=body.notes,
            created_by=user.username,
        )
        db.add(mold)
        try:
            db.flush()
        except IntegrityError as exc:
            return _flush_conflict(exc, body.business_id)
        record_audit(
            db, user=user, action="create", entity_type="mold", entity_id=mold.id,
            correlation_id=correlation_id, payload={"business_id": mold.business_id},
        )
        return status.HTTP_201_CREATED, MoldRead.model_validate(mold).model_dump(mode="json")

    result = idempotent_write(db, request=request, idempotency_key=idempotency_key, user=user, compute=compute)
    db.commit()
    return result


@router.get("/molds", response_model=list[MoldRead])
def list_molds(db: Annotated[Session, Depends(get_db)]):
    return db.query(Mold).order_by(Mold.business_id).all()


@router.post("/molds/{mold_id}/cavities", response_model=CavityRead, status_code=status.HTTP_201_CREATED)
def create_cavity(
    mold_id: str,
    body: CavityCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_PROCESS)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    if db.get(Mold, mold_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "mold not found")

    def compute() -> tuple[int, dict]:
        cavity = Cavity(
            business_id=body.business_id,
            mold_id=mold_id,
            cavity_no=body.cavity_no,
            label=body.label,
            notes=body.notes,
            created_by=user.username,
        )
        db.add(cavity)
        try:
            db.flush()
        except IntegrityError as exc:
            return _flush_conflict(exc, body.business_id)
        record_audit(
            db, user=user, action="create", entity_type="cavity", entity_id=cavity.id,
            correlation_id=correlation_id,
            payload={"business_id": cavity.business_id, "mold_id": str(mold_id)},
        )
        return status.HTTP_201_CREATED, CavityRead.model_validate(cavity).model_dump(mode="json")

    result = idempotent_write(db, request=request, idempotency_key=idempotency_key, user=user, compute=compute)
    db.commit()
    return result


# -- process route (§PT-03) ------------------------------------------------------


@router.post("/process-operations", response_model=ProcessOperationRead, status_code=status.HTTP_201_CREATED)
def create_operation(
    body: ProcessOperationCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_PROCESS)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    for bound in body.window or []:
        if bound.min >= bound.max:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"window for '{bound.parameter}': min must be < max",
            )

    def compute() -> tuple[int, dict]:
        operation = ProcessOperation(
            business_id=body.business_id,
            name=body.name,
            seq_no=body.seq_no,
            equipment=body.equipment,
            description=body.description,
            window=[w.model_dump(mode="json") for w in body.window] if body.window else None,
            created_by=user.username,
        )
        db.add(operation)
        try:
            db.flush()
        except IntegrityError as exc:
            return _flush_conflict(exc, body.business_id)
        record_audit(
            db, user=user, action="create", entity_type="process_operation", entity_id=operation.id,
            correlation_id=correlation_id, payload={"business_id": operation.business_id},
        )
        return status.HTTP_201_CREATED, ProcessOperationRead.model_validate(operation).model_dump(mode="json")

    result = idempotent_write(db, request=request, idempotency_key=idempotency_key, user=user, compute=compute)
    db.commit()
    return result


@router.get("/process-operations", response_model=list[ProcessOperationRead])
def list_operations(db: Annotated[Session, Depends(get_db)]):
    return db.query(ProcessOperation).order_by(ProcessOperation.seq_no).all()


# -- lots (§6.3 Production) ------------------------------------------------------


@router.post("/lots", response_model=LotRead, status_code=status.HTTP_201_CREATED)
def create_lot(
    body: LotCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_PROCESS)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    if db.get(Variant, body.variant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")
    mold = db.get(Mold, body.mold_id)
    if mold is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "mold not found")
    cavity = db.get(Cavity, body.cavity_id)
    if cavity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cavity not found")
    if cavity.mold_id != mold.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "cavity does not belong to this mold")

    def compute() -> tuple[int, dict]:
        lot = Lot(
            **body.model_dump(), created_by=user.username,
        )
        db.add(lot)
        try:
            db.flush()
        except IntegrityError as exc:
            return _flush_conflict(exc, body.business_id)
        record_audit(
            db, user=user, action="create", entity_type="lot", entity_id=lot.id,
            correlation_id=correlation_id,
            payload={"business_id": lot.business_id, "cavity_id": str(lot.cavity_id)},
        )
        return status.HTTP_201_CREATED, LotRead.model_validate(lot).model_dump(mode="json")

    result = idempotent_write(db, request=request, idempotency_key=idempotency_key, user=user, compute=compute)
    db.commit()
    return result


class LotCardRead(LotRead):
    cavity_label: str
    defect_count: int
    out_of_window_runs: int


@router.get("/twins/{variant_id}/lots", response_model=list[LotCardRead])
def list_variant_lots(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    """Lot cards for the Process Twin screen: cavity label + defect and
    out-of-window counters computed server-side so the table renders one row
    per lot without N+1 requests."""
    lots = db.query(Lot).filter_by(variant_id=variant_id).order_by(Lot.produced_at).all()
    cards = []
    for lot in lots:
        card = LotRead.model_validate(lot).model_dump(mode="json")
        card["cavity_label"] = lot.cavity.label
        card["defect_count"] = len(lot.defects)
        card["out_of_window_runs"] = sum(1 for r in lot.process_runs if r.out_of_window)
        cards.append(card)
    return cards


@router.get("/lots/{lot_id}/genealogy", response_model=LotGenealogy)
def get_lot_genealogy(lot_id: str, db: Annotated[Session, Depends(get_db)]):
    """양방향 계보 (AC-02): one lot → mold/cavity, process runs (setpoint vs
    actual), inspections and defects. Read-only — the genealogy is derived
    from immutable rows each time, never cached into a rewriteable blob."""
    lot = db.get(Lot, lot_id)
    if lot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lot not found")

    process_runs = [
        GenealogyProcessRun(
            business_id=run.business_id,
            operation=run.operation.name,
            operation_business_id=run.operation.business_id,
            seq_no=run.operation.seq_no,
            equipment=run.operation.equipment,
            setpoint=run.setpoint,
            actual=run.actual,
            out_of_window=run.out_of_window,
            window_findings=run.window_findings,
            started_at=run.started_at,
        )
        for run in sorted(lot.process_runs, key=lambda r: r.operation.seq_no)
    ]
    test_runs = [
        GenealogyTestRun(
            id=tr.id,
            business_id=tr.business_id,
            executed_at=tr.executed_at,
            measurement_count=len(tr.measurements),
            y_unit=tr.measurements[0].y_unit if tr.measurements else None,
        )
        for tr in db.query(TestRun).filter_by(lot_id=lot.id).order_by(TestRun.executed_at).all()
    ]
    defects = [
        GenealogyDefect(
            business_id=d.business_id,
            defect_class=d.defect_class,
            severity=d.severity,
            quantity=d.quantity,
            note=d.note,
        )
        for d in lot.defects
    ]
    return LotGenealogy(
        lot=LotRead.model_validate(lot),
        mold=MoldRead.model_validate(lot.cavity.mold),
        cavity=CavityRead.model_validate(lot.cavity),
        process_runs=process_runs,
        test_runs=test_runs,
        defects=defects,
    )


# -- process runs + defects ------------------------------------------------------


@router.post("/process-runs", response_model=ProcessRunRead, status_code=status.HTTP_201_CREATED)
def create_process_run(
    body: ProcessRunCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_PROCESS)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    lot = db.get(Lot, body.lot_id)
    if lot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lot not found")
    operation = db.get(ProcessOperation, body.operation_id)
    if operation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "process operation not found")

    out_of_window, findings = _evaluate_window(operation.window, body.actual)

    def compute() -> tuple[int, dict]:
        run = ProcessRun(
            business_id=body.business_id,
            lot_id=body.lot_id,
            operation_id=body.operation_id,
            setpoint=body.setpoint,
            actual=body.actual,
            started_at=body.started_at,
            operator=body.operator,
            out_of_window=out_of_window,
            window_findings=findings or None,
            created_by=user.username,
        )
        db.add(run)
        try:
            db.flush()
        except IntegrityError as exc:
            return _flush_conflict(exc, body.business_id)
        record_audit(
            db, user=user, action="create", entity_type="process_run", entity_id=run.id,
            correlation_id=correlation_id,
            payload={"business_id": run.business_id, "out_of_window": out_of_window},
        )
        return status.HTTP_201_CREATED, ProcessRunRead.model_validate(run).model_dump(mode="json")

    result = idempotent_write(db, request=request, idempotency_key=idempotency_key, user=user, compute=compute)
    db.commit()
    return result


@router.post("/defects", response_model=DefectRead, status_code=status.HTTP_201_CREATED)
def create_defect(
    body: DefectCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_PROCESS)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    if db.get(Lot, body.lot_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lot not found")

    def compute() -> tuple[int, dict]:
        defect = Defect(**body.model_dump(), created_by=user.username)
        db.add(defect)
        try:
            db.flush()
        except IntegrityError as exc:
            return _flush_conflict(exc, body.business_id)
        record_audit(
            db, user=user, action="create", entity_type="defect", entity_id=defect.id,
            correlation_id=correlation_id,
            payload={"business_id": defect.business_id, "defect_class": defect.defect_class},
        )
        return status.HTTP_201_CREATED, DefectRead.model_validate(defect).model_dump(mode="json")

    result = idempotent_write(db, request=request, idempotency_key=idempotency_key, user=user, compute=compute)
    db.commit()
    return result


# -- cavity comparison (§AN-02 / AC-03, lite) ------------------------------------


def _ctq_value(measurements: list[Measurement], metric: str) -> float | None:
    """CTQ of one inspection: peak (= max y, e.g. 작동력 peak) or mean of the
    measured curve."""
    if not measurements:
        return None
    ys = [m.y_value for m in measurements]
    if metric == "mean":
        return sum(ys) / len(ys)
    return max(ys)


def _cavity_ctq_values(db: Session, variant_id: str, metric: str) -> dict[str, list[float]]:
    """variant의 Lot들을 Cavity별로 모아 검사값(검사 run당 CTQ 1개) 리스트."""
    by_cavity: dict[str, list[float]] = {}
    lots = db.query(Lot).filter_by(variant_id=variant_id).all()
    for lot in lots:
        for tr in db.query(TestRun).filter_by(lot_id=lot.id).all():
            value = _ctq_value(tr.measurements, metric)
            if value is None:
                continue
            by_cavity.setdefault(str(lot.cavity_id), []).append(value)
    return by_cavity


def _stats(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, None
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return mean, math.sqrt(variance)


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n % 2:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _mad(values: list[float]) -> float:
    """Median absolute deviation — robust to the one-off outliers that cavity
    mean/sd would chase (AN-02: 반복되는 편차와 일시 이상을 구분)."""
    if not values:
        return 0.0
    med = _median(values)
    return _median([abs(v - med) for v in values])


# σ-equivalent of the MAD under normality (1.4826 = 1/Φ⁻¹(3/4)).
_MAD_SIGMA = 1.4826


@router.get("/cavities/compare", response_model=CavityComparison)
def compare_cavities(
    variant_id: str,
    db: Annotated[Session, Depends(get_db)],
    metric: Annotated[str, Query(pattern="^(peak|mean)$")] = "peak",
    spec_lsl: float | None = None,
    spec_usl: float | None = None,
):
    """Cavity별 CTQ 분포 비교 (AN-02): mean/sd per cavity, optional Cp/Cpk
    against supplied spec limits (AN-03 — spec limits are customer-provided,
    never invented here), and a drift hint when cavity means separate by more
    than 2·sd. The drift hint is a check-required investigation priority."""
    cavity_rows = db.query(Cavity).order_by(Cavity.cavity_no).all()
    labels = {str(c.id): c.label for c in cavity_rows}
    by_cavity = _cavity_ctq_values(db, variant_id, metric)

    stats: list[CavityCtqStats] = []
    for cavity_id, values in by_cavity.items():
        mean, sd = _stats(values)
        cp = cpk = None
        if sd is not None and sd > 0 and spec_lsl is not None and spec_usl is not None:
            cp = (spec_usl - spec_lsl) / (6.0 * sd)
            cpk = min(spec_usl - mean, mean - spec_lsl) / (3.0 * sd)
        stats.append(
            CavityCtqStats(
                cavity_id=cavity_id,
                cavity_label=labels.get(cavity_id, cavity_id),
                lot_count=len(values),
                n_values=len(values),
                mean=mean,
                sd=sd,
                cp=cp,
                cpk=cpk,
            )
        )
    stats.sort(key=lambda s: s.cavity_label)

    drift = False
    note = None
    # Robust drift hint: median separation judged against each cavity's MAD, so
    # a single outlier lot inflates neither side's spread (AN-02).
    by_cavity_raw = list(by_cavity.values())
    if len([v for v in by_cavity_raw if v]) >= 2:
        medians = {cid: _median(vals) for cid, vals in by_cavity.items() if vals}
        mads = {cid: _mad(vals) for cid, vals in by_cavity.items() if vals}
        spread = max(medians.values()) - min(medians.values())
        robust_sd = max((_MAD_SIGMA * mads[cid] for cid in medians), default=0.0)
        if spread > 2.0 * robust_sd + 1e-12:
            drift = True
            note = (
                "Cavity 중심(중앙값) 차이가 데이터 산포의 2배를 넘습니다 — 재현 여부를 확인할 필요가 있습니다 "
                "(원인 확정이 아니라 조사 우선순위)."
            )
    else:
        note = "Cavity 비교에는 Cavity별 2개 이상의 검사값이 필요합니다."

    return CavityComparison(
        variant_id=variant_id, metric=metric,
        unit="", cavities=stats, drift_suspected=drift, check_note=note,
    )


# -- rule-based root-cause hypotheses (§AI-01 lite) ------------------------------


@router.post("/ai/root-cause-hypotheses", response_model=RootCauseHypothesis)
def root_cause_hypotheses(
    body: dict,
    db: Annotated[Session, Depends(get_db)],
):
    """근거 기반 원인 후보 (AI-01 lite): deterministic rules over the lot's
    own records. Every candidate is confidence="check_required" and carries
    evidence pointing at real entities — the API proposes what to investigate,
    it never settles a cause (AI-04). Read-only over immutable rows, hence no
    idempotency wrapper and no audit row (nothing is written)."""
    lot_id = body.get("lot_id")
    lot = db.get(Lot, lot_id or "")
    if lot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lot not found")

    candidates: list[RootCauseCandidate] = []

    # Rule 1 — any process run recorded outside its approved window.
    for run in lot.process_runs:
        if not run.out_of_window:
            continue
        params = ", ".join(
            f"{f['parameter']}={f['actual']} ({f['min']}–{f['max']}{f.get('unit') or ''})"
            for f in (run.window_findings or [])
        )
        candidates.append(
            RootCauseCandidate(
                cause=RootCauseCause.PROCESS_OUT_OF_WINDOW,
                title=f"{run.operation.name} 공정 윈도우 이탈",
                detail=(
                    f"이 Lot의 {run.operation.name} 실측값이 승인 윈도우를 벗어났습니다 ({params}). "
                    f"공정조건과 품질특성의 관련성을 확인하세요."
                ),
                evidence=[{
                    "kind": "process_run",
                    "business_id": run.business_id,
                    "note": f"operation={run.operation.business_id}",
                }],
            )
        )

    # Rule 2 — this lot's inspections sit away from the OTHER cavities'
    # distribution (robust: judged against median/MAD, not a mean that a
    # single outlier would drag).
    own_values = [
        v
        for tr in db.query(TestRun).filter_by(lot_id=lot.id).all()
        if (v := _ctq_value(tr.measurements, "peak")) is not None
    ]
    other_values = [
        v
        for cid, vals in _cavity_ctq_values(db, str(lot.variant_id), "peak").items()
        if cid != str(lot.cavity_id)
        for v in vals
    ]
    if own_values and other_values:
        other_med = _median(other_values)
        dev = _median(own_values) - other_med
        limit = 3.0 * _MAD_SIGMA * _mad(other_values) + 1e-12
        if abs(dev) > limit:
            direction = "높게" if dev > 0 else "낮게"
            candidates.append(
                RootCauseCandidate(
                    cause=RootCauseCause.CAVITY_BIAS,
                    title=f"Cavity {lot.cavity.label} 편차 의심",
                    detail=(
                        f"이 Lot의 검사값이 같은 금형의 다른 Cavity 분포 대비 유의하게 {direction} 나옵니다 "
                        f"(Δ={dev:.2f}, 한계≈{limit:.2f}). Cavity 치수·마모·보전 이력을 확인하세요."
                    ),
                    evidence=[
                        {"kind": "lot", "business_id": lot.business_id, "note": f"median={_median(own_values):.3f}"},
                        {"kind": "cavity", "business_id": lot.cavity.business_id, "note": f"other_median={other_med:.3f}"},
                    ],
                )
            )

    # Rule 3 — the same material lot produced other defective lots.
    if lot.material_lot_id:
        related = (
            db.query(Defect)
            .join(Lot, Defect.lot_id == Lot.id)
            .filter(Lot.material_lot_id == lot.material_lot_id, Lot.id != lot.id)
            .all()
        )
        if related:
            candidates.append(
                RootCauseCandidate(
                    cause=RootCauseCause.MATERIAL_LOT,
                    title=f"원자재 Lot {lot.material_lot_id} 공통성 의심",
                    detail=(
                        f"동일 원자재 Lot를 사용한 다른 Lot에서도 불량이 기록되어 있습니다 "
                        f"({len(related)}건). 자재 검사성적서와 공급이력을 확인하세요."
                    ),
                    evidence=[
                        {"kind": "lot", "business_id": d.lot.business_id, "note": f"defect={d.defect_class}"}
                        for d in related
                    ],
                )
            )

    # Rule 4 — not enough inspection data to say anything at all.
    inspection_count = (
        db.query(TestRun).filter_by(lot_id=lot.id).count()
    )
    if inspection_count == 0:
        candidates.append(
            RootCauseCandidate(
                cause=RootCauseCause.INSUFFICIENT_DATA,
                title="검사 데이터 부족",
                detail="이 Lot에는 업로드된 검사 결과가 없습니다 — 원인 판별 전 검사 데이터를 먼저 수집하세요.",
                evidence=[{"kind": "lot", "business_id": lot.business_id, "note": "test_runs=0"}],
            )
        )

    return RootCauseHypothesis(
        lot_id=lot.id,
        lot_business_id=lot.business_id,
        candidates=candidates,
        disclaimer=(
            "모든 후보는 확인 필요(조사 우선순위)이며 원인 확정이 아닙니다. "
            "최종 판정은 담당 엔지니어의 승인이 필요합니다."
        ),
    )
