"""In-process store for AI-proposed state-changing actions awaiting user
confirmation (user decision: reads immediate, writes behind a confirmation
card). Deliberately simple: a dict with TTL, valid for the single-uvicorn-
worker runbook this PoC ships with. Scale-out path (Redis/DB) is deferred.
A restart therefore expires pending cards — the UI shows a localized
"expired" note and the user re-asks."""

import time
import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException, status

from app.config import settings


@dataclass
class PendingAction:
    action_id: str
    user_subject: str
    tool: str
    args: dict = field(default_factory=dict)
    tool_use_id: str = ""
    created_at: float = 0.0
    state: str = "pending"  # pending | executed | cancelled


class PendingActionStore:
    def __init__(self) -> None:
        self._actions: dict[str, PendingAction] = {}

    def create(self, *, user_subject: str, tool: str, args: dict, tool_use_id: str) -> PendingAction:
        self._sweep()
        action = PendingAction(
            action_id=uuid.uuid4().hex,
            user_subject=user_subject,
            tool=tool,
            args=args,
            tool_use_id=tool_use_id,
            created_at=time.time(),
        )
        self._actions[action.action_id] = action
        return action

    def get(self, action_id: str) -> PendingAction | None:
        self._sweep()
        return self._actions.get(action_id)

    def consume(self, action_id: str, user_subject: str, new_state: str) -> PendingAction:
        """Atomically moves a pending action to executed/cancelled. 404 for
        unknown/expired, 403 for a different user (binding is by Keycloak
        subject, so one user can never confirm another user's card)."""
        action = self.get(action_id)
        if action is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "action not found or expired — ask the assistant again",
            )
        if action.user_subject != user_subject:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "action belongs to a different user")
        if action.state != "pending":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"action already {action.state}",
            )
        action.state = new_state
        return action

    def _sweep(self) -> None:
        ttl = settings.assistant_pending_ttl_seconds
        now = time.time()
        expired = [aid for aid, a in self._actions.items() if a.state == "pending" and now - a.created_at > ttl]
        for aid in expired:
            del self._actions[aid]
        # executed/cancelled records linger until their own TTL passes so
        # double-clicks get a clean 409 instead of a confusing 404.
        stale = [aid for aid, a in self._actions.items() if a.state != "pending" and now - a.created_at > ttl]
        for aid in stale:
            del self._actions[aid]


pending_actions = PendingActionStore()
