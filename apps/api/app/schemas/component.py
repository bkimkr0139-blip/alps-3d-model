import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ComponentLink(BaseModel):
    artifact_version_id: uuid.UUID


class ComponentCreate(BaseModel):
    business_id: str
    variant_id: uuid.UUID
    name: str
    artifact_version_id: uuid.UUID | None = None


class ComponentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    variant_id: uuid.UUID
    name: str
    artifact_version_id: uuid.UUID | None
    created_by: str
    created_at: datetime
