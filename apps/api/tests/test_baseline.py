def _make_variant_with_requirement(client) -> str:
    product = client.post("/api/v1/products", json={"business_id": "PROD-B", "name": "PB"}).json()
    variant = client.post(
        f"/api/v1/products/{product['id']}/variants",
        json={"business_id": "VAR-B", "name": "VB"},
    ).json()
    client.post(
        "/api/v1/requirements",
        json={
            "business_id": "REQ-B1",
            "variant_id": variant["id"],
            "text": "req",
            "verification_method": "test",
            "owner": "test.architect",
        },
    )
    return variant["id"]


def test_baseline_manifest_snapshots_current_requirements(client):
    variant_id = _make_variant_with_requirement(client)
    baseline = client.post(
        "/api/v1/baselines", json={"business_id": "BL-1", "variant_id": variant_id}
    ).json()
    assert baseline["status"] == "active"
    assert len(baseline["manifest"]["requirements"]) == 1
    assert baseline["manifest"]["requirements"][0]["business_id"] == "REQ-B1"


def test_second_baseline_supersedes_the_first(client):
    variant_id = _make_variant_with_requirement(client)
    first = client.post(
        "/api/v1/baselines", json={"business_id": "BL-1", "variant_id": variant_id}
    ).json()
    second = client.post(
        "/api/v1/baselines", json={"business_id": "BL-2", "variant_id": variant_id}
    ).json()

    baselines = client.get(f"/api/v1/variants/{variant_id}/baselines").json()
    by_id = {b["id"]: b for b in baselines}
    assert by_id[first["id"]]["status"] == "superseded"
    assert by_id[second["id"]]["status"] == "active"
