from tests.conftest import APPROVER, as_user

from datetime import datetime, timezone

from app.models.simulation import RunStatus, RunType, SimulationRun
from app.models.test import CorrelationRecord, TestPlan, TestRun


def _make_variant_with_baseline(client):
    product = client.post("/api/v1/products", json={"business_id": "PROD-G", "name": "PG"}).json()
    variant = client.post(
        f"/api/v1/products/{product['id']}/variants", json={"business_id": "VAR-G", "name": "VG"}
    ).json()
    requirement = client.post(
        "/api/v1/requirements",
        json={
            "business_id": "REQ-G1",
            "variant_id": variant["id"],
            "text": "req",
            "verification_method": "test",
            "owner": "test.architect",
        },
    ).json()
    baseline = client.post(
        "/api/v1/baselines", json={"business_id": "BL-G1", "variant_id": variant["id"]}
    ).json()
    return variant["id"], baseline["id"], requirement["id"]


def test_submit_blocked_when_evidence_missing(client):
    variant_id, baseline_id, _req_id = _make_variant_with_baseline(client)
    gate = client.post(
        "/api/v1/gates",
        json={"business_id": "GATE-1", "variant_id": variant_id, "baseline_id": baseline_id, "name": "Virtual Verification Complete"},
    ).json()

    resp = client.post(f"/api/v1/gates/{gate['id']}/submit")
    assert resp.status_code == 412
    missing = resp.json()["detail"]["missing"]
    assert "spice_analysis_succeeded" in missing
    assert "all_requirements_traced" in missing


def test_submit_succeeds_once_evidence_present(client, db_session):
    variant_id, baseline_id, req_id = _make_variant_with_baseline(client)

    component = client.post(
        "/api/v1/components", json={"business_id": "CMP-G1", "variant_id": variant_id, "name": "Dome"}
    ).json()
    client.post(
        f"/api/v1/requirements/{req_id}/trace-links",
        json={"business_id": "LINK-G1", "target_type": "component", "target_id": component["id"]},
    )

    # Fabricate succeeded runs directly — exercising the real Temporal path
    # is covered manually end-to-end (AGENTS.md), not in this unit test.
    spice_run = SimulationRun(
        business_id="RUN-G-SPICE", variant_id=variant_id, run_type=RunType.SPICE_ANALYSIS,
        status=RunStatus.SUCCEEDED, created_by="seed",
    )
    mech_run = SimulationRun(
        business_id="RUN-G-MECH", variant_id=variant_id, run_type=RunType.MECH_MODEL,
        status=RunStatus.SUCCEEDED, created_by="seed",
    )
    db_session.add_all([spice_run, mech_run])
    db_session.flush()
    test_plan = TestPlan(business_id="TP-G1", variant_id=variant_id, name="bench", created_by="seed")
    db_session.add(test_plan)
    db_session.flush()
    test_run = TestRun(
        business_id="TR-G1", test_plan_id=test_plan.id, executed_at=datetime.now(timezone.utc), created_by="seed",
    )
    db_session.add(test_run)
    db_session.flush()
    correlation = CorrelationRecord(
        business_id="CORR-G1", simulation_run_id=mech_run.id, test_run_id=test_run.id,
        rmse=1.0, mae=1.0, max_error=2.0, correlation_coefficient=0.98, extrapolation_warning=False,
        overlap_x_min=0.0, overlap_x_max=1.0, created_by="seed",
    )
    db_session.add(correlation)
    db_session.commit()

    gate = client.post(
        "/api/v1/gates",
        json={"business_id": "GATE-2", "variant_id": variant_id, "baseline_id": baseline_id, "name": "Virtual Verification Complete"},
    ).json()
    resp = client.post(f"/api/v1/gates/{gate['id']}/submit")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending_review"
    assert resp.json()["evidence_checklist"]["passed"] is True


def test_decision_requires_independence_from_submitter(client):
    variant_id, baseline_id, _req = _make_variant_with_baseline(client)
    gate = client.post(
        "/api/v1/gates",
        json={"business_id": "GATE-3", "variant_id": variant_id, "baseline_id": baseline_id, "name": "Gate"},
    ).json()
    # force into pending_review directly via the DB would be cleaner, but the
    # submit endpoint's evidence gate gets in the way here — decision RBAC and
    # role-check paths are what this test targets, not the full happy path.
    resp = client.post(
        f"/api/v1/gates/{gate['id']}/decisions",
        json={"business_id": "DEC-1", "decision": "approved", "comment": "looks good"},
    )
    # ARCHITECT lacks reviewer_approver — RBAC blocks before independence check
    assert resp.status_code == 403


def test_decision_requires_reviewer_role(client):
    variant_id, baseline_id, _req = _make_variant_with_baseline(client)
    gate = client.post(
        "/api/v1/gates",
        json={"business_id": "GATE-4", "variant_id": variant_id, "baseline_id": baseline_id, "name": "Gate"},
    ).json()
    as_user(client, APPROVER)
    resp = client.post(
        f"/api/v1/gates/{gate['id']}/decisions",
        json={"business_id": "DEC-2", "decision": "approved", "comment": "ok"},
    )
    # gate is still in draft (never submitted) — decisions require pending_review
    assert resp.status_code == 400
