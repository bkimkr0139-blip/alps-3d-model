"""ASIC Twin v1.1 R3 backend tests (EPIC I·J — 고도화지시서 §4/§10 R3).

Pinned here: an unresolved high-risk assumption blocks mask release and an
overdue assumption blocks too; assumption edits append to a change ledger AND
auto-create an impact scan whose findings start pending(rerun/review); an
assumption cannot be resolved while a scan is open; deviations keep skipped
activities visible and enforce requester ≠ decider; the copilot refuses to
answer without domain evidence (abstain), attaches evidence links to every
proposal, requires the diff sha256 before acceptance, and reproduces
byte-identical results for the same input snapshot.

Every test stands alone (tables are truncated between tests) — no ordering.
"""

import hashlib
import json as _json

from fastapi.testclient import TestClient

from tests.conftest import (
    APPROVER,
    ARCHITECT,
    ASIC_ENGINEER,
    QUALITY_ENGINEER,
    TEST_ENGINEER,
    as_user,
)


def canonical(o) -> str:
    return _json.dumps(o, sort_keys=True, ensure_ascii=False)

TPL = "current_sensor"


# ── helpers ──────────────────────────────────────────────────────────────────

def _assumption(client: TestClient, bid: str, *, risk: str = "high",
                downstream: list[dict] | None = None, due_in_days: float | None = None,
                template: str = TPL) -> dict:
    from datetime import datetime, timedelta, timezone

    body: dict = {
        "business_id": bid,
        "template_id": template,
        "title": "GMR 소자 감도 온도 드리프트 가정",
        "detail": "공급사 데이터시트 미확증 — 드리프트 ≤0.05 %/°C 로 가정하고 회로 설계 병행",
        "risk": risk,
        "confidence": 0.6,
        "owner": "test.asic",
        "downstream": downstream
        or [
            {"kind": "circuit", "ref": "CHAIN-1", "label": "아날로그 프론트엔드"},
            {"kind": "test", "ref": "TP-1", "label": "양산 테스트 프로그램"},
            {"kind": "quote", "ref": "TS-1", "label": "사업성 시나리오"},
        ],
    }
    if due_in_days is not None:
        body["due_at"] = (
            datetime.now(timezone.utc) + timedelta(days=due_in_days)
        ).isoformat()
    with as_user(client, ASIC_ENGINEER):  # CAN_DESIGN
        r = client.post("/api/v1/asic/assumptions", json=body,
                        headers={"Idempotency-Key": f"idem-{bid}"})
    assert r.status_code == 201, r.text
    return r.json()


def _gate(client: TestClient, template: str = TPL) -> dict:
    r = client.get(f"/api/v1/asic/gate-report/{template}")
    assert r.status_code == 200, r.text
    return r.json()


def _codes(gate: dict) -> set[str]:
    return {b["code"] for b in gate["blockers"]}  # model_dump() dicts — b["code"]


def _scans(client: TestClient, assumption_id: str) -> list[dict]:
    r = client.get(f"/api/v1/asic/assumptions/{assumption_id}/impact-scans")
    assert r.status_code == 200, r.text
    return r.json()


def _flow(client: TestClient, bid: str, *, template: str = TPL) -> dict:
    items = [
        {"seq": 1, "stage": "contact", "name": "Contact 전도성 확인",
         "limits": {"high": 5.0, "unit": "ohm"}, "expected_duration_s": 0.08,
         "site_count": 8,
         "defect_coverage": [{"defect_class": "open", "coverage_pct": 96.0},
                             {"defect_class": "short", "coverage_pct": 94.0}]},
        {"seq": 2, "stage": "dc", "name": "DC 파라미터 (오프셋)",
         "limits": {"low": -25.0, "high": 25.0, "unit": "uV"},
         "expected_duration_s": 0.12, "site_count": 8,
         "defect_coverage": [{"defect_class": "parametric", "coverage_pct": 90.0}]},
        {"seq": 3, "stage": "final_bin", "name": "ESD 내량 (HBM)",
         "limits": {"low": 2000.0, "unit": "V"}, "expected_duration_s": 0.35,
         "site_count": 4,
         "defect_coverage": [{"defect_class": "esd", "coverage_pct": 88.0}]},
    ]
    with as_user(client, ASIC_ENGINEER):  # CAN_ECO
        r = client.post("/api/v1/asic/test-flows", json={
            "business_id": bid, "template_id": template, "program_revision": 1,
            "silicon_revision": "A1", "target": "final_test", "items": items,
        }, headers={"Idempotency-Key": f"idem-{bid}"})
    assert r.status_code == 201, r.text
    return r.json()


