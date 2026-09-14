"""The assistant conversation loop (manual tool-use loop — chosen over SDK
runners because the confirmation flow needs custom control: write tools halt
the turn and wait for a human). Thread contract: the server returns the
canonical, JSON-safe thread and the client echoes it back untouched. Thread
shape is the OpenAI chat format (user/assistant strings, assistant
tool_calls, role:"tool" results) since the provider switch to the local
Ollama daemon — see AGENTS.md Phase 3."""

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import OpenAI

from app.assistant.loopback import call
from app.assistant.prompts import UiLanguage, build_system_prompt
from app.assistant.store import PendingActionStore, pending_actions
from app.assistant.tools import (
    READ_TOOLS,
    TOOL_SCHEMAS,
    WRITE_TOOLS_NEEDING_IDEMPOTENCY,
    compact_result,
    summarize_args,
    write_request,
)
from app.config import settings

_MAX_TEXT_CHARS = 8000


@dataclass
class ChatResult:
    display: list[dict] = field(default_factory=list)
    pending_action: dict | None = None
    thread: list[dict] = field(default_factory=list)


def sanitize_messages(messages: list[dict]) -> list[dict]:
    """Client-echoed thread + possibly a new user text message. Only the
    shapes the server itself produces are accepted. Raises ValueError —
    the router maps that to 422."""
    if len(messages) > settings.assistant_max_messages:
        raise ValueError("conversation too long — start a new one")
    out: list[dict] = []
    for m in messages:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant", "tool"):
            raise ValueError("bad message role")
        role = m["role"]
        content = m.get("content")
        if role == "user":
            # string now; tolerate the legacy single-text-block form
            if isinstance(content, list) and len(content) == 1 and content[0].get("type") == "text":
                content = content[0].get("text")
            if not isinstance(content, str):
                raise ValueError("bad user message content")
            out.append({"role": "user", "content": content[:_MAX_TEXT_CHARS]})
        elif role == "assistant":
            if content is not None and not isinstance(content, str):
                raise ValueError("bad assistant message content")
            entry: dict = {"role": "assistant", "content": content}
            tool_calls = m.get("tool_calls")
            if tool_calls is not None:
                if not isinstance(tool_calls, list) or not tool_calls:
                    raise ValueError("bad tool_calls")
                for tc in tool_calls:
                    fn = tc.get("function") if isinstance(tc, dict) else None
                    if (
                        not isinstance(fn, dict)
                        or not isinstance(tc.get("id"), str)
                        or not isinstance(fn.get("name"), str)
                        or not isinstance(fn.get("arguments"), str)
                    ):
                        raise ValueError("bad tool_call entry")
                entry["tool_calls"] = tool_calls
            out.append(entry)
        else:  # tool result
            if not isinstance(content, str) or not isinstance(m.get("tool_call_id"), str):
                raise ValueError("bad tool message")
            out.append({
                "role": "tool",
                "tool_call_id": m["tool_call_id"],
                "content": content[:_MAX_TEXT_CHARS],
            })
    if not out or out[0]["role"] != "user":
        raise ValueError("conversation must start with a user message")
    return out


