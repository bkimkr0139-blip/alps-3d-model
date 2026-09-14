import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from temporalio import activity

from erc import run_erc
from spice_runner import run_sweep

TOOL_VERSION = "ngspice-47"
DEFAULT_SWEEP_OHMS = [0.1, 1, 10, 100, 500, 1000]
DEFAULT_LOGIC_LOW_THRESHOLD_V = 1.0


@activity.defn(name="run_spice_analysis_activity")
def run_spice_analysis_activity(simulation_run_id: str) -> None:
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
            netlist_text = client.get_object(
                Bucket=settings.minio_bucket, Key=input_version.storage_key
            )["Body"].read().decode("utf-8")

            violations = run_erc(netlist_text)
            if violations:
                raise ValueError(f"ERC failed: {'; '.join(violations)}")

            params = run.parameters or {}
            sweep_ohms = params.get("sweep_ohms", DEFAULT_SWEEP_OHMS)
            logic_low_threshold_v = params.get("logic_low_threshold_v", DEFAULT_LOGIC_LOW_THRESHOLD_V)

            v_out_values, raw_log = run_sweep(netlist_text, sweep_ohms)

            log_artifact = Artifact(
                business_id=f"{input_version.business_id}-simlog",
                kind=ArtifactKind.SIM_LOG,
                name=f"{input_version.business_id} ngspice log",
                created_by="spice-worker",
            )
            db.add(log_artifact)
            db.flush()

            storage_key = f"artifacts/{log_artifact.id}/v1/ngspice.log"
            client.put_object(
                Bucket=settings.minio_bucket,
                Key=storage_key,
                Body=raw_log.encode("utf-8"),
                ContentType="text/plain",
            )

            import hashlib

            log_bytes = raw_log.encode("utf-8")
            log_version = ArtifactVersion(
                business_id=f"{input_version.business_id}-simlog-v1",
                artifact_id=log_artifact.id,
                version=1,
                storage_key=storage_key,
                status=ArtifactVersionStatus.PROMOTED,
                sha256=hashlib.sha256(log_bytes).hexdigest(),
                size_bytes=len(log_bytes),
                tool_version=TOOL_VERSION,
                generated_from_id=input_version.id,
                extra_metadata={"sweep_ohms": sweep_ohms, "erc": "passed"},
                created_by="spice-worker",
            )
            db.add(log_version)
            db.flush()

            for rc, v_out in zip(sweep_ohms, v_out_values):
                db.add(
                    ResultMetric(
                        business_id=f"{run.business_id}-vout-rc{rc}",
                        simulation_run_id=run.id,
                        name=f"v_out_rc_{rc}",
                        value=v_out,
                        unit="V",
                        created_by="spice-worker",
                    )
                )

            worst_case_margin = logic_low_threshold_v - max(v_out_values)
            db.add(
                ResultMetric(
                    business_id=f"{run.business_id}-margin",
                    simulation_run_id=run.id,
                    name="worst_case_logic_low_margin",
                    value=worst_case_margin,
                    unit="V",
                    created_by="spice-worker",
                )
            )

            run.output_artifact_version_id = log_version.id
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
