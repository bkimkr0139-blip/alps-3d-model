def _make_variant(client, suffix: str = "MC") -> str:
    product = client.post("/api/v1/products", json={"business_id": f"PROD-{suffix}", "name": "P"}).json()
    variant = client.post(
        f"/api/v1/products/{product['id']}/variants",
        json={"business_id": f"VAR-{suffix}", "name": "V"},
    ).json()
    return variant["id"]


def test_causal_relation_roundtrip_and_provenance(client):
    variant_id = _make_variant(client)
    resp = client.post(
        f"/api/v1/variants/{variant_id}/causal-relations",
        json={
            "business_id": "CR-1",
            "source_label": "조작 입력력",
            "source_domain": "mechanical",
            "target_label": "돔 변형",
            "target_domain": "mechanical",
            "relation_type": "drives",
            "mechanism": "스냅스루",
            "evidence": [{"kind": "simulation_run", "business_id": "RUN-1"}],
            "provenance": "ai_inferred",
            "confidence": 0.62,
        },
    )
    assert resp.status_code == 201

    paths = client.get(f"/api/v1/twins/{variant_id}/impact-paths").json()
    assert [n["domain"] for n in paths["nodes"]] == ["mechanical", "mechanical"]
    assert len(paths["edges"]) == 1
    edge = paths["edges"][0]
    assert edge["provenance"] == "ai_inferred"
    assert edge["confidence"] == 0.62
    assert edge["evidence"][0]["business_id"] == "RUN-1"


def test_impact_paths_orders_nodes_by_domain(client):
    variant_id = _make_variant(client)
    for i, (s, sd, t, td) in enumerate([
        ("조작감", "kansei", "응답", "kansei"),
        ("V_OL", "electrical", "Debounce", "control"),
        ("입력력", "mechanical", "V_OL", "electrical"),
    ]):
        client.post(
            f"/api/v1/variants/{variant_id}/causal-relations",
            json={
                "business_id": f"CR-{i}",
                "source_label": s,
                "source_domain": sd,
                "target_label": t,
                "target_domain": td,
                "provenance": "human_approved",
            },
        )
    domains = [n["domain"] for n in client.get(f"/api/v1/twins/{variant_id}/impact-paths").json()["nodes"]]
    assert domains == sorted(
        domains, key={"mechanical": 0, "electrical": 1, "control": 2, "kansei": 3}.get
    )


def test_system_model_elements_links_and_component_binding(client):
    variant_id = _make_variant(client)
    component = client.post(
        "/api/v1/components",
        json={"business_id": "CMP-MC", "variant_id": variant_id, "name": "Metal Dome"},
    ).json()

    dome = client.post(
        f"/api/v1/variants/{variant_id}/model-elements",
        json={
            "business_id": "ME-DOME",
            "name": "돔 스냅 기구",
            "domain": "mechanical",
            "geometry_component_id": component["id"],
            "position": {"x": 100, "y": 80},
        },
    )
    assert dome.status_code == 201
    io = client.post(
        f"/api/v1/variants/{variant_id}/model-elements",
        json={"business_id": "ME-IO", "name": "입출력", "domain": "kansei"},
    )
    link = client.post(
        f"/api/v1/variants/{variant_id}/model-links",
        json={
            "business_id": "ML-1",
            "source_element_id": dome.json()["id"],
            "target_element_id": io.json()["id"],
            "signal": "스냅 접촉",
        },
    )
    assert link.status_code == 201

    # a link to another variant's element must be rejected
    other = _make_variant(client, suffix="MC2")
    stray = client.post(
        f"/api/v1/variants/{other}/model-links",
        json={
            "business_id": "ML-2",
            "source_element_id": dome.json()["id"],
            "target_element_id": io.json()["id"],
            "signal": "x",
        },
    )
    assert stray.status_code == 404

    model = client.get(f"/api/v1/twins/{variant_id}/system-model").json()
    assert len(model["elements"]) == 2
    assert model["elements"][0]["geometry_component_id"] == component["id"]
    assert len(model["links"]) == 1


def test_model_card_single_per_variant_and_trust_state(client):
    variant_id = _make_variant(client)
    body = {
        "business_id": "MC-1",
        "title": "F–S 모델",
        "purpose": "조작감 예측",
        "equation_text": "F(δ)",
        "assumptions": ["돔 = 바이어스 스프링"],
        "evidence": [{"kind": "simulation_run", "business_id": "RUN-MECH-01"}],
        "validity_envelope": [{"parameter": "dome_thickness_mm", "unit": "mm", "min": 0.07, "max": 0.13}],
        "trust_state": "validated_for_purpose",
    }
    first = client.post(f"/api/v1/variants/{variant_id}/model-card", json=body)
    assert first.status_code == 201
    duplicate = client.post(f"/api/v1/variants/{variant_id}/model-card", json=body)
    assert duplicate.status_code == 409

    card = client.get(f"/api/v1/twins/{variant_id}/model-card").json()
    assert card["trust_state"] == "validated_for_purpose"
    assert card["validity_envelope"][0]["max"] == 0.13

    empty = client.get(f"/api/v1/twins/{_make_variant(client, suffix='MC3')}/model-card")
    assert empty.status_code == 200
