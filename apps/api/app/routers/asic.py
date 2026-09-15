"""ASIC Twin v1.1 R1 P0 API (지시서 §7 API 확장, EPIC A·E·F·G).

Every write follows the house pattern (AGENTS.md): require_role → domain write
inside compute() → record_audit → all inside idempotent_write. Existence and
payload validation run OUTSIDE compute so 404/422s are not cached as
idempotent replays; business_id conflicts (409) live inside.

Honesty boundaries baked into the routes (지시서 §7):
  - corner/MC studies run synchronously with a deterministic seed and are
    stored source_class=SYNTHETIC (never presented as SPICE/TCAD).
  - FaCase.root_cause can only be approved through POST /{id}/root-cause by a
    human engineering role, with observations + resolvable evidence — an
    AI-inferred conclusion can never be gate evidence.
  - ECO close refuses (412) without regression evidence + a verification run.
"""

import csv
import hashlib
import io
import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.asic_gate_policy import evaluate_gate
from app.asic_signal import TOOL_VERSION, derive_seed, evaluate_chain
from app.config import settings
from app.db import get_db
from app.models.artifact import ArtifactKind, ArtifactVersion, ArtifactVersionStatus
from app.models.artifact import Artifact
from app.models.asic import (
    AsicEco,
    CornerStudy,
    FaCase,
    FaEvent,
    FaultInjectionRun,
    FmedaItem,
    MeasurementRun,
    QualificationPlan,
    QualificationResult,
    SafetyItem,
    SignalChainModel,
)
from app.models.base import utcnow
from app.schemas.asic import (
    AsicEcoAnalyzeRequest,
    AsicEcoCloseRequest,
    AsicEcoCreate,
    AsicEcoRead,
    AsicEcoRegressionRequest,
    AsicGateReport,
    CornerStudyCreate,
    CornerStudyRead,
    FaCaseCreate,
    FaCaseRead,
    FaCaseUpdate,
    FaEventRead,
    FaRootCauseRequest,
    FaultInjectionCreate,
    FaultInjectionRead,
    FmedaItemCreate,
    FmedaItemRead,
    MeasurementRunImportMeta,
    MeasurementRunRead,
    QualificationPlanCreate,
    QualificationPlanRead,
    QualificationResultCreate,
    QualificationResultRead,
    SafetyItemCreate,
    SafetyItemRead,
    SignalChainCreate,
    SignalChainRead,
)
from app.security import CurrentUser, require_role
from app.storage import s3_client
from app.write_support import get_correlation_id, get_idempotency_key, idempotent_write, record_audit

router = APIRouter(prefix="/api/v1/asic", tags=["asic"])

CAN_DESIGN = require_role("system_architect", "electrical_asic_engineer")
CAN_IMPORT = require_role("test_emc_engineer", "electrical_asic_engineer")
CAN_QUAL = require_role("quality_engineer", "system_architect")
CAN_FA = require_role("electrical_asic_engineer", "quality_engineer")
CAN_ECO = require_role("system_architect", "electrical_asic_engineer", "quality_engineer")
CAN_ECO_CLOSE = require_role("system_architect", "reviewer_approver")

# forward-only FA lifecycle (append-only rule, 지시서 §6 불변규칙 1)
_FA_ORDER = ("open", "analyzing", "rca_approved", "eco_open", "verified", "closed")


def _conflict(detail: dict) -> tuple[int, dict]:
    return status.HTTP_409_CONFLICT, detail


def _by_business_id(db: Session, model, business_id: str, what: str):
    row = db.query(model).filter_by(business_id=business_id).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what} '{business_id}' not found")
    return row


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ── EPIC A: signal chains ───────────────────────────────────────────────────


