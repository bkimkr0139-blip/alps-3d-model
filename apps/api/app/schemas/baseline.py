import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.baseline import BaselineStatus


class BaselineCreate(BaseModel):
    business_id: str
    variant_id: uuid.UUID


class BaselineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    variant_id: uuid.UUID
    manifest: dict
    status: BaselineStatus
    created_by: str
    created_at: datetime
