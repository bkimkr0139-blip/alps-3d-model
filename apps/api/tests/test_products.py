from tests.conftest import APPROVER, as_user


def test_create_product(client):
    resp = client.post(
        "/api/v1/products",
        json={"business_id": "PROD-1", "name": "Widget"},
        headers={"Idempotency-Key": "k1"},
    )
    assert resp.status_code == 201
    assert resp.json()["business_id"] == "PROD-1"


def test_duplicate_business_id_without_idempotency_key_conflicts(client):
    client.post("/api/v1/products", json={"business_id": "PROD-1", "name": "Widget"})
    resp = client.post("/api/v1/products", json={"business_id": "PROD-1", "name": "Widget 2"})
    assert resp.status_code == 409


def test_idempotent_retry_returns_same_object_without_duplicating(client):
    body = {"business_id": "PROD-1", "name": "Widget"}
    first = client.post("/api/v1/products", json=body, headers={"Idempotency-Key": "same-key"})
    second = client.post("/api/v1/products", json=body, headers={"Idempotency-Key": "same-key"})
    assert first.json()["id"] == second.json()["id"]


def test_rbac_rejects_role_without_permission(client):
    as_user(client, APPROVER)
    resp = client.post("/api/v1/products", json={"business_id": "PROD-2", "name": "X"})
    assert resp.status_code == 403


def test_create_variant_under_product(client):
    product = client.post("/api/v1/products", json={"business_id": "PROD-3", "name": "P3"}).json()
    resp = client.post(
        f"/api/v1/products/{product['id']}/variants",
        json={"business_id": "VAR-3A", "name": "Variant A"},
    )
    assert resp.status_code == 201
    assert resp.json()["product_id"] == product["id"]