@router.post("/signal-chains", response_model=SignalChainRead, status_code=status.HTTP_201_CREATED)
def create_signal_chain(
    body: SignalChainCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DESIGN)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Create the next revision of a template's signal chain. The previous
    latest revision is marked superseded (불변규칙 1: 승인된 설계는 수정하지
    않고 새 리비전으로 supersede) — uploading as the design role IS the
    approval on this educational platform."""

    def compute() -> tuple[int, dict]:
        prev = (
            db.query(SignalChainModel)
            .filter_by(template_id=body.template_id)
            .order_by(SignalChainModel.revision.desc())
            .first()
        )
        content_hash = hashlib.sha256(
            json.dumps([b.model_dump() for b in body.blocks], sort_keys=True).encode()
        ).hexdigest()
        chain = SignalChainModel(
            business_id=body.business_id,
            template_id=body.template_id,
            variant_id=body.variant_id,
            revision=(prev.revision + 1) if prev else 1,
            status="approved",
            blocks=[b.model_dump() for b in body.blocks],
            source_class=body.source_class,
            supersedes_id=prev.id if prev else None,
            content_hash=content_hash,
            note=body.note,
            created_by=user.username,
        )
        if prev is not None:
            prev.status = "superseded"
        db.add(chain)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="asic_signal_chain",
            entity_id=chain.id,
            correlation_id=correlation_id,
            payload={"business_id": chain.business_id, "revision": chain.revision},
        )
        return status.HTTP_201_CREATED, SignalChainRead.model_validate(chain).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/signal-chains", response_model=list[SignalChainRead])
def list_signal_chains(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(SignalChainModel)
        .filter_by(template_id=template_id)
        .order_by(SignalChainModel.revision.desc())
        .all()
    )


# ── EPIC A: corner / Monte-Carlo studies (synchronous, deterministic) ───────


@router.post("/corner-studies", response_model=CornerStudyRead, status_code=status.HTTP_201_CREATED)
def create_corner_study(
    body: CornerStudyCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DESIGN)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Runs the seeded error-budget sweep inline (<100 ms — 지시서 §9 only
    long-running jobs go to Temporal) and stores the result with its seed so
    the run is reproducible (§12)."""
    chain = db.get(SignalChainModel, body.signal_chain_id)
    if chain is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "signal chain not found")
    seed = body.seed if body.seed is not None else derive_seed(body.business_id)

    def compute() -> tuple[int, dict]:
        result = evaluate_chain(
            blocks=chain.blocks,
            spec=[s.model_dump() for s in body.spec],
            kind=body.kind,
            n_draws=body.n_draws,
            seed=seed,
        )
        study = CornerStudy(
            business_id=body.business_id,
            signal_chain_id=chain.id,
            kind=body.kind,
            n_draws=body.n_draws,
            seed=seed,
            spec=[s.model_dump() for s in body.spec],
            result=result,
            tool_version=TOOL_VERSION,
            source_class="SYNTHETIC",
            status="succeeded",
            created_by=user.username,
        )
        db.add(study)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db,
            user=user,
            action="run_corner_study",
            entity_type="asic_corner_study",
            entity_id=study.id,
            correlation_id=correlation_id,
            payload={"business_id": study.business_id, "seed": seed, "kind": body.kind},
        )
        return status.HTTP_201_CREATED, CornerStudyRead.model_validate(study).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/corner-studies", response_model=list[CornerStudyRead])
def list_corner_studies(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(CornerStudy)
        .join(SignalChainModel, CornerStudy.signal_chain_id == SignalChainModel.id)
        .filter(SignalChainModel.template_id == template_id)
        .order_by(CornerStudy.created_at.desc())
        .all()
    )


# ── EPIC E: equipment measurement import ────────────────────────────────────

REQUIRED_COLUMNS = {"name", "value"}