def _fa_case(client: TestClient, bid: str, *, template: str = TPL) -> dict:
    with as_user(client, ASIC_ENGINEER):  # CAN_FA
        r = client.post("/api/v1/asic/fa-cases", json={
            "business_id": bid, "template_id": template, "scope": "lot",
            "lot_ref": "WL-09", "symptom": "ESD 스트레스 후 출력 스텝 변화 (HBM 2kV)",
            "observations": [{"fact": "입력단 게이트 산화막 손상 의심", "evidence_ref": "FA-IMG-1"}],
        }, headers={"Idempotency-Key": f"idem-{bid}"})
    assert r.status_code == 201, r.text
    return r.json()


def _run_copilot(client: TestClient, usecase: str, *, text: str | None = None,
                 fa_case_id: str | None = None, template: str = TPL,
                 user=QUALITY_ENGINEER, idem_salt: str = "") -> dict:
    body: dict = {"usecase": usecase}
    if text is not None:
        body["text"] = text
    if fa_case_id is not None:
        body["fa_case_id"] = fa_case_id
    with as_user(client, user):  # CAN_COPILOT
        idem = "idem-copl-" + hashlib.sha256(
            canonical({"usecase": usecase, "text": text, "fa": fa_case_id,
                       "salt": idem_salt}).encode()
        ).hexdigest()[:16]
        r = client.post(f"/api/v1/asic/copilot/{template}/run", json=body,
                        headers={"Idempotency-Key": idem})
    assert r.status_code == 201, r.text
    return r.json()


# ── EPIC I: assumptions → impact scans → gate ────────────────────────────────

def test_assumption_create_generates_first_impact_scan(client: TestClient):
    a = _assumption(client, "ASM-R3-01")
    scans = _scans(client, a["id"])
    assert len(scans) == 1
    scan = scans[0]
    assert scan["trigger"] == "created"
    assert scan["status"] == "open"
    kinds = {f["kind"]: f for f in scan["findings"]}
    assert set(kinds) == {"circuit", "test", "quote"}
    assert kinds["circuit"]["action"] == "rerun"
    assert kinds["quote"]["action"] == "review"
    assert all(f["status"] == "pending" for f in scan["findings"])


def test_high_risk_assumption_blocks_gate(client: TestClient):
    gate = _gate(client)
    assert "UNRESOLVED_HIGH_RISK_ASSUMPTION" not in _codes(gate)
    _assumption(client, "ASM-R3-02", risk="high")
    blocked = _codes(_gate(client))
    assert "UNRESOLVED_HIGH_RISK_ASSUMPTION" in blocked
    _assumption(client, "ASM-R3-03", risk="low")
    # low/medium risk는 차단하지 않는다 (이미 high가 있으니 여전히 blocked 상태)
    assert "UNRESOLVED_HIGH_RISK_ASSUMPTION" in _codes(_gate(client))


def test_assumption_overdue_blocks_gate(client: TestClient):
    _assumption(client, "ASM-R3-OD", risk="medium", due_in_days=-1.0)
    assert "ASSUMPTION_OVERDUE" in _codes(_gate(client))


