"""P1 — TACT Product–Process Twin vertical slice: molds/cavities, process
runs with setpoint/actual separation, lot genealogy, cavity comparison and
rule-based root-cause hypotheses (지시서 §PT-02/PT-03, AN-02, AI-01 lite)."""

import io
import uuid

from fastapi.testclient import TestClient

from .conftest import ARCHITECT, MECH_ENGINEER, as_user


def _mold(client: TestClient, bid: str = "MOLD-1") -> dict:
    resp = client.post(
        "/api/v1/molds",
        json={"business_id": bid, "name": "돔 프레스 금형", "tool_revision": "B", "process": "dome stamping"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _cavity(client: TestClient, mold_id: str, bid: str, no: int, label: str) -> dict:
    resp = client.post(f"/api/v1/molds/{mold_id}/cavities", json={"business_id": bid, "cavity_no": no, "label": label})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _operation(client: TestClient, bid: str, seq: int, lo: float, hi: float) -> dict:
    resp = client.post(
        "/api/v1/process-operations",
        json={
            "business_id": bid,
            "name": f"OP-{seq:02d}",
            "seq_no": seq,
            "equipment": "PRESS-01",
            "window": [{"parameter": "dome_thickness_mm", "unit": "mm", "min": lo, "max": hi}],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _variant(client: TestClient, suffix: str = "PT") -> str:
    product = client.post("/api/v1/products", json={"business_id": f"PROD-{suffix}", "name": "P"}).json()
    variant = client.post(
        f"/api/v1/products/{product['id']}/variants", json={"business_id": f"VAR-{suffix}", "name": "V"}
    ).json()
    return variant["id"]


def _lot(client: TestClient, variant_id: str, mold_id: str, cavity_id: str, bid: str,
         material: str = "MAT-100") -> dict:
    resp = client.post(
        "/api/v1/lots",
        json={
            "business_id": bid,
            "variant_id": variant_id,
            "mold_id": mold_id,
            "cavity_id": cavity_id,
            "material_lot_id": material,
            "work_order_id": "WO-1",
            "produced_at": "2026-09-01T09:00:00Z",
            "quantity": 5000,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _process_run(client: TestClient, lot_id: str, op_id: str, bid: str, actual: dict) -> dict:
    resp = client.post(
        "/api/v1/process-runs",
        json={
            "business_id": bid,
            "lot_id": lot_id,
            "operation_id": op_id,
            "setpoint": {"dome_thickness_mm": 0.10},
            "actual": actual,
            "started_at": "2026-09-01T09:30:00Z",
            "operator": "cell-3",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _inspection(client: TestClient, db_session, variant_id: str, lot_id: str, bid: str,
                peaks: list[float]) -> str:
    """Test run on the lot with a force–stroke curve whose peak is
    `max(peaks)`-ish — one x/y pair per entry, x in mm, y in mN."""
    as_user(client, MECH_ENGINEER)
    plan = client.post(
        "/api/v1/test-plans", json={"business_id": f"TP-{bid}", "variant_id": variant_id, "name": "F-S"}
    ).json()
    run = client.post(
        "/api/v1/test-runs",
        json={"business_id": f"TR-{bid}", "test_plan_id": plan["id"], "lot_id": lot_id,
              "executed_at": "2026-09-01T10:00:00Z"},
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    csv = io.BytesIO(
        ("x_value,y_value\n" + "\n".join(f"{i * 0.05},{y}" for i, y in enumerate(peaks)) + "\n").encode()
    )
    up = client.post(
        f"/api/v1/test-runs/{run_id}/measurements",
        files={"file": (f"{bid}.csv", csv, "text/csv")},
        data={"x_unit": "mm", "y_unit": "mN"},
    )
    assert up.status_code == 200, up.text
    as_user(client, ARCHITECT)
    return run_id


# -- molds / cavities -------------------------------------------------------------


def test_mold_and_cavity_roundtrip(client):
    mold = _mold(client)
    c1 = _cavity(client, mold["id"], "CAV-1", 1, "Cavity 1")
    assert c1["mold_id"] == mold["id"]
    molds = client.get("/api/v1/molds").json()
    assert [m["business_id"] for m in molds] == ["MOLD-1"]
    assert molds[0]["tool_revision"] == "B"


def test_lot_rejects_cavity_from_another_mold(client):
    variant_id = _variant(client)
    mold1 = _mold(client, "MOLD-A")
    mold2 = _mold(client, "MOLD-B")
    stranger = _cavity(client, mold2["id"], "CAV-B1", 1, "B/C1")
    resp = client.post(
        "/api/v1/lots",
        json={"business_id": "LOT-X", "variant_id": variant_id, "mold_id": mold1["id"],
              "cavity_id": stranger["id"], "produced_at": "2026-09-01T09:00:00Z"},
    )
    assert resp.status_code == 422
    assert "does not belong" in resp.text


# -- process runs: setpoint/actual + window flag -----------------------------------


def test_process_run_flags_out_of_window_without_rejecting(client):
    variant_id = _variant(client)
    mold = _mold(client)
    cavity = _cavity(client, mold["id"], "CAV-1", 1, "C1")
    lot = _lot(client, variant_id, mold["id"], cavity["id"], "LOT-1")
    op = _operation(client, "OP-10", 10, 0.07, 0.13)

    bad = _process_run(client, lot["id"], op["id"], "PR-BAD", {"dome_thickness_mm": 0.145})
    assert bad["out_of_window"] is True
    assert bad["window_findings"][0]["parameter"] == "dome_thickness_mm"
    assert bad["window_findings"][0]["actual"] == 0.145

    good = _process_run(client, lot["id"], op["id"], "PR-GOOD", {"dome_thickness_mm": 0.10})
    assert good["out_of_window"] is False
    assert good["window_findings"] is None


def test_operation_window_min_max_validated(client):
    resp = client.post(
        "/api/v1/process-operations",
        json={"business_id": "OP-BAD", "name": "x", "seq_no": 1,
              "window": [{"parameter": "p", "min": 0.2, "max": 0.1}]},
    )
    assert resp.status_code == 422


# -- genealogy (AC-02) --------------------------------------------------------------


def test_lot_genealogy_traces_everything(client, db_session):
    variant_id = _variant(client)
    mold = _mold(client)
    cavity = _cavity(client, mold["id"], "CAV-1", 1, "C1")
    lot = _lot(client, variant_id, mold["id"], cavity["id"], "LOT-G")
    op1 = _operation(client, "OP-10", 10, 0.07, 0.13)
    op2 = _operation(client, "OP-20", 20, 0.18, 0.30)
    _process_run(client, lot["id"], op2["id"], "PR-2", {"dome_thickness_mm": 0.20})
    _process_run(client, lot["id"], op1["id"], "PR-1", {"dome_thickness_mm": 0.145})
    _inspection(client, db_session, variant_id, lot["id"], "G", [100.0, 330.0, 120.0])
    defct = client.post(
        "/api/v1/defects",
        json={"business_id": "DEF-1", "lot_id": lot["id"], "defect_class": "force_high",
              "severity": "major", "quantity": 12, "note": "peak 초과"},
    )
    assert defct.status_code == 201, defct.text

    gene = client.get(f"/api/v1/lots/{lot['id']}/genealogy")
    assert gene.status_code == 200, gene.text
    gene = gene.json()
    assert gene["mold"]["business_id"] == "MOLD-1"
    assert gene["cavity"]["label"] == "C1"
    # ordered by operation seq regardless of insertion order
    assert [r["seq_no"] for r in gene["process_runs"]] == [10, 20]
    flagged = [r for r in gene["process_runs"] if r["out_of_window"]]
    assert len(flagged) == 1 and flagged[0]["business_id"] == "PR-1"
    assert gene["test_runs"][0]["measurement_count"] == 3
    assert gene["test_runs"][0]["y_unit"] == "mN"
    assert gene["defects"][0]["defect_class"] == "force_high"

    # lot cards carry the counters the UI table shows
    cards = client.get(f"/api/v1/twins/{variant_id}/lots").json()
    assert cards[0]["cavity_label"] == "C1"
    assert cards[0]["defect_count"] == 1
    assert cards[0]["out_of_window_runs"] == 1


def test_genealogy_unknown_lot_404(client):
    assert client.get(f"/api/v1/lots/{uuid.uuid4()}/genealogy").status_code == 404


# -- cavity comparison (AC-03 / AN-02) -----------------------------------------------


def _two_cavity_fixture(client, db_session, c1_peaks_by_lot, c2_peaks_by_lot):
    """Mold + C1/C2, lots+inspections per cavity. Returns (variant_id, lots)."""
    variant_id = _variant(client)
    mold = _mold(client)
    c1 = _cavity(client, mold["id"], "CAV-1", 1, "C1")
    c2 = _cavity(client, mold["id"], "CAV-2", 2, "C2")
    lots = []
    for bid, peaks in c1_peaks_by_lot.items():
        lot = _lot(client, variant_id, mold["id"], c1["id"], bid, material="MAT-1")
        _inspection(client, db_session, variant_id, lot["id"], bid, peaks)
        lots.append(lot)
    for bid, peaks in c2_peaks_by_lot.items():
        lot = _lot(client, variant_id, mold["id"], c2["id"], bid, material="MAT-1")
        _inspection(client, db_session, variant_id, lot["id"], bid, peaks)
        lots.append(lot)
    return variant_id, lots


def test_cavity_compare_detects_drift_and_computes_cpk(client, db_session):
    variant_id, _ = _two_cavity_fixture(
        client, db_session,
        {"LOT-C1A": [329.0, 330.0], "LOT-C1B": [330.0, 331.0]},
        {"LOT-C2A": [359.0, 360.0], "LOT-C2B": [360.0, 361.0]},
    )
    comp = client.get(
        f"/api/v1/cavities/compare", params={"variant_id": variant_id, "spec_lsl": 260, "spec_usl": 360}
    ).json()
    by_label = {c["cavity_label"]: c for c in comp["cavities"]}
    # per-inspection CTQ = curve peak: 330/331 and 360/361
    assert abs(by_label["C1"]["mean"] - 330.5) < 0.1
    assert abs(by_label["C2"]["mean"] - 360.5) < 0.1
    assert comp["drift_suspected"] is True
    assert "확인" in comp["check_note"]
    assert by_label["C1"]["cp"] is not None and by_label["C1"]["cpk"] is not None
    # C2 rides the USL → its Cpk must be far worse than C1's
    assert by_label["C2"]["cpk"] < by_label["C1"]["cpk"]


def test_cavity_compare_no_drift_when_cavities_agree(client, db_session):
    variant_id, _ = _two_cavity_fixture(
        client, db_session,
        {"LOT-C1A": [330.0, 331.0], "LOT-C1B": [330.5, 331.5]},
        {"LOT-C2A": [330.2, 331.2], "LOT-C2B": [330.8, 331.8]},
    )
    comp = client.get("/api/v1/cavities/compare", params={"variant_id": variant_id}).json()
    assert comp["drift_suspected"] is False
    assert all(c["cp"] is None for c in comp["cavities"])  # no spec limits → no Cp


# -- rule-based root-cause hypotheses (AI-01 lite) ------------------------------------


def test_root_cause_hypotheses_rules_and_evidence(client, db_session):
    variant_id = _variant(client, "RC")
    mold = _mold(client, "MOLD-RC")
    c1 = _cavity(client, mold["id"], "CAV-RC1", 1, "C1")
    c2 = _cavity(client, mold["id"], "CAV-RC2", 2, "C2")
    op = _operation(client, "OP-RC", 10, 0.07, 0.13)

    ok_lot = _lot(client, variant_id, mold["id"], c1["id"], "LOT-OK", material="MAT-9")
    _process_run(client, ok_lot["id"], op["id"], "PR-OK", {"dome_thickness_mm": 0.10})
    _inspection(client, db_session, variant_id, ok_lot["id"], "OK", [329.0, 330.0])

    bad_lot = _lot(client, variant_id, mold["id"], c2["id"], "LOT-BAD", material="MAT-9")
    _process_run(client, bad_lot["id"], op["id"], "PR-BAD", {"dome_thickness_mm": 0.145})
    _inspection(client, db_session, variant_id, bad_lot["id"], "BAD", [359.0, 360.0])

    resp = client.post("/api/v1/ai/root-cause-hypotheses", json={"lot_id": bad_lot["id"]})
    assert resp.status_code == 200, resp.text
    hypo = resp.json()
    causes = [c["cause"] for c in hypo["candidates"]]
    assert "process_out_of_window" in causes
    assert "cavity_bias" in causes  # C2 mean 359.5 vs C1 329.5, both sd ~0.7
    assert all(c["confidence"] == "check_required" for c in hypo["candidates"])

    window_cand = next(c for c in hypo["candidates"] if c["cause"] == "process_out_of_window")
    assert window_cand["evidence"][0]["business_id"] == "PR-BAD"
    cavity_cand = next(c for c in hypo["candidates"] if c["cause"] == "cavity_bias")
    assert any(e["business_id"] == "CAV-RC2" for e in cavity_cand["evidence"])
    assert "확인 필요" in hypo["disclaimer"] or "판정" in hypo["disclaimer"]

    # the healthy lot must NOT get the lot-level process candidate — but the
    # cavity-level hint still applies to it (its cavity deviates; AN-02 makes
    # the hint an investigation priority for the cavity, not a verdict on the
    # individual lot)
    ok_hypo = client.post("/api/v1/ai/root-cause-hypotheses", json={"lot_id": ok_lot["id"]}).json()
    ok_causes = [c["cause"] for c in ok_hypo["candidates"]]
    assert "process_out_of_window" not in ok_causes
    assert "cavity_bias" in ok_causes


def test_root_cause_insufficient_data_and_404(client):
    variant_id = _variant(client, "RD")
    mold = _mold(client, "MOLD-RD")
    cavity = _cavity(client, mold["id"], "CAV-RD", 1, "C1")
    lot = _lot(client, variant_id, mold["id"], cavity["id"], "LOT-RD")

    hypo = client.post("/api/v1/ai/root-cause-hypotheses", json={"lot_id": lot["id"]}).json()
    assert [c["cause"] for c in hypo["candidates"]] == ["insufficient_data"]

    resp = client.post("/api/v1/ai/root-cause-hypotheses", json={"lot_id": str(uuid.uuid4())})
    assert resp.status_code == 404


# -- RBAC ------------------------------------------------------------------------------


def test_lot_creation_requires_process_role(client):
    variant_id = _variant(client, "RB")
    mold = _mold(client, "MOLD-RB")
    cavity = _cavity(client, mold["id"], "CAV-RB", 1, "C1")
    as_user(client, MECH_ENGINEER)
    resp = client.post(
        "/api/v1/lots",
        json={"business_id": "LOT-RB", "variant_id": variant_id, "mold_id": mold["id"],
              "cavity_id": cavity["id"], "produced_at": "2026-09-01T09:00:00Z"},
    )
    assert resp.status_code == 201
    as_user(client, ARCHITECT)
