"""AI assistant endpoint tests. No real LLM calls, no real network for
loopback: the OpenAI-compatible client is a scripted fake (dependency
override), and the loopback client points at the SAME app running under an
ephemeral uvicorn server — so confirms exercise real routing, validation and
RBAC."""

import json
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.assistant.client import get_llm_client, get_loopback_client
from app.assistant.store import pending_actions
from app.config import settings
from app.main import app
from app.security import get_current_user
from tests.conftest import APPROVER, as_user, test_engine

# HTTPBearer requires the header to be present even though get_current_user is
# overridden — the loopback path forwards exactly this credential.
AUTH = {"Authorization": "Bearer test-token-xyz"}


# --- fakes ---------------------------------------------------------------


def fake_tool_call(call_id: str, name: str, args: dict):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def fake_response(content: str | None = None, tool_calls: list | None = None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeLLM:
    """Scripts chat.completions.create responses in order; records every
    request's tools/messages."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


# --- fixtures ------------------------------------------------------------


@pytest.fixture(scope="session")
def loopback_base_url():
    """The real app on an ephemeral port — the production loopback path."""
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started, "uvicorn test server did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def override_loopback(loopback_base_url: str):
    client = httpx.Client(base_url=loopback_base_url, timeout=10.0)
    app.dependency_overrides[get_loopback_client] = lambda: client
    return client


def override_llm(fake: FakeLLM):
    app.dependency_overrides[get_llm_client] = lambda: fake


def seed_variant(client: TestClient) -> str:
    product = client.post(
        "/api/v1/products", json={"business_id": "P-AI-1", "name": "AI Test Product"}
    ).json()
    variant = client.post(
        f"/api/v1/products/{product['id']}/variants",
        json={"business_id": "V-AI-1", "name": "AI Test Variant"},
    ).json()
    for i in range(2):
        client.post(
            "/api/v1/requirements",
            json={
                "business_id": f"REQ-AI-{i}",
                "variant_id": variant["id"],
                "text": f"Requirement {i}",
                "verification_method": "test",
                "owner": "test.architect",
            },
        )
    return variant["id"]


def chat(client: TestClient, messages: list[dict], ui_language: str = "en"):
    return client.post(
        "/api/v1/assistant/chat",
        json={"messages": messages, "ui_language": ui_language},
        headers=AUTH,
    )


def baseline_count() -> int:
    with test_engine.begin() as conn:
        return conn.execute(text("SELECT count(*) FROM baselines")).scalar()


# --- tests ---------------------------------------------------------------


def test_chat_read_tool_happy_path(client, loopback_base_url):
    variant_id = seed_variant(client)
    fake = FakeLLM([
        fake_response(tool_calls=[fake_tool_call("call_1", "get_requirements", {"variant_id": variant_id})]),
        fake_response(content="There are 2 requirements."),
    ])
    override_llm(fake)
    override_loopback(loopback_base_url)

    resp = chat(client, [{"role": "user", "content": "How many requirements are there?"}])

    assert resp.status_code == 200
    body = resp.json()
    assert body["pending_action"] is None
    assert any("2 requirements" in d["text"] for d in body["display"])
    # tool round-trip present in the canonical thread
    roles = [m["role"] for m in body["thread"]]
    assert roles == ["user", "assistant", "tool", "assistant"]
    tool_msg = body["thread"][2]
    assert tool_msg["tool_call_id"] == "call_1"
    assert '"business_id": "REQ-AI-0"' in tool_msg["content"]
    # the request to the model carried the system prompt + the thread with the tool result
    assert len(fake.calls) == 2
    assert fake.calls[1]["messages"][0]["role"] == "system"
    assert any(m.get("role") == "tool" for m in fake.calls[1]["messages"])


def test_read_tool_forwards_user_token(client):
    """Loopback must carry the END USER's bearer token (RBAC rides on it)."""
    variant_id = seed_variant(client)
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json=[])

    fake = FakeLLM([
        fake_response(tool_calls=[fake_tool_call("call_1", "get_requirements", {"variant_id": variant_id})]),
        fake_response(content="ok"),
    ])
    override_llm(fake)
    app.dependency_overrides[get_loopback_client] = lambda: httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://testserver"
    )

    resp = chat(client, [{"role": "user", "content": "list requirements"}])

    assert resp.status_code == 200
    assert captured["authorization"] == AUTH["Authorization"]


def test_write_tool_intercepted_creates_pending_action(client, loopback_base_url):
    variant_id = seed_variant(client)
    fake = FakeLLM([
        fake_response(tool_calls=[fake_tool_call("call_w1", "create_baseline", {"variant_id": variant_id})]),
    ])
    override_llm(fake)
    override_loopback(loopback_base_url)

    resp = chat(client, [{"role": "user", "content": "Create a baseline please"}])

    assert resp.status_code == 200
    body = resp.json()
    assert body["pending_action"] is not None
    assert body["pending_action"]["tool"] == "create_baseline"
    assert body["pending_action"]["tool_use_id"] == "call_w1"
    # nothing written yet — the human has not confirmed
    assert baseline_count() == 0
    tool_msg = body["thread"][2]
    assert tool_msg["role"] == "tool"
    assert "requires_user_confirmation" in tool_msg["content"]