def test_update_appends_ledger_and_auto_scans(client: TestClient):
    a = _assumption(client, "ASM-R3-04")
    with as_user(client, ASIC_ENGINEER):
        r = client.patch(f"/api/v1/asic/assumptions/{a['id']}",
                         json={"detail": "드리프트 가정을 0.08 %/°C 로 상향 (공급사 메일 확인)",
                               "confidence": 0.75},
                         headers={"Idempotency-Key": "idem-patch-1"})
    assert r.status_code == 200, r.text
    scans = _scans(client, a["id"])
    assert len(scans) == 2
    assert scans[0]["trigger"] == "assumption_changed"
    assert all(f["status"] == "pending" for f in scans[0]["findings"])
    # append-only ledger: created + field_changed, old/new 기록
    with as_user(client, ARCHITECT):
        ev = client.get(f"/api/v1/asic/assumptions/{a['id']}/events")
    assert ev.status_code == 200
    events = ev.json()
    assert [e["kind"] for e in events] == ["created", "field_changed"]
    changed = events[-1]["payload"]
    assert "0.6" in changed["confidence"]["old"] and "0.75" in changed["confidence"]["new"]


def test_resolve_blocked_until_scans_cleared(client: TestClient):
    a = _assumption(client, "ASM-R3-05")
    scan = _scans(client, a["id"])[0]
    refs = [f["ref"] for f in scan["findings"]]

    with as_user(client, ASIC_ENGINEER):
        # resolve는 열린 탐색이 있으면 거부 (재실행·재검토가 끝나기 전 종결 금지)
        r = client.post(f"/api/v1/asic/assumptions/{a['id']}/resolve",
                        json={"decision": "resolved", "evidence": {"ref": "DS-1"}})
        assert r.status_code == 412
        # 잘못된 ref는 404
        r = client.post(f"/api/v1/asic/impact-scans/{scan['id']}/findings/done",
                        json={"ref": "NOPE"})
        assert r.status_code == 404
        # pending이 남아 있으면 clear도 거부
        for ref in refs[:-1]:
            r = client.post(f"/api/v1/asic/impact-scans/{scan['id']}/findings/done",
                            json={"ref": ref})
            assert r.status_code == 200, r.text
        r = client.post(f"/api/v1/asic/impact-scans/{scan['id']}/clear")
        assert r.status_code == 412
        r = client.post(f"/api/v1/asic/impact-scans/{scan['id']}/findings/done",
                        json={"ref": refs[-1]})
        assert r.status_code == 200
        r = client.post(f"/api/v1/asic/impact-scans/{scan['id']}/clear")
        assert r.status_code == 200
        assert r.json()["status"] == "cleared"
        # 이제 resolve 가능, 재-resolve는 409
        r = client.post(f"/api/v1/asic/assumptions/{a['id']}/resolve",
                        json={"decision": "resolved",
                              "evidence": {"ref": "MEAS-7", "label": "실측 드리프트 0.041"},
                              "note": "측정 근거로 확정"})
        assert r.status_code == 200, r.text
        r = client.post(f"/api/v1/asic/assumptions/{a['id']}/resolve",
                        json={"decision": "invalidated"})
        assert r.status_code == 409
    assert "UNRESOLVED_HIGH_RISK_ASSUMPTION" not in _codes(_gate(client))


def test_deviation_independence_and_visibility(client: TestClient):
    with as_user(client, ASIC_ENGINEER):
        r = client.post("/api/v1/asic/deviations", json={
            "business_id": "DEV-R3-01", "template_id": TPL,
            "skipped": [{"stage": "ES", "ref": "ES-regression-r1",
                         "label": "ES 리그리션 전수 재실행 (CS 병행 진행으로 생략)"}],
            "rationale": "CS 일정 단축 — ES 리그리션을 CS 결과로 대체 검증",
            "residual_risk": "ES 회귀 미실행 상태로 CS 진입 — CS fail 시 ES 재실행 필요",
        }, headers={"Idempotency-Key": "idem-dev-1"})
        assert r.status_code == 201, r.text
        dev = r.json()
        assert dev["status"] == "submitted"
        # 본인 승인 금지 (독립성 규칙)
        r = client.post(f"/api/v1/asic/deviations/{dev['id']}/decide",
                        json={"decision": "approved"})
        assert r.status_code == 403, r.text
    with as_user(client, ARCHITECT):
        r = client.post(f"/api/v1/asic/deviations/{dev['id']}/decide",
                        json={"decision": "approved",
                              "note": "잔여 위험 수용 — CS fail 조건부 ES 재실행"})
        assert r.status_code == 200, r.text
        assert r.json()["decided_by"] == "test.architect"
        r = client.post(f"/api/v1/asic/deviations/{dev['id']}/decide",
                        json={"decision": "rejected"})
        assert r.status_code == 409
    # 수용기준 3: 생략된 활동은 숨겨지지 않고 승인된 편차로 조회된다
    with as_user(client, QUALITY_ENGINEER):
        r = client.get(f"/api/v1/asic/templates/{TPL}/deviations")
        assert r.status_code == 200
        rows = r.json()
    assert len(rows) == 1
    assert rows[0]["skipped"][0]["label"].startswith("ES 리그리션")
    assert rows[0]["status"] == "approved"


