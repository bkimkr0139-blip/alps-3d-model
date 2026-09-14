"""Deterministic Model-Review checks (§AI-02 lite, §14.1 MV-01..05).

Every check is a rule over stored entities — no LLM, no invented numbers;
each finding cites the business_ids it inspected. Findings are grouped into
runs (run_no increments per POST): append-only, a new run never edits the
previous one. A human resolves/accepts each finding; nothing here changes
gates or trust states.
"""

from sqlalchemy.orm import Session

from app.models.model_canvas import (
    CausalRelation,
    ModelCard,
    ModelElement,
    ModelLink,
    PortContract,
    PortDirection,
    TrustState,
)
from app.models.simulation import SimulationRun
from app.models.test import CorrelationRecord
from app.unitcheck import check_link_units

# trust states at which measured validation evidence must exist
_VALIDATED_STATES = {TrustState.VERIFIED, TrustState.VALIDATED_FOR_PURPOSE, TrustState.APPROVED_FOR_REUSE}


def _finding(category: str, severity: str, title: str, detail: str | None,
             evidence: list[dict] | None, resolution: str | None) -> dict:
    return {
        "category": category,
        "severity": severity,
        "title": title,
        "detail": detail,
        "evidence": evidence or [],
        "resolution": resolution,
    }


def run_model_review(db: Session, variant_id: str) -> list[dict]:
    findings: list[dict] = []

    elements = db.query(ModelElement).filter_by(variant_id=variant_id).all()
    links = db.query(ModelLink).filter_by(variant_id=variant_id).all()
    ports = db.query(PortContract).join(ModelElement, PortContract.element_id == ModelElement.id).filter(
        ModelElement.variant_id == variant_id
    ).all()
    card = db.query(ModelCard).filter_by(variant_id=variant_id).first()

    ports_by_element: dict[str, list[PortContract]] = {}
    for p in ports:
        ports_by_element.setdefault(str(p.element_id), []).append(p)
    elements_by_id = {str(e.id): e for e in elements}

    # MV-01 — every variable has type/unit/source: units + equations present
    for e in elements:
        if e.unit is None:
            findings.append(_finding(
                "missing_definition", "warning",
                f"블록 '{e.name}'에 단위가 없습니다 (MV-01)",
                "요소의 대표 출력 단위가 정의되지 않아 인터페이스 호환성을 검증할 수 없습니다.",
                [{"kind": "model_element", "business_id": e.business_id}],
                "요소에 대표 단위를 정의하거나 포트 계약으로 단위를 명시하세요.",
            ))
        if e.equation_text is None:
            findings.append(_finding(
                "missing_definition", "suggestion",
                f"블록 '{e.name}'에 수식이 없습니다 (MV-01)",
                "원리 기반 모델 요소는 수식 또는 모델 코드 참조를 가져야 합니다.",
                [{"kind": "model_element", "business_id": e.business_id}],
                "수식 텍스트 또는 FMU 변수 참조를 등록하세요.",
            ))

    # MV-02 — connected ports have compatible units and time semantics
    linked_element_ids: set[str] = set()
    for link in links:
        src = elements_by_id.get(str(link.source_element_id))
        dst = elements_by_id.get(str(link.target_element_id))
        if src is None or dst is None:
            continue
        linked_element_ids.update((str(link.source_element_id), str(link.target_element_id)))
        src_out = next((p for p in ports_by_element.get(str(src.id), [])
                        if p.direction in (PortDirection.OUT, PortDirection.INOUT)), None)
        dst_in = next((p for p in ports_by_element.get(str(dst.id), [])
                       if p.direction in (PortDirection.IN, PortDirection.INOUT)), None)
        check = check_link_units(
            link.unit,
            src_out.unit if src_out else (src.unit if src else None),
            dst_in.unit if dst_in else (dst.unit if dst else None),
            src.name if src else link.signal,
            dst.name if dst else link.signal,
            has_conversion=bool(link.unit_conversion),
        )
        if check.level in ("error", "conversion_required"):
            findings.append(_finding(
                "port_unit", "error",
                f"링크 '{link.signal}' 단위 차원 불일치 (MV-02)",
                check.message,
                [{"kind": "model_link", "business_id": link.business_id}],
                "포트 단위를 일치시키거나 명시적 변환을 정의한 뒤 링크를 수정하세요.",
            ))
        elif check.level == "warning":
            findings.append(_finding(
                "port_unit", "warning",
                f"링크 '{link.signal}' 단위 확인 필요 (MV-02)",
                check.message,
                [{"kind": "model_link", "business_id": link.business_id}],
                "같은 차원 내 다른 단위라면 unit_conversion에 변환식을 명시하세요.",
            ))
        if src_out and dst_in and src_out.timing_semantics and dst_in.timing_semantics \
                and src_out.timing_semantics != dst_in.timing_semantics:
            findings.append(_finding(
                "port_unit", "warning",
                f"링크 '{link.signal}' 시간 의미 불일치 (MV-02)",
                f"{src.name if src else ''}: {src_out.timing_semantics} ↔ "
                f"{dst.name if dst else ''}: {dst_in.timing_semantics}",
                [{"kind": "model_link", "business_id": link.business_id}],
                "샘플링/연속 여부를 포트 계약에서 정렬하세요.",
            ))

    # MV-04 — model validity envelope vs actually-run parameters
    if card is None:
        findings.append(_finding(
            "no_card", "suggestion",
            "모델 카드가 없습니다 (TC-03)",
            "목적·가정·유효범위·증거가 기록된 모델 카드를 등록하세요.",
            [], "모델 카드를 작성하고 신뢰 상태를 시작하세요.",
        ))
    elif card.validity_envelope:
        run = (
            db.query(SimulationRun)
            .filter_by(variant_id=variant_id, run_type="mech_model")
            .order_by(SimulationRun.created_at.desc())
            .first()
        )
        if run is not None and run.status == "succeeded":
            params = run.parameters or {}
            for bound in card.validity_envelope:
                value = params.get(bound.get("parameter"))
                if isinstance(value, (int, float)) and not (bound["min"] <= value <= bound["max"]):
                    findings.append(_finding(
                        "envelope", "error",
                        f"실행 파라미터가 유효 범위 밖입니다 (MV-04)",
                        f"{bound['parameter']}={value} 가 카드 유효 범위 "
                        f"[{bound['min']}, {bound['max']}] {bound.get('unit', '')}을 벗어납니다.",
                        [
                            {"kind": "simulation_run", "business_id": run.business_id},
                            {"kind": "model_card", "business_id": card.business_id},
                        ],
                        "유효 범위 안 값으로 재실행하거나 카드 유효 범위의 근거를 갱신하세요.",
                    ))

    # MV-07 adjacent — AI-inferred causal edges are not evidence until approved
    ai_edges = db.query(CausalRelation).filter_by(
        variant_id=variant_id, provenance="ai_inferred"
    ).all()
    if ai_edges:
        findings.append(_finding(
            "ai_inferred_unreviewed", "warning",
            f"사람 승인 전 AI 추론 인과관계 {len(ai_edges)}건 (AI-06)",
            "AI-inferred 관계는 승인 전까지 Gate Evidence로 사용할 수 없습니다.",
            [{"kind": "causal_relation", "business_id": r.business_id} for r in ai_edges],
            "각 인과관계를 검토해 human_approved로 승인하거나 제거하세요.",
        ))

    # validated cards must have measured correlation evidence
    if card is not None and card.trust_state in _VALIDATED_STATES:
        run_ids = [
            r.id for r in db.query(SimulationRun.id).filter_by(variant_id=variant_id).all()
        ]
        has_correlation = (
            db.query(CorrelationRecord.id)
            .filter(CorrelationRecord.simulation_run_id.in_(run_ids or ["00000000-0000-0000-0000-000000000000"]))
            .first()
            is not None
        )
        if not has_correlation:
            findings.append(_finding(
                "missing_validation", "error",
                f"카드 신뢰 상태 '{card.trust_state.value}'에 비해 실측 검증 증거가 없습니다 (MV-06)",
                "검증됨/용도 검증 상태는 실측 상관성 기록을 필요로 합니다.",
                [{"kind": "model_card", "business_id": card.business_id}],
                "예측–실측 상관성을 계산하고 증거를 카드에 연결하세요.",
            ))

    # structure — unconnected blocks
    for e in elements:
        if str(e.id) not in linked_element_ids:
            findings.append(_finding(
                "disconnected", "suggestion",
                f"블록 '{e.name}'이 어떤 신호 링크에도 연결되지 않았습니다",
                None,
                [{"kind": "model_element", "business_id": e.business_id}],
                "캔버스에서 인접 블록과 링크를 연결하거나 제거하세요.",
            ))

    return findings
