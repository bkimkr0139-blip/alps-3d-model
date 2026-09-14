import hashlib
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.artifact import Artifact, ArtifactVersion, ArtifactVersionStatus
from app.schemas.artifact import (
    ArtifactUploadRequest,
    ArtifactUploadResponse,
    ArtifactVersionPromote,
    ArtifactVersionRead,
)
from app.security import CurrentUser, get_current_user, require_role
from app.storage import presigned_get_url, presigned_put_url, s3_client
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["artifacts"])

CAN_MANAGE_ARTIFACT = require_role("mechanical_engineer", "electrical_asic_engineer", "system_architect")


@router.post("/artifacts/uploads", response_model=ArtifactUploadResponse, status_code=status.HTTP_201_CREATED)
def create_upload(
    body: ArtifactUploadRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_ARTIFACT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    def compute() -> tuple[int, dict]:
        artifact = db.query(Artifact).filter_by(business_id=body.business_id).one_or_none()
        if artifact is None:
            artifact = Artifact(
                business_id=body.business_id, kind=body.kind, name=body.name, created_by=user.username
            )
            db.add(artifact)
            db.flush()
            next_version = 1
        else:
            next_version = (
                db.query(ArtifactVersion)
                .filter_by(artifact_id=artifact.id)
                .count()
                + 1
            )

        storage_key = f"artifacts/{artifact.id}/v{next_version}/{body.filename}"
        artifact_version = ArtifactVersion(
            business_id=f"{body.business_id}-v{next_version}",
            artifact_id=artifact.id,
            version=next_version,
            storage_key=storage_key,
            status=ArtifactVersionStatus.PENDING_UPLOAD,
            created_by=user.username,
        )
        db.add(artifact_version)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": "artifact version business_id collision, retry"}

        record_audit(
            db,
            user=user,
            action="upload_requested",
            entity_type="artifact_version",
            entity_id=artifact_version.id,
            correlation_id=correlation_id,
            payload={"storage_key": storage_key},
        )
        return status.HTTP_201_CREATED, {
            "artifact_id": str(artifact.id),
            "artifact_version_id": str(artifact_version.id),
            "storage_key": storage_key,
            "upload_url": presigned_put_url(storage_key),
            "version": next_version,
        }

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/artifacts/versions/{artifact_version_id}/promote", response_model=ArtifactVersionRead)
def promote_artifact_version(
    artifact_version_id: str,
    body: ArtifactVersionPromote,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_ARTIFACT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
):
    """Verifies the uploaded object's hash server-side before promoting it to
    a usable Artifact (§9.3: hash verification must complete before promotion).
    """
    artifact_version = db.get(ArtifactVersion, artifact_version_id)
    if artifact_version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact version not found")
    if artifact_version.status == ArtifactVersionStatus.PROMOTED:
        return artifact_version

    client = s3_client()
    try:
        obj = client.get_object(Bucket=settings.minio_bucket, Key=artifact_version.storage_key)
    except client.exceptions.NoSuchKey as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "object not uploaded yet") from exc

    hasher = hashlib.sha256()
    size = 0
    for chunk in obj["Body"].iter_chunks(chunk_size=1024 * 1024):
        hasher.update(chunk)
        size += len(chunk)
    computed_sha256 = hasher.hexdigest()

    if computed_sha256 != body.sha256:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"sha256 mismatch: client claimed {body.sha256}, server computed {computed_sha256}",
        )

    artifact_version.sha256 = computed_sha256
    artifact_version.size_bytes = size
    artifact_version.status = ArtifactVersionStatus.PROMOTED
    record_audit(
        db,
        user=user,
        action="promote",
        entity_type="artifact_version",
        entity_id=artifact_version.id,
        correlation_id=correlation_id,
        payload={"sha256": computed_sha256, "size_bytes": size},
    )
    db.commit()
    db.refresh(artifact_version)
    return artifact_version


@router.get("/artifacts/versions/{artifact_version_id}", response_model=ArtifactVersionRead)
def get_artifact_version(artifact_version_id: str, db: Annotated[Session, Depends(get_db)]):
    artifact_version = db.get(ArtifactVersion, artifact_version_id)
    if artifact_version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact version not found")
    return artifact_version


@router.get("/artifacts/versions/{artifact_version_id}/download-url")
def get_download_url(artifact_version_id: str, db: Annotated[Session, Depends(get_db)]):
    artifact_version = db.get(ArtifactVersion, artifact_version_id)
    if artifact_version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact version not found")
    if artifact_version.status != ArtifactVersionStatus.PROMOTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "artifact version is not promoted yet")
    return {"download_url": presigned_get_url(artifact_version.storage_key)}


_MEDIA_BY_SUFFIX = {
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".csv": "text/csv",
    ".json": "application/json",
}


@router.get("/artifacts/versions/{artifact_version_id}/content")
def get_artifact_content(
    artifact_version_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
):
    """Streams the stored object through the API instead of handing the
    browser a presigned MinIO URL — the presigned URL points at MinIO's own
    host (localhost:9000), which a browser on any other origin can neither
    reach nor CORS-fetch, and it bypasses API auth entirely. Requires a
    valid token; unlike download-url, which stays for tool-side use."""
    artifact_version = db.get(ArtifactVersion, artifact_version_id)
    if artifact_version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "artifact version not found")
    if artifact_version.status != ArtifactVersionStatus.PROMOTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "artifact version is not promoted yet")

    client = s3_client()
    try:
        obj = client.get_object(Bucket=settings.minio_bucket, Key=artifact_version.storage_key)
    except client.exceptions.NoSuchKey as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "object missing from storage") from exc

    suffix = Path(artifact_version.storage_key).suffix.lower()
    media_type = _MEDIA_BY_SUFFIX.get(suffix, "application/octet-stream")
    return StreamingResponse(obj["Body"], media_type=media_type)
