"""Process monitoring endpoints (TACT 지시서 AN-03 관리도 + AI-03 이상 설명).

Read-only compute over the immutable P1 rows — no new tables, no writes:

- Control chart: limits are robust statistics (median ± 3·1.4826·MAD) of the
  measured stable process, never the spec band (AN-03: 관리한계와 규격한계
  혼동 금지). Points flagged out-of-window in P1 stay on the chart but are
  excluded from the limit basis — the exclusion reason points at the stored
  window_findings, which is AN-03's "제외 사유 감사 가능" without new state.
- Anomaly explanation: a fact sheet built from real rows goes to the local
  LLM; the answer is stored nowhere and labelled 조사 가설 (AI-03: 데이터가
  충분하지 않으면 원인 대신 조사 가설). The prompt forbids inventing numbers
  (AI-04), and the facts used ride along in the response for verification.
"""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.assistant.client import get_llm_client
from app.config import settings
from app.db import get_db
from app.models.process_twin import Cavity, Lot, ProcessOperation, ProcessRun
from app.schemas.process_monitoring import (
    AnomalyExplanation,
    ControlChart,
    ControlChartPoint,
    ProcessParameterInfo,
)
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/v1", tags=["process-monitoring"])

# Injected via Depends so tests can dependency-override it (same as the
# assistant router) — calling get_llm_client() directly would bypass that.
LlmDep = Annotated[OpenAI, Depends(get_llm_client)]

_MIN_BASIS = 3


def _series(db: Session, variant_id: str, parameter: str) -> list[dict]:
    """Chronological actual values for one parameter across a variant's lots.
    One point per process run that reports the parameter in its actual."""
    rows = (
        db.query(ProcessRun, Lot, ProcessOperation, Cavity)
        .join(Lot, ProcessRun.lot_id == Lot.id)
        .join(ProcessOperation, ProcessRun.operation_id == ProcessOperation.id)
        .join(Cavity, Lot.cavity_id == Cavity.id)
        .filter(Lot.variant_id == uuid.UUID(variant_id))
        .order_by(ProcessRun.started_at)
        .all()
    )
    points = []
    for run, lot, op, cavity in rows:
        actual = run.actual or {}
        value = actual.get(parameter)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        excluded = bool(run.out_of_window) and any(
            f.get("parameter") == parameter for f in (run.window_findings or [])
        )
        points.append(
            {
                "lot_business_id": lot.business_id,
                "process_run_business_id": run.business_id,
                "operation": op.name,
                "seq_no": op.seq_no,
                "cavity_label": cavity.label,
                "started_at": run.started_at,
                "value": float(value),
                "excluded_from_limits": excluded,
                "exclusion_reason": "out_of_window" if excluded else None,
            }
        )
    return points


