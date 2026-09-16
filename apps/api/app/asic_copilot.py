"""ASIC Copilot rule engine (지시서 v1.1 §4 EPIC J — 근거 중심 AI Engineering Copilot).

EPIC J는 AI를 "설계 승인자"가 아니라 "증거를 찾고 비교하며 다음 실험을
제안하는 보조자"로 한정한다. 이 엔진의 규칙들:

  1. 모든 사실(fact)은 DB에서 조회된 것만 — 엔진이 숫자를 만들지 않는다
     (지시서 §7 도메인 금지와 TACT AI-03 facts_used 패턴과 동일 계약).
  2. 모든 제안(proposal)은 근거 링크(evidence)를 최소 1개 요구한다. 근거가
     없으면 제안 대신 abstain — 근거 링크 없는 AI 제안은 게이트 증적으로
     첨부될 수 없다(수용기준 1; 구조적으로도 copilot은 gate/evidence
     테이블에 절대 쓰지 않는다).
  3. OOD·근거 부족·충돌 시 답변 대신 명시적 보류(abstain + 이유).
  4. 같은 입력·엔진 버전·DB 스냅샷이면 결과가 결정론적으로 재현된다 —
     input_hash가 감사 재현 메타데이터(수용기준 3)의 열쇠.
  5. confidence는 근거 수·커버리지에서 온 휴리스틱이며, 정확한 값이 아니라
     화면에 반드시 "휴리스틱"으로 표시된다.

LLM 서술(narration)은 여기 넣지 않았다 — 팩트 시트 자체가 요약이고, 규칙
엔진이라 감사 재현이 자명하다 (R3 종료조건: 모든 제안이 인간 검토를 거친다).
"""

import hashlib
import json
import re
from difflib import unified_diff

from sqlalchemy.orm import Session

from app.asic_gate_policy import evaluate_gate
from app.asic_testprog import analyze_wafer_map, optimization_proposals
from app.models.asic import (
    AsicCopilotInteraction,
    CornerStudy,
    FaCase,
    MeasurementRun,
    SignalChainModel,
    TestFlow,
    TestFlowItem,
    ToolRun,
    TradeStudy,
    WaferMap,
)

ENGINE_VERSION = "asic-copilot-rules-v1"

# ── 감사 재현 메타데이터 ─────────────────────────────────────────────────────


def canonical_snapshot(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def snapshot_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_snapshot(payload).encode("utf-8")).hexdigest()


def proposal_diff(diff_base: str, proposal_text: str) -> str:
    """수용기준 2용 서버 측 diff — UI는 이 문자열을 그대로 표시하고 그
    sha256을 돌려받아 수락 시 대조한다 (사용자가 본 것 == 서버가 재계산한 것)."""
    return "\n".join(
        unified_diff(
            (diff_base or "").splitlines(),
            proposal_text.splitlines(),
            fromfile="original",
            tofile="proposal",
            lineterm="",
        )
    )


# ── 유스케이스 1: 고객 요구 문장 → 측정 가능한 요구·검증 초안 ─────────────────

_UNIT = (
    r"(?:k?V|mV|[uµ]V|k?A|mA|[uµ]A|nA|pA|Hz|kHz|MHz|GHz|k?Ω|M?Ω|"
    r"fF|pF|nF|[uµ]F|ms|[uµ]s|ns|ppm|%|°C|mm|counts|LSB)"
)
_MEASURE_RE = re.compile(rf"([0-9]*\.?[0-9]+)\s*({_UNIT})", re.UNICODE)
# 문장 안의 '이하/이상/이내/±' 등 방향 힌트 → limit 방향 결정에 쓴다
_LE_RE = re.compile(r"(이하|이내|이상|以下|以下|max|maximum|≤|<)", re.IGNORECASE)
_VERIFICATION_BY_UNIT = {
    "V": "test", "mV": "test", "µV": "test", "uV": "test",
    "A": "test", "mA": "test", "µA": "test", "uA": "test", "nA": "test", "pA": "test",
    "Hz": "test", "kHz": "test", "MHz": "test", "GHz": "test",
    "Ω": "test", "kΩ": "test", "MΩ": "test",
    "F": "analysis", "fF": "analysis", "pF": "analysis", "nF": "analysis",
    "µF": "analysis", "uF": "analysis",
    "s": "analysis", "ms": "test", "µs": "analysis", "us": "analysis", "ns": "analysis",
    "ppm": "test", "%": "test", "°C": "test",
    "mm": "inspection", "counts": "analysis", "LSB": "test",
}


