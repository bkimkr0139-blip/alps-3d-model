"""Defect → FailureAnalysis → CAPA workflow (HANDOFF §5 item 4).

Covers: RBAC on every write endpoint, the CAPA state machine's valid/invalid
transitions, the append-only CapaEvent ledger, and one full happy-path
lifecycle (defect → FA → CAPA → approve → implement → verify → close) with
effectiveness verification linked to a real TestRun (not a free-text claim).
"""

import io

from fastapi.testclient import TestClient

from app.security import CurrentUser

from .conftest import ARCHITECT, MECH_ENGINEER, as_user

QUALITY = CurrentUser(subject="test-quality", username="test.quality", roles=frozenset({"quality_engineer"}))
APPROVER2 = CurrentUser(subject="test-approver2", username="test.approver2", roles=frozenset({"reviewer_approver"}))


def _variant(client: TestClient, suffix: str = "FC") -> str:
    product = client.post("/api/v1/products", json={"business_id": f"PROD-{suffix}", "name": "P"}).json()
    variant = client.post(
        f"/api/v1/products/{product['id']}/variants", json={"business_id": f"VAR-{suffix}", "name": "V"}
    ).json()
    return variant["id"]


def _mold_cavity_lot(client: TestClient, variant_id: str, suffix: str) -> tuple[str, str]:
    mold = client.post(
        "/api/v1/molds", json={"business_id": f"MOLD-{suffix}", "name": "금형", "tool_revision": "A"}
    ).json()
    cavity = client.post(
        f"/api/v1/molds/{mold['id']}/cavities", json={"business_id": f"CAV-{suffix}", "cavity_no": 1, "label": "C1"}
    ).json()
    lot = client.post(
        "/api/v1/lots",
        json={
            "business_id": f"LOT-{suffix}",
            "variant_id": variant_id,
            "mold_id": mold["id"],
            "cavity_id": cavity["id"],
            "produced_at": "2026-09-01T09:00:00Z",
        },
    ).json()
    return mold["id"], lot["id"]


