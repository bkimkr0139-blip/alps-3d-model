import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor: str
    actor_roles: list[str]
    action: str
    entity_type: str
    entity_id: uuid.UUID
    correlation_id: str
    payload: dict
    created_at: datetime
