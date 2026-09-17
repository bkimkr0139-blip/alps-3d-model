"""AXOS 피드백 폐루프 — 웹 접수 채널.

화면의 AXOS 피드백 버튼이 접수한 피드백을 ALPS 저장소 루트의 ``feedback/``에
FB-####.json 한 건으로 기록한다. 레코드 스키마는 axos-si 플러그인의
feedback.py(상태머신 실행기)와 동일하다 — 웹 접수는 또 하나의 채널일 뿐이고,
개발팀은 같은 큐를 다음처럼 소비한다::

    python3 ~/works/axos-si/skills/axos-feedback-loop/scripts/feedback.py --root <alps> list

DB 마이그레이션이 없는 파일 저장소(assistant/store.py의 단순 저장 선례).
개인정보(제출자 계정)를 담으므로 ``feedback/``는 저장소 커밋 대상이 아니다.
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.feedback import FeedbackCreate, FeedbackCreated, FeedbackSummary
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/v1", tags=["feedback"])

# ALPS 저장소 루트(apps/api/app/routers/feedback.py 에서 routers→app→api→apps
# 의 4단 위). 테스트는 tmp_path로 갈아끼운다.
STORE_DIR = Path(__file__).resolve().parents[4] / "feedback"

_PREFIX = "FB"
_ALLOWED_PRIORITIES = ("상", "중", "하")
# 웹 접수 레코드에만 실리는 자동 맥락. feedback.py가 모르는 키라도 읽고/갱신/
# 저장할 때 통과만 하므로 스키마를 깨지 않는다.
_CHANNEL_SOURCE = "alps_web"

# sync 엔드포인트는 스레드풀에서 돌므로 ID 할당+기록은 한 번에.
_lock = threading.Lock()


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _next_id(store: Path) -> str:
    """상수위 마크(high-water) 방식 ID — 반려로 빠진 번호의 재발급 방지."""
    seq = 0
    seq_file = store / ".sequence"
    if seq_file.exists():
        try:
            seq = int(seq_file.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            seq = 0
    for path in store.glob(f"{_PREFIX}-*.json"):
        try:
            seq = max(seq, int(path.stem.rsplit("-", 1)[-1]))
        except ValueError:
            continue
    return f"{_PREFIX}-{seq + 1:04d}"


def _write_record(store: Path, record: dict) -> None:
    store.mkdir(parents=True, exist_ok=True)
    path = store / f"{record['id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    # 상수위를 디스크에 남긴다 — reject(레코드 삭제) 후에도 번호 재사용 금지.
    seq_file = store / ".sequence"
    current = record["id"].rsplit("-", 1)[-1]
    if not seq_file.exists() or seq_file.read_text(encoding="utf-8").strip() != current:
        seq_file.write_text(current + "\n", encoding="utf-8")


@router.post("/feedback", response_model=FeedbackCreated, status_code=201)
def submit_feedback(
    body: FeedbackCreate,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> FeedbackCreated:
    if body.priority not in _ALLOWED_PRIORITIES:
        raise HTTPException(status_code=422, detail="priority must be one of 상|중|하")
    record = {
        # axos-si feedback.py 레코드 스키마(고정 키) — 순서·이름 그대로.
        "id": "",
        "status": "접수",
        "created_at": _now(),
        "title": body.title.strip(),
        "category": body.category.strip() or "미분류",
        "type": "개선",
        "priority": body.priority,
        "target_screen": body.source_route.strip(),
        "related_req_ids": [],
        "as_is": body.as_is.strip(),
        "to_be": body.to_be.strip(),
        "effect": body.expected_effect.strip(),
        "attachments": [],
        "submitter": {"name": user.username, "org": body.org.strip()},
        "review": None,
        "started": None,
        "result": None,
        "rejection": None,
        # 위젯 자동 기록 맥락(경로·메뉴·필터·화면버전·데이터 기준 시각).
        "channel": {
            "source": _CHANNEL_SOURCE,
            "menu": body.source_menu.strip(),
            "filters": body.applied_filters,
            "screen_version": body.screen_version.strip(),
            "reference_time": body.data_reference_time.strip() or _now(),
        },
    }
    with _lock:
        record["id"] = _next_id(STORE_DIR)
        _write_record(STORE_DIR, record)
    return FeedbackCreated(id=record["id"], status=record["status"])


@router.get("/feedback", response_model=list[FeedbackSummary])
def list_feedback(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    route: str = Query(default=""),
    limit: int = Query(default=5, ge=1, le=50),
) -> list[FeedbackSummary]:
    if not STORE_DIR.exists():
        return []
    items: list[FeedbackSummary] = []
    for path in sorted(STORE_DIR.glob(f"{_PREFIX}-*.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if route and rec.get("target_screen") != route:
            continue
        items.append(
            FeedbackSummary(
                id=rec.get("id", path.stem),
                title=rec.get("title", ""),
                status=rec.get("status", ""),
                priority=rec.get("priority", ""),
                category=rec.get("category", ""),
                created_at=rec.get("created_at", ""),
            )
        )
    # created_at는 초 단위 — 같은 초에 몰린 접수는 ID 역순(더 큰 ID=더 나중)이
    # 최신이 되도록 타이브레이커를 둔다.
    items.sort(key=lambda s: (s.created_at, s.id), reverse=True)
    return items[:limit]
