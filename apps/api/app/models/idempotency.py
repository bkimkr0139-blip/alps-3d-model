import uuid

from sqlalchemy import Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import utcnow
from datetime import datetime

from sqlalchemy import DateTime


class IdempotencyRecord(Base):
    """Caches the response of a write so a retried request with the same
    Idempotency-Key + actor + endpoint returns the original result (§9.3).

    Deliberately not a domain entity (no Business ID / provenance mixin) —
    this is technical bookkeeping, not something engineers browse.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("key", "endpoint", "actor", name="uq_idempotency_scope"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    key: Mapped[str] = mapped_column(String(255))
    endpoint: Mapped[str] = mapped_column(String(255))
    actor: Mapped[str] = mapped_column(String(255))
    status_code: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
