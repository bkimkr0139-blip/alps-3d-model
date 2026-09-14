from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.audit import AuditEvent
from app.schemas.audit import AuditEventRead
from app.security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/v1", tags=["audit"])


@router.get("/audit-events", response_model=list[AuditEventRead])
def list_audit_events(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[CurrentUser, Depends(get_current_user)],
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=100, le=1000),
):
    query = db.query(AuditEvent)
    if entity_type:
        query = query.filter_by(entity_type=entity_type)
    if entity_id:
        query = query.filter_by(entity_id=entity_id)
    return query.order_by(AuditEvent.created_at.desc()).limit(limit).all()