def _parse_measurement_csv(raw_bytes: bytes) -> tuple[list[dict], list[dict]]:
    """Parse the tester CSV into points, recording FACTS in findings — a
    partial file or a time reversal is reported, never silently fixed
    (지시서 §7 도메인 금지: 무음 변환/수정 금지)."""
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"file is not UTF-8: {exc}") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "CSV must have at least name,value columns",
        )
    points: list[dict] = []
    findings: list[dict] = []
    if text and not text.endswith("\n"):
        findings.append(
            {"code": "partial_file", "row": None, "detail": "파일이 행 경계에서 끝나지 않습니다(쓰기 중단 의심)"}
        )
    prev_ts: datetime | None = None
    seen_blocks: set[tuple] = set()
    for i, row in enumerate(reader):
        # None values mean genuinely absent fields (DictReader restval) — a
        # truncated row. Empty cells ("") are legit and parse as absent data.
        if None in row or any(v is None for v in row.values()) or not row.get("name") or not row.get("value"):
            findings.append(
                {"code": "partial_row", "row": i, "detail": f"{i + 2}행이 불완전합니다(부분 파일 의심)"}
            )
            continue
        try:
            value = float(row["value"])
        except (TypeError, ValueError):
            findings.append(
                {"code": "unparseable_value", "row": i, "detail": f"value '{row['value']}'를 숫자로 해석할 수 없습니다"}
            )
            continue
        name = row["name"].strip()
        site = int(row["site"]) if row.get("site") else None
        block_key = (name, site)
        if block_key in seen_blocks:
            findings.append(
                {"code": "duplicate_block", "row": i, "detail": f"{name}/site={site} 조합이 중복됩니다"}
            )
        seen_blocks.add(block_key)

        ts = _parse_ts(row.get("ts") or row.get("timestamp"))
        if ts is not None:
            if prev_ts is not None and ts < prev_ts:
                findings.append(
                    {
                        "code": "time_reversal",
                        "row": i,
                        "detail": f"{i + 2}행의 타임스탬프가 이전 행보다 과거입니다",
                        "ts": ts.isoformat(),
                    }
                )
            prev_ts = ts

        temperature = None
        if row.get("temperature_c"):
            try:
                temperature = float(row["temperature_c"])
            except ValueError:
                findings.append(
                    {"code": "unparseable_temperature", "row": i, "detail": f"temperature_c '{row['temperature_c']}'를 해석할 수 없습니다"}
                )
        points.append(
            {
                "name": name,
                "value": value,
                "unit": row.get("unit") or None,
                "raw_value": float(row["raw_value"]) if row.get("raw_value") else None,
                "raw_unit": row.get("raw_unit") or None,
                "site": site,
                "temperature_c": temperature,
            }
        )
    return points, findings


