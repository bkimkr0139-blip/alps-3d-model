"""Process monitoring tests (AN-03 control chart + AI-03 anomaly
explanation). No real LLM calls — the OpenAI-compatible client is a
dependency-overridden fake, same approach as test_assistant.py."""

import types
import uuid

from fastapi.testclient import TestClient

from app.assistant.client import get_llm_client
from app.main import app
from app.security import get_current_user
from tests.conftest import ARCHITECT, as_user
from tests.test_process_twin import _cavity, _lot, _mold, _operation, _process_run, _variant


def _fixture(client: TestClient, values: list[float]) -> str:
    """One mold, two cavities, op10 with the dome window; one process run
    per value alternating cavities, chronological timestamps included."""
    mold = _mold(client)
    c1 = _cavity(client, mold["id"], "CAV-1", 1, "Cavity 1")
    c2 = _cavity(client, mold["id"], "CAV-2", 2, "Cavity 2")
    op = _operation(client, "OP-10", 10, 0.07, 0.13)
    variant_id = _variant(client)
    for i, v in enumerate(values):
        cavity = c1 if i % 2 == 0 else c2
        lot = _lot(client, variant_id, mold["id"], cavity["id"], f"LOT-{i:02d}")
        resp = client.post(
            "/api/v1/process-runs",
            json={
                "business_id": f"PR-{i:02d}",
                "lot_id": lot["id"],
                "operation_id": op["id"],
                "setpoint": {"dome_thickness_mm": 0.10},
                "actual": {"dome_thickness_mm": v},
                "started_at": f"2026-09-01T09:{10 + i:02d}:00Z",
            },
        )
        assert resp.status_code == 201, resp.text
    return variant_id


def test_process_parameters_discovery(client):
    variant_id = _fixture(client, [0.10, 0.11, 0.09])
    resp = client.get(f"/api/v1/twins/{variant_id}/process-parameters")
    assert resp.status_code == 200, resp.text
    params = resp.json()
    dome = [p for p in params if p["parameter"] == "dome_thickness_mm"]
    assert len(dome) == 1
    assert dome[0]["unit"] == "mm"
    assert dome[0]["n_points"] == 3
    assert dome[0]["operation_business_ids"] == ["OP-10"]


def test_control_chart_stable_series_and_exclusion(client):
    # 0.145 leaves the 0.07–0.13 window → on-chart but excluded from the
    # limit basis; the in-window values keep the chart stable. (Values need
    # spread: a constant basis makes MAD → 0 and the limits collapse.)
    variant_id = _fixture(client, [0.10, 0.11, 0.09, 0.12, 0.145, 0.08])
    resp = client.get(
        f"/api/v1/twins/{variant_id}/control-chart", params={"parameter": "dome_thickness_mm"}
    )
    assert resp.status_code == 200, resp.text
    chart = resp.json()
    assert chart["n_points"] == 6
    assert chart["n_basis"] == 5
    assert chart["center_line"] == 0.10
    assert chart["lcl"] < chart["center_line"] < chart["ucl"]
    excluded = [p for p in chart["points"] if p["excluded_from_limits"]]
    assert len(excluded) == 1
    assert excluded[0]["exclusion_reason"] == "out_of_window"
    assert excluded[0]["process_run_business_id"] == "PR-04"
    assert "규격한계가 아닙니다" in chart["note"]


def test_excluded_outlier_still_flagged_beyond_3_sigma(client):
    # With a tight basis the 0.145 outlier sits beyond the upper limit even
    # though it was excluded from computing that limit — a check-required
    # hint, computed for every point on the chart.
    variant_id = _fixture(client, [0.100, 0.101, 0.099, 0.100, 0.145])
    resp = client.get(
        f"/api/v1/twins/{variant_id}/control-chart", params={"parameter": "dome_thickness_mm"}
    )
    chart = resp.json()
    outlier = [p for p in chart["points"] if p["process_run_business_id"] == "PR-04"][0]
    assert outlier["violations"] == ["beyond_3_sigma"]
    assert "beyond_3_sigma" in chart["rule_hits"]
    stable = [p for p in chart["points"] if p["process_run_business_id"] == "PR-00"][0]
    assert stable["violations"] == []


