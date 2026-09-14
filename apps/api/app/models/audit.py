import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import IdentifiedMixin, ProvenanceMixin


class AuditEvent(Base, IdentifiedMixin, ProvenanceMixin):
    """Append-only audit trail (§FR-09). Never updated or deleted from the app layer."""

    __tablename__ = "audit_events"

    actor: Mapped[str] = mapped_column(String(255))
    actor_roles: Mapped[list] = mapped_column(JSONB)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    correlation_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