@router.post("/measurement-runs/import", response_model=MeasurementRunRead, status_code=status.HTTP_201_CREATED)
async def import_measurement_run(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_IMPORT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
    file: UploadFile = File(...),
    business_id: str = Form(...),
    template_id: str = Form(...),
    equipment_id: str = Form(...),
    equipment_type: str = Form(...),
    variant_id: str | None = Form(None),
    equipment_model: str | None = Form(None),
    firmware: str | None = Form(None),
    calibration_expires_at: str | None = Form(None),
    program_revision: str | None = Form(None),
    operator: str | None = Form(None),
    executed_at: str | None = Form(None),
    lot_ref: str | None = Form(None),
):
    """Multipart import of a raw equipment file (EPIC E 수용기준 1). The raw
    bytes are promoted to an immutable artifact BEFORE parsing; the same file
    re-uploaded can never become a second run (file_hash UNIQUE → 409).
    Calibration expiry is stored as data and enforced later by the gate
    policy — ingest never blocks on it."""
    try:
        meta = MeasurementRunImportMeta(
            business_id=business_id,
            template_id=template_id,  # type: ignore[arg-type]
            variant_id=variant_id,
            equipment_id=equipment_id,
            equipment_type=equipment_type,  # type: ignore[arg-type]
            equipment_model=equipment_model,
            firmware=firmware,
            calibration_expires_at=calibration_expires_at,
            program_revision=program_revision,
            operator=operator,
            executed_at=executed_at,
            lot_ref=lot_ref,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    raw_bytes = await file.read()
    file_hash = hashlib.sha256(raw_bytes).hexdigest()
    points, findings = _parse_measurement_csv(raw_bytes)
    status_value = "verified_ingest" if points else "rejected"

    def compute() -> tuple[int, dict]:
        # dedup lives INSIDE compute so a retried request with the same
        # Idempotency-Key replays the cached 201 instead of re-hitting this
        # check (수용기준 1: 같은 파일은 절대 두 런을 만들지 않는다)
        duplicate = db.query(MeasurementRun).filter_by(file_hash=file_hash).one_or_none()
        if duplicate is not None:
            return _conflict(
                {"detail": "동일 파일이 이미 업로드되어 있습니다", "existing_business_id": duplicate.business_id}
            )
        artifact = Artifact(
            business_id=f"{meta.business_id}-raw",
            kind=ArtifactKind.CSV,
            name=f"{meta.business_id} raw equipment file",
            created_by=user.username,
        )
        db.add(artifact)
        db.flush()
        storage_key = f"artifacts/{artifact.id}/v1/{file.filename or 'measurements.csv'}"
        s3_client().put_object(
            Bucket=settings.minio_bucket, Key=storage_key, Body=raw_bytes, ContentType="text/csv"
        )
        raw_version = ArtifactVersion(
            business_id=f"{meta.business_id}-raw-v1",
            artifact_id=artifact.id,
            version=1,
            storage_key=storage_key,
            status=ArtifactVersionStatus.PROMOTED,
            sha256=file_hash,
            size_bytes=len(raw_bytes),
            created_by=user.username,
        )
        db.add(raw_version)
        db.flush()
        run = MeasurementRun(
            business_id=meta.business_id,
            template_id=meta.template_id,
            variant_id=meta.variant_id,
            equipment_id=meta.equipment_id,
            equipment_type=meta.equipment_type,
            equipment_model=meta.equipment_model,
            firmware=meta.firmware,
            calibration_expires_at=meta.calibration_expires_at,
            program_revision=meta.program_revision,
            operator=meta.operator,
            executed_at=meta.executed_at,
            raw_artifact_version_id=raw_version.id,
            file_hash=file_hash,
            status=status_value,
            points=points,
            findings=findings,
            lot_ref=meta.lot_ref,
            created_by=user.username,
        )
        db.add(run)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{meta.business_id}' already exists"})
        record_audit(
            db,
            user=user,
            action="import_measurement_run",
            entity_type="asic_measurement_run",
            entity_id=run.id,
            correlation_id=correlation_id,
            payload={
                "business_id": run.business_id,
                "file_hash": file_hash,
                "points": len(points),
                "findings": len(findings),
                "status": status_value,
            },
        )
        return (
            status.HTTP_201_CREATED,
            MeasurementRunRead.model_validate(run).model_dump(mode="json"),
        )

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/measurement-runs", response_model=list[MeasurementRunRead])
def list_measurement_runs(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(MeasurementRun)
        .filter_by(template_id=template_id)
        .order_by(MeasurementRun.created_at.desc())
        .all()
    )


# ── EPIC F: qualification matrix ────────────────────────────────────────────


@router.post("/qualification-plans", response_model=QualificationPlanRead, status_code=status.HTTP_201_CREATED)
def create_qualification_plan(
    body: QualificationPlanCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_QUAL)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):

    def compute() -> tuple[int, dict]:
        plan = QualificationPlan(
            business_id=body.business_id,
            template_id=body.template_id,
            variant_id=body.variant_id,
            grade=body.grade,
            standard_version=body.standard_version,
            note=body.note,
            created_by=user.username,
        )
        db.add(plan)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="asic_qual_plan",
            entity_id=plan.id,
            correlation_id=correlation_id,
            payload={"business_id": plan.business_id, "grade": plan.grade},
        )
        return (
            status.HTTP_201_CREATED,
            QualificationPlanRead.model_validate(plan).model_dump(mode="json"),
        )

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/qualification-plans", response_model=list[QualificationPlanRead])
def list_qualification_plans(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(QualificationPlan)
        .filter_by(template_id=template_id)
        .order_by(QualificationPlan.created_at.desc())
        .all()
    )


