"""Worker-side artifact writing for the AirInput field-twin runs.

Follows the spice-worker's write-from-worker pattern: PROMOTED
ArtifactVersion in MinIO + DB rows in one transaction. All four field-twin
payload schemas (airinput.field-grid.v1 / surrogate-rbf.v1 /
sensitivity-volume.v1 / replay.v1) serialize through ``dump_payload`` —
deterministic float rounding + sorted keys — so a replay re-run produces a
BYTE-IDENTICAL object (the reproducibility property pytest pins).

ArtifactKind.OTHER is used unchanged (no enum migration): the payload's
``schema`` field inside the JSON is the real discriminator.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

ROUND_DECIMALS = 6


def round_floats(obj, decimals: int = ROUND_DECIMALS):
    """Deterministic recursive float rounding for JSON serialization."""
    if isinstance(obj, bool):
        return obj  # before float/int: bool is an int subclass
    if isinstance(obj, float):
        return round(obj, decimals)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    # numpy scalars (np.float64/np.int64/np.bool_) — .item() → python types
    if not isinstance(obj, (str, bytes, dict, list, tuple, type(None))) and hasattr(obj, "item"):
        try:
            return round_floats(obj.item(), decimals)
        except (AttributeError, TypeError):
            pass
    if isinstance(obj, dict):
        return {k: round_floats(v, decimals) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [round_floats(v, decimals) for v in obj]
    return obj


def dump_payload(payload: dict) -> bytes:
    """Payload → canonical JSON bytes (rounded, sorted keys, compact)."""
    return json.dumps(
        round_floats(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def write_run_artifact(
    db,
    run,
    input_version,  # ArtifactVersion | None — field-twin runs have no input artifact
    payload: dict,
    filename: str,
    tool_version: str,
    created_by: str = "mech-model-worker",
) -> object:
    """Write ``payload`` as a PROMOTED artifact version; returns the version.

    Mirrors spice-worker/activities.py L55-89. Caller commits. Naming falls
    back to the run's business_id when the run has no input artifact (the
    field-twin runs are self-contained: their inputs live in parameters).
    """
    from app.config import settings
    from app.models.artifact import Artifact, ArtifactKind, ArtifactVersion, ArtifactVersionStatus
    from app.storage import s3_client

    body = dump_payload(payload)
    name_prefix = input_version.business_id if input_version is not None else run.business_id

    artifact = Artifact(
        business_id=f"{name_prefix}-{filename.split('.')[0]}",
        kind=ArtifactKind.OTHER,
        name=f"{name_prefix} {payload.get('schema', 'payload')}",
        created_by=created_by,
    )
    db.add(artifact)
    db.flush()

    storage_key = f"artifacts/{artifact.id}/v1/{filename}"
    client = s3_client()
    client.put_object(
        Bucket=settings.minio_bucket,
        Key=storage_key,
        Body=body,
        ContentType="application/json",
    )

    version = ArtifactVersion(
        business_id=f"{name_prefix}-{filename.split('.')[0]}-v1",
        artifact_id=artifact.id,
        version=1,
        storage_key=storage_key,
        status=ArtifactVersionStatus.PROMOTED,
        sha256=hashlib.sha256(body).hexdigest(),
        size_bytes=len(body),
        tool_version=tool_version,
        generated_from_id=input_version.id if input_version is not None else None,
        extra_metadata={
            "schema": payload.get("schema"),
            "tier": payload.get("tier"),
            # run.id arrives as uuid.UUID — psycopg serializes JSONB with
            # plain json.dumps, which rejects UUID objects.
            "simulation_run_id": str(run.id),
        },
        created_by=created_by,
    )
    db.add(version)
    db.flush()
    return version


def utcnow():
    return datetime.now(timezone.utc)
