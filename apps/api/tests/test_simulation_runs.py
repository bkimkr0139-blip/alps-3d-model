import uuid


def _make_variant(client) -> str:
    product = client.post("/api/v1/products", json={"business_id": "PROD-S", "name": "PS"}).json()
    variant = client.post(
        f"/api/v1/products/{product['id']}/variants",
        json={"business_id": "VAR-S", "name": "VS"},
    ).json()
    return variant["id"]


# These only exercise validation that runs BEFORE the Temporal client call —
# a full run (queued -> succeeded) needs a live worker and is verified
# manually end-to-end instead (see AGENTS.md).


def test_unknown_variant_is_rejected(client):
    resp = client.post(
        "/api/v1/simulation-runs",
        json={"business_id": "RUN-1", "variant_id": str(uuid.uuid4()), "run_type": "spice_analysis"},
    )
    assert resp.status_code == 404


def test_non_promoted_artifact_is_rejected(client):
    variant_id = _make_variant(client)
    upload = client.post(
        "/api/v1/artifacts/uploads",
        json={"business_id": "ART-S1", "kind": "netlist", "name": "n", "filename": "n.cir"},
    ).json()
    resp = client.post(
        "/api/v1/simulation-runs",
        json={
            "business_id": "RUN-2",
            "variant_id": variant_id,
            "run_type": "spice_analysis",
            "input_artifact_version_id": upload["artifact_version_id"],
        },
    )
    assert resp.status_code == 400
    assert "not promoted" in resp.json()["detail"]


def test_run_requires_engineering_role(client):
    from tests.conftest import APPROVER, as_user

    variant_id = _make_variant(client)
    as_user(client, APPROVER)
    resp = client.post(
        "/api/v1/simulation-runs",
        json={"business_id": "RUN-3", "variant_id": variant_id, "run_type": "spice_analysis"},
    )
    assert resp.status_code == 403