def test_assumption_rbac(client: TestClient):
    with as_user(client, TEST_ENGINEER):  # CAN_DESIGN 아님
        r = client.post("/api/v1/asic/assumptions", json={
            "business_id": "ASM-R3-RBAC", "template_id": TPL,
            "title": "권한 없는 가정", "detail": "x", "owner": "t",
        })
        assert r.status_code == 403


# ── EPIC J: evidence-grounded copilot ────────────────────────────────────────

def test_req_draft_diff_accept_flow(client: TestClient):
    it = _run_copilot(
        client, "req_draft",
        text="입력 오프셋은 25 uV 이하, 대역폭 8 kHz 이상, 부하 정전용량 100 pF 에서 동작",
    )
    assert it["result"]["abstain"] is False
    proposals = it["result"]["proposals"]
    assert len(proposals) >= 3
    assert all(p["evidence"] for p in proposals)  # 근거 링크 없는 제안은 생성 불가
    assert it["engine_version"] == "asic-copilot-rules-v1"
    assert it["input_hash"]  # 감사 재현 메타데이터

    pid = proposals[0]["pid"]
    # diff 엔드포인트가 서버 측 diff + 해시를 준다
    with as_user(client, ASIC_ENGINEER):
        d = client.get(f"/api/v1/asic/copilot/interactions/{it['id']}/proposals/{pid}/diff")
        assert d.status_code == 200, d.text
        diff = d.json()
        assert diff["diff"]  # 원문 대비 diff 본문
        # 틀린 해시로 수락 → 422 (diff를 확인하지 않았다는 뜻)
        r = client.post(f"/api/v1/asic/copilot/interactions/{it['id']}/proposals/accept",
                        json={"pid": pid, "diff_sha256": "0" * 64})
        assert r.status_code == 422, r.text
        # 올바른 해시로 수락 → 기록, 재수락 → 409
        r = client.post(f"/api/v1/asic/copilot/interactions/{it['id']}/proposals/accept",
                        json={"pid": pid, "diff_sha256": diff["sha256"]})
        assert r.status_code == 200, r.text
        assert r.json()["accepted_proposals"][0]["pid"] == pid
        assert r.json()["accepted_proposals"][0]["accepted_by"] == "test.asic"
        r = client.post(f"/api/v1/asic/copilot/interactions/{it['id']}/proposals/accept",
                        json={"pid": pid, "diff_sha256": diff["sha256"]})
        assert r.status_code == 409


def test_req_draft_abstains_without_measurable_quantity(client: TestClient):
    it = _run_copilot(client, "req_draft", text="고객은 양질의 제품과 안정적인 공급을 원합니다")
    assert it["result"]["abstain"] is True
    assert it["result"]["abstain_reason"] == "no_measurable_quantity"
    assert it["result"]["proposals"] == []