def test_malformed_tool_arguments_fed_back_not_raised(client, loopback_base_url):
    variant_id = seed_variant(client)
    broken = SimpleNamespace(
        id="call_x",
        function=SimpleNamespace(name="get_requirements", arguments="{not json"),
    )
    fake = FakeLLM([
        fake_response(tool_calls=[broken]),
        fake_response(content="The arguments were malformed."),
    ])
    override_llm(fake)
    override_loopback(loopback_base_url)

    resp = chat(client, [{"role": "user", "content": "list requirements"}])

    assert resp.status_code == 200
    assert "malformed tool arguments" in resp.json()["thread"][2]["content"]


def test_confirm_executes_and_double_confirm_conflicts(client, loopback_base_url):
    variant_id = seed_variant(client)
    fake = FakeLLM([
        fake_response(tool_calls=[fake_tool_call("call_w2", "create_baseline", {"variant_id": variant_id})]),
    ])
    override_llm(fake)
    override_loopback(loopback_base_url)

    body = chat(client, [{"role": "user", "content": "Create a baseline"}]).json()
    action_id = body["pending_action"]["action_id"]

    resp = client.post(f"/api/v1/assistant/actions/{action_id}/confirm", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "executed"
    assert baseline_count() == 1

    resp = client.post(f"/api/v1/assistant/actions/{action_id}/confirm", headers=AUTH)
    assert resp.status_code == 409


def test_confirm_wrong_user_forbidden(client, loopback_base_url):
    variant_id = seed_variant(client)
    fake = FakeLLM([
        fake_response(tool_calls=[fake_tool_call("call_w3", "create_baseline", {"variant_id": variant_id})]),
    ])
    override_llm(fake)
    override_loopback(loopback_base_url)

    body = chat(client, [{"role": "user", "content": "Create a baseline"}]).json()
    action_id = body["pending_action"]["action_id"]

    # a different signed-in user must not confirm someone else's card
    as_user(client, APPROVER)
    resp = client.post(f"/api/v1/assistant/actions/{action_id}/confirm", headers=AUTH)
    assert resp.status_code == 403
    assert baseline_count() == 0


def test_cancel_then_confirm_conflicts(client, loopback_base_url):
    variant_id = seed_variant(client)
    fake = FakeLLM([
        fake_response(tool_calls=[fake_tool_call("call_w4", "create_baseline", {"variant_id": variant_id})]),
    ])
    override_llm(fake)
    override_loopback(loopback_base_url)

    body = chat(client, [{"role": "user", "content": "Create a baseline"}]).json()
    action_id = body["pending_action"]["action_id"]

    assert client.post(f"/api/v1/assistant/actions/{action_id}/cancel", headers=AUTH).status_code == 200
    assert client.post(f"/api/v1/assistant/actions/{action_id}/confirm", headers=AUTH).status_code == 409


def test_ttl_expiry(client, loopback_base_url):
    variant_id = seed_variant(client)
    fake = FakeLLM([
        fake_response(tool_calls=[fake_tool_call("call_w5", "create_baseline", {"variant_id": variant_id})]),
    ])
    override_llm(fake)
    override_loopback(loopback_base_url)

    body = chat(client, [{"role": "user", "content": "Create a baseline"}]).json()
    action_id = body["pending_action"]["action_id"]

    pending_actions.get(action_id).created_at -= settings.assistant_pending_ttl_seconds + 1
    resp = client.post(f"/api/v1/assistant/actions/{action_id}/confirm", headers=AUTH)
    assert resp.status_code == 404


def test_unknown_action_404(client):
    override_llm(FakeLLM([]))
    resp = client.post("/api/v1/assistant/actions/deadbeef/confirm", headers=AUTH)
    assert resp.status_code == 404


def test_unconfigured_base_url_503(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "")
    resp = chat(client, [{"role": "user", "content": "hi"}])
    assert resp.status_code == 503
    assert "LLM_BASE_URL" in resp.json()["detail"]


def test_thread_echo_with_new_user_message_422_shapes(client, loopback_base_url):
    """The canonical thread round-trips: server output must sanitize cleanly
    when echoed back with a new user message appended."""
    variant_id = seed_variant(client)
    fake = FakeLLM([
        fake_response(tool_calls=[fake_tool_call("call_r", "get_requirements", {"variant_id": variant_id})]),
        fake_response(content="2 requirements found."),
        fake_response(content="Gates list is empty."),
    ])
    override_llm(fake)
    override_loopback(loopback_base_url)

    body = chat(client, [{"role": "user", "content": "list requirements"}]).json()
    echoed = body["thread"] + [{"role": "user", "content": "and gates?"}]
    resp = chat(client, echoed)
    assert resp.status_code == 200, resp.text  # canonical thread survives its own sanitizer

    # a tampered tool message (non-string content) must 422
    bad = [dict(m) for m in body["thread"]]
    bad[2] = {**bad[2], "content": None}
    assert chat(client, bad + [{"role": "user", "content": "hi"}]).status_code == 422


def test_too_many_messages_422(client):
    override_llm(FakeLLM([]))
    messages = [{"role": "user", "content": f"m{i}"} for i in range(settings.assistant_max_messages + 1)]
    resp = chat(client, messages)
    assert resp.status_code == 422
