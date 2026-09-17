from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    """웹 접수 채널(AXOS 피드백 위젯)의 제출 페이로드.

    제목·현행(As-Is)만 필수 — 접수 도구(feedback.py)와 같은 규율. 경로·메뉴·
    필터·화면버전은 위젯이 자동 기록해 채워 넣는다. 우선순위는 위젯의 4단계
    (긴급/높음/보통/낮음)를 상/중/하로 사상한 값이 온다.
    """

    title: str = Field(min_length=1)
    as_is: str = Field(min_length=1)
    to_be: str = ""
    expected_effect: str = ""
    category: str = "화면개선"
    priority: str = "중"
    source_route: str = ""
    source_menu: str = ""
    applied_filters: dict = Field(default_factory=dict)
    screen_version: str = ""
    # 위젯이 화면 데이터의 기준 시각을 자동 기록해 실어 보낸다(빈 값이면 서버가
    # 접수 시각으로 대체).
    data_reference_time: str = ""
    org: str = ""


class FeedbackCreated(BaseModel):
    id: str
    status: str


class FeedbackSummary(BaseModel):
    id: str
    title: str
    status: str
    priority: str
    category: str
    created_at: str