def test_copilot_abstains_on_empty_domain(client: TestClient):
    # 도메인 증거가 전혀 없는 템플릿에서는 답변 대신 보류 (수용기준: OOD·근거 부족 시 보류)
    for usecase, reason in [
        ("corner_sensitivity", "no_corner_studies"),
        ("similar_fa", "no_fa_cases"),
        ("test_efficiency", "no_test_flows"),
        ("wafer_anomaly", "no_wafer_maps"),
    ]:
        it = _run_copilot(client, usecase, text="쿼리")
        assert it["result"]["abstain"] is True, usecase
        assert it["result"]["abstain_reason"] == reason, usecase


def test_fa_hypothesis_with_confirm_tests(client: TestClient):
    flow = _flow(client, "TP-R3-01")
    case = _fa_case(client, "FAC-R3-01")
    it = _run_copilot(client, "fa_hypothesis", fa_case_id=case["id"])
    res = it["result"]
    assert res["abstain"] is False
    kinds = {p["kind"] for p in res["proposals"]}
    assert "fa_hypothesis" in kinds and "confirm_test" in kinds
    confirm = next(p for p in res["proposals"] if p["kind"] == "confirm_test")
    assert flow["business_id"] in " ".join(
        e["ref"] for e in confirm["evidence"]
    )
    # 근거: fa_case + test_flow 링크가 전부 달려 있다
    assert all(p["evidence"] for p in res["proposals"])


def test_gate_gap_summarizes_missing_evidence(client: TestClient):
    it = _run_copilot(client, "gate_gap")
    res = it["result"]
    assert res["abstain"] is False
    assert any("MOCK_RESULT_PRESENT" in f for f in res["facts"])
    assert any(e["kind"] == "gate_report" for e in res["evidence"])


def test_test_efficiency_with_wafer_retest_candidate(client: TestClient):
    """재시험률 ≥5% 웨이퍼 맵이 있어도 test_efficiency가 깨지지 않는다.

    regression: high_retest_review 후보에는 name/item_id가 없어 cand['name']
    KeyError → 500 (dev 시드의 retest 5.2% 맵에서 발견).
    """
    bins = [
        {"x": 0, "y": 0, "bin": 1, "site": 1},
        {"x": 1, "y": 0, "bin": 3, "site": 1},   # overkill
        {"x": 2, "y": 0, "bin": 2, "site": 2},   # retest
    ]
    gt = {"bad_xy": [[1, 0]], "note": "synthetic injection"}
    with as_user(client, TEST_ENGINEER):  # CAN_IMPORT
        r = client.post("/api/v1/asic/wafer-maps", json={
            "business_id": "WM-R3-RETEST", "template_id": TPL,
            "grid": {"rows": 1, "cols": 3}, "bins": bins, "ground_truth": gt,
            "source_class": "SYNTHETIC"},
            headers={"Idempotency-Key": "idem-wm-r3-retest"})
    assert r.status_code == 201, r.text
    _flow(client, "TP-R3-RETEST")
    it = _run_copilot(client, "test_efficiency", user=QUALITY_ENGINEER)
    res = it["result"]
    assert res["abstain"] is False
    assert any("high_retest_review" in f for f in res["facts"])
    assert all(p["evidence"] for p in res["proposals"])


def test_audit_reproducibility(client: TestClient):
    a = _assumption(client, "ASM-R3-09", risk="medium")
    it1 = _run_copilot(client, "gate_gap", idem_salt="1")
    it2 = _run_copilot(client, "gate_gap", idem_salt="2")
    assert it1["input_hash"] == it2["input_hash"]
    assert it1["result"]["facts"] == it2["result"]["facts"]
    assert it1["id"] != it2["id"]  # 각 상호작용은 별도 감사 행


def test_copilot_rbac(client: TestClient):
    from tests.conftest import MECH_ENGINEER

    with as_user(client, MECH_ENGINEER):  # CAN_COPILOT 아님
        r = client.post(f"/api/v1/asic/copilot/{TPL}/run", json={"usecase": "gate_gap"})
        assert r.status_code == 403
    # copilot은 게이트 증적 테이블을 건드리지 않는다 — 게이트는 여전히 평가 가능
    assert _gate(client)["policy_version"]