def test_run_of_7_rule():
    from app.routers.process_monitoring import _violations

    cl, sigma = 100.0, 1.0
    values = [cl - 0.5, cl - 0.2, cl - 0.4] + [cl + s for s in (0.5, 0.3, 0.6, 0.4, 0.2, 0.5, 0.3)]
    hits = _violations(values, cl, sigma)
    flagged = [i for i, h in enumerate(hits) if "run_of_7_same_side" in h]
    # the run spans the seven trailing same-side points, nothing else
    assert set(flagged) == set(range(3, 10))


def test_two_of_three_rule():
    from app.routers.process_monitoring import _violations

    cl, sigma = 100.0, 1.0
    values = [cl + 2.5, cl + 0.1, cl + 2.2]  # two of three beyond 2σ, same side
    hits = _violations(values, cl, sigma)
    assert hits == [
        ["two_of_three_beyond_2_sigma"],
        [],
        ["two_of_three_beyond_2_sigma"],
    ]


def test_chart_insufficient_sample_no_limits(client):
    variant_id = _fixture(client, [0.10, 0.11])
    resp = client.get(
        f"/api/v1/twins/{variant_id}/control-chart", params={"parameter": "dome_thickness_mm"}
    )
    chart = resp.json()
    assert chart["n_basis"] == 2
    assert chart["center_line"] is None and chart["ucl"] is None
    assert "표본수 부족" in chart["note"]
    assert chart["rule_hits"] == []


def test_chart_unknown_parameter_404(client):
    variant_id = _fixture(client, [0.10, 0.11, 0.09])
    resp = client.get(
        f"/api/v1/twins/{variant_id}/control-chart", params={"parameter": "no_such_param"}
    )
    assert resp.status_code == 404, resp.text


class _FakeCompletions:
    def create(self, *, model, messages, temperature):
        assert "조사 가설" in messages[0]["content"]
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="OP-10 실측값이 9월 초부터 상한 쪽으로 이동했다는 조사 가설을 세울 수 있다. LOT-03의 윈도우 이탈과 Cavity 2의 중위값 차이를 우선 확인하라."))]
        )


def test_anomaly_explanation_with_fake_llm(client):
    variant_id = _fixture(client, [0.10, 0.11, 0.09, 0.145])
    app.dependency_overrides[get_llm_client] = lambda: types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=_FakeCompletions())
    )
    try:
        resp = client.post(
            "/api/v1/ai/anomaly-explanation",
            json={"variant_id": variant_id, "parameter": "dome_thickness_mm"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_client, None)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "조사 가설" in body["hypothesis"]
    assert body["model"] == "qwen2.5:32b"
    # every fact the model saw rides along, incl. the out-of-window run
    assert any("PR-03" in f for f in body["facts_used"])
    assert "원인 확정" in body["disclaimer"]


def test_anomaly_explanation_requires_llm_config(client, monkeypatch):
    variant_id = _fixture(client, [0.10, 0.11, 0.09])
    from app.config import settings

    monkeypatch.setattr(settings, "llm_base_url", "")
    resp = client.post(
        "/api/v1/ai/anomaly-explanation",
        json={"variant_id": variant_id, "parameter": "dome_thickness_mm"},
    )
    assert resp.status_code == 503, resp.text
    assert "LLM_BASE_URL" in resp.json()["detail"]


def test_anomaly_explanation_requires_auth(client):
    variant_id = _fixture(client, [0.10, 0.11, 0.09])
    # drop the conftest default override: an unsigned token must be rejected
    app.dependency_overrides.pop(get_current_user, None)
    token = f"anon-{uuid.uuid4().hex}"
    resp = client.post(
        "/api/v1/ai/anomaly-explanation",
        json={"variant_id": variant_id, "parameter": "dome_thickness_mm"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (401, 403), resp.text
