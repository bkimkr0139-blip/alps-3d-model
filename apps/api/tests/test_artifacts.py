def test_create_upload_returns_presigned_url(client):
    resp = client.post(
        "/api/v1/artifacts/uploads",
        json={"business_id": "ART-1", "kind": "step", "name": "Part", "filename": "part.step"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["version"] == 1
    assert body["upload_url"].startswith("http://localhost:9000/")


def test_promote_before_upload_fails(client):
    upload = client.post(
        "/api/v1/artifacts/uploads",
        json={"business_id": "ART-2", "kind": "step", "name": "Part", "filename": "part.step"},
    ).json()
    resp = client.post(
        f"/api/v1/artifacts/versions/{upload['artifact_version_id']}/promote",
        json={"sha256": "0" * 64},
    )
    assert resp.status_code == 400


def test_second_upload_for_same_business_id_increments_version(client):
    first = client.post(
        "/api/v1/artifacts/uploads",
        json={"business_id": "ART-3", "kind": "step", "name": "Part", "filename": "a.step"},
    ).json()
    second = client.post(
        "/api/v1/artifacts/uploads",
        json={"business_id": "ART-3", "kind": "step", "name": "Part", "filename": "b.step"},
    ).json()
    assert first["version"] == 1
    assert second["version"] == 2
    assert first["artifact_id"] == second["artifact_id"]


def test_content_of_unknown_version_is_404(client):
    resp = client.get("/api/v1/artifacts/versions/00000000-0000-0000-0000-000000000000/content")
    assert resp.status_code == 404


def test_content_before_promotion_is_rejected(client):
    upload = client.post(
        "/api/v1/artifacts/uploads",
        json={"business_id": "ART-4", "kind": "step", "name": "Part", "filename": "part.step"},
    ).json()
    resp = client.get(f"/api/v1/artifacts/versions/{upload['artifact_version_id']}/content")
    assert resp.status_code == 400
