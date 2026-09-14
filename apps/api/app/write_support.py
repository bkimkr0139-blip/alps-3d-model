"""Cross-cutting concerns every write endpoint must apply, per §9.3 / §10.1:
idempotency, actor/audit trail, and correlation-id propagation."""

import uuid
from collections.abc import Callable

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.idempotency import IdempotencyRecord
from app.security import CurrentUser


def get_correlation_id(
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-Id")
) -> str:
    return x_correlation_id or str(uuid.uuid4())


def get_idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")
) -> str | None:
    return idempotency_key


def record_audit(
    db: Session,
    *,
    user: CurrentUser,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    correlation_id: str,
    payload: dict,
) -> None:
    db.add(
        AuditEvent(
            business_id=f"audit-{uuid.uuid4()}",
            created_by=user.username,
            actor=user.username,
            actor_roles=sorted(user.roles),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=correlation_id,
            payload=payload,
        )
    )


def idempotent_write(
    db: Session,
    *,
    request: Request,
    idempotency_key: str | None,
    user: CurrentUser,
    compute: Callable[[], tuple[int, dict]],
) -> dict:
    """Runs `compute()` at most once per (Idempotency-Key, endpoint, actor).

    A retried request with the same key returns the cached response instead
    of re-executing the write (§9.3: every write API takes an Idempotency-Key).
    """
    endpoint = request.scope.get("route").path if request.scope.get("route") else request.url.path

    if idempotency_key:
        existing = (
            db.query(IdempotencyRecord)
            .filter_by(key=idempotency_key, endpoint=endpoint, actor=user.username)
            .one_or_none()
        )
        if existing is not None:
            if existing.status_code >= 400:
                raise HTTPException(existing.status_code, existing.response_body)
            return existing.response_body

    status_code, body = compute()

    if idempotency_key:
        db.add(
            IdempotencyRecord(
                key=idempotency_key,
                endpoint=endpoint,
                actor=user.username,
                status_code=status_code,
                response_body=body,
            )
        )
        try:
            db.flush()
        except IntegrityError:
            # lost a race with a concurrent identical request — fetch its result
            db.rollback()
            existing = (
                db.query(IdempotencyRecord)
                .filter_by(key=idempotency_key, endpoint=endpoint, actor=user.username)
                .one()
            )
            return existing.response_body

    if status_code >= 400:
        raise HTTPException(status_code, body)
    return body