def _defect(client: TestClient, lot_id: str, bid: str) -> dict:
    resp = client.post(
        "/api/v1/defects",
        json={
            "business_id": bid,
            "lot_id": lot_id,
            "defect_class": "contact_resistance_high",
            "severity": "major",
            "quantity": 3,
            "note": "접점저항 규격 초과",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _test_run(client: TestClient, variant_id: str, lot_id: str, bid: str) -> str:
    """A real retest TestRun on the lot — used as the effectiveness-
    verification anchor (never a free-text claim)."""
    as_user(client, MECH_ENGINEER)
    plan = client.post(
        "/api/v1/test-plans", json={"business_id": f"TP-{bid}", "variant_id": variant_id, "name": "retest"}
    ).json()
    run = client.post(
        "/api/v1/test-runs",
        json={"business_id": f"TR-{bid}", "test_plan_id": plan["id"], "lot_id": lot_id,
              "executed_at": "2026-09-02T10:00:00Z"},
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    csv = io.BytesIO(b"x_value,y_value\n0.0,300\n0.05,310\n")
    up = client.post(
        f"/api/v1/test-runs/{run_id}/measurements",
        files={"file": (f"{bid}.csv", csv, "text/csv")},
        data={"x_unit": "mm", "y_unit": "mN"},
    )
    assert up.status_code == 200, up.text
    as_user(client, ARCHITECT)
    return run_id


def _fa(client: TestClient, defect_id: str, bid: str, *, confirmed: bool = True) -> dict:
    resp = client.post(
        f"/api/v1/defects/{defect_id}/failure-analyses",
        json={
            "business_id": bid,
            "method": "5-Why",
            "findings": "접점 도금 두께 불균일로 접촉저항 상승 관찰.",
            "analyst": "test.quality",
            "analyzed_at": "2026-09-01T12:00:00Z",
            "root_cause": "도금 공정 편차",
            "root_cause_confirmed": confirmed,
            "evidence": [{"kind": "process_run", "business_id": "OP-10-RUN-1", "note": "관련 공정"}],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _capa(client: TestClient, fa_id: str, bid: str) -> dict:
    resp = client.post(
        f"/api/v1/failure-analyses/{fa_id}/capas",
        json={
            "business_id": bid,
            "title": "도금 공정 파라미터 재관리",
            "capa_type": "corrective",
            "description": "도금 두께 관리 범위를 재설정하고 SPC 관리도를 적용한다.",
            "owner": "test.quality",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# -- FA -----------------------------------------------------------------------


def test_create_failure_analysis_requires_quality_role(client):
    variant_id = _variant(client)
    _mold_id, lot_id = _mold_cavity_lot(client, variant_id, "R1")
    defect = _defect(client, lot_id, "DEF-R1")

    as_user(client, MECH_ENGINEER)  # lacks quality_engineer/manufacturing_engineer/system_architect
    resp = client.post(
        f"/api/v1/defects/{defect['id']}/failure-analyses",
        json={
            "business_id": "FA-R1",
            "method": "5-Why",
            "findings": "x",
            "analyst": "a",
            "analyzed_at": "2026-09-01T12:00:00Z",
        },
    )
    assert resp.status_code == 403

    as_user(client, QUALITY)
    resp = client.post(
        f"/api/v1/defects/{defect['id']}/failure-analyses",
        json={
            "business_id": "FA-R1",
            "method": "5-Why",
            "findings": "x",
            "analyst": "a",
            "analyzed_at": "2026-09-01T12:00:00Z",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["root_cause_confirmed"] is False


def test_list_failure_analyses_for_defect(client):
    variant_id = _variant(client)
    _mold_id, lot_id = _mold_cavity_lot(client, variant_id, "R2")
    defect = _defect(client, lot_id, "DEF-R2")
    _fa(client, defect["id"], "FA-R2-1")
    _fa(client, defect["id"], "FA-R2-2")

    listed = client.get(f"/api/v1/defects/{defect['id']}/failure-analyses").json()
    assert {f["business_id"] for f in listed} == {"FA-R2-1", "FA-R2-2"}

    lot_defects = client.get(f"/api/v1/lots/{lot_id}/defects").json()
    assert [d["business_id"] for d in lot_defects] == ["DEF-R2"]
    assert lot_defects[0]["id"] == defect["id"]


# -- CAPA state machine ---------------------------------------------------------


def test_capa_starts_in_draft(client):
    variant_id = _variant(client)
    _mold_id, lot_id = _mold_cavity_lot(client, variant_id, "R3")
    defect = _defect(client, lot_id, "DEF-R3")
    fa = _fa(client, defect["id"], "FA-R3")
    capa = _capa(client, fa["id"], "CAPA-R3")
    assert capa["status"] == "draft"
    assert capa["failure_analysis_id"] == fa["id"]


def test_capa_decision_requires_reviewer_role(client):
    variant_id = _variant(client)
    _mold_id, lot_id = _mold_cavity_lot(client, variant_id, "R4")
    defect = _defect(client, lot_id, "DEF-R4")
    fa = _fa(client, defect["id"], "FA-R4")
    capa = _capa(client, fa["id"], "CAPA-R4")
    client.post(f"/api/v1/capas/{capa['id']}/submit", json={"business_id": "CAPA-R4-EV-SUBMIT"})

    # default client user is ARCHITECT (system_architect) — lacks reviewer_approver
    resp = client.post(
        f"/api/v1/capas/{capa['id']}/decisions",
        json={"business_id": "CAPA-R4-EV-DEC", "decision": "approved", "comment": "ok"},
    )
    assert resp.status_code == 403


def test_capa_cannot_skip_states(client):
    variant_id = _variant(client)
    _mold_id, lot_id = _mold_cavity_lot(client, variant_id, "R5")
    defect = _defect(client, lot_id, "DEF-R5")
    fa = _fa(client, defect["id"], "FA-R5")
    capa = _capa(client, fa["id"], "CAPA-R5")

    # still draft — implement/verify/close/decide must all reject
    resp = client.post(f"/api/v1/capas/{capa['id']}/implement", json={"business_id": "X1"})
    assert resp.status_code == 400
    resp = client.post(
        f"/api/v1/capas/{capa['id']}/verify-effectiveness",
        json={"business_id": "X2", "test_run_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 400
    as_user(client, APPROVER2)
    resp = client.post(f"/api/v1/capas/{capa['id']}/close", json={"business_id": "X3"})
    assert resp.status_code == 400
    resp = client.post(
        f"/api/v1/capas/{capa['id']}/decisions",
        json={"business_id": "X4", "decision": "approved", "comment": "too early"},
    )
    assert resp.status_code == 400
    as_user(client, ARCHITECT)

    # re-submitting an already-submitted CAPA also rejects
    client.post(f"/api/v1/capas/{capa['id']}/submit", json={"business_id": "CAPA-R5-EV-SUBMIT"})
    resp = client.post(f"/api/v1/capas/{capa['id']}/submit", json={"business_id": "CAPA-R5-EV-SUBMIT-2"})
    assert resp.status_code == 400


def test_capa_rejected_is_terminal(client):
    variant_id = _variant(client)
    _mold_id, lot_id = _mold_cavity_lot(client, variant_id, "R6")
    defect = _defect(client, lot_id, "DEF-R6")
    fa = _fa(client, defect["id"], "FA-R6")
    capa = _capa(client, fa["id"], "CAPA-R6")
    client.post(f"/api/v1/capas/{capa['id']}/submit", json={"business_id": "CAPA-R6-EV-SUBMIT"})

    as_user(client, APPROVER2)
    resp = client.post(
        f"/api/v1/capas/{capa['id']}/decisions",
        json={"business_id": "CAPA-R6-EV-DEC", "decision": "rejected", "comment": "insufficient evidence"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    as_user(client, ARCHITECT)
    resp = client.post(f"/api/v1/capas/{capa['id']}/implement", json={"business_id": "CAPA-R6-EV-IMPL"})
    assert resp.status_code == 400


def test_verify_effectiveness_requires_existing_test_run(client):
    variant_id = _variant(client)
    _mold_id, lot_id = _mold_cavity_lot(client, variant_id, "R7")
    defect = _defect(client, lot_id, "DEF-R7")
    fa = _fa(client, defect["id"], "FA-R7")
    capa = _capa(client, fa["id"], "CAPA-R7")
    client.post(f"/api/v1/capas/{capa['id']}/submit", json={"business_id": "CAPA-R7-EV-SUBMIT"})
    as_user(client, APPROVER2)
    client.post(
        f"/api/v1/capas/{capa['id']}/decisions",
        json={"business_id": "CAPA-R7-EV-DEC", "decision": "approved", "comment": "ok"},
    )
    as_user(client, ARCHITECT)
    client.post(f"/api/v1/capas/{capa['id']}/implement", json={"business_id": "CAPA-R7-EV-IMPL"})

    resp = client.post(
        f"/api/v1/capas/{capa['id']}/verify-effectiveness",
        json={"business_id": "CAPA-R7-EV-VERIFY", "test_run_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


def test_capa_full_lifecycle(client):
    """defect → FA → CAPA → approve → implement → verify(real TestRun) →
    close, with the full append-only event trail asserted at the end."""
    variant_id = _variant(client)
    _mold_id, lot_id = _mold_cavity_lot(client, variant_id, "R8")
    defect = _defect(client, lot_id, "DEF-R8")
    fa = _fa(client, defect["id"], "FA-R8")
    capa = _capa(client, fa["id"], "CAPA-R8")
    assert capa["status"] == "draft"

    resp = client.post(f"/api/v1/capas/{capa['id']}/submit", json={"business_id": "CAPA-R8-EV-SUBMIT", "comment": "ready"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending_review"
    assert resp.json()["submitted_by"] == ARCHITECT.username

    as_user(client, APPROVER2)
    resp = client.post(
        f"/api/v1/capas/{capa['id']}/decisions",
        json={"business_id": "CAPA-R8-EV-DEC", "decision": "approved", "comment": "plan looks sound"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    as_user(client, ARCHITECT)
    resp = client.post(f"/api/v1/capas/{capa['id']}/implement", json={"business_id": "CAPA-R8-EV-IMPL", "comment": "done on line 3"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "implemented"

    test_run_id = _test_run(client, variant_id, lot_id, "R8")
    resp = client.post(
        f"/api/v1/capas/{capa['id']}/verify-effectiveness",
        json={"business_id": "CAPA-R8-EV-VERIFY", "test_run_id": test_run_id, "comment": "재검사 결과 재발 없음"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "effectiveness_verified"
    assert body["verification_test_run_id"] == test_run_id

    as_user(client, APPROVER2)
    resp = client.post(f"/api/v1/capas/{capa['id']}/close", json={"business_id": "CAPA-R8-EV-CLOSE", "comment": "closed"})
    assert resp.status_code == 200
    final = resp.json()
    assert final["status"] == "closed"
    assert final["closed_at"] is not None

    events = client.get(f"/api/v1/capas/{capa['id']}/events").json()
    assert [e["event_type"] for e in events] == [
        "submitted", "approved", "implemented", "effectiveness_verified", "closed",
    ]
    verify_event = events[3]
    assert verify_event["evidence"]["test_run_id"] == test_run_id

    # global list/filter + get
    all_closed = client.get("/api/v1/capas", params={"status": "closed"}).json()
    assert capa["id"] in [c["id"] for c in all_closed]
    fetched = client.get(f"/api/v1/capas/{capa['id']}").json()
    assert fetched["status"] == "closed"
