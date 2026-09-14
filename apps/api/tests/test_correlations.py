import io

from tests.conftest import MECH_ENGINEER, as_user


def _make_variant(client):
    product = client.post("/api/v1/products", json={"business_id": "PROD-C", "name": "PC"}).json()
    return client.post(
        f"/api/v1/products/{product['id']}/variants", json={"business_id": "VAR-C", "name": "VC"}
    ).json()["id"]


def test_correlation_requires_succeeded_simulation_run(client):
    variant_id = _make_variant(client)
    as_user(client, MECH_ENGINEER)
    run = client.post(
        "/api/v1/simulation-runs",
        json={"business_id": "RUN-C1", "variant_id": variant_id, "run_type": "mech_model"},
    ).json()
    # queued, not succeeded — no worker involved in this test
    resp = client.post(
        "/api/v1/correlations",
        json={"business_id": "CORR-1", "simulation_run_id": run["id"], "test_run_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 400


def test_measurement_upload_requires_x_y_value_columns(client):
    variant_id = _make_variant(client)
    as_user(client, MECH_ENGINEER)
    plan = client.post(
        "/api/v1/test-plans", json={"business_id": "TP-1", "variant_id": variant_id, "name": "bench"}
    ).json()
    run = client.post(
        "/api/v1/test-runs",
        json={"business_id": "TR-1", "test_plan_id": plan["id"], "executed_at": "2026-01-01T00:00:00Z"},
    ).json()

    bad_csv = io.BytesIO(b"stroke,force\n0.1,10\n")
    resp = client.post(
        f"/api/v1/test-runs/{run['id']}/measurements",
        files={"file": ("bad.csv", bad_csv, "text/csv")},
        data={"x_unit": "mm", "y_unit": "mN"},
    )
    assert resp.status_code == 422


def test_measurement_upload_and_duplicate_rejected(client):
    variant_id = _make_variant(client)
    as_user(client, MECH_ENGINEER)
    plan = client.post(
        "/api/v1/test-plans", json={"business_id": "TP-2", "variant_id": variant_id, "name": "bench"}
    ).json()
    run = client.post(
        "/api/v1/test-runs",
        json={"business_id": "TR-2", "test_plan_id": plan["id"], "executed_at": "2026-01-01T00:00:00Z"},
    ).json()

    good_csv = b"x_value,y_value\n0.0,10\n0.1,50\n0.2,90\n"
    resp = client.post(
        f"/api/v1/test-runs/{run['id']}/measurements",
        files={"file": ("good.csv", io.BytesIO(good_csv), "text/csv")},
        data={"x_unit": "mm", "y_unit": "mN"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 3

    # re-upload for the same test run must be rejected — raw data doesn't get
    # silently overwritten (§FR-07 "원본 불변 저장")
    resp2 = client.post(
        f"/api/v1/test-runs/{run['id']}/measurements",
        files={"file": ("good.csv", io.BytesIO(good_csv), "text/csv")},
        data={"x_unit": "mm", "y_unit": "mN"},
    )
    assert resp2.status_code == 409
