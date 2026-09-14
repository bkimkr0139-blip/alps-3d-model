"""The actual conversion activity. Not imported by workflow_defn.py (Temporal
sandboxes whatever module defines the workflow class), only by worker.py."""

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from temporalio import activity

from convert import convert_step_to_glb

TOOL_VERSION = "OCP 8.0.1 + trimesh 5.1.0 (xcaf-pbr)"


@activity.defn(name="convert_step_to_gltf_activity")
def convert_step_to_gltf_activity(simulation_run_id: str) -> None:
    import hashlib

    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    from app.config import settings
    from app.db import engine
    from app.models.artifact import Artifact, ArtifactKind, ArtifactVersion, ArtifactVersionStatus
    from app.models.simulation import ResultMetric, RunStatus, SimulationRun
    from app.storage import s3_client

    with Session(bind=engine) as db:
        run = db.get(SimulationRun, simulation_run_id)
        if run is None:
            raise ValueError(f"simulation_run {simulation_run_id} not found")

        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        run.tool_version = TOOL_VERSION
        db.commit()

        try:
            input_version = db.get(ArtifactVersion, run.input_artifact_version_id)
            client = s3_client()
            step_bytes = client.get_object(
                Bucket=settings.minio_bucket, Key=input_version.storage_key
            )["Body"].read()

            glb_bytes, metadata = convert_step_to_glb(step_bytes)

            # The derived artifact's business_id is deterministic on the input
            # version, so RE-converting the same input reuses it and appends a
            # new version instead of colliding on the unique business_id.
            def _next_version(artifact: Artifact) -> int:
                return (
                    db.query(func.max(ArtifactVersion.version))
                    .filter(ArtifactVersion.artifact_id == artifact.id)
                    .scalar()
                    or 0
                ) + 1

            derived_business_id = f"{input_version.business_id}-gltf"
            derived_artifact = (
                db.query(Artifact).filter(Artifact.business_id == derived_business_id).first()
            )
            if derived_artifact is None:
                derived_artifact = Artifact(
                    business_id=derived_business_id,
                    kind=ArtifactKind.GLTF,
                    name=f"{input_version.business_id} (glTF derivative)",
                    created_by="cad-converter-worker",
                )
                db.add(derived_artifact)
                try:
                    db.flush()
                except IntegrityError:
                    # Another activity execution converted the same input
                    # concurrently and committed the artifact between our
                    # lookup and INSERT — roll back, adopt the winner's
                    # artifact, and append a version to it instead. (A stale
                    # worker without this lookup once crashed here with a
                    # UniqueViolation; Temporal's retry masked it but left a
                    # stale error_message on a SUCCEEDED run.)
                    db.rollback()
                    derived_artifact = (
                        db.query(Artifact).filter(Artifact.business_id == derived_business_id).first()
                    )
                    if derived_artifact is None:  # pragma: no cover — constraint says it exists
                        raise
                else:
                    next_version = 1
            # Fresh artifact has no versions yet → 1; existing one → max+1.
            next_version = _next_version(derived_artifact)

            storage_key = f"artifacts/{derived_artifact.id}/v{next_version}/derived.glb"
            client.put_object(
                Bucket=settings.minio_bucket,
                Key=storage_key,
                Body=glb_bytes,
                ContentType="model/gltf-binary",
            )

            derived_version = ArtifactVersion(
                business_id=f"{input_version.business_id}-gltf-v{next_version}",
                artifact_id=derived_artifact.id,
                version=next_version,
                storage_key=storage_key,
                status=ArtifactVersionStatus.PROMOTED,
                sha256=hashlib.sha256(glb_bytes).hexdigest(),
                size_bytes=len(glb_bytes),
                tool_version=TOOL_VERSION,
                generated_from_id=input_version.id,
                extra_metadata=metadata,
                created_by="cad-converter-worker",
            )
            db.add(derived_version)
            db.flush()

            for key in ("volume_mm3", "vertex_count", "triangle_count"):
                db.add(
                    ResultMetric(
                        business_id=f"{run.business_id}-{key}",
                        simulation_run_id=run.id,
                        name=key,
                        value=float(metadata[key]),
                        unit="mm^3" if key == "volume_mm3" else None,
                        created_by="cad-converter-worker",
                    )
                )

            run.output_artifact_version_id = derived_version.id
            run.status = RunStatus.SUCCEEDED
            # A Temporal retry may have recorded a failure on an earlier
            # attempt — never show stale errors on a run that succeeded.
            run.error_message = None
            run.finished_at = datetime.now(timezone.utc)
            db.commit()

        except Exception as exc:  # noqa: BLE001 — must record failure on ANY error
            db.rollback()
            run = db.get(SimulationRun, simulation_run_id)
            run.status = RunStatus.FAILED
            run.error_message = str(exc)[:4000]
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            raise
