import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.artifact import ArtifactKind, ArtifactVersionStatus


class ArtifactUploadRequest(BaseModel):
    business_id: str
    kind: ArtifactKind
    name: str
    filename: str


class ArtifactUploadResponse(BaseModel):
    artifact_id: uuid.UUID
    artifact_version_id: uuid.UUID
    storage_key: str
    upload_url: str
    version: int


class ArtifactVersionPromote(BaseModel):
    sha256: str


class ArtifactVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: str
    artifact_id: uuid.UUID
    version: int
    storage_key: str
    status: ArtifactVersionStatus
    sha256: str | None
    size_bytes: int | None
    tool_version: str | None
    generated_from_id: uuid.UUID | None
    extra_metadata: dict | None
    created_by: str
    created_at: datetime
