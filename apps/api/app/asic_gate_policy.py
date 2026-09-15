"""ASIC gate policy v1.1 (지시서 §8 게이트 정책 확장 + Readiness Ladder 개편).

Computes the blocker list and readiness rung from DATABASE state — the
frontend renders this report verbatim and never hand-authors a blocker
(지시서 §6 불변규칙 4: 준수 상태는 매트릭스에서 계산, 사용자가 직접 PASS 입력 불가).

Blockers implemented in R1:
  MOCK_RESULT_PRESENT   — hard policy: this platform is an educational twin,
                          ASIC evidence is synthetic-labeled by construction
                          (§15: 시스템은 인증기관/양산 판정을 대체하지 않는다)
  CALIBRATION_EXPIRED   — a measurement run's cal_expires_at < now
  MODEL_OOD             — a corner study flagged model_ood
  MIXED_REVISION_EVIDENCE — evidence rows span >1 signal-chain revision
  QUAL_FAILURE_OPEN     — a failed qual row with no approved-RCA FA case
  WAIVER_EXPIRED        — a qual waiver past its expiry

Readiness ladder (§8 개편): education_only → connected_nonvalidated →
validated_shadow → controlled_pilot → production_candidate → released.
production_candidate/released are NOT reachable from synthetic evidence —
same honesty rule as the frontend ladder's `reachable: false`.
"""

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.asic import (
    AsicEco,
    AsicPartner,
    CornerStudy,
    FaCase,
    LotTraveler,
    MeasurementRun,
    PartnerChange,
    QualityAction,
    QualificationPlan,
    QualificationResult,
    SignalChainModel,
    TestFlow,
    ToolRun,
)
from app.schemas.asic import GateBlocker

POLICY_VERSION = "alps-asic-v1.1"

# (readiness rung, reachable-from-educational-evidence) — the top two rungs
# require REAL_MEASURED attestation this platform cannot honestly claim yet.
READINESS_LADDER = (
    ("education_only", True),
    ("connected_nonvalidated", True),
    ("validated_shadow", True),
    ("controlled_pilot", True),
    ("production_candidate", False),
    ("released", False),
)


def _latest_row_per_group(rows: list[QualificationResult]) -> list[QualificationResult]:
    """The matrix reads per stress group, latest row wins: a fail superseded
    by a later pass retest (ECO 검증 재시험) no longer fails the group.
    Rows keep their append-only history — only the group verdict is derived."""
    latest: dict[str, QualificationResult] = {}
    for r in sorted(rows, key=lambda x: (x.created_at, x.id)):
        latest[r.group] = r
    return list(latest.values())


