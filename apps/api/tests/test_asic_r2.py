"""ASIC Twin v1.1 R2 backend tests (EPIC B·C·D·H — 고도화지시서 §4/§10).

Pinned here: TBD cost entries never compute as zero (their totals stay null
and are named); option 단가 is role-restricted while the list view is public
but redacted; the same (template, tool, input_hash) always joins one lineage;
results spanning design revisions block the gate; wafer-sort ↔ final-test
duplication/gap analysis and the wafer-map confusion matrix are plain
arithmetic; a limit change proposes with impact and only a human applies it
into a NEW revision; silicon/program revision mismatch blocks; and the
partner portal shows a partner ONLY its own rows while unapproved partners /
pending PCNs / open quality actions block the gate.

Every test stands alone (tables are truncated between tests) — no ordering.
"""

import hashlib
import json
import re as _re

from fastapi.testclient import TestClient

from tests.conftest import (
    APPROVER,
    ARCHITECT,
    ASIC_ENGINEER,
    MECH_ENGINEER,
    QUALITY_ENGINEER,
    TEST_ENGINEER,
    as_user,
)

TPL = "current_sensor"


def _opt_payload(bid: str, *, pkg_tooling_tbd: bool = False, tech: int = 4,
                 moq: int = 5000, wafer_base: float = 980_000.0) -> dict:
    nre = {
        "design": {"amount": 900_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
        "mask": {"amount": 2_400_000_000, "currency": "KRW", "basis_date": "2026-09-01"},
    }
    if pkg_tooling_tbd:
        nre["pkg_tooling"] = {"amount_tbd": "견적 대기"}
    else:
        nre["pkg_tooling"] = {"amount": 180_000_000, "currency": "KRW", "basis_date": "2026-09-01"}
    return {
        "business_id": bid, "template_id": TPL, "foundry": "F1 Fab (가명)", "node": "28nm",
        "package": "QFN-32", "moq": moq, "tech_score": tech, "nre": nre,
        "unit_cost": {
            "wafer": {"base": wafer_base, "best": wafer_base * 0.95, "worst": wafer_base * 1.1,
                      "unit": "KRW", "dies_per_wafer": 8200, "basis_date": "2026-09-01"},
            "assembly": {"base": 210.0, "unit": "KRW", "basis_date": "2026-09-01"},
            "final_test": {"base": 85.0, "unit": "KRW", "basis_date": "2026-09-01"},
            "logistics": {"base": 40.0, "unit": "KRW", "basis_date": "2026-09-01"},
            "die_yield": {"base": 0.82, "basis_date": "2026-09-01"},
            "scrap": {"base": 0.008, "basis_date": "2026-09-01"},
        },
        "schedule": [{"phase": "design", "weeks_base": 14, "weeks_best": 12, "weeks_worst": 20},
                     {"phase": "wafer", "weeks_base": 12, "weeks_best": 10, "weeks_worst": 16}],
        "risks": [{"kind": "long_lead", "note": "mask lead time", "severity": "medium"}],
    }


def _create_option(client: TestClient, bid: str, **kw) -> dict:
    with as_user(client, ASIC_ENGINEER):  # CAN_ECO
        r = client.post("/api/v1/asic/manufacturing-options", json=_opt_payload(bid, **kw),
                        headers={"Idempotency-Key": f"idem-{bid}"})
    assert r.status_code == 201, r.text
    return r.json()


def _tool_run(client: TestClient, bid: str, *, tool: str = "ams", input_hash: str,
              design_revision: int = 1, runner_class: str = "real_adapter",
              template: str = TPL) -> dict:
    with as_user(client, TEST_ENGINEER):  # CAN_IMPORT
        r = client.post("/api/v1/asic/tool-runs", json={
            "business_id": bid, "template_id": template,
            "design_revision": design_revision, "tool": tool, "tool_version": "ngspice-44",
            "runner_class": runner_class, "input_hash": input_hash,
            "output_hash": hashlib.sha256(bid.encode()).hexdigest(), "exit_code": 0,
        }, headers={"Idempotency-Key": f"idem-{bid}"})
    assert r.status_code == 201, r.text
    return r.json()


def _flow(client: TestClient, bid: str, target: str, *, silicon: str = "A1",
          template: str = TPL, extra_items: list | None = None,
          cost_rate: float | None = None) -> dict:
    items = [
        {"seq": 1, "stage": "contact", "name": "Contact 전도성 확인",
         "limits": {"high": 5.0, "unit": "ohm"}, "expected_duration_s": 0.08, "site_count": 8,
         "defect_coverage": [{"defect_class": "open", "coverage_pct": 96.0},
                             {"defect_class": "short", "coverage_pct": 94.0}]},
        {"seq": 2, "stage": "dc", "name": "DC 파라미터 (오프셋)",
         "limits": {"low": -25.0, "high": 25.0, "unit": "uV"},
         "expected_duration_s": 0.12, "site_count": 8,
         "defect_coverage": [{"defect_class": "parametric", "coverage_pct": 90.0}]},
    ]
    if extra_items:
        items.extend(extra_items)
    for i, it in enumerate(items, start=1):
        it["seq"] = i
    with as_user(client, ASIC_ENGINEER):  # CAN_ECO
        r = client.post("/api/v1/asic/test-flows", json={
            "business_id": bid, "template_id": template, "program_revision": 1,
            "silicon_revision": silicon, "compatible_mask_rev": "MASK-A1",
            "compatible_package_rev": "PKG-A1", "target": target,
            "cost_rate_per_site_hour": cost_rate, "items": items,
        }, headers={"Idempotency-Key": f"idem-{bid}"})
    assert r.status_code == 201, r.text
    return r.json()


def _traveler(client: TestClient, bid: str, lot_ref: str, *, silicon: str = "A1",
              steps: list | None = None, template: str = TPL) -> dict:
    if steps is None:
        steps = [{"partner_business_id": "PRT-A", "step": "fab", "result": "pass"}]
    with as_user(client, TEST_ENGINEER):  # CAN_IMPORT
        r = client.post("/api/v1/asic/lot-travelers", json={
            "business_id": bid, "template_id": template, "lot_ref": lot_ref,
            "silicon_revision": silicon, "mask_rev": "MASK-A1", "package_rev": "PKG-A1",
            "steps": steps,
        }, headers={"Idempotency-Key": f"idem-{bid}"})
    assert r.status_code == 201, r.text
    return r.json()


def _partner(client: TestClient, bid: str, *, status: str = "conditional") -> dict:
    with as_user(client, ASIC_ENGINEER):  # CAN_ECO
        r = client.post("/api/v1/asic/partners", json={
            "business_id": bid, "name": f"partner {bid}", "kind": "foundry",
            "status": status,
        }, headers={"Idempotency-Key": f"idem-{bid}"})
    assert r.status_code == 201, r.text
    return r.json()


def _blocker_codes(client: TestClient, template: str = TPL) -> list[str]:
    return sorted(b["code"] for b in client.get(f"/api/v1/asic/gate-report/{template}").json()["blockers"])


# ── EPIC B ──────────────────────────────────────────────────────────────────

def test_option_cost_redaction_and_role_gate(client: TestClient):
    opt = _create_option(client, "R2-OPT-REDACT")
    # public list — readable WITHOUT auth (EPIC B 수용기준 5 예외), but 단가는 redacted
    rows = client.get(f"/api/v1/asic/templates/{TPL}/manufacturing-options").json()
    row = next(r for r in rows if r["business_id"] == "R2-OPT-REDACT")
    assert row["nre"] is None and row["unit_cost"] is None and row["cost_restricted"] is True
    # detail costs need a cost role — a non-cost role is refused
    with as_user(client, MECH_ENGINEER):  # role outside CAN_COST
        r_denied = client.get(f"/api/v1/asic/manufacturing-options/{opt['id']}/costs")
    assert r_denied.status_code == 403
    with as_user(client, ASIC_ENGINEER):  # CAN_COST
        r_ok = client.get(f"/api/v1/asic/manufacturing-options/{opt['id']}/costs")
    assert r_ok.status_code == 200
    assert r_ok.json()["unit_cost"]["wafer"]["base"] == 980_000.0


def test_tbd_never_computes_as_zero(client: TestClient):
    """수용기준: 미확정 값은 TBD이며 0으로 계산되지 않는다 — B55 pkg_tooling
    TBD → NRE 합계·상각 곡선·연간 총액이 null이고 partial이 아니라 곡선만 null."""
    full = _create_option(client, "R2-OPT-FULL")
    tbd = _create_option(client, "R2-OPT-TBD", pkg_tooling_tbd=True, wafer_base=500_000.0)
    with as_user(client, ASIC_ENGINEER):
        r = client.post("/api/v1/asic/trade-studies", json={
            "business_id": "R2-TS-TBD", "template_id": TPL, "title": "TBD rule",
            "option_ids": [full["id"], tbd["id"]],
            "weights": {"cost": 0.4, "schedule": 0.2, "technology": 0.2, "supply": 0.2},
            "annual_volume": 1_000_000,
        }, headers={"Idempotency-Key": "idem-r2-ts-tbd"})
    assert r.status_code == 201, r.text
    res = r.json()["result"]
    per = {p["business_id"]: p for p in res["per_option"]}
    assert per["R2-OPT-FULL"]["nre_total"] is not None
    assert per["R2-OPT-FULL"]["annual_volume_cost"] is not None
    # the TBD option: named components, null totals — never 0
    assert per["R2-OPT-TBD"]["nre_tbd_components"] == ["pkg_tooling"]
    assert per["R2-OPT-TBD"]["nre_total"] is None
    assert per["R2-OPT-TBD"]["amortized"][0]["total_cost"] is None
    assert per["R2-OPT-TBD"]["annual_volume_cost"] is None
    assert res["tbd_note"]


def test_trade_study_decision_records_approver_and_blocks_redecision(client: TestClient):
    a = _create_option(client, "R2-OPT-DA", tech=5)
    b = _create_option(client, "R2-OPT-DB", tech=2)
    with as_user(client, ASIC_ENGINEER):
        study = client.post("/api/v1/asic/trade-studies", json={
            "business_id": "R2-TS-DEC", "template_id": TPL, "title": "decision flow",
            "option_ids": [a["id"], b["id"]],
            "weights": {"cost": 1.0}, "annual_volume": 100_000,
        }, headers={"Idempotency-Key": "idem-r2-ts-dec"}).json()
    winner = study["result"]["ranking"][0]
    # decision is close-level: an engineer cannot make it
    with as_user(client, ASIC_ENGINEER):
        r_denied = client.post(f"/api/v1/asic/trade-studies/{study['id']}/decision", json={
            "option_id": winner, "rationale": "engineer should not decide"})
    assert r_denied.status_code == 403
    with as_user(client, ARCHITECT):  # CAN_ECO_CLOSE
        r_ok = client.post(f"/api/v1/asic/trade-studies/{study['id']}/decision", json={
            "option_id": winner, "rationale": "가중 점수 1위",
            "residual_risks": ["mask lead time"]},
            headers={"Idempotency-Key": "idem-r2-ts-decide"})
    assert r_ok.status_code == 200, r_ok.text
    dec = r_ok.json()["decision"]
    assert dec["option_id"] == winner and dec["rationale"] and dec["residual_risks"]
    assert r_ok.json()["status"] == "decided"
    with as_user(client, ARCHITECT):
        r_again = client.post(f"/api/v1/asic/trade-studies/{study['id']}/decision", json={
            "option_id": winner, "rationale": "re-decide"})
    assert r_again.status_code == 409


def test_trade_study_rejects_cross_template_and_unknown_options(client: TestClient):
    a = _create_option(client, "R2-OPT-XA")
    b = _create_option(client, "R2-OPT-XB")
    with as_user(client, ASIC_ENGINEER):
        other = client.post("/api/v1/asic/manufacturing-options", json={
            **_opt_payload("R2-OPT-ENV"), "template_id": "env_sensor"},
            headers={"Idempotency-Key": "idem-r2-opt-env"})
        assert other.status_code == 201
        r_cross = client.post("/api/v1/asic/trade-studies", json={
            "business_id": "R2-TS-X", "template_id": TPL, "title": "cross",
            "option_ids": [a["id"], other.json()["id"]], "weights": {"cost": 1.0},
            "annual_volume": 1000}, headers={"Idempotency-Key": "idem-r2-ts-x"})
        assert r_cross.status_code == 422
        assert r_cross.json()["detail"]["offending"] == ["R2-OPT-ENV"]
        import uuid as _u
        probe = str(_u.uuid4())  # never persisted → the only unresolved id
        r_missing = client.post("/api/v1/asic/trade-studies", json={
            "business_id": "R2-TS-M", "template_id": TPL, "title": "missing",
            "option_ids": [a["id"], probe], "weights": {"cost": 1.0},
            "annual_volume": 1000}, headers={"Idempotency-Key": "idem-r2-ts-m"})
    assert r_missing.status_code == 422
    assert r_missing.json()["detail"]["unresolved"] == [probe]


# ── EPIC C ──────────────────────────────────────────────────────────────────

def test_tool_run_lineage_groups_same_input_and_splits_new_input(client: TestClient):
    ih = hashlib.sha256(b"netlist v1").hexdigest()
    a = _tool_run(client, "R2-TR-L1", input_hash=ih, tool="ams")
    b = _tool_run(client, "R2-TR-L2", input_hash=ih, tool="ams")
    assert a["lineage_id"] == b["lineage_id"]  # same input joins the lineage
    c = _tool_run(client, "R2-TR-L3", input_hash=hashlib.sha256(b"netlist v2").hexdigest(),
                  tool="ams")
    assert c["lineage_id"] != a["lineage_id"]  # a different input never joins
    # mock runs are recorded but distinguishable from real adapters
    m = _tool_run(client, "R2-TR-MOCK", input_hash=hashlib.sha256(b"lint").hexdigest(),
                  tool="lint", runner_class="mock")
    assert m["runner_class"] == "mock"
    rows = client.get(f"/api/v1/asic/templates/{TPL}/tool-runs").json()
    assert {r["business_id"] for r in rows} >= {"R2-TR-L1", "R2-TR-L2", "R2-TR-L3"}


def test_tool_run_input_hash_must_be_sha256(client: TestClient):
    with as_user(client, TEST_ENGINEER):
        r = client.post("/api/v1/asic/tool-runs", json={
            "business_id": "R2-TR-BAD", "template_id": TPL, "design_revision": 1,
            "tool": "ams", "tool_version": "x", "runner_class": "real_adapter",
            "input_hash": "nothex", "exit_code": 0},
            headers={"Idempotency-Key": "idem-r2-tr-bad"})
    assert r.status_code == 422


def test_gate_blocks_mixed_design_revision_tool_results(client: TestClient):
    """수용기준 2: 한 게이트의 EDA 결과는 하나의 설계 리비전에 있어야 한다."""
    ih = hashlib.sha256(b"mixed-net").hexdigest()
    _tool_run(client, "R2-TR-REV1", input_hash=ih, design_revision=1)
    assert "MIXED_REVISION_EVIDENCE" not in _blocker_codes(client)
    _tool_run(client, "R2-TR-REV2", input_hash=hashlib.sha256(b"mixed-net-2").hexdigest(),
              design_revision=2)
    assert "MIXED_REVISION_EVIDENCE" in _blocker_codes(client)


# ── EPIC D ──────────────────────────────────────────────────────────────────

def test_flow_totals_coverage_and_tbd_cost(client: TestClient):
    flow = _flow(client, "R2-TF-WS", "wafer_sort", cost_rate=None)
    rep = client.get(f"/api/v1/asic/templates/{TPL}/test-flow-analysis").json()
    ws = rep["per_target"]["wafer_sort"]
    assert ws["flow_id"] == flow["id"]
    # wall time = 0.08/8 + 0.12/8 = 0.025 s per die (sites run in parallel)
    assert ws["totals"]["wall_time_s_per_die"] == 0.025
    assert ws["totals"]["cost_per_die"] is None  # rate 미확정 → TBD (0 아님)
    cov = ws["coverage"]
    assert cov["per_class"]["open"]["coverage_pct"] == 96.0
    assert cov["per_class"]["parametric"]["coverage_pct"] == 90.0
    assert "esd" in cov["uncovered_classes"] and "latchup" in cov["uncovered_classes"]
    # final test (full pack) re-covers esd/latchup → no gap for them
    _flow(client, "R2-TF-FT", "final_test", cost_rate=14500.0, extra_items=[
        {"stage": "interface", "name": "ESD (HBM 2kV)", "expected_duration_s": 0.1,
         "site_count": 2, "defect_coverage": [{"defect_class": "esd", "coverage_pct": 92.0}]},
        {"stage": "interface", "name": "Latch-up (25mA)", "expected_duration_s": 0.1,
         "site_count": 2, "defect_coverage": [{"defect_class": "latchup", "coverage_pct": 90.0}]},
        {"stage": "final_bin", "name": "최종 빈 분류", "expected_duration_s": 0.02,
         "site_count": 8},
    ])
    rep2 = client.get(f"/api/v1/asic/templates/{TPL}/test-flow-analysis").json()
    cross = rep2["cross_target"]
    assert cross is not None
    # DC 파라미터 appears on both targets with identical limits → drop candidate
    dups = {d["name"]: d for d in cross["duplicates"]}
    dc = dups["DC 파라미터 (오프셋)"]
    assert dc["same_limits"] is True and dc["drop_candidate"] is True
    # contact도 동일 limits 중복
    assert dups["Contact 전도성 확인"]["drop_candidate"] is True
    # both shared classes are re-covered on final → gaps empty for this pair
    assert [g["defect_class"] for g in cross["coverage_gaps"] if g["defect_class"] in
            ("parametric", "open", "short")] == []
    # a sort-side class the final test never re-covers is a gap:
    # wafer sort keeps a leakage screen the final flow does not repeat
    _flow(client, "R2-TF-WS2", "wafer_sort", extra_items=[
        {"stage": "dc", "name": "누설 전류 (reverse)", "expected_duration_s": 0.05,
         "site_count": 8, "defect_coverage": [{"defect_class": "leakage", "coverage_pct": 87.0}]},
    ])
    rep3 = client.get(f"/api/v1/asic/templates/{TPL}/test-flow-analysis").json()
    gaps = [g["defect_class"] for g in rep3["cross_target"]["coverage_gaps"]]
    assert "leakage" in gaps


def test_limit_change_proposes_with_impact_then_supersedes_on_apply(client: TestClient):
    """수용기준 2: 한계값 변경 시 영향받는 로트·제품·인증 증적 자동 표시.
    수용기준 1과 불변규칙 1: 적용은 인간(close 역할), 원 flow는 supersede."""
    flow = _flow(client, "R2-TF-LC", "final_test", cost_rate=14500.0)
    _partner(client, "PRT-A")
    _traveler(client, "R2-LT-LC", "LOT-LC-01")
    flow_detail = next(
        f for f in client.get(f"/api/v1/asic/templates/{TPL}/test-flows").json()
        if f["id"] == flow["id"]
    )
    item = next(it for it in flow_detail["items"] if it["name"] == "DC 파라미터 (오프셋)")
    with as_user(client, ASIC_ENGINEER):
        r = client.post(f"/api/v1/asic/test-flows/{flow['id']}/limit-changes", json={
            "item_id": item["id"],
            "new_limits": {"low": -20.0, "high": 20.0, "unit": "uV"},
            "rationale": "가드밴드 축소 검토",
        }, headers={"Idempotency-Key": "idem-r2-lc"})
    assert r.status_code == 201, r.text
    lc = r.json()
    assert lc["status"] == "proposed"
    assert lc["impact"]["delta"] == {"low": {"old": -25.0, "new": -20.0},
                                     "high": {"old": 25.0, "new": 20.0}}
    assert lc["impact"]["affected_lots"][0]["lot_ref"] == "LOT-LC-01"
    assert lc["impact"]["affected_measurement_runs"] == []
    assert lc["impact"]["review_only"] is True
    # applying is close-level
    with as_user(client, ASIC_ENGINEER):
        r_denied = client.post(f"/api/v1/asic/limit-changes/{lc['id']}/apply")
    assert r_denied.status_code == 403
    with as_user(client, ARCHITECT):
        r_apply = client.post(f"/api/v1/asic/limit-changes/{lc['id']}/apply",
                              headers={"Idempotency-Key": "idem-r2-lc-apply"})
    assert r_apply.status_code == 200, r_apply.text
    new_flow = r_apply.json()
    assert new_flow["program_revision"] == 2
    assert new_flow["status"] == "draft"
    new_item = next(it for it in new_flow["items"] if it["name"] == "DC 파라미터 (오프셋)")
    assert new_item["limits"] == {"low": -20.0, "high": 20.0, "unit": "uV"}
    old_now = next(
        f for f in client.get(f"/api/v1/asic/templates/{TPL}/test-flows").json()
        if f["id"] == flow["id"]
    )
    assert old_now["status"] == "superseded"
    with as_user(client, ARCHITECT):
        r_again = client.post(f"/api/v1/asic/limit-changes/{lc['id']}/apply")
    assert r_again.status_code == 409


def test_gate_blocks_program_silicon_revision_mismatch(client: TestClient):
    """수용기준 3: 프로그램과 실리콘 리비전 불일치 시 차단."""
    _partner(client, "PRT-A")
    _flow(client, "R2-TF-A1", "wafer_sort", silicon="A1")
    _traveler(client, "R2-LT-A1", "LOT-A1", silicon="A1")
    assert "TEST_PROGRAM_REV_MISMATCH" not in _blocker_codes(client)
    _traveler(client, "R2-LT-B1", "LOT-B1", silicon="B1")
    assert "TEST_PROGRAM_REV_MISMATCH" in _blocker_codes(client)


def test_wafer_map_confusion_matrix_and_ground_truth_guard(client: TestClient):
    """오버킬/언더킬 = 공개된 합성 ground truth에 대한 혼동행렬 산술."""
    bins = [
        {"x": 0, "y": 0, "bin": 1, "site": 1},   # good, good
        {"x": 1, "y": 0, "bin": 3, "site": 1},   # fail, good → OVERKILL
        {"x": 2, "y": 0, "bin": 1, "site": 2},   # good, BAD → UNDERKILL
        {"x": 3, "y": 0, "bin": 3, "site": 2},   # fail, bad → detected
        {"x": 4, "y": 0, "bin": 2, "site": 2},   # retest
    ]
    gt = {"bad_xy": [[2, 0], [3, 0]], "note": "synthetic injection"}
    with as_user(client, TEST_ENGINEER):
        r = client.post("/api/v1/asic/wafer-maps", json={
            "business_id": "R2-WM-1", "template_id": TPL, "grid": {"rows": 1, "cols": 5},
            "bins": bins, "ground_truth": gt, "source_class": "SYNTHETIC"},
            headers={"Idempotency-Key": "idem-r2-wm"})
    assert r.status_code == 201, r.text
    a = r.json()["analysis"]
    assert a["total"] == 5
    assert a["yield_pct"] == 40.0
    assert a["retest_rate_pct"] == 20.0
    conf = a["confusion"]
    assert conf["bad_dies"] == 2 and conf["detected"] == 1
    assert conf["escaped_underkill"] == 1 and conf["underkill_xy"] == [[2, 0]]
    assert conf["overkill_count"] == 1 and conf["overkill_xy"] == [[1, 0]]
    # ground truth on a non-SYNTHETIC map is refused — no fake yield data
    with as_user(client, TEST_ENGINEER):
        r_bad = client.post("/api/v1/asic/wafer-maps", json={
            "business_id": "R2-WM-2", "template_id": TPL, "grid": {"rows": 1, "cols": 1},
            "bins": bins[:1], "ground_truth": gt, "source_class": "REAL_MEASURED"},
            headers={"Idempotency-Key": "idem-r2-wm2"})
    assert r_bad.status_code == 422


def test_optimization_proposals_are_review_only(client: TestClient):
    """수용기준 4: AI는 시험 삭제를 자동 적용하지 않고 검토안만 생성한다."""
    _flow(client, "R2-TF-PROP-WS", "wafer_sort")  # twin target: 동일 항목이 sort에 존재
    flow = _flow(client, "R2-TF-PROP", "final_test", cost_rate=14500.0, extra_items=[
        {"stage": "analog", "name": "Contact 전도성 확인", "expected_duration_s": 0.08,
         "site_count": 8, "limits": {"high": 5.0, "unit": "ohm"}},  # duplicate, no links
    ])
    r = client.get(f"/api/v1/asic/test-flows/{flow['id']}/proposals").json()
    assert r["review_only"] is True and r["note"]
    kinds = [p["kind"] for p in r["proposals"]]
    assert "duplicate_removal_review" in kinds       # wafer sort 쪽과 중복
    assert "unlinked_item_review" in kinds           # 링크 없는 항목
    for p in r["proposals"]:
        assert p["review_only"] is True
    # proposals are read-only: there is no apply/execute endpoint
    apply_attempt = client.post(f"/api/v1/asic/test-flows/{flow['id']}/proposals")
    assert apply_attempt.status_code == 405


def test_optimization_proposals_on_wafer_sort_flow(client: TestClient):
    """wafer_sort flow 자신의 proposals도 조회 가능해야 한다 (drop 후보는 이 flow 쪽
    항목을 가리킨다) — regression: final_item_id 하드코딩 StopIteration → 500."""
    ws = _flow(client, "R2-TF-PROP-WS2", "wafer_sort")
    _flow(client, "R2-TF-PROP-FT2", "final_test", extra_items=[
        {"stage": "analog", "name": "Contact 전도성 확인", "expected_duration_s": 0.08,
         "site_count": 8, "limits": {"high": 5.0, "unit": "ohm"}},  # sort 쪽과 중복
    ])
    r = client.get(f"/api/v1/asic/test-flows/{ws['id']}/proposals")
    assert r.status_code == 200, r.text
    body = r.json()
    own_ids = {it["id"] for it in ws["items"]}
    dups = [p for p in body["proposals"] if p["kind"] == "duplicate_removal_review"]
    assert dups, "sort 측 중복 항목이 검토안으로 나와야 한다"
    for p in dups:
        assert p["item_id"] in own_ids  # 이 flow(=wafer sort)의 항목을 가리킴
        assert "wafer sort 반복" in p["rationale"]
        assert p["review_only"] is True


# ── EPIC H ──────────────────────────────────────────────────────────────────

def test_partner_lifecycle_and_approval_role(client: TestClient):
    p = _partner(client, "PRT-R2-A")
    assert p["status"] == "conditional"  # create can NOT self-approve
    with as_user(client, ASIC_ENGINEER):
        r_denied = client.post(f"/api/v1/asic/partners/{p['id']}/approve")
    assert r_denied.status_code == 403
    with as_user(client, ARCHITECT):
        r_ok = client.post(f"/api/v1/asic/partners/{p['id']}/approve",
                           headers={"Idempotency-Key": "idem-appr"})
        assert r_ok.status_code == 200
        assert r_ok.json()["status"] == "approved"
        assert r_ok.json()["approved_at"] is not None
        r_again = client.post(f"/api/v1/asic/partners/{p['id']}/approve")
    assert r_again.status_code == 409


def test_lot_traveler_requires_known_partners(client: TestClient):
    _partner(client, "PRT-A")
    _traveler(client, "R2-LT-OK", "LOT-OK")
    with as_user(client, TEST_ENGINEER):
        r_unknown = client.post("/api/v1/asic/lot-travelers", json={
            "business_id": "R2-LT-BAD", "template_id": TPL, "lot_ref": "LOT-BAD",
            "silicon_revision": "A1",
            "steps": [{"partner_business_id": "PRT-NOSUCH", "step": "fab"}]},
            headers={"Idempotency-Key": "idem-r2-lt-bad"})
    assert r_unknown.status_code == 404


def test_partner_artifact_dedup_by_file_hash(client: TestClient):
    _partner(client, "PRT-A")
    _traveler(client, "R2-LT-PA", "LOT-PA")
    h = hashlib.sha256(b"report bytes").hexdigest()
    with as_user(client, TEST_ENGINEER):
        body = {
            "business_id": "R2-PA-1", "partner_business_id": "PRT-A", "template_id": TPL,
            "kind": "test_report", "file_hash": h,
        }
        r1 = client.post("/api/v1/asic/partner-artifacts", json=body,
                         headers={"Idempotency-Key": "idem-pa-1"})
        assert r1.status_code == 201, r1.text
        body2 = {**body, "business_id": "R2-PA-2"}
        r2 = client.post("/api/v1/asic/partner-artifacts", json=body2,
                         headers={"Idempotency-Key": "idem-pa-2"})
    assert r2.status_code == 409
    assert r2.json()["detail"]["existing_business_id"] == "R2-PA-1"


def test_gate_blocks_pending_pcn_until_approved(client: TestClient):
    _partner(client, "PRT-A")
    _traveler(client, "R2-LT-PCN", "LOT-PCN")
    with as_user(client, TEST_ENGINEER):
        r = client.post("/api/v1/asic/partner-changes", json={
            "business_id": "R2-PCN-1", "partner_business_id": "PRT-A",
            "kind": "site_transfer", "description": "2사이트 이전",
            "affected_template_ids": [TPL]},
            headers={"Idempotency-Key": "idem-pcn"})
    assert r.status_code == 201, r.text
    pcn = r.json()
    assert pcn["status"] == "submitted"
    assert "PARTNER_CHANGE_PENDING" in _blocker_codes(client)
    with as_user(client, ARCHITECT):
        r_appr = client.post(f"/api/v1/asic/partner-changes/{pcn['id']}/review", json={
            "decision": "approved", "note": "동등성 확인"},
            headers={"Idempotency-Key": "idem-pcn-appr"})
    assert r_appr.status_code == 200
    assert r_appr.json()["status"] == "approved"
    assert r_appr.json()["reviewed_by"] == "test.architect"
    assert "PARTNER_CHANGE_PENDING" not in _blocker_codes(client)
    with as_user(client, ARCHITECT):
        r_again = client.post(f"/api/v1/asic/partner-changes/{pcn['id']}/review", json={
            "decision": "rejected"})
    assert r_again.status_code == 409


def test_gate_blocks_unapproved_partner_and_open_quality_action(client: TestClient):
    _partner(client, "PRT-A")  # conditional — never approved
    _traveler(client, "R2-LT-UNA", "LOT-UNA")
    codes = _blocker_codes(client)
    assert "PARTNER_NOT_APPROVED" in codes
    assert "LINEAGE_INVALID" not in codes  # path is complete, partner just unapproved
    with as_user(client, QUALITY_ENGINEER):
        r = client.post("/api/v1/asic/quality-actions", json={
            "business_id": "R2-QA-1", "template_id": TPL, "lot_ref": "LOT-UNA",
            "action": "hold", "reason": "오버킬 급증"},
            headers={"Idempotency-Key": "idem-qa"})
    assert r.status_code == 201, r.text
    qa = r.json()
    assert qa["status"] == "open" and qa["partner_id"] is None  # traveler 미연결
    assert "QUALITY_ACTION_OPEN" in _blocker_codes(client)
    with as_user(client, QUALITY_ENGINEER):
        r_close = client.post(f"/api/v1/asic/quality-actions/{qa['id']}/close", json={
            "note": "프로브 카드 교체"}, headers={"Idempotency-Key": "idem-qa-close"})
    assert r_close.status_code == 200
    assert "QUALITY_ACTION_OPEN" not in _blocker_codes(client)


def test_portal_isolates_partner_data(client: TestClient):
    """파트너 격리: 포털은 자기 partner_id의 rows만 본다 (mocked principal)."""
    _partner(client, "PRT-A")
    _partner(client, "PRT-B")
    _traveler(client, "R2-LT-A", "LOT-A",
              steps=[{"partner_business_id": "PRT-A", "step": "fab"}])
    _traveler(client, "R2-LT-B", "LOT-B",
              steps=[{"partner_business_id": "PRT-B", "step": "fab"}])
    h = hashlib.sha256(b"A-only report").hexdigest()
    with as_user(client, TEST_ENGINEER):
        r = client.post("/api/v1/asic/partner-artifacts", json={
            "business_id": "R2-PA-A1", "partner_business_id": "PRT-A", "template_id": TPL,
            "kind": "test_report", "file_hash": h},
            headers={"Idempotency-Key": "idem-pa-a1"})
    assert r.status_code == 201
    dash_a = client.get("/api/v1/asic/portal/PRT-A/dashboard").json()
    dash_b = client.get("/api/v1/asic/portal/PRT-B/dashboard").json()
    assert [lt["lot_ref"] for lt in dash_a["lot_travelers"]] == ["LOT-A"]
    assert [lt["lot_ref"] for lt in dash_b["lot_travelers"]] == ["LOT-B"]
    assert [a["business_id"] for a in dash_a["artifacts"]] == ["R2-PA-A1"]
    assert dash_b["artifacts"] == []
    assert dash_b["partner"]["business_id"] == "PRT-B"


# ── P1-08: 3-language evidence report ───────────────────────────────────────

def _report(client: TestClient, lang: str):
    return client.get(f"/api/v1/asic/templates/{TPL}/evidence-report?lang={lang}")


def test_evidence_report_localizes_all_three_languages(client: TestClient):
    """ko/en/ja all render with native labels — TBD named, never 0, money
    withheld, and a ja report never leaks Korean labels."""
    a = _create_option(client, "R2-OPT-ER-A", pkg_tooling_tbd=True)
    b = _create_option(client, "R2-OPT-ER-B")
    _flow(client, "R2-TF-ER", "wafer_sort")  # TBD cost rate + base item pack
    with as_user(client, ASIC_ENGINEER):
        r = client.post("/api/v1/asic/trade-studies", json={
            "business_id": "R2-TS-ER", "template_id": TPL, "title": "report",
            "option_ids": [a["id"], b["id"]], "weights": {"cost": 1.0},
            "annual_volume": 1000}, headers={"Idempotency-Key": "idem-r2-ts-er"})
    assert r.status_code == 201

    reports = {}
    for lang in ("ko", "en", "ja"):
        resp = _report(client, lang)
        assert resp.status_code == 200, (lang, resp.text)
        reports[lang] = resp.json()

    ja = reports["ja"]
    assert ja["lang"] == "ja"
    assert ja["title"] == "ASICエビデンス報告書"
    assert all(s["title"] and s["title"] != reports["ko"]["title"] for s in ja["sections"])
    ja_labels = {r["label"] for s in ja["sections"] for r in s["rows"]}
    assert ja_labels
    # the leak check: proper nouns (ECO…) repeat across languages by design,
    # but no Korean script may appear in a ja (or en) report
    assert not any(_re.search(r"[가-힣]", str(r["label"])) for s in ja["sections"] for r in s["rows"])
    assert not any(_re.search(r"[가-힣]", str(r["value"])) for s in ja["sections"] for r in s["rows"])

    tp = next(s for s in ja["sections"] if s["key"] == "test_program")
    assert "TBD" in json.dumps(tp, ensure_ascii=False)  # TBD cost named, not 0
    assert "0으로 계산" not in json.dumps(tp, ensure_ascii=False)

    trade = next(s for s in reports["en"]["sections"] if s["key"] == "trade_study")
    flat = json.dumps(trade, ensure_ascii=False)
    assert "CAN_COST" in flat  # money withheld from the report
    gate = next(s for s in reports["ko"]["sections"] if s["key"] == "gate")
    assert gate["rows"][0]["label"] == "블로커"


def test_evidence_report_rejects_unknown_language(client: TestClient):
    r = _report(client, "zh")
    assert r.status_code == 422
    assert set(r.json()["detail"]["supported"]) == {"ko", "en", "ja"}