@router.post(
    "/qualification-plans/{plan_id}/results",
    response_model=QualificationResultRead,
    status_code=status.HTTP_201_CREATED,
)
def add_qualification_result(
    plan_id: uuid.UUID,
    body: QualificationResultCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_QUAL)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    plan = db.get(QualificationPlan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "qualification plan not found")
    for fk in (body.pre_electrical_run_id, body.post_electrical_run_id):
        if fk is not None and db.get(MeasurementRun, fk) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "electrical measurement run not found")
    if body.fa_case_id is not None and db.get(FaCase, body.fa_case_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "FA case not found")

    def compute() -> tuple[int, dict]:
        row = QualificationResult(
            business_id=body.business_id,
            plan_id=plan.id,
            group=body.group,
            method=body.method,
            condition=body.condition,
            samples=body.samples,
            lots=body.lots,
            pre_electrical_run_id=body.pre_electrical_run_id,
            post_electrical_run_id=body.post_electrical_run_id,
            status=body.status,
            failed_param=body.failed_param,
            fa_case_id=body.fa_case_id,
            waiver_ref=body.waiver_ref,
            waiver_expires_at=body.waiver_expires_at,
            created_by=user.username,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        if plan.status in ("draft", "in_progress") and row.status in ("pass", "fail"):
            plan.status = "in_progress"
        record_audit(
            db,
            user=user,
            action="add_qual_result",
            entity_type="asic_qual_result",
            entity_id=row.id,
            correlation_id=correlation_id,
            payload={"business_id": row.business_id, "group": row.group, "status": row.status},
        )
        return (
            status.HTTP_201_CREATED,
            QualificationResultRead.model_validate(row).model_dump(mode="json"),
        )

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


# ── EPIC F: safety trace / FMEDA / fault injection ──────────────────────────


@router.post("/safety-items", response_model=SafetyItemRead, status_code=status.HTTP_201_CREATED)
def create_safety_item(
    body: SafetyItemCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DESIGN)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    parent_id = None
    if body.parent_business_id:
        parent_id = _by_business_id(db, SafetyItem, body.parent_business_id, "parent safety item").id

    def compute() -> tuple[int, dict]:
        item = SafetyItem(
            business_id=body.business_id,
            template_id=body.template_id,
            variant_id=body.variant_id,
            level=body.level,
            parent_id=parent_id,
            title=body.title,
            asil=body.asil,
            safety_mechanism=body.safety_mechanism,
            diagnostic_coverage_pct=body.diagnostic_coverage_pct,
            safe_state=body.safe_state,
            response_time_ms=body.response_time_ms,
            created_by=user.username,
        )
        db.add(item)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="asic_safety_item",
            entity_id=item.id,
            correlation_id=correlation_id,
            payload={"business_id": item.business_id, "level": item.level},
        )
        return status.HTTP_201_CREATED, SafetyItemRead.model_validate(item).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/safety-items", response_model=list[SafetyItemRead])
