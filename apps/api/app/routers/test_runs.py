import csv
import hashlib
import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.artifact import Artifact, ArtifactKind, ArtifactVersion, ArtifactVersionStatus
from app.models.process_twin import Lot
from app.models.test import Measurement, TestPlan, TestRun
from app.schemas.test import MeasurementRead, TestRunCreate, TestRunRead
from app.security import CurrentUser, require_role
from app.storage import s3_client
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1", tags=["test-runs"])

CAN_MANAGE_TEST = require_role("test_emc_engineer", "mechanical_engineer", "electrical_asic_engineer")


@router.post("/test-runs", response_model=TestRunRead, status_code=status.HTTP_201_CREATED)
def create_test_run(
    body: TestRunCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_TEST)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    if db.get(TestPlan, body.test_plan_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test plan not found")
    if body.lot_id is not None and db.get(Lot, body.lot_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lot not found")

    def compute() -> tuple[int, dict]:
        run = TestRun(
            business_id=body.business_id,
            test_plan_id=body.test_plan_id,
            lot_id=body.lot_id,
            executed_at=body.executed_at,
            equipment_id=body.equipment_id,
            environment=body.environment,
            created_by=user.username,
        )
        db.add(run)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return status.HTTP_409_CONFLICT, {"detail": f"business_id '{body.business_id}' already exists"}
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="test_run",
            entity_id=run.id,
            correlation_id=correlation_id,
            payload={"business_id": run.business_id, "test_plan_id": str(body.test_plan_id)},
        )
        return status.HTTP_201_CREATED, TestRunRead.model_validate(run).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/test-runs/{test_run_id}/measurements", response_model=list[MeasurementRead])
async def upload_measurements(
    test_run_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_MANAGE_TEST)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    file: UploadFile = File(...),
    x_unit: str = Form(...),
    y_unit: str = Form(...),
):
    """CSV upload (§FR-07): raw file is stored unmodified as an Artifact
    before parsing — the parsed Measurement rows are a derived view, not the
    source of truth. Re-uploading for the same test run replaces neither; a
    fresh TestRun should be created for a re-test.
    """
    run = db.get(TestRun, test_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test run not found")
    if run.measurements:
        raise HTTPException(status.HTTP_409_CONFLICT, "measurements already uploaded for this test run")

    raw_bytes = await file.read()
    try:
        reader = csv.DictReader(io.StringIO(raw_bytes.decode("utf-8")))
        rows = [(float(r["x_value"]), float(r["y_value"])) for r in reader]
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"CSV must have x_value,y_value columns: {exc}"
        ) from exc
    if not rows:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "CSV had no data rows")

    raw_artifact = Artifact(
        business_id=f"{run.business_id}-raw-csv",
        kind=ArtifactKind.CSV,
        name=f"{run.business_id} raw measurements",
        created_by=user.username,
    )
    db.add(raw_artifact)
    db.flush()

    storage_key = f"artifacts/{raw_artifact.id}/v1/{file.filename or 'measurements.csv'}"
    s3_client().put_object(Bucket=settings.minio_bucket, Key=storage_key, Body=raw_bytes, ContentType="text/csv")

    raw_version = ArtifactVersion(
        business_id=f"{run.business_id}-raw-csv-v1",
        artifact_id=raw_artifact.id,
        version=1,
        storage_key=storage_key,
        status=ArtifactVersionStatus.PROMOTED,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        size_bytes=len(raw_bytes),
        created_by=user.username,
    )
    db.add(raw_version)
    db.flush()
    run.raw_artifact_version_id = raw_version.id

    measurements = [
        Measurement(
            business_id=f"{run.business_id}-m{i}",
            test_run_id=run.id,
            x_value=x,
            y_value=y,
            x_unit=x_unit,
            y_unit=y_unit,
            created_by=user.username,
        )
        for i, (x, y) in enumerate(rows)
    ]
    db.add_all(measurements)

    record_audit(
        db,
        user=user,
        action="upload_measurements",
        entity_type="test_run",
        entity_id=run.id,
        correlation_id=correlation_id,
        payload={"row_count": len(rows), "raw_artifact_version_id": str(raw_version.id)},
    )
    db.commit()
    for m in measurements:
        db.refresh(m)
    return measurements


@router.get("/test-runs/{test_run_id}/measurements", response_model=list[MeasurementRead])
def list_measurements(test_run_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(Measurement).filter_by(test_run_id=test_run_id).order_by(Measurement.x_value).all()


@router.get("/test-runs/{test_run_id}", response_model=TestRunRead)
def get_test_run(test_run_id: str, db: Annotated[Session, Depends(get_db)]):
    run = db.get(TestRun, test_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test run not found")
    return run
