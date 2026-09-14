"""AI assistant tools. Read tools execute immediately via loopback HTTP
carrying the END USER'S bearer token — so the API's own RBAC/validation/
gate-readiness rules apply with zero new auth paths (§10.2 permission check
before retrieval). Write tools are NEVER executed inside the model loop:
they only produce a pending confirmation (see store.py)."""

import json
from datetime import datetime, timezone
from typing import Any

import httpx

MAX_LIST_ITEMS = 20
MAX_RESULT_CHARS = 8000


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    # OpenAI function-calling wire format (also what Ollama's /v1 speaks).
    # No "strict": true — it requires every property listed in `required`,
    # which conflicts with our nullable-optional args (name, entity_type).
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


# additionalProperties: false keeps models from inventing arguments.
TOOL_SCHEMAS: list[dict] = [
    _tool("get_products", "List all products.", {}, []),
    _tool("get_variants", "List variants of a product.", {"product_id": {"type": "string"}}, ["product_id"]),
    _tool("get_requirements", "List requirements of a variant.", {"variant_id": {"type": "string"}}, ["variant_id"]),
    _tool("get_components", "List 3D components of a variant.", {"variant_id": {"type": "string"}}, ["variant_id"]),
    _tool("get_twin_graph", "Requirement-to-component trace graph of a variant.", {"variant_id": {"type": "string"}}, ["variant_id"]),
    _tool("get_impact_paths", "Physical causal-chain graph of a variant (input force → mechanism → electrical → control → kansei). Edge provenance is human_approved, rule_derived, ai_inferred or imported — never present an ai_inferred relation as confirmed.", {"variant_id": {"type": "string"}}, ["variant_id"]),
    _tool("get_baselines", "List baselines of a variant.", {"variant_id": {"type": "string"}}, ["variant_id"]),
    _tool("get_simulation_runs", "List simulation runs of a variant (status, metrics, tool versions).", {"variant_id": {"type": "string"}}, ["variant_id"]),
    _tool("get_correlations", "List model-vs-test correlation records of a simulation run.", {"simulation_run_id": {"type": "string"}}, ["simulation_run_id"]),
    _tool("get_test_plans", "List test plans of a variant.", {"variant_id": {"type": "string"}}, ["variant_id"]),
    _tool("get_test_run", "Get one test run with its measurements.", {"test_run_id": {"type": "string"}}, ["test_run_id"]),
    _tool("get_gates", "List review gates of a variant.", {"variant_id": {"type": "string"}}, ["variant_id"]),
    _tool("get_gate_detail", "One gate with its comments and decisions.", {"gate_id": {"type": "string"}}, ["gate_id"]),
    _tool("get_recent_audit_events", "Recent audit-trail events. Pass entity_type as null to list all.", {"entity_type": {"type": ["string", "null"]}}, ["entity_type"]),
    # --- write tools: intercepted, require user confirmation ---
    _tool("create_baseline", "Freeze the current requirement/component set of a variant as a new baseline.", {"variant_id": {"type": "string"}}, ["variant_id"]),
    _tool(
        "open_gate",
        "Open a review gate on the variant's active baseline. Resolves the active baseline automatically. Pass name as null to use the default gate name.",
        {"variant_id": {"type": "string"}, "name": {"type": ["string", "null"]}},
        ["variant_id", "name"],
    ),
    _tool("submit_gate", "Submit a draft gate for review (server checks the evidence checklist and blocks on gaps).", {"gate_id": {"type": "string"}}, ["gate_id"]),
    _tool("add_gate_comment", "Add a review comment to a gate.", {"gate_id": {"type": "string"}, "text": {"type": "string", "minLength": 1}}, ["gate_id", "text"]),
    _tool(
        "decide_gate",
        "Record a review decision on a gate pending review. Requires independence: the decider must differ from the submitter.",
        {"gate_id": {"type": "string"}, "decision": {"type": "string", "enum": ["approved", "rejected", "conditionally_approved"]}, "comment": {"type": "string", "minLength": 1}},
        ["gate_id", "decision", "comment"],
    ),
]

READ_TOOLS = frozenset({
    "get_products", "get_variants", "get_requirements", "get_components", "get_twin_graph",
    "get_impact_paths",
    "get_baselines", "get_simulation_runs", "get_correlations", "get_test_plans",
    "get_test_run", "get_gates", "get_gate_detail", "get_recent_audit_events",
})

_WRITE_TOOLS = frozenset({"create_baseline", "open_gate", "submit_gate", "add_gate_comment", "decide_gate"})

assert READ_TOOLS | _WRITE_TOOLS == {t["function"]["name"] for t in TOOL_SCHEMAS}


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")


def write_request(tool: str, args: dict) -> tuple[str, str, dict]:
    """Maps a confirmed write tool to a loopback HTTP request, synthesizing the
    server-side business_id exactly the way the UI does (GatePanel patterns).
    Returns (method, path, json_body)."""
    match tool:
        case "create_baseline":
            return "POST", "/api/v1/baselines", {
                "business_id": f"BL-AI-{_ts()}",
                "variant_id": args["variant_id"],
            }
        case "open_gate":
            # baseline resolution needs a read first — handled by the caller
            # via resolve_open_gate(); here args already contain baseline_id.
            return "POST", "/api/v1/gates", {
                "business_id": f"{args['baseline_business_id']}-GATE-VV-AI-{_ts()}",
                "variant_id": args["variant_id"],
                "baseline_id": args["baseline_id"],
                "name": args.get("name") or "Virtual Verification Complete",
            }
        case "submit_gate":
            return "POST", f"/api/v1/gates/{args['gate_id']}/submit", {}
        case "add_gate_comment":
            return "POST", f"/api/v1/gates/{args['gate_id']}/comments", {
                "business_id": f"{args['gate_id']}-comment-AI-{_ts()}",
                "text": args["text"],
            }
        case "decide_gate":
            return "POST", f"/api/v1/gates/{args['gate_id']}/decisions", {
                "business_id": f"{args['gate_id']}-decision-AI-{_ts()}",
                "decision": args["decision"],
                "comment": args["comment"],
            }
    raise ValueError(f"unknown write tool: {tool}")  # pragma: no cover


WRITE_TOOLS_NEEDING_IDEMPOTENCY = frozenset({"create_baseline", "open_gate", "add_gate_comment", "decide_gate"})


def summarize_args(tool: str, args: dict) -> str:
    """Compact JSON of the proposal shown on the confirmation card (the card's
    sentence itself is localized client-side from tool + args)."""
    show = {k: v for k, v in args.items() if k != "text"} if tool == "add_gate_comment" else args
    if tool == "add_gate_comment":
        text = str(args.get("text", ""))
        return json.dumps({**show, "text": text if len(text) <= 200 else text[:200] + "…"}, ensure_ascii=False)
    return json.dumps(show, ensure_ascii=False)


def _compact(obj: Any, depth: int = 0) -> Any:
    """Trims tool results before they re-enter model context: lists capped,
    long strings clipped. Gate evidence manifests can be large."""
    if isinstance(obj, list):
        items = [_compact(i, depth + 1) for i in obj[:MAX_LIST_ITEMS]]
        if len(obj) > MAX_LIST_ITEMS:
            items.append({"_truncated": f"{len(obj) - MAX_LIST_ITEMS} more items omitted"})
        return items
    if isinstance(obj, dict):
        return {k: _compact(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, str) and len(obj) > 500:
        return obj[:500] + "…"
    return obj


def compact_result(payload: Any) -> str:
    text = json.dumps(_compact(payload), ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "…(truncated)"
    return text