def list_safety_items(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(SafetyItem).filter_by(template_id=template_id).order_by(SafetyItem.created_at).all()


def _template_safety_rows(db: Session, model, template_id: str) -> list:
    """FMEDA / fault-injection rows hang off safety items — join to filter by
    the owning template (the rows themselves carry no template column)."""
    return (
        db.query(model)
        .join(SafetyItem, model.safety_item_id == SafetyItem.id)
        .filter(SafetyItem.template_id == template_id)
        .order_by(model.created_at)
        .all()
    )


@router.get("/templates/{template_id}/fmeda-items", response_model=list[FmedaItemRead])
def list_fmeda_items(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return _template_safety_rows(db, FmedaItem, template_id)


@router.get("/templates/{template_id}/fault-injections", response_model=list[FaultInjectionRead])
def list_fault_injections(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return _template_safety_rows(db, FaultInjectionRun, template_id)


@router.post("/fmeda-items", response_model=FmedaItemRead, status_code=status.HTTP_201_CREATED)
def create_fmeda_item(
    body: FmedaItemCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DESIGN)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    item = _by_business_id(db, SafetyItem, body.safety_item_business_id, "safety item")

    def compute() -> tuple[int, dict]:
        row = FmedaItem(
            business_id=body.business_id,
            safety_item_id=item.id,
            failure_mode=body.failure_mode,
            distribution_pct=body.distribution_pct,
            dc_pct=body.dc_pct,
            fit_rate=body.fit_rate,
            source_ref=body.source_ref,
            source_hash=body.source_hash,
            formula_version=body.formula_version,
            note=body.note,
            created_by=user.username,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="asic_fmeda_item",
            entity_id=row.id,
            correlation_id=correlation_id,
            payload={"business_id": row.business_id, "failure_mode": row.failure_mode},
        )
        return status.HTTP_201_CREATED, FmedaItemRead.model_validate(row).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/fault-injections", response_model=FaultInjectionRead, status_code=status.HTTP_201_CREATED)
def create_fault_injection(
    body: FaultInjectionCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DESIGN)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    item = _by_business_id(db, SafetyItem, body.safety_item_business_id, "safety item")

    def compute() -> tuple[int, dict]:
        row = FaultInjectionRun(
            business_id=body.business_id,
            safety_item_id=item.id,
            method=body.method,
            stimulus=body.stimulus,
            expected=body.expected,
            observed=body.observed,
            status=body.status,
            executed_by=body.executed_by or (user.username if body.status != "pending" else None),
            executed_at=body.executed_at or (utcnow() if body.status != "pending" else None),
            created_by=user.username,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="asic_fault_injection",
            entity_id=row.id,
            correlation_id=correlation_id,
            payload={"business_id": row.business_id, "status": row.status},
        )
        return status.HTTP_201_CREATED, FaultInjectionRead.model_validate(row).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


# ── EPIC G: FA cases → RCA → ECO closed loop ────────────────────────────────


def _fa_event(
    db: Session,
    *,
    case: FaCase,
    event_type: str,
    user: CurrentUser,
    comment: str | None = None,
    evidence: dict | None = None,
) -> None:
    db.add(
        FaEvent(
            business_id=f"faevt-{uuid.uuid4().hex[:12]}",
            case_id=case.id,
            event_type=event_type,
            actor=user.username,
            actor_roles=sorted(user.roles),
            comment=comment,
            evidence=evidence,
            occurred_at=utcnow(),
            created_by=user.username,
        )
    )


@router.post("/fa-cases", response_model=FaCaseRead, status_code=status.HTTP_201_CREATED)
def create_fa_case(
    body: FaCaseCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_FA)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):

    def compute() -> tuple[int, dict]:
        case = FaCase(
            business_id=body.business_id,
            template_id=body.template_id,
            variant_id=body.variant_id,
            scope=body.scope,
            lot_ref=body.lot_ref,
            wafer_ref=body.wafer_ref,
            die_ref=body.die_ref,
            symptom=body.symptom,
            repro_condition=body.repro_condition,
            status="open",
            observations=[o.model_dump() for o in body.observations],
            location=body.location,
            analysts=[{"role": sorted(user.roles)[0], "actor": user.username, "at": utcnow().isoformat()}],
            created_by=user.username,
        )
        db.add(case)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        _fa_event(db, case=case, event_type="case_opened", user=user, comment=body.symptom)
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="asic_fa_case",
            entity_id=case.id,
            correlation_id=correlation_id,
            payload={"business_id": case.business_id, "scope": case.scope},
        )
        return status.HTTP_201_CREATED, FaCaseRead.model_validate(case).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/fa-cases", response_model=list[FaCaseRead])
def list_fa_cases(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(FaCase).filter_by(template_id=template_id).order_by(FaCase.created_at.desc()).all()


@router.patch("/fa-cases/{case_id}", response_model=FaCaseRead)
def update_fa_case(
    case_id: uuid.UUID,
    body: FaCaseUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_FA)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Investigation progress: observations (FACTS), hypotheses (working tree),
    location, forward-only status. RCA approval is NOT possible here — see
    POST /{id}/root-cause."""
    case = db.get(FaCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "FA case not found")
    if body.status == "rca_approved":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "RCA 승인은 PATCH가 아니라 POST /fa-cases/{id}/root-cause로만 가능합니다",
        )
    if body.status is not None:
        if _FA_ORDER.index(body.status) < _FA_ORDER.index(case.status):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"상태는 뒤로 갈 수 없습니다: {case.status} → {body.status}",
            )

    def compute() -> tuple[int, dict]:
        changed = {}
        if body.observations is not None:
            case.observations = [o.model_dump() for o in body.observations]
            changed["observations"] = len(case.observations)
        if body.hypotheses is not None:
            case.hypotheses = [h.model_dump() for h in body.hypotheses]
            changed["hypotheses"] = len(case.hypotheses)
        if body.location is not None:
            case.location = body.location
            changed["location"] = True
        if body.status is not None and body.status != case.status:
            case.status = body.status
            changed["status"] = body.status
        _fa_event(db, case=case, event_type="case_updated", user=user, evidence={"changed": changed})
        record_audit(
            db,
            user=user,
            action="update",
            entity_type="asic_fa_case",
            entity_id=case.id,
            correlation_id=correlation_id,
            payload={"changed": changed},
        )
        return status.HTTP_200_OK, FaCaseRead.model_validate(case).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/fa-cases/{case_id}/root-cause", response_model=FaCaseRead)
def approve_root_cause(
    case_id: uuid.UUID,
    body: FaRootCauseRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_FA)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Human-only RCA approval (지시서 §7: AI가 최종 원인을 확정하지 않는다).
    수용기준: 관찰 사실 + 확인 증적 없이 승인 불가 — both are enforced here."""
    case = db.get(FaCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "FA case not found")
    if not case.observations:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "관찰 사실(observations) 없이는 RCA를 승인할 수 없습니다",
        )
    if not body.evidence_business_ids:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "확인 증적(evidence_business_ids) 없이는 RCA를 승인할 수 없습니다",
        )
    # every evidence id must resolve to a concrete evidence row
    evidence_models = (MeasurementRun, CornerStudy, FaultInjectionRun, QualificationResult)
    unresolved = []
    for eid in body.evidence_business_ids:
        if not any(db.query(m).filter_by(business_id=eid).first() for m in evidence_models):
            unresolved.append(eid)
    if unresolved:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"detail": "확인 증적을 찾을 수 없습니다", "unresolved": unresolved},
        )
    if case.status in ("rca_approved", "eco_open", "verified", "closed"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"RCA가 이미 승인되어 있습니다(status={case.status})")

    def compute() -> tuple[int, dict]:
        case.root_cause = body.root_cause
        case.cause_class = body.cause_class
        case.root_cause_confirmed = True
        case.status = "rca_approved"
        case.analysts = (case.analysts or []) + [
            {"role": sorted(user.roles)[0], "actor": user.username, "at": utcnow().isoformat()}
        ]
        _fa_event(
            db,
            case=case,
            event_type="rca_approved",
            user=user,
            comment=body.comment,
            evidence={"evidence_business_ids": body.evidence_business_ids, "cause_class": body.cause_class},
        )
        record_audit(
            db,
            user=user,
            action="approve_root_cause",
            entity_type="asic_fa_case",
            entity_id=case.id,
            correlation_id=correlation_id,
            payload={"cause_class": body.cause_class, "evidence": body.evidence_business_ids},
        )
        return status.HTTP_200_OK, FaCaseRead.model_validate(case).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/fa-cases/{case_id}/events", response_model=list[FaEventRead])
