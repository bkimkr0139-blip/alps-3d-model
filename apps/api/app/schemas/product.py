import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProductCreate(BaseModel):
    business_id: str
    name: str
    description: str | None = None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    name: str
    description: str | None
    created_by: str
    created_at: datetime


class VariantCreate(BaseModel):
    business_id: str
    name: str
    description: str | None = None


class VariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    product_id: uuid.UUID
    name: str
    description: str | None
    created_by: str
    created_at: datetime
