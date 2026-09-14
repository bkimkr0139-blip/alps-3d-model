def _make_variant(client) -> str:
    product = client.post("/api/v1/products", json={"business_id": "PROD-R", "name": "PR"}).json()
    variant = client.post(
        f"/api/v1/products/{product['id']}/variants",
        json={"business_id": "VAR-R", "name": "VR"},
    ).json()
    return variant["id"]


def test_requirement_component_trace_and_twin_graph(client):
    variant_id = _make_variant(client)

    requirement = client.post(
        "/api/v1/requirements",
        json={
            "business_id": "REQ-1",
            "variant_id": variant_id,
            "text": "clear click feel",
            "verification_method": "test",
            "owner": "test.architect",
        },
    ).json()

    component = client.post(
        "/api/v1/components",
        json={"business_id": "CMP-1", "variant_id": variant_id, "name": "Dome"},
    ).json()

    link = client.post(
        f"/api/v1/requirements/{requirement['id']}/trace-links",
        json={"business_id": "LINK-1", "target_type": "component", "target_id": component["id"]},
    )
    assert link.status_code == 201

    graph = client.get(f"/api/v1/twins/{variant_id}/graph").json()
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["target"] == component["id"]


def test_component_creation_requires_engineering_role(client):
    from tests.conftest import APPROVER, as_user

    variant_id = _make_variant(client)
    as_user(client, APPROVER)
    resp = client.post(
        "/api/v1/components",
        json={"business_id": "CMP-X", "variant_id": variant_id, "name": "X"},
    )
    assert resp.status_code == 403