def list_fa_events(case_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]):
    case = db.get(FaCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "FA case not found")
    return case.events


# ── EPIC G: ECOs ────────────────────────────────────────────────────────────


@router.post("/ecos", response_model=AsicEcoRead, status_code=status.HTTP_201_CREATED)
def create_eco(
    body: AsicEcoCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    fa_case = None
    if body.fa_case_business_id:
        fa_case = _by_business_id(db, FaCase, body.fa_case_business_id, "FA case")
        if body.trigger == "fa_case" and not fa_case.root_cause_confirmed:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "RCA가 승인된 FA 케이스만 fa_case 트리거 ECO를 만들 수 있습니다",
            )

    def compute() -> tuple[int, dict]:
        eco = AsicEco(
            business_id=body.business_id,
            fa_case_id=fa_case.id if fa_case else None,
            template_id=body.template_id,
            trigger=body.trigger,
            title=body.title,
            description=body.description,
            design_rev_from=body.design_rev_from,
            design_rev_to=body.design_rev_to,
            mask_revision=body.mask_revision,
            test_program_revision=body.test_program_revision,
            impact=body.impact,
            created_by=user.username,
        )
        db.add(eco)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        if fa_case is not None:
            fa_case.status = "eco_open"
            _fa_event(
                db,
                case=fa_case,
                event_type="eco_opened",
                user=user,
                evidence={"eco_business_id": eco.business_id, "title": eco.title},
            )
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="asic_eco",
            entity_id=eco.id,
            correlation_id=correlation_id,
            payload={"business_id": eco.business_id, "trigger": eco.trigger},
        )
        return status.HTTP_201_CREATED, AsicEcoRead.model_validate(eco).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/ecos", response_model=list[AsicEcoRead])