def _req_draft(db: Session, template_id: str, text: str) -> tuple[dict, list[dict], list[str]]:
    """(result_dict, proposals, snapshot_retrieved) — 규칙: 숫자+단위 조합이
    하나도 없으면 측정 가능한 요구로 다듬을 수 없으므로 abstain."""
    found = _MEASURE_RE.findall(text or "")
    if not found:
        return (
            {
                "summary": "측정 가능한 수량(숫자+단위)이 문장에서 발견되지 않아 초안을 생성하지 않습니다.",
                "facts": [],
                "evidence": [],
                "proposals": [],
                "confidence": 0.0,
                "abstain": True,
                "abstain_reason": "no_measurable_quantity",
            },
            [],
            [],
        )
    seen: set[tuple[str, str]] = set()
    proposals: list[dict] = []
    facts: list[str] = []
    for idx, (num, unit) in enumerate(found, start=1):
        key = (num, unit)
        if key in seen:
            continue
        seen.add(key)
        direction = "upper" if _LE_RE.search(text) else "both"
        proposals.append({
            "pid": f"REQ-D{idx:02d}",
            "kind": "requirement_draft",
            "text": (
                f"[초안] 측정값 {num} {unit} 기준 요구사항 — "
                f"한계 방향 {direction}, 검증 방법 "
                f"{_VERIFICATION_BY_UNIT.get(unit, 'analysis')}. 담당자가 값·방향·단위를 확정해야 한다."
            ),
            "diff_base": text,
            "evidence": [{"kind": "requirement", "ref": "customer_input", "label": f"{num} {unit}"}],
        })
        facts.append(f"입력 문장에서 수량 {num} {unit} 발견 (검증방법 후보: {_VERIFICATION_BY_UNIT.get(unit, 'analysis')})")
    n = len(proposals)
    return (
        {
            "summary": f"{n}개의 측정 가능 수량에서 요구사항·검증 초안 {n}건을 제안합니다 (전부 DRAFT — 수락 전 diff 확인 필수).",
            "facts": facts,
            "evidence": [],
            "proposals": proposals,
            "confidence": round(min(0.4 + 0.1 * n, 0.8), 2),  # 휴리스틱: 수량 수 기반
            "abstain": False,
            "abstain_reason": None,
        },
        proposals,
        ["customer_input"],
    )


# ── 유스케이스 2: 과거 FA 유사사례 검색 ───────────────────────────────────────