def _median(values: list[float]) -> float:
    xs = sorted(values)
    n = len(xs)
    if n % 2:
        return xs[n // 2]
    return (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def _robust_sigma(values: list[float]) -> float:
    median = _median(values)
    mad = _median([abs(v - median) for v in values])
    return 1.4826 * mad


def _violations(values: list[float], cl: float, sigma: float) -> list[list[str]]:
    """AN-03 anomaly rules, each pointing at the points that trip it:
    beyond 3σ; 2 of 3 consecutive beyond 2σ on one side; a run of 7 on one
    side of the center line. Every rule uses the same +1e-12 guard as the
    M9/MAD rules so a perfect constant process isn't flagged."""
    hits: list[list[str]] = [[] for _ in values]

    for i, v in enumerate(values):
        if abs(v - cl) > 3 * sigma + 1e-12:
            hits[i].append("beyond_3_sigma")

    for i in range(len(values) - 2):
        window = values[i : i + 3]
        for side in (1.0, -1.0):
            if sum(1 for v in window if side * (v - cl) > 2 * sigma + 1e-12) >= 2:
                for j in range(i, i + 3):
                    if (
                        side * (values[j] - cl) > 2 * sigma + 1e-12
                        and "two_of_three_beyond_2_sigma" not in hits[j]
                    ):
                        hits[j].append("two_of_three_beyond_2_sigma")

    run = 0
    run_start = 0
    side = 0.0
    for i, v in enumerate(values):
        s = 1.0 if v > cl + 1e-12 else (-1.0 if v < cl - 1e-12 else 0.0)
        if s != 0 and s == side:
            run += 1
        else:
            run, side, run_start = (1, s, i) if s != 0 else (0, 0.0, i)
        if run >= 7:
            for j in range(run_start, i + 1):
                if "run_of_7_same_side" not in hits[j]:
                    hits[j].append("run_of_7_same_side")
    return hits


def _control_chart(db: Session, variant_id: str, parameter: str) -> ControlChart:
    points = _series(db, variant_id, parameter)
    if not points:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"no process-run data for parameter '{parameter}' on this variant",
        )

    unit = None
    operations = db.query(ProcessOperation).filter(ProcessOperation.window.isnot(None)).all()
    for operation in operations:
        for bound in operation.window or []:
            if bound.get("parameter") == parameter and bound.get("unit"):
                unit = bound["unit"]
                break
        if unit:
            break

    basis = [p["value"] for p in points if not p["excluded_from_limits"]]
    cl = sigma = lcl = ucl = None
    note = (
        "관리한계는 실측(윈도우 이탈 제외) 데이터의 중위값 ± 3σ(강건 추정)이며 "
        "규격한계가 아닙니다. 이상 신호는 원인 확정이 아니라 조사 우선순위입니다."
    )
    if len(basis) < _MIN_BASIS:
        note = (
            f"표본수 부족(기준 n={len(basis)} < {_MIN_BASIS}) — 관리한계를 산정하지 않았습니다. "
            + note
        )
    else:
        cl = _median(basis)
        sigma = _robust_sigma(basis)
        lcl, ucl = cl - 3 * sigma, cl + 3 * sigma
        hits = _violations([p["value"] for p in points], cl, sigma)
        rule_hits = sorted({r for h in hits for r in h})
        for p, h in zip(points, hits):
            p["violations"] = h

    return ControlChart(
        variant_id=uuid.UUID(variant_id),
        parameter=parameter,
        unit=unit,
        n_points=len(points),
        n_basis=len(basis),
        center_line=cl,
        sigma=sigma,
        lcl=lcl,
        ucl=ucl,
        points=[ControlChartPoint(**p) for p in points],
        rule_hits=rule_hits if cl is not None else [],
        note=note,
    )


@router.get("/twins/{variant_id}/process-parameters")
def list_process_parameters(variant_id: str, db: Annotated[Session, Depends(get_db)]):
    """Parameters available for charting: the union of the variant's
    operation windows that actually have data, with point counts."""
    rows = (
        db.query(ProcessRun, Lot, ProcessOperation)
        .join(Lot, ProcessRun.lot_id == Lot.id)
        .join(ProcessOperation, ProcessRun.operation_id == ProcessOperation.id)
        .filter(Lot.variant_id == uuid.UUID(variant_id))
        .all()
    )
    seen: dict[str, ProcessParameterInfo] = {}
    for run, lot, op in rows:
        window = op.window or []
        for bound in window:
            parameter = bound.get("parameter")
            if not parameter or isinstance((run.actual or {}).get(parameter), bool):
                continue
            if not isinstance((run.actual or {}).get(parameter), (int, float)):
                continue
            info = seen.get(parameter)
            if info is None:
                info = seen[parameter] = ProcessParameterInfo(
                    parameter=parameter,
                    unit=bound.get("unit"),
                    n_points=0,
                    operation_business_ids=[],
                )
            if op.business_id not in info.operation_business_ids:
                info.operation_business_ids.append(op.business_id)
            info.n_points += 1
    return sorted(
        [info.model_dump(mode="json") for info in seen.values()],
        key=lambda i: i["parameter"],
    )


@router.get("/twins/{variant_id}/control-chart")
def control_chart(
    variant_id: str,
    parameter: Annotated[str, Query(min_length=1)],
    db: Annotated[Session, Depends(get_db)],
):
    return _control_chart(db, variant_id, parameter).model_dump(mode="json")


class AnomalyExplanationBody(BaseModel):
    variant_id: uuid.UUID
    parameter: str


@router.post("/ai/anomaly-explanation")
def anomaly_explanation(
    body: AnomalyExplanationBody,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    client: LlmDep,
):
    """AI-03: summarize when the anomalies happened and which events
    (window exits, cavity spread, material lots) they line up with. The
    answer is an investigation hypothesis — never a confirmed cause — and
    the response carries every fact the model saw so it can be checked."""
    chart = _control_chart(db, str(body.variant_id), body.parameter)

    facts: list[str] = [
        f"파라미터 {body.parameter}: 관리점 {chart.n_points}개(한계 산정 기준 {chart.n_basis}개)",
    ]
    if chart.center_line is not None:
        facts.append(
            f"중심선 {chart.center_line:.4g}, 관리한계 [{chart.lcl:.4g}, {chart.ucl:.4g}] (실측 기반, 규격 아님)"
        )
    for p in chart.points:
        if p.violations:
            facts.append(
                f"관리도 이상: {p.lot_business_id} / {p.process_run_business_id} 값 {p.value:.4g} — 규칙 {', '.join(p.violations)}"
            )
        if p.excluded_from_limits:
            facts.append(f"윈도우 이탈(한계 산정 제외): {p.lot_business_id} 값 {p.value:.4g}")

    lots = (
        db.query(Lot)
        .filter(Lot.variant_id == body.variant_id)
        .order_by(Lot.produced_at)
        .all()
    )
    by_cavity: dict[str, list[float]] = {}
    for lot in lots:
        for p in chart.points:
            if p.lot_business_id == lot.business_id and not p.excluded_from_limits:
                by_cavity.setdefault(lot.cavity.label, []).append(p.value)
    for label, values in sorted(by_cavity.items()):
        if values:
            facts.append(f"Cavity별 {label} 중위값 {_median(values):.4g} (n={len(values)})")
    materials = sorted({lot.material_lot_id for lot in lots if lot.material_lot_id})
    if materials:
        facts.append("투입 원자재 Lot: " + ", ".join(materials))
    if len(facts) <= 1:
        facts.append("이상 신호 없음 — 관리한계 내 안정 구간")

    system = (
        "너는 제조 품질 공정의 분석 보조 AI다. 사용자가 준 사실 목록에 적힌 숫자와 사실만 "
        "근거로 서술하고, 어떤 숫자도 새로 만들거나 추정하지 않는다. 상관을 인과로 단정하지 "
        "말고, 결론은 원인 확정이 아니라 '조사 가설'과 확인이 필요한 항목으로 서술한다. "
        "3~6문장으로 한국어로 작성한다."
    )
    prompt = (
        f"아래는 공정 파라미터 '{body.parameter}'의 관리도 요약과 관련 사실이다.\n\n"
        + "\n".join(f"- {f}" for f in facts)
        + "\n\n이 사실들만 근거로 조사 가설을 작성하라. 이상 신호의 발생 시점과 관련 이벤트 "
        "(윈도우 이탈, Cavity 차이, 원자재 Lot)를 시간 순으로 연결하고, 우선 확인할 항목을 "
        "명시하라. 데이터가 부족한 부분은 부족하다고 말하라."
    )
    try:
        completion = client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            temperature=0.2,
        )
    except Exception as exc:  # connection/timeout — actionable message, not a stack trace
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"cannot reach the LLM at {settings.llm_base_url} (model {settings.llm_model}) — is it running? ({exc.__class__.__name__})",
        ) from exc
    hypothesis = (completion.choices[0].message.content or "").strip()
    if not hypothesis:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "LLM returned an empty hypothesis")

    return AnomalyExplanation(
        variant_id=body.variant_id,
        parameter=body.parameter,
        hypothesis=hypothesis,
        facts_used=facts,
        model=settings.llm_model,
        disclaimer=(
            "이 설명은 규칙 기반 관리도 결과에 대한 조사 가설이며 원인 확정·합격 판정이 아닙니다. "
            "최종 판정은 담당 엔지니어의 승인이 필요합니다."
        ),
        generated_at=datetime.now(timezone.utc),
    ).model_dump(mode="json")