def list_ecos(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(AsicEco).filter_by(template_id=template_id).order_by(AsicEco.created_at.desc()).all()


def _get_eco(db: Session, eco_id: uuid.UUID) -> AsicEco:
    eco = db.get(AsicEco, eco_id)
    if eco is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ECO not found")
    return eco


@router.post("/ecos/{eco_id}/analyze", response_model=AsicEcoRead)
def analyze_eco(
    eco_id: uuid.UUID,
    body: AsicEcoAnalyzeRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    eco = _get_eco(db, eco_id)
    if eco.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"open 상태의 ECO만 분석할 수 있습니다(status={eco.status})")

    def compute() -> tuple[int, dict]:
        eco.design_rev_from = body.design_rev_from or eco.design_rev_from
        eco.design_rev_to = body.design_rev_to or eco.design_rev_to
        eco.mask_revision = body.mask_revision or eco.mask_revision
        eco.test_program_revision = body.test_program_revision or eco.test_program_revision
        if body.impact is not None:
            eco.impact = body.impact
        eco.status = "analyzed"
        record_audit(
            db,
            user=user,
            action="analyze_eco",
            entity_type="asic_eco",
            entity_id=eco.id,
            correlation_id=correlation_id,
            payload={"business_id": eco.business_id},
        )
        return status.HTTP_200_OK, AsicEcoRead.model_validate(eco).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/ecos/{eco_id}/regression", response_model=AsicEcoRead)
def attach_regression(
    eco_id: uuid.UUID,
    body: AsicEcoRegressionRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    eco = _get_eco(db, eco_id)
    evidence_models = (MeasurementRun, CornerStudy)
    unresolved = [
        rid
        for rid in body.regression_run_ids
        if not any(db.query(m).filter_by(business_id=rid).first() for m in evidence_models)
    ]
    if unresolved:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"detail": "회귀 증적을 찾을 수 없습니다", "unresolved": unresolved},
        )

    def compute() -> tuple[int, dict]:
        eco.regression_run_ids = body.regression_run_ids
        eco.status = "regression_pending"
        record_audit(
            db,
            user=user,
            action="attach_eco_regression",
            entity_type="asic_eco",
            entity_id=eco.id,
            correlation_id=correlation_id,
            payload={"regression_run_ids": body.regression_run_ids},
        )
        return status.HTTP_200_OK, AsicEcoRead.model_validate(eco).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/ecos/{eco_id}/close", response_model=AsicEcoRead)
def close_eco(
    eco_id: uuid.UUID,
    body: AsicEcoCloseRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO_CLOSE)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """ECO 종결 = 효과검증까지 완료 (수용기준: ECO 완료만으로 FA를 닫을 수
    없음). 회귀 증적이 없거나 검증 측정런이 없으면 412로 거부한다."""
    eco = _get_eco(db, eco_id)
    if eco.status == "closed":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 종결된 ECO입니다")
    if not eco.regression_run_ids:
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            "회귀(재시험) 증적 없이는 ECO를 종결할 수 없습니다 — 먼저 /regression을 연결하세요",
        )
    verification_run = _by_business_id(
        db, MeasurementRun, body.verification_run_business_id, "verification measurement run"
    )

    def compute() -> tuple[int, dict]:
        eco.verification_run_id = verification_run.id
        eco.verification_note = body.verification_note
        eco.status = "closed"
        eco.closed_at = utcnow()
        if eco.fa_case_id is not None:
            fa_case = db.get(FaCase, eco.fa_case_id)
            if fa_case is not None and _FA_ORDER.index("verified") > _FA_ORDER.index(fa_case.status):
                fa_case.status = "verified"
                _fa_event(
                    db,
                    case=fa_case,
                    event_type="eco_verified",
                    user=user,
                    evidence={"eco_business_id": eco.business_id, "verification_run": verification_run.business_id},
                )
        record_audit(
            db,
            user=user,
            action="close_eco",
            entity_type="asic_eco",
            entity_id=eco.id,
            correlation_id=correlation_id,
            payload={
                "business_id": eco.business_id,
                "verification_run": verification_run.business_id,
            },
        )
        return status.HTTP_200_OK, AsicEcoRead.model_validate(eco).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


# ── gate report (지시서 §8) ─────────────────────────────────────────────────


@router.get("/gate-report/{template_id}", response_model=AsicGateReport)
def get_gate_report(template_id: str, db: Annotated[Session, Depends(get_db)]):
    report = evaluate_gate(db, template_id)
    return AsicGateReport.model_validate(report).model_dump(mode="json")
