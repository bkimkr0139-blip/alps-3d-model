"""P1-08 — 3-language evidence report (ko/en/ja) for the ASIC twin.

One deterministic dict per (template, lang): every human-readable label comes
from the _L table below, data values stay as-is (ids, codes, numbers), and
provenance survives the trip — each row carries its source_class so a
SYNTHETIC/MOCK fact can never read as measured in any language (§12: 합성·목
구분은 모든 내보내기에서 유지).

Money is deliberately absent: unit costs live behind the CAN_COST-restricted
trade-study reads, so the report names studies/decisions/TBD components only —
it never embeds amounts (수용기준 5). TBD is named, never zero.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.asic_gate_policy import POLICY_VERSION, evaluate_gate
from app.asic_testprog import coverage_matrix, flow_totals
from app.models.asic import (
    AsicEco,
    AsicPartner,
    FaCase,
    FaultInjectionRun,
    FmedaItem,
    LotTraveler,
    ManufacturingOption,
    MeasurementRun,
    PartnerArtifact,
    PartnerChange,
    QualityAction,
    QualificationPlan,
    QualificationResult,
    SafetyItem,
    SignalChainModel,
    TestFlow,
    TradeStudy,
    WaferMap,
)

REPORT_VERSION = "asic-evidence-report-v1"
LANGS = ("ko", "en", "ja")

# The whole localized surface of the report — nothing user-visible is composed
# outside this table, so a missing language can only fail loudly, never leak
# Korean into a ja report.
_L: dict[str, dict[str, str]] = {
    "ko": {
        "title": "ASIC 증적 보고서",
        "generated_at": "생성 시각",
        "policy": "게이트 정책",
        "not_found": "데이터 없음",
        "sec.design": "설계 (신호 체인)",
        "sec.measurements": "측정 증적",
        "sec.qualification": "양산 시험 (AEC-Q100)",
        "sec.safety": "안전 · FMEDA",
        "sec.fa_eco": "FA · ECO 폐루프",
        "sec.test_program": "테스트 프로그램",
        "sec.trade_study": "원가 트레이드 스터디",
        "sec.supply_chain": "공급망 · 품질",
        "sec.gate": "출시 게이트",
        "revision": "리비전",
        "status": "상태",
        "blocks": "블록 수",
        "source": "데이터 구분",
        "equipment": "장비",
        "calibration": "교정 만료",
        "cal_expired": "만료 (게이트 블로커)",
        "file_hash": "파일 해시",
        "grade": "등급",
        "stress_groups": "스트레스 그룹",
        "results": "결과",
        "waiver": "웨이버",
        "safety_items": "안전 항목",
        "fmeda_rows": "FMEDA 행",
        "fault_injection": "고장 주입",
        "passed": "통과",
        "failed": "실패",
        "open_cases": "열린 케이스",
        "closed_cases": "종결 케이스",
        "ecos": "ECO",
        "target": "대상",
        "program_rev": "프로그램 리비전",
        "silicon": "실리콘 리비전",
        "items": "항목 수",
        "wall_time": "다이당 소요 시간",
        "cost": "다이당 비용",
        "tbd": "TBD (미확정 — 0으로 계산되지 않음)",
        "coverage": "결함 커버리지",
        "studies": "스터디",
        "decided": "결정된 옵션",
        "undecided": "미결정",
        "tbd_components": "미확정 구성요소",
        "money_note": "금액은 원가 권한(CAN_COST) 조회에서만 제공됩니다",
        "partners": "파트너",
        "lots": "로트",
        "changes": "변경 통지(PCN)",
        "open_actions": "열린 품질 조치",
        "artifacts": "파트너 아티팩트",
        "yield": "수율",
        "retest": "재검사율",
        "sec.wafer_maps": "웨이퍼 맵",
        "blockers": "블로커",
        "none": "없음",
        "readiness": "준비도",
        "note_tbd": "TBD 항목은 0이 아닌 미확정으로 명시됩니다.",
        "note_source": "SYNTHETIC/MOCK 표기는 모든 언어에서 유지됩니다.",
    },
    "en": {
        "title": "ASIC evidence report",
        "generated_at": "Generated at",
        "policy": "Gate policy",
        "not_found": "no data",
        "sec.design": "Design (signal chain)",
        "sec.measurements": "Measurement evidence",
        "sec.qualification": "Qualification (AEC-Q100)",
        "sec.safety": "Safety · FMEDA",
        "sec.fa_eco": "FA · ECO loop",
        "sec.test_program": "Test program",
        "sec.trade_study": "Cost trade study",
        "sec.supply_chain": "Supply chain · quality",
        "sec.gate": "Release gate",
        "revision": "Revision",
        "status": "Status",
        "blocks": "Blocks",
        "source": "Source class",
        "equipment": "Equipment",
        "calibration": "Calibration expires",
        "cal_expired": "EXPIRED (gate blocker)",
        "file_hash": "File hash",
        "grade": "Grade",
        "stress_groups": "Stress groups",
        "results": "Results",
        "waiver": "Waiver",
        "safety_items": "Safety items",
        "fmeda_rows": "FMEDA rows",
        "fault_injection": "Fault injection",
        "passed": "pass",
        "failed": "fail",
        "open_cases": "Open cases",
        "closed_cases": "Closed cases",
        "ecos": "ECOs",
        "target": "Target",
        "program_rev": "Program rev",
        "silicon": "Silicon rev",
        "items": "Items",
        "wall_time": "Wall time per die",
        "cost": "Cost per die",
        "tbd": "TBD (undetermined — never computed as 0)",
        "coverage": "Defect coverage",
        "studies": "Studies",
        "decided": "Decided option",
        "undecided": "undecided",
        "tbd_components": "TBD components",
        "money_note": "Amounts are served only through CAN_COST-restricted views",
        "partners": "Partners",
        "lots": "Lots",
        "changes": "Change notices (PCN)",
        "open_actions": "Open quality actions",
        "artifacts": "Partner artifacts",
        "yield": "Yield",
        "retest": "Retest rate",
        "sec.wafer_maps": "Wafer maps",
        "blockers": "Blockers",
        "none": "none",
        "readiness": "Readiness",
        "note_tbd": "TBD entries are stated as undetermined, never as 0.",
        "note_source": "SYNTHETIC/MOCK labelling is preserved in every language.",
    },
    "ja": {
        "title": "ASICエビデンス報告書",
        "generated_at": "生成日時",
        "policy": "ゲートポリシー",
        "not_found": "データなし",
        "sec.design": "設計(信号チェーン)",
        "sec.measurements": "測定エビデンス",
        "sec.qualification": "量産試験(AEC-Q100)",
        "sec.safety": "安全・FMEDA",
        "sec.fa_eco": "FA・ECOループ",
        "sec.test_program": "テストプログラム",
        "sec.trade_study": "コストトレードスタディ",
        "sec.supply_chain": "サプライチェーン・品質",
        "sec.gate": "出荷ゲート",
        "revision": "リビジョン",
        "status": "状態",
        "blocks": "ブロック数",
        "source": "データ区分",
        "equipment": "装置",
        "calibration": "校正期限",
        "cal_expired": "期限切れ(ゲートブロッカー)",
        "file_hash": "ファイルハッシュ",
        "grade": "グレード",
        "stress_groups": "ストレスグループ",
        "results": "結果",
        "waiver": "ウェーバー",
        "safety_items": "安全項目",
        "fmeda_rows": "FMEDA行",
        "fault_injection": "故障注入",
        "passed": "合格",
        "failed": "不合格",
        "open_cases": "未完了ケース",
        "closed_cases": "完了ケース",
        "ecos": "ECO",
        "target": "対象",
        "program_rev": "プログラムリビジョン",
        "silicon": "シリコンリビジョン",
        "items": "項目数",
        "wall_time": "ダイ当たり処理時間",
        "cost": "ダイ当たりコスト",
        "tbd": "TBD(未確定 — 0として計算しない)",
        "coverage": "欠陥カバレッジ",
        "studies": "スタディ",
        "decided": "決定オプション",
        "undecided": "未決定",
        "tbd_components": "未確定構成要素",
        "money_note": "金額はコスト権限(CAN_COST)ビューでのみ提供されます",
        "partners": "パートナー",
        "lots": "ロット",
        "changes": "変更通知(PCN)",
        "open_actions": "未完了品質対応",
        "artifacts": "パートナーアーティファクト",
        "yield": "歩留まり",
        "retest": "再検査率",
        "sec.wafer_maps": "ウェハマップ",
        "blockers": "ブロッカー",
        "none": "なし",
        "readiness": "準備度",
        "note_tbd": "TBD項目は0ではなく未確定として明示されます。",
        "note_source": "SYNTHETIC/MOCK表記は全言語で保持されます。",
    },
}


def _t(db: Session, model, template_id: str):
    return db.query(model).filter_by(template_id=template_id)


def _fmt_cal(run: MeasurementRun, t: dict) -> str:
    if run.calibration_expires_at is None:
        return "—"
    expired = run.calibration_expires_at <= datetime.now(timezone.utc)
    iso = run.calibration_expires_at.isoformat()
    return f"{iso} ({t['cal_expired']})" if expired else iso


def build_evidence_report(db: Session, template_id: str, lang: str) -> dict:
    """Localized report dict — sections of {label, value} rows, provenance kept."""
    t = _L[lang]
    now = datetime.now(timezone.utc)

    def row(label: str, value) -> dict:
        return {"label": label, "value": value}

    def sec(key: str, rows: list[dict], provenance: str | None = None) -> dict:
        out = {"key": key, "title": t[f"sec.{key}"], "rows": rows}
        if provenance:
            out["source_class"] = provenance
        return out

    sections: list[dict] = []

    # ── design: signal chain revisions ───────────────────────────────
    chains = _t(db, SignalChainModel, template_id).order_by(SignalChainModel.revision).all()
    sections.append(sec("design", [
        row(f"{t['revision']} r{c.revision}", f"{t['status']}: {c.status} · {t['blocks']}: {len(c.blocks or [])}")
        for c in chains
    ] or [row(t["not_found"], "—")]))

    # ── measurements: calibration + hashes stay attached ────────────
    runs = _t(db, MeasurementRun, template_id).order_by(MeasurementRun.created_at).all()
    sections.append(sec("measurements", [
        row(run.equipment_id, (
            f"{t['equipment']}: {run.equipment_type} · {t['calibration']}: {_fmt_cal(run, t)} · "
            f"{t['file_hash']}: {run.file_hash[:12]}… · {t['status']}: {run.status}"
        ))
        for run in runs
    ] or [row(t["not_found"], "—")]))

    # ── qualification matrix ─────────────────────────────────────────
    plans = _t(db, QualificationPlan, template_id).order_by(QualificationPlan.created_at).all()
    qual_rows: list[dict] = []
    for p in plans:
        results = (
            db.query(QualificationResult).filter_by(plan_id=p.id).order_by(QualificationResult.created_at).all()
        )
        groups = ", ".join(f"{r.group}:{r.status}" for r in results) or t["not_found"]
        waivers = [r.waiver_ref for r in results if r.waiver_ref]
        qual_rows.append(row(
            f"{t['grade']} {p.grade} · {p.business_id}",
            f"{t['stress_groups']}: {groups} · {t['status']}: {p.status}"
            + (f" · {t['waiver']}: {len(waivers)}" if waivers else ""),
        ))
    sections.append(sec("qualification", qual_rows or [row(t["not_found"], "—")]))

    # ── safety ───────────────────────────────────────────────────────
    safety_items = _t(db, SafetyItem, template_id).all()
    safety_ids = [s.id for s in safety_items]
    fmeda_n = (
        db.query(FmedaItem).filter(FmedaItem.safety_item_id.in_(safety_ids)).count()
        if safety_ids
        else 0
    )
    injections = (
        db.query(FaultInjectionRun)
        .filter(FaultInjectionRun.safety_item_id.in_(safety_ids))
        .all()
        if safety_ids
        else []
    )
    inj_summary = (
        f"{sum(1 for i in injections if i.status == 'pass')}/{len(injections)} {t['passed']}"
        if injections else t["not_found"]
    )
    sections.append(sec("safety", [
        row(t["safety_items"], len(safety_items)),
        row(t["fmeda_rows"], fmeda_n),
        row(t["fault_injection"], inj_summary),
    ]))

    # ── FA · ECO loop ────────────────────────────────────────────────
    cases = _t(db, FaCase, template_id).all()
    ecos = _t(db, AsicEco, template_id).all()
    sections.append(sec("fa_eco", [
        row(t["open_cases"], sum(1 for c in cases if c.status not in ("closed", "verified"))),
        row(t["closed_cases"], sum(1 for c in cases if c.status in ("closed", "verified"))),
        row(t["ecos"], f"{len(ecos)} ({sum(1 for e in ecos if e.status == 'closed')} closed)"),
    ]))

    # ── test program twin: wall time + cost TBD naming ───────────────
    flows = (
        _t(db, TestFlow, template_id)
        .filter(TestFlow.status != "superseded")
        .order_by(TestFlow.target, TestFlow.program_revision)
        .all()
    )
    flow_rows: list[dict] = []
    for f in flows:
        items = list(f.items)
        totals = flow_totals(items, f.cost_rate_per_site_hour)
        cov = coverage_matrix(items)
        cost = t["tbd"] if totals["cost_per_die"] is None else str(totals["cost_per_die"])
        flow_rows.append(row(
            f"{t['target']}: {f.target} · {t['program_rev']} r{f.program_revision}",
            f"{t['silicon']}: {f.silicon_revision} · {t['items']}: {totals['item_count']} · "
            f"{t['wall_time']}: {totals['wall_time_s_per_die']}s · {t['cost']}: {cost} · "
            f"{t['coverage']}: {cov['aggregate_avg_pct']}%",
        ))
    sections.append(sec("test_program", flow_rows or [row(t["not_found"], "—")]))

    # ── wafer maps (P1-05): yield/retest from stored analysis ────────
    maps = _t(db, WaferMap, template_id).order_by(WaferMap.created_at).all()
    map_rows = [
        row(
            f"{m.wafer_ref} ({m.source_class})",
            f"{t['yield']}: {m.analysis['yield_pct']}% · {t['retest']}: {m.analysis['retest_rate_pct']}%"
            if m.analysis else m.source_class,
        )
        for m in maps
    ]
    if map_rows:
        sections.append(sec("wafer_maps", map_rows))

    # ── trade study: existence + decision + TBD names, never amounts ─
    studies = _t(db, TradeStudy, template_id).order_by(TradeStudy.created_at).all()
    option_ids = {str(o.id): o for o in _t(db, ManufacturingOption, template_id).all()}
    study_rows: list[dict] = []
    for s in studies:
        if s.decision:
            dec = option_ids.get(str(s.decision.get("option_id", "")))
            decided = dec.business_id if dec else str(s.decision.get("option_id", "?"))
        else:
            decided = t["undecided"]
        result_tbd = sorted({
            c
            for po in ((s.result or {}).get("per_option") or [])
            for key in ("nre_tbd_components", "unit_tbd_components")
            for c in (po.get(key) or [])
        })
        study_rows.append(row(
            f"{s.business_id} · {t['status']}: {s.status}",
            f"{t['decided']}: {decided}"
            + (f" · {t['tbd_components']}: {', '.join(result_tbd)}" if result_tbd else ""),
        ))
    study_rows.append(row(t["money_note"], "—"))
    sections.append(sec("trade_study", study_rows))

    # ── supply chain ─────────────────────────────────────────────────
    # PCNs carry no template column — scope them like the gate does: changes
    # naming this template OR raised by a partner on this template's lots.
    partners = db.query(AsicPartner).order_by(AsicPartner.business_id).all()
    lots = _t(db, LotTraveler, template_id).all()
    lot_partner_ids = {
        s.get("partner_id")
        for lt in lots
        for s in (lt.steps or [])
        if s.get("partner_id")
    }
    changes = [
        pc
        for pc in db.query(PartnerChange).order_by(PartnerChange.created_at).all()
        if template_id in (pc.affected_template_ids or [])
        or str(pc.partner_id) in lot_partner_ids
    ]
    actions = _t(db, QualityAction, template_id).all()
    artifacts = _t(db, PartnerArtifact, template_id).all()
    sections.append(sec("supply_chain", [
        row(t["partners"], ", ".join(f"{p.business_id}({p.status})" for p in partners) or t["not_found"]),
        row(t["lots"], ", ".join(lt.lot_ref for lt in lots) or t["not_found"]),
        row(t["changes"], ", ".join(f"{pc.business_id}:{pc.status}" for pc in changes) or t["not_found"]),
        row(t["open_actions"], sum(1 for qa in actions if qa.status == "open")),
        row(t["artifacts"], len(artifacts)),
    ]))

    # ── gate: recomputed, not echoed ─────────────────────────────────
    gate = evaluate_gate(db, template_id)
    sections.append(sec("gate", [
        row(t["blockers"], ", ".join(b["code"] for b in gate["blockers"]) or t["none"]),
        row(t["readiness"], gate["readiness"]),
        row(t["policy"], POLICY_VERSION),
    ]))

    return {
        "report_version": REPORT_VERSION,
        "template_id": template_id,
        "lang": lang,
        "generated_at": now.isoformat(),
        "title": t["title"],
        "notes": [t["note_tbd"], t["note_source"]],
        "sections": sections,
    }