class AssistantService:
    def __init__(self, client: OpenAI, loopback: httpx.Client, store: PendingActionStore) -> None:
        self.client = client
        self.loopback = loopback
        self.store = store

    # -- read tools ---------------------------------------------------------

    def _exec_read(self, name: str, args: dict, token: str) -> str:
        try:
            return self._exec_read_inner(name, args, token)
        except KeyError as exc:
            # malformed/missing model argument — data back to the model, never a 500
            return json.dumps({"error": f"missing argument {exc} for tool {name}"})

    def _exec_read_inner(self, name: str, args: dict, token: str) -> str:
        if name == "get_products":
            result = call(self.loopback, token, "GET", "/api/v1/products")
        elif name == "get_variants":
            result = call(self.loopback, token, "GET", f"/api/v1/products/{args['product_id']}/variants")
        elif name == "get_requirements":
            result = call(self.loopback, token, "GET", f"/api/v1/variants/{args['variant_id']}/requirements")
        elif name == "get_components":
            result = call(self.loopback, token, "GET", f"/api/v1/variants/{args['variant_id']}/components")
        elif name == "get_twin_graph":
            result = call(self.loopback, token, "GET", f"/api/v1/twins/{args['variant_id']}/graph")
        elif name == "get_impact_paths":
            result = call(self.loopback, token, "GET", f"/api/v1/twins/{args['variant_id']}/impact-paths")
        elif name == "get_baselines":
            result = call(self.loopback, token, "GET", f"/api/v1/variants/{args['variant_id']}/baselines")
        elif name == "get_simulation_runs":
            result = call(self.loopback, token, "GET", f"/api/v1/variants/{args['variant_id']}/simulation-runs")
        elif name == "get_correlations":
            result = call(self.loopback, token, "GET", f"/api/v1/simulation-runs/{args['simulation_run_id']}/correlations")
        elif name == "get_test_plans":
            result = call(self.loopback, token, "GET", f"/api/v1/variants/{args['variant_id']}/test-plans")
        elif name == "get_test_run":
            result = call(self.loopback, token, "GET", f"/api/v1/test-runs/{args['test_run_id']}")
        elif name == "get_gates":
            result = call(self.loopback, token, "GET", f"/api/v1/variants/{args['variant_id']}/gates")
        elif name == "get_recent_audit_events":
            entity_type = args.get("entity_type")
            query = f"?entity_type={entity_type}&limit=20" if entity_type else "?limit=20"
            result = call(self.loopback, token, "GET", f"/api/v1/audit-events{query}")
        elif name == "get_gate_detail":
            gate = call(self.loopback, token, "GET", f"/api/v1/gates/{args['gate_id']}")
            comments = call(self.loopback, token, "GET", f"/api/v1/gates/{args['gate_id']}/comments")
            decisions = call(self.loopback, token, "GET", f"/api/v1/gates/{args['gate_id']}/decisions")
            result = {
                "status": max(gate["status"], comments["status"], decisions["status"]),
                "json": {"gate": gate.get("json"), "comments": comments.get("json"), "decisions": decisions.get("json")},
            }
        else:  # pragma: no cover — schema/READ_TOOLS assert keeps this dead
            result = {"status": 400, "json": {"error": f"unknown tool {name}"}}

        if result["status"] == 401:
            return json.dumps({"error": "session expired — the user must sign in again"})
        return compact_result(result.get("json", result))

    # -- main loop ----------------------------------------------------------

    def run_chat(self, *, token: str, user_subject: str, messages: list[dict], ui_language: UiLanguage) -> ChatResult:
        thread = sanitize_messages(messages)
        system = build_system_prompt(ui_language, user_subject)
        pending: dict | None = None
        session_expired = False

        for _ in range(settings.assistant_max_tool_rounds):
            response = self.client.chat.completions.create(
                model=settings.llm_model,
                max_tokens=settings.llm_max_tokens,
                # qwen2.5 hallucinates argument JSON at high temperature;
                # near-greedy keeps tool-call args and id resolution stable
                temperature=0.1,
                messages=[{"role": "system", "content": system}, *thread],
                tools=TOOL_SCHEMAS,
            )
            msg = response.choices[0].message

            assistant_entry: dict = {"role": "assistant", "content": msg.content}
            if msg.tool_calls:
                # rebuilt field-by-field (not model_dump) so test fakes can be plain objects
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ]
            thread.append(assistant_entry)
            if not msg.tool_calls:
                break

            tool_messages: list[dict] = []
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = None
                if not isinstance(args, dict):
                    tool_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({"error": "malformed tool arguments — call the tool again with a JSON object"}),
                    })
                    continue
                if tc.function.name in READ_TOOLS:
                    payload = self._exec_read(tc.function.name, args, token)
                    expired = "session expired" in payload
                    tool_messages.append({"role": "tool", "tool_call_id": tc.id, "content": payload})
                    if expired:
                        session_expired = True
                else:
                    action = self.store.create(
                        user_subject=user_subject,
                        tool=tc.function.name,
                        args=args,
                        tool_use_id=tc.id,
                    )
                    pending = {
                        "action_id": action.action_id,
                        "tool": tc.function.name,
                        "tool_use_id": tc.id,  # wire name kept: the provider's tool_call id
                        "args": action.args,
                        "summary_args": summarize_args(tc.function.name, args),
                    }
                    tool_messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({
                            "status": "requires_user_confirmation",
                            "action_id": action.action_id,
                            "note": "waiting for explicit user confirmation; do not assume execution",
                        }),
                    })

            thread.extend(tool_messages)
            if pending or session_expired:
                break  # human in the loop (or dead session) ends the turn

        display = [
            {"type": "text", "text": m["content"]}
            for m in thread
            if m["role"] == "assistant" and isinstance(m.get("content"), str) and m["content"].strip()
        ]

        return ChatResult(
            display=display,
            pending_action=pending,
            thread=[dict(m) for m in thread],
        )


def build_default_service() -> AssistantService:
    from app.assistant.client import get_llm_client, get_loopback_client

    return AssistantService(get_llm_client(), get_loopback_client(), pending_actions)


def execute_confirmed_action(
    loopback: httpx.Client,
    token: str,
    tool: str,
    args: dict,
    action_id: str,
) -> dict:
    """Runs the write behind an approved confirmation card. `open_gate` may
    need a baseline read first (the model often doesn't know its id)."""
    if tool == "open_gate" and "baseline_id" not in args:
        baselines = call(loopback, token, "GET", f"/api/v1/variants/{args['variant_id']}/baselines")
        active = next(
            (b for b in (baselines.get("json") or []) if b.get("status") == "active"),
            None,
        )
        if active is None:
            return {"status": "failed", "detail": "no active baseline — create_baseline first"}
        args = {**args, "baseline_id": active["id"], "baseline_business_id": active["business_id"]}

    method, path, body = write_request(tool, args)
    headers = (
        {"Idempotency-Key": f"ai-assist-{action_id}"}
        if tool in WRITE_TOOLS_NEEDING_IDEMPOTENCY
        else None
    )
    result = call(loopback, token, method, path, json_body=body or None, headers=headers)
    if 200 <= result["status"] < 300:
        return {"status": "executed", "tool": tool, "result": result.get("json")}
    return {"status": "failed", "detail": result.get("json") or result.get("text", "unknown error")}
