"""AXOS 피드백 웹 접수 채널 — 파일 저장소 규약 테스트.

레코드가 axos-si feedback.py가 읽는 고정 스키마(접수 시 상태·제출자·대상화면)를
유지하는지, 경로 필터/건수 제한/ID 상수위가 동작하는지 검증한다. 파일 저장소라
DB 픽스처 불필요 — STORE_DIR을 tmp_path로 갈아끼운다(절대 dev DB를 보지 않음).
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.routers import feedback as feedback_router

PAYLOAD = {
    "title": "출하현황 필터 초기화 버튼 없음",
    "as_is": "필터 적용 후 초기화 불가",
    "to_be": "원클릭 초기화 제공",
    "expected_effect": "재조회 시간 단축",
    "category": "화면개선",
    "priority": "중",
    "source_route": "/model",
    "source_menu": "3D Viewer",
    "applied_filters": {"product": "MPX5700", "variant": "A"},
    "screen_version": "w7",
}


@pytest.fixture()
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(feedback_router, "STORE_DIR", tmp_path / "feedback")
    return tmp_path / "feedback"


def test_store_dir_is_repo_root() -> None:
    """STORE_DIR은 저장소 루트의 feedback/ — parents 단수 오차 회귀 방지
    (실제로 parents[3]로 두면 apps/feedback에 기록되는 버그가 나왔었다)."""
    assert feedback_router.STORE_DIR == Path(__file__).resolve().parents[3] / "feedback"


def test_submit_creates_axos_record(client: TestClient, store: Path) -> None:
    resp = client.post("/api/v1/feedback", json=PAYLOAD)
    assert resp.status_code == 201
    assert resp.json() == {"id": "FB-0001", "status": "접수"}

    record = json.loads((store / "FB-0001.json").read_text("utf-8"))
    # feedback.py가 읽는 고정 키 전부 + 제출자는 토큰 계정(서버가 채움).
    for key in (
        "id", "status", "created_at", "title", "category", "type", "priority",
        "target_screen", "related_req_ids", "as_is", "to_be", "effect",
        "attachments", "submitter", "review", "started", "result", "rejection",
    ):
        assert key in record, key
    assert record["submitter"]["name"] == "test.architect"
    assert record["target_screen"] == "/model"
    assert record["related_req_ids"] == []
    assert record["channel"]["filters"] == {"product": "MPX5700", "variant": "A"}


def test_submit_requires_title_and_as_is(client: TestClient, store: Path) -> None:
    for missing in ("title", "as_is"):
        body = {k: v for k, v in PAYLOAD.items() if k != missing}
        resp = client.post("/api/v1/feedback", json=body)
        assert resp.status_code == 422, missing
    assert not store.exists()


def test_submit_rejects_raw_priority(client: TestClient, store: Path) -> None:
    resp = client.post("/api/v1/feedback", json={**PAYLOAD, "priority": "긴급"})
    assert resp.status_code == 422
    assert not store.exists()


def test_list_filters_by_route_and_limits(client: TestClient, store: Path) -> None:
    for route in ("/model", "/model", "/proc"):
        client.post("/api/v1/feedback", json={**PAYLOAD, "source_route": route})

    model = client.get("/api/v1/feedback", params={"route": "/model"}).json()
    assert [r["id"] for r in model] == ["FB-0002", "FB-0001"]  # 최근 우선
    assert set(model[0]) == {"id", "title", "status", "priority", "category", "created_at"}

    capped = client.get("/api/v1/feedback", params={"route": "/model", "limit": 1}).json()
    assert [r["id"] for r in capped] == ["FB-0002"]
    assert client.get("/api/v1/feedback", params={"route": "/none"}).json() == []


def test_id_high_water_not_reused(client: TestClient, store: Path) -> None:
    client.post("/api/v1/feedback", json=PAYLOAD)
    # 개발팀이 reject하면 레코드가 지워져도 번호는 재발급되지 않아야 한다 —
    # .sequence 상수위가 그 보루(feedback.py와 같은 규약).
    (store / "FB-0001.json").unlink()
    (store / ".sequence").write_text("1\n", encoding="utf-8")

    resp = client.post("/api/v1/feedback", json=PAYLOAD)
    assert resp.json()["id"] == "FB-0002"
