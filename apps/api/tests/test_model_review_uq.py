"""M9: port contracts + unit checks, rule-based model review, envelope
blocking, UQ determinism, gap-analysis candidates."""

import uuid

from app.security import get_current_user

from .conftest import ARCHITECT, MECH_ENGINEER, as_user


def _make_variant(client, suffix: str = "M9") -> str:
    product = client.post("/api/v1/products", json={"business_id": f"PROD-{suffix}", "name": "P"}).json()
    variant = client.post(
        f"/api/v1/products/{product['id']}/variants",
        json={"business_id": f"VAR-{suffix}", "name": "V"},
    ).json()
    return variant["id"]


def _element(client, variant_id: str, bid: str, name: str, unit: str | None = None) -> dict:
    resp = client.post(
        f"/api/v1/variants/{variant_id}/model-elements",
        json={"business_id": bid, "name": name, "domain": "mechanical", "unit": unit},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _port(client, element_id: str, bid: str, direction: str, quantity: str, unit: str) -> dict:
    resp = client.post(
        f"/api/v1/model-elements/{element_id}/ports",
        json={"business_id": bid, "name": bid, "direction": direction, "quantity": quantity, "unit": unit},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _link(client, variant_id: str, bid: str, src_id: str, dst_id: str, unit: str | None,
          conversion: str | None = None):
    return client.post(
        f"/api/v1/variants/{variant_id}/model-links",
        json={
            "business_id": bid,
            "source_element_id": src_id,
            "target_element_id": dst_id,
            "signal": "s",
            **({"unit": unit} if unit else {}),
            **({"unit_conversion": conversion} if conversion else {}),
        },
    )


# -- port contracts + SM-01 unit checks ----------------------------------------


def test_port_contract_roundtrip_and_system_model_listing(client):
    variant_id = _make_variant(client)
    dome = _element(client, variant_id, "ME-D", "돔", "mm")
    _port(client, dome["id"], "MP-1", "in", "displacement", "mm")

    system = client.get(f"/api/v1/twins/{variant_id}/system-model").json()
    assert len(system["ports"]) == 1
    port = system["ports"][0]
    assert port["direction"] == "in"
    assert port["quantity"] == "displacement"
    assert port["unit"] == "mm"
    assert port["element_id"] == dome["id"]


def test_link_dimension_mismatch_rejected_422(client):
    variant_id = _make_variant(client)
    src = _element(client, variant_id, "ME-S", "소스", "mm")
    dst = _element(client, variant_id, "ME-D", "목적", "V")
    resp = _link(client, variant_id, "ML-1", src["id"], dst["id"], "mm")
    assert resp.status_code == 422
    assert "dimension mismatch" in resp.text


def test_same_dimension_different_units_requires_conversion(client):
    variant_id = _make_variant(client)
    src = _element(client, variant_id, "ME-S", "소스", "mm")
    dst = _element(client, variant_id, "ME-D", "목적", "m")

    # no conversion statement → SM-01 blocks the save
    assert _link(client, variant_id, "ML-1", src["id"], dst["id"], "mm").status_code == 422

    # explicit unit_conversion → allowed
    ok = _link(client, variant_id, "ML-2", src["id"], dst["id"], "mm", conversion="× 0.001 m/mm")
    assert ok.status_code == 201, ok.text
    assert ok.json()["unit_conversion"] == "× 0.001 m/mm"

    # identical units need no conversion
    dst2 = _element(client, variant_id, "ME-D2", "목적2", "mm")
    assert _link(client, variant_id, "ML-3", src["id"], dst2["id"], "mm").status_code == 201


def test_unknown_units_are_allowed_but_flagged_by_review(client):
    variant_id = _make_variant(client)
    src = _element(client, variant_id, "ME-S", "소스", "furlongs")
    dst = _element(client, variant_id, "ME-D", "목적", "furlongs")
    resp = _link(client, variant_id, "ML-1", src["id"], dst["id"], "furlongs")
    assert resp.status_code == 201  # cannot verify ≠ invalid

    findings = client.post(f"/api/v1/twins/{variant_id}/model-review").json()["findings"]
    unknown = [f for f in findings if f["category"] == "port_unit" and "furlongs" in (f["detail"] or "")]
    assert unknown, "unknown unit must surface as a review finding"


def test_absent_link_unit_is_not_dimensionless(client):
    """unit=None on a link means 'not declared' — it must not be treated as an
    explicit dimensionless unit and clash with a pressure/voltage endpoint."""
    from app.unitcheck import unit_dimension

    assert unit_dimension(None) is None
    variant_id = _make_variant(client)
    src = _element(client, variant_id, "ME-S", "소스")
    dst = _element(client, variant_id, "ME-D", "목적")
    _port(client, src["id"], "MP-SO", "out", "pressure", "MPa")
    _port(client, dst["id"], "MP-DI", "in", "pressure", "MPa")
    resp = _link(client, variant_id, "ML-NONE", src["id"], dst["id"], None)
    assert resp.status_code == 201, resp.text


def test_port_contracts_drive_link_validation(client):
    """Ports take precedence over element units: mismatched ports are rejected
    even when the element-level units would have agreed."""
    variant_id = _make_variant(client)
    src = _element(client, variant_id, "ME-S", "소스")
    dst = _element(client, variant_id, "ME-D", "목적")
    _port(client, src["id"], "MP-SO", "out", "force", "N")
    _port(client, dst["id"], "MP-DI", "in", "voltage", "mV")
    resp = _link(client, variant_id, "ML-1", src["id"], dst["id"], None)
    assert resp.status_code == 422


# -- rule-based model review ----------------------------------------------------


def test_review_run_is_append_only_and_latest_is_served(client):
    variant_id = _make_variant(client)
    _element(client, variant_id, "ME-A", "블록A")  # no unit, no equation, unlinked

    first = client.post(f"/api/v1/twins/{variant_id}/model-review")
    assert first.status_code == 201
    run1 = first.json()
    assert run1["run_no"] == 1
    assert any(f["category"] == "missing_definition" for f in run1["findings"])

    second = client.post(f"/api/v1/twins/{variant_id}/model-review").json()
    assert second["run_no"] == 2  # a re-run appends, never edits

    latest = client.get(f"/api/v1/twins/{variant_id}/model-review").json()
    assert latest["run_no"] == 2
    for f in latest["findings"]:
        assert f["status"] == "open"
        assert f["provenance"] == "rule_derived"


def test_review_flags_ai_inferred_edges(client):
    variant_id = _make_variant(client)
    client.post(
        f"/api/v1/variants/{variant_id}/causal-relations",
        json={
            "business_id": "CR-AI",
            "source_label": "a",
            "source_domain": "mechanical",
            "target_label": "b",
            "target_domain": "kansei",
            "provenance": "ai_inferred",
        },
    )
    findings = client.post(f"/api/v1/twins/{variant_id}/model-review").json()["findings"]
    flagged = [f for f in findings if f["category"] == "ai_inferred_unreviewed"]
    assert len(flagged) == 1
    assert flagged[0]["evidence"][0]["business_id"] == "CR-AI"
    assert "Gate Evidence" in flagged[0]["detail"]


def test_review_requires_engineer_or_architect(client):
    variant_id = _make_variant(client)
    as_user(client, MECH_ENGINEER)
    assert client.post(f"/api/v1/twins/{variant_id}/model-review").status_code == 201
    as_user(client, ARCHITECT)  # restore for later tests / teardown


# -- MV-04 envelope blocking ----------------------------------------------------


def test_mech_run_outside_validity_envelope_rejected(client):
    variant_id = _make_variant(client)
    client.post(
        f"/api/v1/variants/{variant_id}/model-card",
        json={
            "business_id": "MC-ENV",
            "title": "t",
            "purpose": "p",
            "validity_envelope": [
                {"parameter": "dome_thickness_mm", "unit": "mm", "min": 0.07, "max": 0.13},
            ],
        },
    )
    resp = client.post(
        "/api/v1/simulation-runs",
        json={
            "business_id": f"RUN-ENV-{uuid.uuid4().hex[:8]}",
            "variant_id": variant_id,
            "run_type": "mech_model",
            "parameters": {"model_type": "fs_dome", "dome_thickness_mm": 0.20, "dome_diameter_mm": 6.0},
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "dome_thickness_mm" in str(body["detail"])


def test_mech_run_inside_envelope_and_cardless_variant_pass(client):
    # cardless variant: unaffected by MV-04
    variant_id = _make_variant(client)
    ok = client.post(
        "/api/v1/simulation-runs",
        json={
            "business_id": f"RUN-OK-{uuid.uuid4().hex[:8]}",
            "variant_id": variant_id,
            "run_type": "mech_model",
            "parameters": {"model_type": "fs_dome", "dome_thickness_mm": 0.20, "dome_diameter_mm": 6.0},
        },
    )
    assert ok.status_code == 201

    # carded variant, in-envelope parameters: accepted
    variant2 = _make_variant(client, "M9B")
    client.post(
        f"/api/v1/variants/{variant2}/model-card",
        json={
            "business_id": "MC-ENV2",
            "title": "t",
            "purpose": "p",
            "validity_envelope": [
                {"parameter": "dome_thickness_mm", "unit": "mm", "min": 0.07, "max": 0.13},
            ],
        },
    )
    ok2 = client.post(
        "/api/v1/simulation-runs",
        json={
            "business_id": f"RUN-OK2-{uuid.uuid4().hex[:8]}",
            "variant_id": variant2,
            "run_type": "mech_model",
            "parameters": {"model_type": "fs_dome", "dome_thickness_mm": 0.10, "dome_diameter_mm": 6.0},
        },
    )
    assert ok2.status_code == 201


# -- UQ lite --------------------------------------------------------------------


def _uq_body(variant_id: str, bid: str, **overrides) -> dict:
    body = {
        "business_id": bid,
        "variant_id": variant_id,
        "model_type": "fs_dome",
        "n_samples": 500,
        "seed": 42,
        "inputs": [
            {"name": "dome_thickness_mm", "distribution": "triangular",
             "params": {"min": 0.07, "mode": 0.10, "max": 0.13}, "unit": "mm", "source": "assumed"},
            {"name": "dome_diameter_mm", "distribution": "triangular",
             "params": {"min": 5.0, "mode": 6.0, "max": 6.5}, "unit": "mm", "source": "assumed"},
        ],
        "target_band": {"min": 260.0, "max": 360.0, "unit": "mN", "source": "demo"},
    }
    body.update(overrides)
    return body


def test_uq_deterministic_same_seed_identical_results(client):
    variant_id = _make_variant(client)
    r1 = client.post("/api/v1/variants/{}/uq".format(variant_id),
                     json=_uq_body(variant_id, "UQ-1"))
    assert r1.status_code == 201, r1.text
    r2 = client.post("/api/v1/variants/{}/uq".format(variant_id),
                     json=_uq_body(variant_id, "UQ-2"))
    a, b = r1.json(), r2.json()
    assert a["results"] == b["results"], "same seed + inputs ⇒ identical results (MV-05)"

    diff_seed = client.post("/api/v1/variants/{}/uq".format(variant_id),
                            json=_uq_body(variant_id, "UQ-3", seed=7)).json()
    assert diff_seed["results"]["mean"] != a["results"]["mean"]

    assert a["metric_name"] == "peak_force_mN"
    assert a["metric_unit"] == "mN"
    results = a["results"]
    assert results["p05"] <= results["p50"] <= results["p95"]
    assert 0.0 <= results["violation_prob"] <= 1.0
    assert len(results["hist"]["counts"]) == 20
    assert all(i["source"] == "assumed" for i in a["inputs"])


def test_uq_latest_get_and_bad_inputs(client):
    variant_id = _make_variant(client)
    client.post("/api/v1/variants/{}/uq".format(variant_id), json=_uq_body(variant_id, "UQ-1"))
    latest = client.get(f"/api/v1/twins/{variant_id}/uq")
    assert latest.status_code == 200
    assert latest.json()["business_id"] == "UQ-1"

    bad = client.post(
        "/api/v1/variants/{}/uq".format(variant_id),
        json=_uq_body(variant_id, "UQ-BAD", inputs=[
            {"name": "dome_thickness_mm", "distribution": "normal",
             "params": {"mean": 0.1, "sd": 0.0}, "unit": "mm", "source": "assumed"},
            {"name": "dome_diameter_mm", "distribution": "triangular",
             "params": {"min": 5.0, "mode": 6.0, "max": 6.5}, "unit": "mm", "source": "assumed"},
        ]),
    )
    assert bad.status_code == 422  # sd must be > 0


# -- gap analysis (AI-05 lite) --------------------------------------------------


def _succeeded_curve_run(client, db_session, variant_id: str, bid: str, ys: list[float]) -> str:
    """Worker-less: queue a mech run via the API, then flip it to succeeded
    with a force_mN_at_x curve metric set (fs_dome family, mm/mN)."""
    run = client.post(
        "/api/v1/simulation-runs",
        json={
            "business_id": bid,
            "variant_id": variant_id,
            "run_type": "mech_model",
            "parameters": {"model_type": "fs_dome", "dome_thickness_mm": 0.10, "dome_diameter_mm": 6.0},
        },
    ).json()
    from app.models.simulation import ResultMetric, RunStatus, SimulationRun

    run_row = db_session.get(SimulationRun, run["id"])
    run_row.status = RunStatus.SUCCEEDED
    for i, y in enumerate(ys):
        db_session.add(ResultMetric(
            business_id=f"{bid}-M{i}", simulation_run_id=run_row.id,
            name=f"force_mN_at_x_{i * 0.25:.2f}", value=y, unit="mN",
            created_by="test.mech",
        ))
    db_session.commit()
    return run["id"]


def _correlated_pair(client, db_session, suffix: str, ys: list[float], meas: list[tuple[float, float]]) -> str:
    variant_id = _make_variant(client, f"GA{suffix}")
    run_id = _succeeded_curve_run(client, db_session, variant_id, f"RUN-GA{suffix}", ys)
    as_user(client, MECH_ENGINEER)
    plan = client.post(
        "/api/v1/test-plans", json={"business_id": f"TP-GA{suffix}", "variant_id": variant_id, "name": "bench"}
    ).json()
    test_run = client.post(
        "/api/v1/test-runs",
        json={"business_id": f"TR-GA{suffix}", "test_plan_id": plan["id"], "executed_at": "2026-01-01T00:00:00Z"},
    ).json()
    import io

    csv = io.BytesIO(("x_value,y_value\n" + "\n".join(f"{x},{y}" for x, y in meas) + "\n").encode())
    up = client.post(
        f"/api/v1/test-runs/{test_run['id']}/measurements",
        files={"file": (f"ga{suffix}.csv", csv, "text/csv")},
        data={"x_unit": "mm", "y_unit": "mN"},
    )
    assert up.status_code == 200, up.text
    corr = client.post(
        "/api/v1/correlations",
        json={"business_id": f"CORR-GA{suffix}", "simulation_run_id": run_id, "test_run_id": test_run["id"]},
    )
    assert corr.status_code == 201, corr.text
    as_user(client, ARCHITECT)
    return corr.json()["id"]


def test_gap_analysis_detects_constant_offset(client, db_session):
    """Predicted = measured + constant → parameter_offset candidate, flagged
    'check_required' (확인 필요), never a verdict."""
    pred = [100 + 200 * (i * 0.25) for i in range(5)]           # 100..300 mN
    meas = [(i * 0.25, pred[i] - 20.0) for i in range(5)]        # constant −20 offset
    corr_id = _correlated_pair(client, db_session, "1", pred, meas)

    resp = client.get(f"/api/v1/correlations/{corr_id}/gap-analysis")
    assert resp.status_code == 200, resp.text
    gap = resp.json()
    causes = [c["cause"] for c in gap["candidates"]]
    assert "parameter_offset" in causes
    assert all(c["confidence"] == "check_required" for c in gap["candidates"])
    assert gap["stats"]["y_unit"] == "mN"
    assert abs(gap["stats"]["mean"] - 20.0) < 1.0
    assert gap["residuals"]["x"] and gap["residuals"]["residual"]


def test_gap_analysis_detects_scale_trend(client, db_session):
    pred = [100 + 200 * (i * 0.25) for i in range(5)]
    meas = [(i * 0.25, pred[i] - 50 * i * 0.25) for i in range(5)]  # x-proportional gap
    corr_id = _correlated_pair(client, db_session, "2", pred, meas)

    gap = client.get(f"/api/v1/correlations/{corr_id}/gap-analysis").json()
    assert "scale_or_structure" in [c["cause"] for c in gap["candidates"]]


def test_gap_analysis_unknown_correlation_404(client):
    assert client.get(f"/api/v1/correlations/{uuid.uuid4()}/gap-analysis").status_code == 404
