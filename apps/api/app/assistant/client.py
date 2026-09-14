"""Client factories for the AI assistant, exposed as FastAPI dependencies so
tests can override them (conftest-style dependency_overrides) instead of
mocking the SDK. Deterministic: settings values only — never an ambient login
profile. Any OpenAI-compatible endpoint works; the default is the local
Ollama daemon (macOS Studio deployment), which needs no API key."""

import httpx
from fastapi import HTTPException, status
from openai import OpenAI

from app.config import settings


def get_llm_client() -> OpenAI:
    if not settings.llm_base_url:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI assistant is not configured: set LLM_BASE_URL (settings or environment)",
        )
    # Non-streaming create() with a long timeout — local 32B-class models take
    # tens of seconds per multi-tool turn; max_retries covers daemon hiccups.
    return OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key or "local",
        timeout=300.0,
        max_retries=2,
    )


def get_loopback_client() -> httpx.Client:
    """HTTP client the assistant tools use to call THIS API back with the end
    user's bearer token. Tests override it with ASGITransport(app=app)."""
    return httpx.Client(base_url=settings.internal_api_base_url, timeout=60.0)