def evaluate_gate(db: Session, template_id: str, gate_id: str = "RELEASE_SIGNED") -> dict:
    now = datetime.now(timezone.utc)
    blockers: list[GateBlocker] = []
    checks: list[dict] = []

    def add_check(check_id: str, ok: bool, actual, target, evidence: list[str]) -> None:
        checks.append(
            {"check_id": check_id, "status": "pass" if ok else "fail", "actual": actual,
             "target": target, "evidence_refs": evidence}
        )

    # ── signal-chain revisions in play ──────────────────────────────────
    chain_count = (
        db.query(func.count(SignalChainModel.id)).filter_by(template_id=template_id).scalar() or 0
    )
    latest_chain = (
        db.query(SignalChainModel)
        .filter_by(template_id=template_id)
        .order_by(SignalChainModel.revision.desc())
        .first()
    )
    latest_rev = latest_chain.revision if latest_chain else 0

    # ── MOCK_RESULT_PRESENT — unconditional honesty blocker ────────────
    blockers.append(
        GateBlocker(
            code="MOCK_RESULT_PRESENT",
            detail=(
                "이 워크벤치의 ASIC 증적은 교육용 합성 데이터입니다. "
                "실측 근거 없이는 출시 승인 게이트를 통과할 수 없습니다. (지시서 §15)"
            ),
        )
    )
    add_check("mock_result_isolated", False, "synthetic", "real_evidence_only", [])

    # ── EPIC E: equipment measurement evidence ──────────────────────────
    runs = db.query(MeasurementRun).filter_by(template_id=template_id).all()
    expired = [r for r in runs if r.calibration_expires_at and r.calibration_expires_at < now]
    verified = [r for r in runs if r.status == "verified_ingest"]
    if expired:
        blockers.append(
            GateBlocker(
                code="CALIBRATION_EXPIRED",
                detail=f"교정 유효기간이 만료된 장비의 측정 {len(expired)}건이 증적에 포함되어 있습니다.",
                evidence=[r.business_id for r in expired],
            )
        )
    add_check("equipment_calibration_valid", not expired, f"expired={len(expired)}", "expired=0",
              [r.business_id for r in expired])

    # ── EPIC A: corner studies + OOD ────────────────────────────────────
    studies = (
        db.query(CornerStudy)
        .join(SignalChainModel, CornerStudy.signal_chain_id == SignalChainModel.id)
        .filter(SignalChainModel.template_id == template_id)
        .all()
    )
    ood = [s for s in studies if (s.result or {}).get("model_ood")]
    if ood:
        blockers.append(
            GateBlocker(
                code="MODEL_OOD",
                detail="보정 모델이 학습 데이터 범위를 벗어난 Corner/MC 결과가 있습니다. OOD 검토가 필요합니다.",
                evidence=[s.business_id for s in ood],
            )
        )
    add_check("corner_coverage_present", bool(studies), f"studies={len(studies)}", "studies>=1",
              [s.business_id for s in studies])

    # ── mixed-revision evidence ─────────────────────────────────────────
    revisions_with_evidence: set[int] = set()
    for s in studies:
        rev = db.get(SignalChainModel, s.signal_chain_id)
        if rev is not None:
            revisions_with_evidence.add(rev.revision)
    # R2 EPIC C (수용기준 2): one gate's EDA tool results must all belong to a
    # single design revision — results spanning revisions block here too.
    for tr in db.query(ToolRun).filter_by(template_id=template_id).all():
        revisions_with_evidence.add(tr.design_revision)
    if len(revisions_with_evidence) > 1:
        blockers.append(
            GateBlocker(
                code="MIXED_REVISION_EVIDENCE",
                detail=f"증적이 여러 설계 리비전({sorted(revisions_with_evidence)})에 걸쳐 있습니다. "
                "하나의 리비전으로 재증적화해야 합니다.",
                evidence=[f"chain-rev-{r}" for r in sorted(revisions_with_evidence)],
            )
        )
    add_check("evidence_single_revision", len(revisions_with_evidence) <= 1,
              f"revisions={sorted(revisions_with_evidence)}", "revisions<=1", [])

    # ── EPIC F: qualification matrix ────────────────────────────────────
    plans = db.query(QualificationPlan).filter_by(template_id=template_id).all()
    plan_ids = [p.id for p in plans]
    qual_rows = (
        db.query(QualificationResult).filter(QualificationResult.plan_id.in_(plan_ids)).all()
        if plan_ids
        else []
    )
    failed_open = []
    expired_waivers = []
    for row in qual_rows:
        if row.status == "fail":
            fa = db.get(FaCase, row.fa_case_id) if row.fa_case_id else None
            if fa is None or fa.status not in ("rca_approved", "eco_open", "verified", "closed"):
                failed_open.append(row.business_id)
        if row.waiver_expires_at and row.waiver_expires_at < now:
            expired_waivers.append(row.business_id)
    if failed_open:
        blockers.append(
            GateBlocker(
                code="QUAL_FAILURE_OPEN",
                detail=f"신뢰성 시험 실패 {len(failed_open)}건의 RCA 승인이 열려 있습니다.",
                evidence=failed_open,
            )
        )
    if expired_waivers:
        blockers.append(
            GateBlocker(
                code="WAIVER_EXPIRED",
                detail=f"유효기간이 지난 웨이버 {len(expired_waivers)}건이 있습니다.",
                evidence=expired_waivers,
            )
        )
    qual_ok = bool(qual_rows) and all(
        r.status == "pass" or (r.waiver_ref and r.waiver_expires_at and r.waiver_expires_at >= now)
        for r in _latest_row_per_group(qual_rows)
    )
    add_check("qual_matrix_complete", qual_ok,
              f"groups={len(_latest_row_per_group(qual_rows))}", "latest row per group pass/valid waiver",
              [r.business_id for r in qual_rows])

    # ── EPIC G: FA closed loop ──────────────────────────────────────────
    open_ecos = (
        db.query(AsicEco).filter_by(template_id=template_id).filter(AsicEco.status != "closed").all()
    )
    add_check("eco_loop_closed", not open_ecos, f"open={len(open_ecos)}", "open=0",
              [e.business_id for e in open_ecos])

    # ── R2 EPIC D/H: test program ↔ silicon revision + supply chain ────
    flows = (
        db.query(TestFlow)
        .filter_by(template_id=template_id)
        .filter(TestFlow.status != "superseded")
        .all()
    )
    travelers = db.query(LotTraveler).filter_by(template_id=template_id).all()
    partners = {str(p.id): p for p in db.query(AsicPartner).all()}

    flow_silicon_revs = {f.silicon_revision for f in flows}
    rev_mismatch = [t.lot_ref for t in travelers if t.silicon_revision not in flow_silicon_revs]
    if rev_mismatch and flows:
        blockers.append(
            GateBlocker(
                code="TEST_PROGRAM_REV_MISMATCH",
                detail=(
                    "테스트 프로그램이 커버하지 않는 실리콘 리비전의 로트가 있습니다 — "
                    "실행·승인이 차단됩니다 (수용기준 3)."
                ),
                evidence=rev_mismatch,
            )
        )
    add_check("test_program_revision_match", not (rev_mismatch and flows),
              f"lot_mismatch={len(rev_mismatch)}", "mismatch=0", rev_mismatch)

    unapproved, bad_lineage = [], []
    for t in travelers:
        seen: set[tuple[str, str]] = set()
        for s in t.steps or []:
            p = partners.get(str(s.get("partner_id")))
            if p is None:
                bad_lineage.append(f"{t.lot_ref}:unknown-partner")
                continue
            if p.status != "approved":
                unapproved.append(f"{t.lot_ref}:{p.business_id}")
            key = (str(s.get("partner_id")), str(s.get("step")))
            if key in seen:
                bad_lineage.append(f"{t.lot_ref}:duplicate-step:{s.get('step')}")
            seen.add(key)
    if unapproved:
        blockers.append(
            GateBlocker(
                code="PARTNER_NOT_APPROVED",
                detail="승인되지 않은 파트너가 lot 여행 경로에 포함되어 있습니다.",
                evidence=sorted(set(unapproved)),
            )
        )
    if bad_lineage:
        blockers.append(
            GateBlocker(
                code="LINEAGE_INVALID",
                detail="lot genealogy에 알 수 없는 파트너 또는 중복 단계가 있습니다.",
                evidence=sorted(set(bad_lineage)),
            )
        )

    traveler_partner_ids = {
        str(s.get("partner_id"))
        for t in travelers
        for s in (t.steps or [])
        if s.get("partner_id")
    }
    pending_pcns = (
        db.query(PartnerChange)
        .filter(PartnerChange.status.in_(["submitted", "under_review"]))
        .all()
        if traveler_partner_ids
        else []
    )
    pending_pcns = [c for c in pending_pcns if str(c.partner_id) in traveler_partner_ids]
    if pending_pcns:
        blockers.append(
            GateBlocker(
                code="PARTNER_CHANGE_PENDING",
                detail="승인 대기 중인 파트너 변경(PCN)이 lot 경로의 파트너에 있습니다.",
                evidence=[c.business_id for c in pending_pcns],
            )
        )

    open_actions = (
        db.query(QualityAction)
        .filter_by(template_id=template_id, status="open")
        .all()
    )
    if open_actions:
        blockers.append(
            GateBlocker(
                code="QUALITY_ACTION_OPEN",
                detail="종결되지 않은 품질 조치(hold/quarantine/8D)가 있습니다.",
                evidence=[a.business_id for a in open_actions],
            )
        )
    add_check("supply_chain_clean",
              not (unapproved or bad_lineage or pending_pcns or open_actions),
              f"unapproved={len(unapproved)} lineage={len(bad_lineage)} "
              f"pcn={len(pending_pcns)} qa={len(open_actions)}",
              "all=0", [])

    # ── readiness rung from evidence depth ─────────────────────────────
    if not runs and not studies:
        readiness, reachable = READINESS_LADDER[0]
    elif not verified:
        readiness, reachable = READINESS_LADDER[1]
    elif not studies:
        readiness, reachable = READINESS_LADDER[2]
    elif qual_ok and not failed_open:
        readiness, reachable = READINESS_LADDER[3]
    else:
        readiness, reachable = READINESS_LADDER[2]

    return {
        "template_id": template_id,
        "gate_id": gate_id,
        "policy_version": POLICY_VERSION,
        "status": "blocked" if blockers else "pass",
        "blockers": [b.model_dump(mode="json") for b in blockers],
        "readiness": readiness,
        "readiness_reachable": reachable,
        "checks": checks,
        "evaluated_at": now.isoformat(),
    }
