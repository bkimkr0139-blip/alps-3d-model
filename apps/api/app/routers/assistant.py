from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import BaseModel

from app.assistant.client import get_llm_client, get_loopback_client
from app.assistant.service import AssistantService, execute_confirmed_action
from app.assistant.store import pending_actions
from app.config import settings
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

# The raw bearer credential (not just CurrentUser) is needed: assistant tools
# ride loopback calls with the END USER'S token, so the API's own RBAC applies.
_bearer = HTTPBearer()

TokenCred = Annotated[HTTPAuthorizationCredentials, Depends(_bearer)]
UserDep = Annotated[CurrentUser, Depends(get_current_user)]
LoopbackDep = Annotated[httpx.Client, Depends(get_loopback_client)]
LlmDep = Annotated[OpenAI, Depends(get_llm_client)]


class ChatMessage(BaseModel):
    # tool_calls / tool_call_id must survive the parse→model_dump round trip —
    # they are TOP-LEVEL keys of the OpenAI thread shape (the old Anthropic
    # block format carried everything inside `content`, so {role, content}
    # used to be enough).
    role: str
    content: Any
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    ui_language: Literal["ko", "en", "ja"] = "en"


@router.post("/chat")
def chat(
    body: ChatRequest,
    user: UserDep,
    token_cred: TokenCred,
    client: LlmDep,
    loopback: LoopbackDep,
):
    """One assistant turn. `messages` is the thread the server returned last
    time (echoed verbatim) plus the new user message. ValueError from
    sanitization → 422 so the client shows a 'start a new conversation' note;
    unreachable/failed LLM provider → 503/502 so the client shows the
    'assistant unavailable' note instead of a generic 500."""
    service = AssistantService(client, loopback, pending_actions)
    try:
        result = service.run_chat(
            token=token_cred.credentials,
            user_subject=user.subject,
            messages=[m.model_dump() for m in body.messages],
            ui_language=body.ui_language,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except APIConnectionError as exc:  # includes APITimeoutError
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"cannot reach the LLM at {settings.llm_base_url} (model {settings.llm_model}) — is it running?",
        ) from exc
    except APIStatusError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"LLM provider error ({exc.status_code}): {exc.message}",
        ) from exc
    return {
        "display": result.display,
        "pending_action": result.pending_action,
        "thread": result.thread,
    }


@router.post("/actions/{action_id}/confirm")
def confirm_action(
    action_id: str,
    user: UserDep,
    token_cred: TokenCred,
    loopback: LoopbackDep,
):
    """Executes a confirmed write. Runs with the CONFIRMER'S token through the
    normal API (RBAC, independence, gate readiness all enforced there). A
    loopback 4xx is returned as status:"failed" data — not raised — so the
    card can render e.g. the 412 missing-evidence list or the 403
    independence rejection and the model can explain it next turn."""
    action = pending_actions.consume(action_id, user.subject, new_state="executed")
    outcome = execute_confirmed_action(loopback, token_cred.credentials, action.tool, action.args, action.action_id)
    return {"action_id": action_id, "tool": action.tool, **outcome}


@router.post("/actions/{action_id}/cancel")
def cancel_action(action_id: str, user: UserDep):
    pending_actions.consume(action_id, user.subject, new_state="cancelled")
    return {"action_id": action_id, "status": "cancelled"}