def _obs_text(o) -> str:
    """FaObservation의 본문 키는 `fact` (schema 기준) — 예전 dict/raw도 관용."""
    if isinstance(o, dict):
        return o.get("fact") or o.get("text") or ""
    return str(o)


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"\s+", "", (s or "").lower())
    return {s[i : i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def _similar_fa(db: Session, template_id: str, text: str) -> tuple[dict, list[dict], list[str]]:
    cases = (
        db.query(FaCase)
        .filter_by(template_id=template_id)
        .order_by(FaCase.created_at.desc())
        .limit(50)
        .all()
    )
    retrieved = [c.business_id for c in cases]
    if not cases:
        return (
            {
                "summary": "검색 가능한 과거 FA 케이스가 없어 유사사례를 제시하지 않습니다.",
                "facts": [], "evidence": [], "proposals": [],
                "confidence": 0.0,
                "abstain": True,
                "abstain_reason": "no_fa_cases",
            },
            [],
            retrieved,
        )
    q = _bigrams(text or "")
    ranked = []
    for c in cases:
        cand = _bigrams(c.symptom) | _bigrams(" ".join(
            _obs_text(o) for o in (c.observations or [])
        ))
        jac = len(q & cand) / len(q | cand) if q and cand else 0.0
        if jac > 0:
            ranked.append((jac, c))
    ranked.sort(key=lambda t: (-t[0], t[1].business_id))
    top = ranked[:3]
    if not top:
        return (
            {
                "summary": "토큰이 겹치는 과거 사례가 없습니다 — 유사사례 없음도 검색 결과이다.",
                "facts": [f"검색 대상 FA 케이스 {len(cases)}건"],
                "evidence": [{"kind": "fa_case", "ref": c.business_id, "label": c.symptom[:48]} for c in cases[:3]],
                "proposals": [],
                "confidence": 0.3,
                "abstain": True,
                "abstain_reason": "no_similar_case",
            },
            [],
            retrieved,
        )
    evidence = [
        {"kind": "fa_case", "ref": c.business_id, "label": f"score={s:.2f} · {c.symptom[:48]}"}
        for s, c in top
    ]
    facts = [f"유사도 {s:.2f}: {c.business_id} ({c.status}) — {c.symptom[:60]}" for s, c in top]
    proposals = [
        {
            "pid": "FA-SIMILAR-01",
            "kind": "fa_hypothesis",
            "text": (
                f"[검토안] 유사사례 {top[0][1].business_id}의 원인 분류({top[0][1].cause_class or 'unknown'})를 "
                "현재 케이스의 가설 후보로 검토 — 인간 분석가가 채택/기각한다."
            ),
            "diff_base": None,
            "evidence": evidence,
        }
    ]
    return (
        {
            "summary": f"과거 FA {len(cases)}건 중 유사 상위 {len(top)}건을 제시합니다 (문자 2-gram Jaccard — 근거 링크로 직접 확인 요망).",
            "facts": facts,
            "evidence": evidence,
            "proposals": proposals,
            "confidence": round(min(0.3 + top[0][0], 0.75), 2),
            "abstain": False,
            "abstain_reason": None,
        },
        proposals,
        retrieved,
    )


# ── 유스케이스 3: Corner/MC 결과의 규격 민감도 설명 ───────────────────────────


def _corner_sensitivity(db: Session, template_id: str) -> tuple[dict, list[dict], list[str]]:
    chains = db.query(SignalChainModel).filter_by(template_id=template_id).all()
    chain_ids = [c.id for c in chains]
    studies = (
        db.query(CornerStudy)
        .filter(CornerStudy.signal_chain_id.in_(chain_ids))
        .order_by(CornerStudy.created_at.desc())
        .limit(10)
        .all()
        if chain_ids
        else []
    )
    retrieved = [s.business_id for s in studies]
    if not studies:
        return (
            {
                "summary": "Corner/Monte-Carlo 연구가 없어 민감도를 설명할 수 없습니다.",
                "facts": [], "evidence": [], "proposals": [],
                "confidence": 0.0, "abstain": True, "abstain_reason": "no_corner_studies",
            },
            [],
            retrieved,
        )
    facts: list[str] = []
    evidence: list[dict] = []
    tool_runs = db.query(ToolRun).filter_by(template_id=template_id).count()
    for s in studies[:3]:
        res = s.result or {}
        for po in res.get("per_output", [])[:4]:
            window = None
            for sp in s.spec or []:
                if sp.get("output") == po.get("output") and sp.get("min") is not None and sp.get("max") is not None:
                    window = float(sp["max"]) - float(sp["min"])
            spread = (po.get("p99", 0) or 0) - (po.get("p50", 0) or 0)
            ratio = (spread / window) if window else None
            facts.append(
                f"{s.business_id} · {po.get('output')}: p99−p50={spread:.4g}"
                + (f" (스펙 윈도 대비 {ratio:.0%})" if ratio is not None else " (스펙 윈도 미정 — TBD)")
                + f", 위반률 {po.get('violation_rate', 0):.2%}"
            )
        if res.get("model_ood"):
            facts.append(f"{s.business_id}: 모델 OOD 플래그 — {res.get('ood_reason', 'reason 미기록')}. 민감도 해석 전 OOD 검토 필요.")
        evidence.append({"kind": "corner_study", "ref": s.business_id, "label": f"{s.kind} n={s.n_draws}"})
    proposals = []
    ood_studies = [s for s in studies if (s.result or {}).get("model_ood")]
    if ood_studies:
        proposals.append({
            "pid": "CORNER-OOD-01",
            "kind": "review_candidate",
            "text": f"[검토안] OOD 플래그가 있는 연구 {len(ood_studies)}건 — 재검토 또는 학습 범위 확대 후 재실행 (MODEL_OOD 게이트 블로커와 연동).",
            "diff_base": None,
            "evidence": [{"kind": "corner_study", "ref": s.business_id, "label": s.kind} for s in ood_studies[:3]],
        })
    conf = 0.5 + 0.05 * min(len(studies), 4) + (0.05 if tool_runs else 0.0)
    return (
        {
            "summary": (
                f"최근 Corner/MC {min(len(studies), 3)}건의 출력별 분포를 규격 윈도 대비로 정리했습니다. "
                "스펙 민감도가 큰 출력부터 재검토하십시오 (휴리스틱 신뢰도)."
            ),
            "facts": facts,
            "evidence": evidence,
            "proposals": proposals,
            "confidence": round(min(conf, 0.8), 2),
            "abstain": False,
            "abstain_reason": None,
        },
        proposals,
        retrieved,
    )


# ── 유스케이스 4: Wafer map·site·온도·시간 이상 패턴 탐지 ─────────────────────


def _wafer_anomaly(db: Session, template_id: str) -> tuple[dict, list[dict], list[str]]:
    maps = (
        db.query(WaferMap)
        .filter_by(template_id=template_id)
        .order_by(WaferMap.created_at.desc())
        .limit(10)
        .all()
    )
    retrieved = [w.business_id for w in maps]
    if not maps:
        return (
            {
                "summary": "분석할 wafer map이 없습니다.",
                "facts": [], "evidence": [], "proposals": [],
                "confidence": 0.0, "abstain": True, "abstain_reason": "no_wafer_maps",
            },
            [],
            retrieved,
        )
    facts: list[str] = []
    evidence: list[dict] = []
    anomalies: list[str] = []
    for w in maps:
        a = w.analysis if isinstance(w.analysis, dict) else analyze_wafer_map(w.bins, w.ground_truth)
        site = a.get("site_fail_rate_pct", {})
        if site:
            vals = sorted(site.values())
            median = vals[len(vals) // 2]
            for s, v in site.items():
                if median and v >= 2 * max(median, 0.0001) and v > 0:
                    anomalies.append(f"{w.business_id}: site {s} 실패율 {v:.2f}% — 중앙값의 2배 초과 (site 편향 의심)")
        # edge band: 중심으로부터 0.8R 밖에서 실패 집중
        rows, cols = (w.grid or {}).get("rows", 0), (w.grid or {}).get("cols", 0)
        if rows and cols and w.bins:
            cx, cy = (cols - 1) / 2, (rows - 1) / 2
            rx = max(cx, cy) or 1
            edge_fail = edge_total = inner_fail = inner_total = 0
            for b in w.bins:
                x, y = int(b.get("x", 0)), int(b.get("y", 0))
                d = (((x - cx) / rx) ** 2 + ((y - cy) / rx) ** 2) ** 0.5
                fail = int(b.get("bin", 1)) >= 3
                if d > 0.8:
                    edge_total += 1
                    edge_fail += fail
                else:
                    inner_total += 1
                    inner_fail += fail
            if edge_total and inner_total:
                er, ir = edge_fail / edge_total, inner_fail / inner_total
                if er > 0 and er >= 2 * max(ir, 0.0001):
                    anomalies.append(
                        f"{w.business_id}: edge band 실패율 {er:.1%} vs 내부 {ir:.1%} — edge ring/스크라이브 손상 패턴 의심"
                    )
        conf_mat = a.get("confusion") or {}
        if conf_mat.get("escaped_underkill"):
            anomalies.append(
                f"{w.business_id}: underkill {conf_mat['escaped_underkill']}다이 — 탈출 결함 (ground_truth 대비, SYNTHETIC fixture)"
            )
        facts.append(f"{w.business_id}: 수율 {a.get('yield_pct', 0):.2f}% · 재시험 {a.get('retest_rate_pct', 0):.2f}% · 실패 {a.get('fail_rate_pct', 0):.2f}%")
        evidence.append({"kind": "wafer_map", "ref": w.business_id, "label": w.wafer_ref or w.business_id})
    if not anomalies:
        return (
            {
                "summary": f"wafer map {len(maps)}건에서 site·edge·underkill 패턴 이상이 발견되지 않았습니다.",
                "facts": facts, "evidence": evidence, "proposals": [],
                "confidence": 0.6, "abstain": False, "abstain_reason": None,
            },
            [],
            retrieved,
        )
    proposals = [{
        "pid": "WM-ANO-01",
        "kind": "review_candidate",
        "text": "[검토안] 이상 패턴이 관측된 웨이퍼에 FA 케이스 개시 또는 장비/site 교정 확인 — 인간이 개시한다.",
        "diff_base": None,
        "evidence": evidence[:3],
    }]
    return (
        {
            "summary": f"wafer map {len(maps)}건에서 이상 패턴 {len(anomalies)}건을 탐지했습니다 (규칙: site 2× 편향, edge 2× 집중, underkill>0).",
            "facts": facts + anomalies,
            "evidence": evidence,
            "proposals": proposals,
            "confidence": 0.7,
            "abstain": False,
            "abstain_reason": None,
        },
        proposals,
        retrieved,
    )


# ── 유스케이스 5: FA 가설 + 확인 시험 후보 ────────────────────────────────────

_CAUSE_KEYWORDS = {
    "esd": ("ESD 계통 손상", "esd"),
    "latch": ("latch-up", "latchup"),
    "leak": ("누설 전류 계통", "leakage"),
    "short": ("단락 계통", "short"),
    "open": ("개방 계통", "open"),
    "drift": ("파라메트릭 드리프트(온도/경시)", "parametric"),
    "noise": ("노이즈/그라운드 결함", "parametric"),
    "offset": ("오프셋 보정 이상", "parametric"),
}


def _fa_hypothesis(db: Session, template_id: str, fa_case: FaCase) -> tuple[dict, list[dict], list[str]]:
    if fa_case.root_cause_confirmed or fa_case.status in ("rca_approved", "eco_open", "verified", "closed"):
        return (
            {
                "summary": "이 케이스는 RCA가 이미 승인되었습니다 — 가설 제안은 RCA 승인 전 단계의 도구입니다.",
                "facts": [], "evidence": [], "proposals": [],
                "confidence": 0.0, "abstain": True, "abstain_reason": "rca_already_approved",
            },
            [],
            [fa_case.business_id],
        )
    blob = " ".join([
        fa_case.symptom or "",
        fa_case.repro_condition or "",
        " ".join((o.get("text", "") if isinstance(o, dict) else str(o)) for o in (fa_case.observations or [])),
    ]).lower()
    hits = [(kw, label, dclass) for kw, (label, dclass) in _CAUSE_KEYWORDS.items() if kw in blob]
    retrieved = [fa_case.business_id]
    if not hits:
        return (
            {
                "summary": "증상·관찰 기록에서 알려진 원인 계통 키워드를 찾지 못했습니다 — 보류 (근거 없는 가설을 만들지 않는다).",
                "facts": [f"symptom: {fa_case.symptom[:80]}"],
                "evidence": [{"kind": "fa_case", "ref": fa_case.business_id, "label": fa_case.symptom[:48]}],
                "proposals": [],
                "confidence": 0.2, "abstain": True, "abstain_reason": "no_cause_keyword",
            },
            [],
            retrieved,
        )
    # 확인 시험 후보: 결함 클래스를 커버하는 TestFlowItem (사람이 실제 시험으로 실행)
    flows = db.query(TestFlow).filter_by(template_id=template_id).filter(TestFlow.status != "superseded").all()
    confirm: list[dict] = []
    want = {d for _, _, d in hits}
    for f in flows:
        for it in f.items:
            covered = {c.get("defect_class") for c in (it.defect_coverage or []) if isinstance(c, dict)}
            if covered & want:
                confirm.append({
                    "pid": f"CONFIRM-{it.seq:02d}",
                    "kind": "confirm_test",
                    "text": f"[확인시험 후보] {f.business_id} #{it.seq} {it.name} — 결함 클래스 {sorted(covered & want)} 커버 (사람이 실행·판정).",
                    "diff_base": None,
                    "evidence": [
                        {"kind": "fa_case", "ref": fa_case.business_id, "label": fa_case.symptom[:48]},
                        {"kind": "test_flow", "ref": f.business_id, "label": f"item #{it.seq} {it.name}"},
                    ],
                })
    hypotheses = [label for _, label, _ in hits]
    evidence = [
        {"kind": "fa_case", "ref": fa_case.business_id, "label": f"키워드 '{kw}' → {label}"}
        for kw, label, _ in hits
    ]
    proposals = [{
        "pid": "HYP-01",
        "kind": "fa_hypothesis",
        "text": f"[가설 후보] {'; '.join(hypotheses)} — 관찰 근거와 대조 후 분석가가 채택/기각. AI는 원인을 결론짓지 않는다.",
        "diff_base": None,
        "evidence": evidence,
    }] + confirm[:3]
    return (
        {
            "summary": (
                f"증상 텍스트에서 원인 계통 키워드 {len(hits)}개를 찾았습니다: {', '.join(hypotheses)}. "
                "확인 시험 후보는 결함 커버리지가 맞는 기존 테스트 항목입니다."
            ),
            "facts": [f"symptom: {fa_case.symptom[:80]}"] + [f"키워드 매치: {kw} → {label}" for kw, label, _ in hits],
            "evidence": evidence,
            "proposals": proposals,
            "confidence": 0.55,
            "abstain": False,
            "abstain_reason": None,
        },
        proposals,
        retrieved,
    )


# ── 유스케이스 6: 테스트 시간 대비 결함 검출 효율 낮은 항목 ───────────────────


def _test_efficiency(db: Session, template_id: str) -> tuple[dict, list[dict], list[str]]:
    flows = (
        db.query(TestFlow)
        .filter_by(template_id=template_id)
        .filter(TestFlow.status != "superseded")
        .all()
    )
    retrieved = [f.business_id for f in flows]
    if not flows:
        return (
            {
                "summary": "테스트 플로우가 없어 효율 분석을 할 수 없습니다.",
                "facts": [], "evidence": [], "proposals": [],
                "confidence": 0.0, "abstain": True, "abstain_reason": "no_test_flows",
            },
            [],
            retrieved,
        )
    maps = db.query(WaferMap).filter_by(template_id=template_id).all()
    facts: list[str] = []
    proposals: list[dict] = []
    evidence: list[dict] = []
    for f in flows:
        twin = next((o for o in flows if o.id != f.id and o.target != f.target), None)
        p = optimization_proposals(f, twin_items=(twin.items if twin else None), wafer_maps=maps)
        for cand in p.get("proposals", []):
            item = db.get(TestFlowItem, cand.get("item_id")) if cand.get("item_id") else None
            dur = item.expected_duration_s if item else None
            # high_retest_review 등 일부 후보는 item_id/name이 없다 (wafer_ref로 식별)
            label = cand.get("name") or cand.get("wafer_ref") or cand.get("kind", "")
            facts.append(
                f"{f.business_id} · {label}: {cand['kind']}"
                + (f" — 항목 시간 {dur:.1f}s/die 기준" if dur and cand['kind'] == 'duplicate_removal_review' else "")
                + f" — {cand['rationale']}"
            )
            proposals.append({
                "pid": f"EFF-{len(proposals) + 1:02d}",
                "kind": "review_candidate",
                "text": f"[검토안] {f.business_id} · {label} — {cand['rationale']} (review_only: 자동 제거 없음)",
                "diff_base": None,
                "evidence": [{"kind": "test_flow", "ref": f.business_id, "label": label}],
            })
            evidence.append({"kind": "test_flow", "ref": f.business_id, "label": f"proposal {cand['kind']}"})
    if not proposals:
        return (
            {
                "summary": "시간 대비 검출 효율이 낮은 검토 후보가 없습니다 — 모든 항목이 커버리지 링크를 갖습니다.",
                "facts": [f"플로우 {len(flows)}건 분석"],
                "evidence": [{"kind": "test_flow", "ref": f.business_id, "label": f.target} for f in flows],
                "proposals": [],
                "confidence": 0.6, "abstain": False, "abstain_reason": None,
            },
            [],
            retrieved,
        )
    return (
        {
            "summary": (
                f"테스트 플로우 {len(flows)}건에서 검토 후보 {len(proposals)}건을 찾았습니다. "
                "전부 review_only — 제거·변경은 인간의 supersede 절차로만 가능합니다."
            ),
            "facts": facts,
            "evidence": evidence,
            "proposals": proposals,
            "confidence": 0.65,
            "abstain": False,
            "abstain_reason": None,
        },
        proposals,
        retrieved,
    )


# ── 유스케이스 7: 게이트 누락 증적·충돌 리비전 요약 ───────────────────────────


def _gate_gap(db: Session, template_id: str) -> tuple[dict, list[dict], list[str]]:
    report = evaluate_gate(db, template_id)
    retrieved = [f"gate-report/{template_id}"]
    if report["status"] == "pass":
        return (
            {
                "summary": "게이트 블로커가 없습니다 — 누락 증적 요약도 없습니다 (MOCK 블로커는 정책상 항상 부과됨).",
                "facts": [], "evidence": [{"kind": "gate_report", "ref": f"gate-report/{template_id}", "label": report["policy_version"]}],
                "proposals": [], "confidence": 0.9, "abstain": False, "abstain_reason": None,
            },
            [],
            retrieved,
        )
    facts = [f"{b['code']}: {b['detail']}" for b in report["blockers"]]
    evidence = [{"kind": "gate_report", "ref": f"gate-report/{template_id}", "label": report["policy_version"]}]
    for b in report["blockers"]:
        for ev in b.get("evidence", [])[:3]:
            evidence.append({"kind": "gate_evidence", "ref": str(ev), "label": b["code"]})
    proposals = []
    mixed = [b for b in report["blockers"] if b["code"] == "MIXED_REVISION_EVIDENCE"]
    if mixed:
        proposals.append({
            "pid": "GAP-REV-01",
            "kind": "review_candidate",
            "text": "[검토안] 증적이 여러 설계 리비전에 걸쳐 있습니다 — 리비전 통일 재증적화 계획을 세우십시오 (충돌 리비전 요약).",
            "diff_base": None,
            "evidence": evidence[:3],
        })
    return (
        {
            "summary": (
                f"게이트 블로커 {len(report['blockers'])}건 — readiness {report['readiness']}. "
                "블로커별 누락 증적은 facts와 근거 링크에 정리되어 있습니다."
            ),
            "facts": facts,
            "evidence": evidence,
            "proposals": proposals,
            "confidence": 0.85,
            "abstain": False,
            "abstain_reason": None,
        },
        proposals,
        retrieved,
    )


# ── 진입점 ────────────────────────────────────────────────────────────────────

_USECASE_FN = {
    "req_draft": _req_draft,
    "similar_fa": _similar_fa,
    "corner_sensitivity": lambda db, tid, _text: _corner_sensitivity(db, tid),
    "wafer_anomaly": lambda db, tid, _text: _wafer_anomaly(db, tid),
    "test_efficiency": lambda db, tid, _text: _test_efficiency(db, tid),
    "gate_gap": lambda db, tid, _text: _gate_gap(db, tid),
    # fa_hypothesis는 fa_case 인자가 필요해 별도 분기
}


def run_copilot(db: Session, template_id: str, usecase: str, *, text: str | None = None,
                fa_case: FaCase | None = None) -> tuple[dict, dict, str, list[dict]]:
    """(result, input_snapshot, input_hash, proposals) — proposals는 accept
    흐름을 위해 result 밖으로도 노출한다 (pid로 result.proposals와 일치)."""
    snapshot: dict = {
        "template_id": template_id,
        "usecase": usecase,
        "text": text,
        "fa_case_id": str(fa_case.id) if fa_case else None,
    }
    if usecase == "fa_hypothesis":
        if fa_case is None:
            result = {
                "summary": "fa_case_id가 필요합니다.", "facts": [], "evidence": [], "proposals": [],
                "confidence": 0.0, "abstain": True, "abstain_reason": "missing_fa_case",
            }
            proposals: list[dict] = []
        else:
            result, proposals, retrieved = _fa_hypothesis(db, template_id, fa_case)
    else:
        result, proposals, retrieved = _USECASE_FN[usecase](db, template_id, text or "")
    snapshot["retrieved_refs"] = retrieved
    # 근거 링크 없는 제안은 만들어지지 않는다 — 만약 생기면 그 즉시 폐기 (수용기준 1)
    proposals = [p for p in proposals if p.get("evidence")]
    result["proposals"] = proposals
    return result, snapshot, snapshot_hash(snapshot), proposals
