"""Loopback HTTP executor: calls THIS API with the end user's own bearer
token. HTTP errors are returned as data (never raised) — the model reasons
over 4xx responses and confirmation cards render them."""

from typing import Any

import httpx


def call(
    loopback: httpx.Client,
    token: str,
    method: str,
    path: str,
    json_body: dict | None = None,
    headers: dict | None = None,
) -> dict[str, Any]:
    """Returns {"status": int, "json": ... | "text": ...}. A 401 mid-loop
    means the user's Keycloak token expired — callers turn that into a
    friendly end-of-turn message rather than retrying with a stale token."""
    try:
        resp = loopback.request(
            method,
            path,
            json=json_body,
            headers={"Authorization": f"Bearer {token}", **(headers or {})},
        )
    except httpx.HTTPError as exc:
        return {"status": 0, "error": f"loopback transport error: {exc}"}
    try:
        body: Any = resp.json()
    except ValueError:
        body = None
    result = {"status": resp.status_code, "json": body}
    if body is None:
        result["text"] = resp.text[:500]
    return result
