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
from sqlalchemy.orm.attributes import flag_modified

from app.asic_gate_policy import evaluate_gate
from app.asic_copilot import ENGINE_VERSION, proposal_diff, run_copilot
from app.asic_report import LANGS as REPORT_LANGS, build_evidence_report
from app.asic_signal import TOOL_VERSION, derive_seed, evaluate_chain
from app.asic_testprog import (
    analyze_wafer_map,
    coverage_matrix,
    cross_target_analysis,
    flow_totals,
    limit_change_impact,
    optimization_proposals,
    revision_compatibility,
)
from app.asic_trade import compute_trade_study
from app.config import settings
from app.db import get_db
from app.models.artifact import ArtifactKind, ArtifactVersion, ArtifactVersionStatus
from app.models.artifact import Artifact
from app.models.asic import (
    AsicAssumption,
    AsicAssumptionEvent,
    AsicCopilotInteraction,
    AsicDeviation,
    AsicEco,
    AsicImpactScan,
    AsicPartner,
    CornerStudy,
    FaCase,
    FaEvent,
    FaultInjectionRun,
    FmedaItem,
    LimitChange,
    LotTraveler,
    ManufacturingOption,
    MeasurementRun,
    PartnerArtifact,
    PartnerChange,
    QualityAction,
    QualificationPlan,
    QualificationResult,
    SafetyItem,
    SignalChainModel,
    TestFlow,
    TestFlowItem,
    ToolRun,
    TradeStudy,
    WaferMap,
)
from app.models.base import utcnow
from app.models.product import Variant
from app.models.requirement import Requirement
from app.schemas.asic import (
    AsicEcoAnalyzeRequest,
    AsicEcoCloseRequest,
    AsicEcoCreate,
    AsicEcoRead,
    AsicEcoRegressionRequest,
    AsicGateReport,
    AsicPartnerCreate,
    AsicPartnerRead,
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
    LimitChangeCreate,
    LimitChangeRead,
    LotTravelerCreate,
    LotTravelerRead,
    ManufacturingOptionCreate,
    ManufacturingOptionRead,
    MeasurementRunImportMeta,
    MeasurementRunRead,
    PartnerArtifactCreate,
    PartnerArtifactRead,
    PartnerChangeCreate,
    PartnerChangeRead,
    PartnerChangeReview,
    QualityActionClose,
    QualityActionCreate,
    QualityActionRead,
    QualificationPlanCreate,
    QualificationPlanRead,
    QualificationResultCreate,
    QualificationResultRead,
    SafetyItemCreate,
    SafetyItemRead,
    SignalChainCreate,
    SignalChainRead,
    TestFlowCreate,
    TestFlowRead,
    ToolRunCreate,
    ToolRunRead,
    TradeStudyCreate,
    TradeStudyDecision,
    TradeStudyRead,
    WaferMapCreate,
    WaferMapRead,
    # R3 EPIC I
    AssumptionCreate,
    AssumptionEventRead,
    AssumptionRead,
    AssumptionResolve,
    AssumptionUpdate,
    DeviationCreate,
    DeviationDecision,
    DeviationRead,
    FindingDone,
    ImpactScanRead,
    TEMPLATE_IDS,
    # R3 EPIC J
    CopilotInteractionRead,
    CopilotRun,
    ProposalAccept,
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
CAN_CE_DECIDE = require_role("system_architect", "reviewer_approver")  # 편차 결정 — 요청자와 독립
# R2 EPIC B: 단가/NRE 열람은 사업·엔지니어링 역할로 제한 (수용기준 5).
CAN_COST = require_role(
    "system_architect", "electrical_asic_engineer", "quality_engineer", "reviewer_approver"
)

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


# ── P1-08: 3-language evidence report (ko/en/ja) ────────────────────────────


@router.get("/templates/{template_id}/evidence-report")
def get_evidence_report(
    template_id: str,
    db: Annotated[Session, Depends(get_db)],
    lang: str = "ko",
):
    """Localized evidence export (지시서 §10 R2 P1-08). Reads-only, no money:
    amounts stay behind the CAN_COST-restricted trade-study views, and every
    section keeps source_class so synthetic/mock never reads as measured."""
    if lang not in REPORT_LANGS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"detail": "unsupported language", "supported": list(REPORT_LANGS)},
        )
    return build_evidence_report(db, template_id, lang)


# ── R2 EPIC B: FAB·패키지·원가·납기 (지시서 §4 EPIC B, §10 R2) ────────────────


@router.post("/manufacturing-options", response_model=ManufacturingOptionRead, status_code=status.HTTP_201_CREATED)
def create_manufacturing_option(
    body: ManufacturingOptionCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Register one sourcing option (2~5 of these feed a trade study).

    TBD entries ({amount_tbd: 이유}) are stored verbatim and NEVER computed
    as zero — app/asic_trade.py nulls any total that crosses one
    (수용기준: 미확정 값은 TBD이며 0으로 계산되지 않는다).
    """

    def compute() -> tuple[int, dict]:
        opt = ManufacturingOption(
            business_id=body.business_id,
            template_id=body.template_id,
            variant_id=body.variant_id,
            foundry=body.foundry,
            node=body.node,
            wafer_size_mm=body.wafer_size_mm,
            voltage_option=body.voltage_option,
            device_option=body.device_option,
            temperature_grade=body.temperature_grade,
            package=body.package,
            osat=body.osat,
            moq=body.moq,
            tech_score=body.tech_score,
            nre={k: v.model_dump() for k, v in body.nre.items()},
            unit_cost={k: v.model_dump() for k, v in body.unit_cost.items()},
            schedule=[s.model_dump() for s in body.schedule],
            risks=[r.model_dump() for r in body.risks],
            status=body.status,
            note=body.note,
            created_by=user.username,
        )
        db.add(opt)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="asic_manufacturing_option",
            entity_id=opt.id,
            correlation_id=correlation_id,
            payload={"business_id": opt.business_id, "foundry": opt.foundry},
        )
        return (
            status.HTTP_201_CREATED,
            _redact_option(ManufacturingOptionRead.model_validate(opt)).model_dump(mode="json"),
        )

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


def _redact_option(read: ManufacturingOptionRead) -> ManufacturingOptionRead:
    """Cost fields out of the unrestricted read (수용기준: 내부 단가 데이터는
    역할·프로젝트·협력사별로 열람 범위를 제한한다) — structure stays public,
    money moves to GET /manufacturing-options/{id}/costs (CAN_COST)."""
    read.nre = None
    read.unit_cost = None
    read.cost_restricted = True
    return read


@router.get("/templates/{template_id}/manufacturing-options", response_model=list[ManufacturingOptionRead])
def list_manufacturing_options(template_id: str, db: Annotated[Session, Depends(get_db)]):
    rows = (
        db.query(ManufacturingOption)
        .filter_by(template_id=template_id)
        .order_by(ManufacturingOption.created_at)
        .all()
    )
    return [_redact_option(ManufacturingOptionRead.model_validate(r)).model_dump(mode="json") for r in rows]


@router.get("/manufacturing-options/{option_id}/costs")
def get_option_costs(
    option_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_COST)],
):
    """NRE + unit-cost detail — role-restricted money view (EPIC B 수용기준 5)."""
    opt = db.get(ManufacturingOption, option_id)
    if opt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "manufacturing option not found")
    return {
        "option_id": str(opt.id),
        "business_id": opt.business_id,
        "nre": opt.nre,
        "unit_cost": opt.unit_cost,
    }


@router.post("/trade-studies", response_model=TradeStudyRead, status_code=status.HTTP_201_CREATED)
def create_trade_study(
    body: TradeStudyCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Weighted 2~5-option comparison — synchronous deterministic arithmetic
    (app/asic_trade.py, no solver), same Temporal-exempt tier as corner studies."""

    options = (
        db.query(ManufacturingOption).filter(ManufacturingOption.id.in_(body.option_ids)).all()
    )
    found = {str(o.id) for o in options}
    missing = [str(i) for i in body.option_ids if str(i) not in found]
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"detail": "unresolved option ids", "unresolved": missing},
        )
    wrong_template = sorted(o.business_id for o in options if o.template_id != body.template_id)
    if wrong_template:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"detail": "options from another template", "offending": wrong_template},
        )
    if any(o.status == "superseded" for o in options):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "superseded option cannot be studied")

    ordered = [next(o for o in options if str(o.id) == str(i)) for i in body.option_ids]

    def compute() -> tuple[int, dict]:
        study = TradeStudy(
            business_id=body.business_id,
            template_id=body.template_id,
            variant_id=body.variant_id,
            title=body.title,
            option_ids=[str(i) for i in body.option_ids],
            weights=body.weights,
            annual_volume=body.annual_volume,
            result=compute_trade_study(ordered, body.weights, body.annual_volume),
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
            action="create",
            entity_type="asic_trade_study",
            entity_id=study.id,
            correlation_id=correlation_id,
            payload={"business_id": study.business_id, "options": study.option_ids},
        )
        return status.HTTP_201_CREATED, TradeStudyRead.model_validate(study).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/trade-studies", response_model=list[TradeStudyRead])
def list_trade_studies(
    template_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_COST)],
):
    """Study results embed unit costs, so unlike other ASIC reads this one is
    role-restricted (수용기준 5 — the deliberate exception to unauth reads)."""
    return (
        db.query(TradeStudy)
        .filter_by(template_id=template_id)
        .order_by(TradeStudy.created_at)
        .all()
    )


@router.post("/trade-studies/{study_id}/decision", response_model=TradeStudyRead)
def decide_trade_study(
    study_id: uuid.UUID,
    body: TradeStudyDecision,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO_CLOSE)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Record the option selection: 승인자·판단 근거·잔여 위험 (수용기준 4).
    One decision per study — a change of mind is a NEW study, not an edit."""

    study = db.get(TradeStudy, study_id)
    if study is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trade study not found")
    if study.decision is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "trade study already decided")
    if str(body.option_id) not in [str(i) for i in study.option_ids]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "option not part of this study")

    def compute() -> tuple[int, dict]:
        study.decision = {
            "option_id": str(body.option_id),
            "decided_by": user.username,
            "decided_at": utcnow().isoformat(),
            "rationale": body.rationale,
            "residual_risks": body.residual_risks,
        }
        study.status = "decided"
        record_audit(
            db,
            user=user,
            action="decide_trade_study",
            entity_type="asic_trade_study",
            entity_id=study.id,
            correlation_id=correlation_id,
            payload={"business_id": study.business_id, "option_id": str(body.option_id)},
        )
        return status.HTTP_200_OK, TradeStudyRead.model_validate(study).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


# ── R2 EPIC C: EDA 실행·검증 오케스트레이션 (지시서 §4 EPIC C) ────────────────

_TOOLRUN_TOOLS = {
    "schematic_check", "spice", "ams", "lint", "cdc", "rdc",
    "synthesis", "sta", "pr", "drc", "lvs", "erc", "signoff",
}


@router.post("/tool-runs", response_model=ToolRunRead, status_code=status.HTTP_201_CREATED)
def create_tool_run(
    body: ToolRunCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_IMPORT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Ingest one external EDA execution. Lineage rule (수용기준 4): the same
    (template, tool, input_hash) joins the SAME lineage_id — a retry with a
    different input hash can never masquerade as a retry. Append-only: a
    re-run adds a row and never overwrites an earlier result (수용기준 3)."""

    if body.report_artifact_version_id is not None and db.get(
        ArtifactVersion, body.report_artifact_version_id
    ) is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "report artifact version not found"
        )

    def compute() -> tuple[int, dict]:
        prev = (
            db.query(ToolRun)
            .filter_by(template_id=body.template_id, tool=body.tool, input_hash=body.input_hash)
            .first()
        )
        run = ToolRun(
            business_id=body.business_id,
            template_id=body.template_id,
            variant_id=body.variant_id,
            design_revision=body.design_revision,
            tool=body.tool,
            tool_version=body.tool_version,
            runner_class=body.runner_class,
            environment=body.environment,
            command_profile=body.command_profile,
            input_hash=body.input_hash,
            output_hash=body.output_hash,
            exit_code=body.exit_code,
            log_uri=body.log_uri,
            report_artifact_version_id=body.report_artifact_version_id,
            lineage_id=prev.lineage_id if prev is not None else uuid.uuid4(),
            metrics=body.metrics,
            status="completed" if body.exit_code == 0 else "failed",
            note=body.note,
            created_by=user.username,
        )
        db.add(run)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db,
            user=user,
            action="create",
            entity_type="asic_tool_run",
            entity_id=run.id,
            correlation_id=correlation_id,
            payload={
                "business_id": run.business_id,
                "tool": run.tool,
                "runner_class": run.runner_class,
                "lineage_id": str(run.lineage_id),
            },
        )
        return status.HTTP_201_CREATED, ToolRunRead.model_validate(run).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/tool-runs", response_model=list[ToolRunRead])
def list_tool_runs(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(ToolRun)
        .filter_by(template_id=template_id)
        .order_by(ToolRun.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# EPIC D — DFT·양산 테스트 프로그램 트윈 (지시서 §4, s6)
# ---------------------------------------------------------------------------

def _flow_read(flow: TestFlow) -> dict:
    return TestFlowRead.model_validate(flow).model_dump(mode="json")


@router.post("/test-flows", response_model=TestFlowRead, status_code=status.HTTP_201_CREATED)
def create_test_flow(
    body: TestFlowCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Create one program revision with its items in a single append-only
    write. Limit edits never mutate a released flow — they go through
    /limit-changes and supersede into a NEW revision (수용기준 2, 불변규칙 1)."""
    if body.variant_id is not None and db.get(Variant, body.variant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")

    def compute() -> tuple[int, dict]:
        flow = TestFlow(
            business_id=body.business_id,
            template_id=body.template_id,
            variant_id=body.variant_id,
            program_revision=body.program_revision,
            silicon_revision=body.silicon_revision,
            compatible_mask_rev=body.compatible_mask_rev,
            compatible_package_rev=body.compatible_package_rev,
            target=body.target,
            cost_rate_per_site_hour=body.cost_rate_per_site_hour,
            status=body.status,
            note=body.note,
            created_by=user.username,
        )
        db.add(flow)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        for item in body.items:
            db.add(TestFlowItem(
                business_id=f"{body.business_id}-it{item.seq:03d}",
                test_flow_id=flow.id,
                seq=item.seq,
                stage=item.stage,
                name=item.name,
                limits=item.limits.model_dump() if item.limits is not None else None,
                temperature_c=item.temperature_c,
                site_count=item.site_count,
                pattern=item.pattern,
                instrument=item.instrument,
                equipment_channel=item.equipment_channel,
                expected_duration_s=item.expected_duration_s,
                requirement_ids=item.requirement_ids,
                failure_mode_refs=item.failure_mode_refs,
                defect_coverage=(
                    [c.model_dump() for c in item.defect_coverage]
                    if item.defect_coverage is not None else None
                ),
                created_by=user.username,
            ))
            db.flush()
        record_audit(
            db, user=user, action="create", entity_type="asic_test_flow",
            entity_id=flow.id, correlation_id=correlation_id,
            payload={"business_id": flow.business_id, "target": flow.target,
                     "program_revision": flow.program_revision,
                     "items": len(body.items)},
        )
        return status.HTTP_201_CREATED, _flow_read(flow)

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/test-flows", response_model=list[TestFlowRead])
def list_test_flows(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(TestFlow)
        .filter_by(template_id=template_id)
        .order_by(TestFlow.created_at.desc())
        .all()
    )


@router.get("/templates/{template_id}/test-flow-analysis")
def analyze_test_flows(
    template_id: str,
    db: Annotated[Session, Depends(get_db)],
    program_revision: int | None = None,
):
    """시간/원가·커버리지·wafer sort↔final test 중복/누락·리비전 호환성 in one
    deterministic report. Picks the latest non-superseded flow per target at
    the requested (or highest) program revision."""
    q = db.query(TestFlow).filter_by(template_id=template_id).filter(TestFlow.status != "superseded")
    if program_revision is not None:
        q = q.filter_by(program_revision=program_revision)
    flows = q.order_by(TestFlow.program_revision.desc(), TestFlow.created_at.desc()).all()
    latest_by_target: dict[str, TestFlow] = {}
    for f in flows:
        latest_by_target.setdefault(f.target, f)
    if not latest_by_target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no test flow for template")

    per_target: dict[str, dict] = {}
    for target, f in latest_by_target.items():
        items = f.items
        mask_rev = None
        pkg_rev = None
        if f.variant_id is not None:
            lot = (
                db.query(LotTraveler)
                .filter_by(template_id=template_id, variant_id=f.variant_id)
                .order_by(LotTraveler.created_at.desc())
                .first()
            )
            mask_rev, pkg_rev = (lot.mask_rev, lot.package_rev) if lot else (None, None)
        per_target[target] = {
            "flow_id": str(f.id),
            "business_id": f.business_id,
            "program_revision": f.program_revision,
            "silicon_revision": f.silicon_revision,
            "totals": flow_totals(items, f.cost_rate_per_site_hour),
            "coverage": coverage_matrix(items),
            "compatibility": revision_compatibility(f, mask_rev, pkg_rev),
        }

    cross = None
    if "wafer_sort" in latest_by_target and "final_test" in latest_by_target:
        cross = cross_target_analysis(
            latest_by_target["wafer_sort"].items, latest_by_target["final_test"].items
        )
    silicon_revs = sorted({f.silicon_revision for f in latest_by_target.values()})
    return {
        "tool_version": "asic-testprog-v1",
        "template_id": template_id,
        "program_revision": program_revision,
        "silicon_revisions": silicon_revs,
        "per_target": per_target,
        "cross_target": cross,
        "tbd_note": (
            "cost_rate_per_site_hour 미확정 flow의 원가는 null(TBD)로 표시되며 0으로 계산되지 않습니다."
        ),
    }


@router.post(
    "/test-flows/{flow_id}/limit-changes",
    response_model=LimitChangeRead, status_code=status.HTTP_201_CREATED,
)
def propose_limit_change(
    flow_id: uuid.UUID,
    body: LimitChangeCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """한계값 변경 제안 + 영향 자동 표시 (수용기준 2). The proposal row stores
    the computed impact (lots/products/qual evidence/measurements) verbatim;
    nothing is applied until a human calls /apply."""
    flow = db.get(TestFlow, flow_id)
    if flow is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test flow not found")
    item = db.get(TestFlowItem, body.item_id)
    if item is None or item.test_flow_id != flow.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item not in this flow")

    new_limits = body.new_limits.model_dump()
    lots = (
        db.query(LotTraveler)
        .filter_by(template_id=flow.template_id, silicon_revision=flow.silicon_revision)
        .all()
    )
    variants = (
        [db.get(Variant, flow.variant_id)] if flow.variant_id is not None else []
    )
    plan_ids = [
        p.id for p in db.query(QualificationPlan).filter_by(template_id=flow.template_id).all()
    ]
    lot_refs = {l.lot_ref for l in lots}
    quals = []
    if plan_ids:
        for r in db.query(QualificationResult).filter(
            QualificationResult.plan_id.in_(plan_ids)
        ).all():
            row_lots = set(r.lots or [])
            if not row_lots or (row_lots & lot_refs):
                quals.append(r)
    measurements = (
        db.query(MeasurementRun)
        .filter_by(template_id=flow.template_id, program_revision=str(flow.program_revision))
        .all()
    )
    impact = limit_change_impact(
        item, new_limits, lots=lots, variants=[v for v in variants if v],
        quals=quals, measurements=measurements,
    )

    def compute() -> tuple[int, dict]:
        lc = LimitChange(
            business_id=f"lc-{flow.business_id}-it{item.seq:03d}-{utcnow().strftime('%H%M%S')}",
            test_flow_id=flow.id,
            item_id=item.id,
            old_limits=item.limits,
            new_limits=new_limits,
            rationale=body.rationale,
            impact=impact,
            status="proposed",
            created_by=user.username,
        )
        db.add(lc)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": "duplicate limit-change business_id, retry"})
        record_audit(
            db, user=user, action="create", entity_type="asic_limit_change",
            entity_id=lc.id, correlation_id=correlation_id,
            payload={"test_flow_id": str(flow.id), "item_id": str(item.id),
                     "new_limits": new_limits},
        )
        return status.HTTP_201_CREATED, LimitChangeRead.model_validate(lc).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/test-flows/{flow_id}/limit-changes", response_model=list[LimitChangeRead])
def list_limit_changes(flow_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(LimitChange)
        .filter_by(test_flow_id=flow_id)
        .order_by(LimitChange.created_at.desc())
        .all()
    )


@router.post("/limit-changes/{lc_id}/apply", response_model=TestFlowRead)
def apply_limit_change(
    lc_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO_CLOSE)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Human-only application: supersede the flow into a NEW program revision
    with the new limits (불변규칙 1 — never edit a released flow in place).
    Close-level role because a limit move re-opens release evidence."""
    lc = db.get(LimitChange, lc_id)
    if lc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "limit change not found")
    if lc.status == "applied":
        raise HTTPException(status.HTTP_409_CONFLICT, "limit change already applied")
    if lc.status == "rejected":
        raise HTTPException(status.HTTP_409_CONFLICT, "limit change was rejected")
    flow = db.get(TestFlow, lc.test_flow_id)
    item = db.get(TestFlowItem, lc.item_id)

    def compute() -> tuple[int, dict]:
        new_rev = flow.program_revision + 1
        base_bid = f"{flow.business_id}-r{new_rev}"[:64]
        if db.query(TestFlow).filter_by(business_id=base_bid).first() is not None:
            db.rollback()
            return _conflict({"detail": f"flow revision '{base_bid}' already exists"})
        new_flow = TestFlow(
            business_id=base_bid,
            template_id=flow.template_id,
            variant_id=flow.variant_id,
            program_revision=new_rev,
            silicon_revision=flow.silicon_revision,
            compatible_mask_rev=flow.compatible_mask_rev,
            compatible_package_rev=flow.compatible_package_rev,
            target=flow.target,
            cost_rate_per_site_hour=flow.cost_rate_per_site_hour,
            status="draft",
            note=f"supersedes {flow.business_id} via limit change {lc.business_id}",
            created_by=user.username,
        )
        db.add(new_flow)
        db.flush()
        for src in flow.items:
            limits = dict(src.limits or {}) if src.id == item.id else src.limits
            if src.id == item.id:
                limits = dict(lc.new_limits)
            db.add(TestFlowItem(
                business_id=f"{new_flow.business_id}-it{src.seq:03d}",
                test_flow_id=new_flow.id,
                seq=src.seq, stage=src.stage, name=src.name, limits=limits,
                temperature_c=src.temperature_c, site_count=src.site_count,
                pattern=src.pattern, instrument=src.instrument,
                equipment_channel=src.equipment_channel,
                expected_duration_s=src.expected_duration_s,
                requirement_ids=src.requirement_ids,
                failure_mode_refs=src.failure_mode_refs,
                defect_coverage=src.defect_coverage,
                created_by=user.username,
            ))
        db.flush()
        flow.status = "superseded"
        lc.status = "applied"
        lc.applied_flow_id = new_flow.id
        record_audit(
            db, user=user, action="apply", entity_type="asic_limit_change",
            entity_id=lc.id, correlation_id=correlation_id,
            payload={"superseded_flow": flow.business_id,
                     "new_flow": new_flow.business_id,
                     "new_program_revision": new_rev},
        )
        return status.HTTP_201_CREATED, _flow_read(new_flow)

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/test-flows/{flow_id}/proposals")
def test_flow_proposals(flow_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]):
    """비용 최적화 검토안 — REVIEW-ONLY (수용기준 4). Read-only by design;
    applying anything is a human supersedes action."""
    flow = db.get(TestFlow, flow_id)
    if flow is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test flow not found")
    twin = (
        db.query(TestFlow)
        .filter_by(
            template_id=flow.template_id, target=(
                "final_test" if flow.target == "wafer_sort" else "wafer_sort"
            ),
        )
        .filter(TestFlow.status != "superseded")
        .order_by(TestFlow.program_revision.desc(), TestFlow.created_at.desc())
        .first()
    )
    maps = db.query(WaferMap).filter_by(template_id=flow.template_id).all()
    return optimization_proposals(
        flow, twin_items=(twin.items if twin is not None else None), wafer_maps=maps
    )


@router.post("/wafer-maps", response_model=WaferMapRead, status_code=status.HTTP_201_CREATED)
def create_wafer_map(
    body: WaferMapCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_IMPORT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Store a bin/wafer map and compute its analysis at ingest. `ground_truth`
    is accepted for SYNTHETIC fixtures only — overkill/underkill are then a
    disclosed confusion matrix, never presented as production yield."""
    if body.ground_truth is not None and body.source_class != "SYNTHETIC":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "ground_truth is only valid for SYNTHETIC fixtures",
        )
    if body.test_flow_id is not None and db.get(TestFlow, body.test_flow_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "test flow not found")

    def compute() -> tuple[int, dict]:
        wm = WaferMap(
            business_id=body.business_id,
            template_id=body.template_id,
            variant_id=body.variant_id,
            lot_ref=body.lot_ref,
            wafer_ref=body.wafer_ref,
            test_flow_id=body.test_flow_id,
            grid=body.grid,
            bins=body.bins,
            ground_truth=body.ground_truth,
            source_class=body.source_class,
            note=body.note,
            created_by=user.username,
        )
        db.add(wm)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        wm.analysis = analyze_wafer_map(wm.bins, wm.ground_truth)
        record_audit(
            db, user=user, action="create", entity_type="asic_wafer_map",
            entity_id=wm.id, correlation_id=correlation_id,
            payload={"business_id": wm.business_id, "source_class": wm.source_class},
        )
        return status.HTTP_201_CREATED, WaferMapRead.model_validate(wm).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/wafer-maps", response_model=list[WaferMapRead])
def list_wafer_maps(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(WaferMap)
        .filter_by(template_id=template_id)
        .order_by(WaferMap.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# EPIC H — 파운드리·OSAT 포털·lot genealogy (지시서 §4, s9)
# ---------------------------------------------------------------------------

@router.post("/partners", response_model=AsicPartnerRead, status_code=status.HTTP_201_CREATED)
def create_partner(
    body: AsicPartnerCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Register a foundry/OSAT partner. New partners start `conditional` —
    approval is a separate close-level human decision (supply-chain gate
    input: evidence from a non-approved partner blocks the gate)."""

    def compute() -> tuple[int, dict]:
        partner = AsicPartner(
            business_id=body.business_id,
            name=body.name,
            kind=body.kind,
            status=body.status if body.status != "approved" else "conditional",
            approved_scope=body.approved_scope,
            approved_at=None,
            note=body.note,
            created_by=user.username,
        )
        db.add(partner)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db, user=user, action="create", entity_type="asic_partner",
            entity_id=partner.id, correlation_id=correlation_id,
            payload={"business_id": partner.business_id, "kind": partner.kind},
        )
        return status.HTTP_201_CREATED, AsicPartnerRead.model_validate(partner).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/partners/{partner_id}/approve", response_model=AsicPartnerRead)
def approve_partner(
    partner_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO_CLOSE)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    partner = db.get(AsicPartner, partner_id)
    if partner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "partner not found")
    if partner.status == "approved":
        raise HTTPException(status.HTTP_409_CONFLICT, "partner already approved")
    if partner.status == "suspended":
        raise HTTPException(status.HTTP_409_CONFLICT, "suspended partner needs re-review flow")

    def compute() -> tuple[int, dict]:
        partner.status = "approved"
        partner.approved_at = utcnow()
        record_audit(
            db, user=user, action="approve", entity_type="asic_partner",
            entity_id=partner.id, correlation_id=correlation_id,
            payload={"business_id": partner.business_id},
        )
        return status.HTTP_200_OK, AsicPartnerRead.model_validate(partner).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/partners", response_model=list[AsicPartnerRead])
def list_partners(db: Annotated[Session, Depends(get_db)]):
    return db.query(AsicPartner).order_by(AsicPartner.created_at.desc()).all()


@router.post("/lot-travelers", response_model=LotTravelerRead, status_code=status.HTTP_201_CREATED)
def create_lot_traveler(
    body: LotTravelerCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_IMPORT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Append-only lot genealogy record. Every step's partner must resolve to
    a registered partner — the gate's lineage check walks these steps."""
    if body.variant_id is not None and db.get(Variant, body.variant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")
    partners_by_bid: dict[str, AsicPartner] = {}
    for s in body.steps:
        p = _by_business_id(db, AsicPartner, s.partner_business_id, "partner")
        partners_by_bid[s.partner_business_id] = p

    def compute() -> tuple[int, dict]:
        steps = []
        for s in body.steps:
            p = partners_by_bid[s.partner_business_id]
            steps.append({
                "partner_id": str(p.id),
                "partner_business_id": p.business_id,
                "step": s.step,
                "result": s.result,
                "recorded_at": utcnow().isoformat(),
            })
        last = partners_by_bid[body.steps[-1].partner_business_id]
        traveler = LotTraveler(
            business_id=body.business_id,
            template_id=body.template_id,
            variant_id=body.variant_id,
            lot_ref=body.lot_ref,
            parent_lot_refs=body.parent_lot_refs,
            silicon_revision=body.silicon_revision,
            mask_rev=body.mask_rev,
            package_rev=body.package_rev,
            current_partner_id=last.id,
            status="in_process",
            steps=steps,
            note=body.note,
            created_by=user.username,
        )
        db.add(traveler)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db, user=user, action="create", entity_type="asic_lot_traveler",
            entity_id=traveler.id, correlation_id=correlation_id,
            payload={"lot_ref": traveler.lot_ref, "steps": len(steps)},
        )
        return status.HTTP_201_CREATED, LotTravelerRead.model_validate(traveler).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/lot-travelers", response_model=list[LotTravelerRead])
def list_lot_travelers(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(LotTraveler)
        .filter_by(template_id=template_id)
        .order_by(LotTraveler.created_at.desc())
        .all()
    )


@router.post("/partner-artifacts", response_model=PartnerArtifactRead, status_code=status.HTTP_201_CREATED)
def create_partner_artifact(
    body: PartnerArtifactCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_IMPORT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Partner portal upload (sha256 원본 해시). Duplicate file_hash → 409 —
    the same evidence can never enter the chain twice. The partner identity
    arrives as `partner_business_id` (portal principal mapping; realm claim
    integration is a later slice — no realm changes in R2)."""
    partner = _by_business_id(db, AsicPartner, body.partner_business_id, "partner")
    if body.lot_traveler_id is not None and db.get(LotTraveler, body.lot_traveler_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lot traveler not found")

    def compute() -> tuple[int, dict]:
        dup = db.query(PartnerArtifact).filter_by(file_hash=body.file_hash).first()
        if dup is not None:
            db.rollback()
            return _conflict({
                "detail": "identical file already ingested",
                "existing_business_id": dup.business_id,
            })
        art = PartnerArtifact(
            business_id=body.business_id,
            partner_id=partner.id,
            lot_traveler_id=body.lot_traveler_id,
            template_id=body.template_id,
            kind=body.kind,
            file_hash=body.file_hash,
            artifact_version_id=None,
            meta=body.meta,
            status="submitted",
            note=body.note,
            created_by=user.username,
        )
        db.add(art)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db, user=user, action="create", entity_type="asic_partner_artifact",
            entity_id=art.id, correlation_id=correlation_id,
            payload={"business_id": art.business_id, "partner": partner.business_id,
                     "file_hash": art.file_hash},
        )
        return status.HTTP_201_CREATED, PartnerArtifactRead.model_validate(art).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/partner-artifacts", response_model=list[PartnerArtifactRead])
def list_partner_artifacts(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(PartnerArtifact)
        .filter_by(template_id=template_id)
        .order_by(PartnerArtifact.created_at.desc())
        .all()
    )


@router.post("/partner-changes", response_model=PartnerChangeRead, status_code=status.HTTP_201_CREATED)
def create_partner_change(
    body: PartnerChangeCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_IMPORT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """PCN 접수. status starts `submitted`; only /review moves it — and until
    it is approved, the template gate carries PARTNER_CHANGE_PENDING."""
    partner = _by_business_id(db, AsicPartner, body.partner_business_id, "partner")

    def compute() -> tuple[int, dict]:
        change = PartnerChange(
            business_id=body.business_id,
            partner_id=partner.id,
            kind=body.kind,
            description=body.description,
            effective_at=body.effective_at,
            affected_template_ids=body.affected_template_ids,
            status="submitted",
            note=body.note,
            created_by=user.username,
        )
        db.add(change)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db, user=user, action="create", entity_type="asic_partner_change",
            entity_id=change.id, correlation_id=correlation_id,
            payload={"business_id": change.business_id, "partner": partner.business_id,
                     "kind": change.kind},
        )
        return status.HTTP_201_CREATED, PartnerChangeRead.model_validate(change).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/partner-changes", response_model=list[PartnerChangeRead])
def list_partner_changes(template_id: str, db: Annotated[Session, Depends(get_db)]):
    """PCN ledger for a template — a submitted/under_review row here is what
    the gate turns into PARTNER_CHANGE_PENDING."""
    partner_ids = [p.id for p in db.query(AsicPartner).all()]
    if not partner_ids:
        return []
    return (
        db.query(PartnerChange)
        .filter(PartnerChange.partner_id.in_(partner_ids))
        .order_by(PartnerChange.created_at.desc())
        .all()
    )


@router.post("/partner-changes/{change_id}/review", response_model=PartnerChangeRead)
def review_partner_change(
    change_id: uuid.UUID,
    body: PartnerChangeReview,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_ECO_CLOSE)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """Human PCN decision (close-level role — a partner change re-opens the
    supply-chain evidence the release gate leans on)."""
    change = db.get(PartnerChange, change_id)
    if change is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "partner change not found")
    if change.status in ("approved", "rejected"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"change already {change.status}")

    def compute() -> tuple[int, dict]:
        change.status = body.decision
        change.reviewed_by = user.username
        change.reviewed_at = utcnow()
        if body.note:
            change.note = body.note
        record_audit(
            db, user=user, action="review", entity_type="asic_partner_change",
            entity_id=change.id, correlation_id=correlation_id,
            payload={"decision": body.decision},
        )
        return status.HTTP_200_OK, PartnerChangeRead.model_validate(change).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/quality-actions", response_model=QualityActionRead, status_code=status.HTTP_201_CREATED)
def create_quality_action(
    body: QualityActionCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_QUAL)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """품질 조치 등록 (hold/quarantine/8D…). An OPEN action on the lot chain is
    a gate blocker (QUALITY_ACTION_OPEN) until a human closes it."""
    if body.lot_traveler_id is not None and db.get(LotTraveler, body.lot_traveler_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lot traveler not found")
    if body.fa_case_id is not None and db.get(FaCase, body.fa_case_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "fa case not found")
    partner_id = None
    if body.lot_traveler_id is not None:
        lt = db.get(LotTraveler, body.lot_traveler_id)
        partner_id = lt.current_partner_id

    def compute() -> tuple[int, dict]:
        qa = QualityAction(
            business_id=body.business_id,
            partner_id=partner_id,
            lot_traveler_id=body.lot_traveler_id,
            template_id=body.template_id,
            lot_ref=body.lot_ref,
            action=body.action,
            reason=body.reason,
            status="open",
            fa_case_id=body.fa_case_id,
            note=body.note,
            created_by=user.username,
        )
        db.add(qa)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(
            db, user=user, action="create", entity_type="asic_quality_action",
            entity_id=qa.id, correlation_id=correlation_id,
            payload={"business_id": qa.business_id, "action": qa.action,
                     "lot_ref": qa.lot_ref},
        )
        return status.HTTP_201_CREATED, QualityActionRead.model_validate(qa).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/quality-actions/{action_id}/close", response_model=QualityActionRead)
def close_quality_action(
    action_id: uuid.UUID,
    body: QualityActionClose,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_QUAL)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    qa = db.get(QualityAction, action_id)
    if qa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "quality action not found")
    if qa.status == "closed":
        raise HTTPException(status.HTTP_409_CONFLICT, "quality action already closed")

    def compute() -> tuple[int, dict]:
        qa.status = "closed"
        qa.closed_at = utcnow()
        if body.note:
            qa.note = body.note
        record_audit(
            db, user=user, action="close", entity_type="asic_quality_action",
            entity_id=qa.id, correlation_id=correlation_id,
            payload={"business_id": qa.business_id},
        )
        return status.HTTP_200_OK, QualityActionRead.model_validate(qa).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/quality-actions", response_model=list[QualityActionRead])
def list_quality_actions(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(QualityAction)
        .filter_by(template_id=template_id)
        .order_by(QualityAction.created_at.desc())
        .all()
    )


@router.get("/portal/{partner_business_id}/dashboard")
def partner_portal_dashboard(
    partner_business_id: str,
    db: Annotated[Session, Depends(get_db)],
    template_id: str | None = None,
):
    """파트너 포털 뷰 — 파트너 격리 수용기준.

    Isolation contract: this endpoint returns ONLY rows whose partner_id
    matches `partner_business_id` — never another partner's lots, artifacts,
    PCNs or actions. R2 wires the principal via a path parameter (tests prove
    isolation with mocked principals); the later realm slice replaces the
    path parameter with a token claim — the scoping query does not change.
    """
    partner = _by_business_id(db, AsicPartner, partner_business_id, "partner")
    q = db.query(LotTraveler)
    if template_id is not None:
        q = q.filter_by(template_id=template_id)
    # steps is JSONB — match the partner in Python (row counts are lot-scale)
    lots = [
        lt for lt in q.order_by(LotTraveler.created_at.desc()).all()
        if any(s.get("partner_id") == str(partner.id) for s in (lt.steps or []))
    ]
    artifact_q = db.query(PartnerArtifact).filter_by(partner_id=partner.id)
    change_q = db.query(PartnerChange).filter_by(partner_id=partner.id)
    action_q = db.query(QualityAction).filter_by(partner_id=partner.id)
    if template_id is not None:
        artifact_q = artifact_q.filter_by(template_id=template_id)
        actions = [a for a in action_q.all() if a.template_id == template_id]
    else:
        actions = action_q.all()
    return {
        "partner": AsicPartnerRead.model_validate(partner).model_dump(mode="json"),
        "lot_travelers": [
            LotTravelerRead.model_validate(lt).model_dump(mode="json") for lt in lots
        ],
        "artifacts": [
            PartnerArtifactRead.model_validate(a).model_dump(mode="json")
            for a in artifact_q.order_by(PartnerArtifact.created_at.desc()).all()
        ],
        "partner_changes": [
            PartnerChangeRead.model_validate(c).model_dump(mode="json")
            for c in change_q.order_by(PartnerChange.created_at.desc()).all()
        ],
        "quality_actions": [
            QualityActionRead.model_validate(a).model_dump(mode="json") for a in actions
        ],
    }


# ══ R3 EPIC I: Concurrent Engineering 제어판 ══════════════════════════════════

_CE_KIND_ACTION = {
    # 수용기준 2: 영향 목록은 재실행(rerun)·재검토(review) 상태로 자동 전환된다
    "circuit": ("rerun", "회로 시뮬레이션(corner/MC·ToolRun) 재실행 필요"),
    "layout": ("rerun", "레이아웃/P&R 도구 재실행 필요"),
    "package": ("review", "패키지·조립 영향 재검토 필요"),
    "test": ("review", "시험 프로그램·한계값 재검토 필요"),
    "quote": ("review", "견적·납기 시나리오 갱신 필요"),
}


def _impact_findings(downstream: list[dict], assumption_bid: str) -> list[dict]:
    findings = []
    for d in downstream:
        action, reason = _CE_KIND_ACTION.get(
            d.get("kind", "review"), ("review", "영향 재검토 필요")
        )
        findings.append({
            "kind": d.get("kind", "review"),
            "ref": d.get("ref", ""),
            "label": d.get("label", ""),
            "action": action,
            "status": "pending",
            "reason": reason,
        })
    return findings


def _open_scans(db: Session, assumption_id: uuid.UUID) -> list[AsicImpactScan]:
    return (
        db.query(AsicImpactScan)
        .filter_by(assumption_id=assumption_id, status="open")
        .all()
    )


@router.post("/assumptions", response_model=AssumptionRead, status_code=status.HTTP_201_CREATED)
def create_assumption(
    body: AssumptionCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DESIGN)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """EPIC I — 가정 등록. 등록 즉시 1차 영향 탐색이 생성된다(재실행·재검토
    상태로 시작 — 수용기준 2). 요구사항과 연결하면 ASSUMPTION_BASED로 추적된다."""
    if body.requirement_id is not None and db.get(Requirement, body.requirement_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "requirement not found")
    if body.variant_id is not None and db.get(Variant, body.variant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variant not found")

    def compute() -> tuple[int, dict]:
        a = AsicAssumption(
            business_id=body.business_id,
            template_id=body.template_id,
            variant_id=body.variant_id,
            requirement_id=body.requirement_id,
            title=body.title,
            detail=body.detail,
            risk=body.risk,
            confidence=body.confidence,
            owner=body.owner,
            due_at=body.due_at,
            downstream=[d.model_dump() for d in body.downstream],
            note=body.note,
            created_by=user.username,
        )
        db.add(a)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        db.add(AsicAssumptionEvent(
            business_id=f"{a.business_id}-EV-CREATED-{uuid.uuid4().hex[:8]}",
            assumption_id=a.id, kind="created", payload={"risk": a.risk, "confidence": a.confidence},
            created_by=user.username,
        ))
        scan = AsicImpactScan(
            business_id=f"{a.business_id}-SCAN-{uuid.uuid4().hex[:8]}",
            assumption_id=a.id, trigger="created",
            findings=_impact_findings(a.downstream, a.business_id),
            created_by=user.username,
        )
        db.add(scan)
        record_audit(db, user=user, action="create", entity_type="asic_assumption",
                     entity_id=a.id, correlation_id=correlation_id,
                     payload={"business_id": a.business_id, "risk": a.risk})
        resp = AssumptionRead.model_validate(a).model_dump(mode="json")
        resp["initial_scan_id"] = str(scan.id)
        return status.HTTP_201_CREATED, resp

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/assumptions", response_model=list[AssumptionRead])
def list_assumptions(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(AsicAssumption).filter_by(template_id=template_id).order_by(
        AsicAssumption.created_at.desc()
    ).all()


@router.get("/assumptions/{assumption_id}/events", response_model=list[AssumptionEventRead])
def list_assumption_events(assumption_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]):
    a = db.get(AsicAssumption, assumption_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assumption not found")
    return (
        db.query(AsicAssumptionEvent)
        .filter_by(assumption_id=assumption_id)
        .order_by(AsicAssumptionEvent.created_at.asc())
        .all()
    )


@router.get("/assumptions/{assumption_id}/impact-scans", response_model=list[ImpactScanRead])
def list_assumption_scans(assumption_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]):
    a = db.get(AsicAssumption, assumption_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assumption not found")
    return (
        db.query(AsicImpactScan)
        .filter_by(assumption_id=assumption_id)
        .order_by(AsicImpactScan.created_at.desc())
        .all()
    )


@router.patch("/assumptions/{assumption_id}", response_model=AssumptionRead)
def update_assumption(
    assumption_id: uuid.UUID,
    body: AssumptionUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DESIGN)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """EPIC I — 가정 변경. 내용(title/detail)·신뢰도·리스크·downstream이 바뀌면
    변경 장부(append-only)와 새 영향 탐색이 자동 생성된다 — 영향 목록이
    재실행·재검토 상태로 자동 전환(수용기준 2)."""
    a = db.get(AsicAssumption, assumption_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assumption not found")
    if a.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"closed assumption cannot be edited (status={a.status})")
    fields = ("title", "detail", "risk", "confidence", "owner", "due_at", "downstream", "note")
    changes = {f: getattr(body, f) for f in fields if getattr(body, f) is not None}
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "no fields to update")

    def compute() -> tuple[int, dict]:
        old: dict = {}
        for f, new in changes.items():
            old[f] = getattr(a, f)
            if f == "downstream":
                setattr(a, f, [d.model_dump() for d in new])
            else:
                setattr(a, f, new)
        db.add(AsicAssumptionEvent(
            business_id=f"{a.business_id}-EV-{uuid.uuid4().hex[:8]}",
            assumption_id=a.id, kind="field_changed",
            payload={f: {"old": str(old[f]), "new": str(changes[f])} for f in changes},
            created_by=user.username,
        ))
        content_changed = any(f in changes for f in
                              ("title", "detail", "risk", "confidence", "downstream"))
        scan_id = None
        if content_changed:
            scan = AsicImpactScan(
                business_id=f"{a.business_id}-SCAN-{uuid.uuid4().hex[:8]}",
                assumption_id=a.id, trigger="assumption_changed",
                findings=_impact_findings(a.downstream, a.business_id),
                created_by=user.username,
            )
            db.add(scan)
            scan_id = scan.id
        record_audit(db, user=user, action="update", entity_type="asic_assumption",
                     entity_id=a.id, correlation_id=correlation_id,
                     payload={"changed": sorted(changes)})
        resp = AssumptionRead.model_validate(a).model_dump(mode="json")
        resp["impact_scan_id"] = str(scan_id) if scan_id else None
        return status.HTTP_200_OK, resp

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/assumptions/{assumption_id}/resolve", response_model=AssumptionRead)
def resolve_assumption(
    assumption_id: uuid.UUID,
    body: AssumptionResolve,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DESIGN)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """가정 해결/무효화. 열린 영향 탐색이 남아 있으면 거부한다 — 재실행·재검토가
    끝나기 전에 가정이 조용히 닫히는 것을 막는다 (수용기준 2의 강제)."""
    a = db.get(AsicAssumption, assumption_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assumption not found")
    if a.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, f"assumption already {a.status}")
    open_scans = _open_scans(db, assumption_id)
    if open_scans:
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            {"detail": "열린 영향 탐색이 있습니다 — findings를 완료하고 탐색을 clear한 뒤 해결하세요.",
             "open_scans": [s.business_id for s in open_scans]},
        )

    def compute() -> tuple[int, dict]:
        a.status = body.decision
        a.resolved_evidence = body.evidence
        a.resolved_at = utcnow()
        db.add(AsicAssumptionEvent(
            business_id=f"{a.business_id}-EV-{uuid.uuid4().hex[:8]}",
            assumption_id=a.id, kind=body.decision,
            payload={"evidence": body.evidence, "note": body.note},
            created_by=user.username,
        ))
        record_audit(db, user=user, action=body.decision, entity_type="asic_assumption",
                     entity_id=a.id, correlation_id=correlation_id, payload={})
        return status.HTTP_200_OK, AssumptionRead.model_validate(a).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/impact-scans/{scan_id}/findings/done", response_model=ImpactScanRead)
def complete_finding(
    scan_id: uuid.UUID,
    body: FindingDone,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DESIGN)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """영향 항목 하나를 완료 처리 (재실행·재검토가 실제로 끝났을 때 사람이 표시)."""
    scan = db.get(AsicImpactScan, scan_id)
    if scan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "impact scan not found")
    if scan.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "scan already cleared")
    target = next((f for f in scan.findings if f.get("ref") == body.ref), None)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"finding ref '{body.ref}' not in scan")

    def compute() -> tuple[int, dict]:
        target["status"] = "done"
        if body.note:
            target["done_note"] = body.note
        flag_modified(scan, "findings")
        record_audit(db, user=user, action="update", entity_type="asic_impact_scan",
                     entity_id=scan.id, correlation_id=correlation_id,
                     payload={"ref": body.ref, "status": "done"})
        return status.HTTP_200_OK, ImpactScanRead.model_validate(scan).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/impact-scans/{scan_id}/clear", response_model=ImpactScanRead)
def clear_scan(
    scan_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DESIGN)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    scan = db.get(AsicImpactScan, scan_id)
    if scan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "impact scan not found")
    if scan.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "scan already cleared")
    pending = [f.get("ref") for f in scan.findings if f.get("status") != "done"]
    if pending:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED,
                            {"detail": "완료되지 않은 findings가 있습니다", "pending": pending})

    def compute() -> tuple[int, dict]:
        scan.status = "cleared"
        record_audit(db, user=user, action="update", entity_type="asic_impact_scan",
                     entity_id=scan.id, correlation_id=correlation_id,
                     payload={"status": "cleared"})
        return status.HTTP_200_OK, ImpactScanRead.model_validate(scan).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.post("/deviations", response_model=DeviationRead, status_code=status.HTTP_201_CREATED)
def create_deviation(
    body: DeviationCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DESIGN)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """EPIC I — CS 단축/변형으로 생략·병행한 활동의 편차 문서 (수용기준 3:
    숨기지 않고 승인된 편차로 남긴다). 승인은 요청자와 다른 사람이 한다."""

    def compute() -> tuple[int, dict]:
        d = AsicDeviation(
            business_id=body.business_id,
            template_id=body.template_id,
            skipped=[s.model_dump() for s in body.skipped],
            rationale=body.rationale,
            residual_risk=body.residual_risk,
            requested_by=user.username,
            note=body.note,
            created_by=user.username,
        )
        db.add(d)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return _conflict({"detail": f"business_id '{body.business_id}' already exists"})
        record_audit(db, user=user, action="create", entity_type="asic_deviation",
                     entity_id=d.id, correlation_id=correlation_id,
                     payload={"business_id": d.business_id})
        return status.HTTP_201_CREATED, DeviationRead.model_validate(d).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/deviations", response_model=list[DeviationRead])
def list_deviations(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return db.query(AsicDeviation).filter_by(template_id=template_id).order_by(
        AsicDeviation.created_at.desc()
    ).all()


@router.post("/deviations/{deviation_id}/decide", response_model=DeviationRead)
def decide_deviation(
    deviation_id: uuid.UUID,
    body: DeviationDecision,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_CE_DECIDE)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """편차 승인/기각 — 독립성 규칙(FA/CAPA와 동일): 요청자 ≠ 결정자."""
    d = db.get(AsicDeviation, deviation_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deviation not found")
    if d.status != "submitted":
        raise HTTPException(status.HTTP_409_CONFLICT, f"deviation already {d.status}")
    if d.requested_by == user.username:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "독립성 규칙: 편차 요청자는 본인의 편차를 승인할 수 없습니다",
        )

    def compute() -> tuple[int, dict]:
        d.status = body.decision
        d.decided_by = user.username
        d.decided_at = utcnow()
        if body.note:
            d.note = body.note
        record_audit(db, user=user, action=body.decision, entity_type="asic_deviation",
                     entity_id=d.id, correlation_id=correlation_id, payload={})
        return status.HTTP_200_OK, DeviationRead.model_validate(d).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


# ══ R3 EPIC J: 근거 중심 AI Engineering Copilot ═══════════════════════════════

CAN_COPILOT = require_role(
    "system_architect", "electrical_asic_engineer", "quality_engineer", "test_emc_engineer"
)


@router.post("/copilot/{template_id}/run", response_model=CopilotInteractionRead,
             status_code=status.HTTP_201_CREATED)
def run_copilot_usecase(
    template_id: str,
    body: CopilotRun,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_COPILOT)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """EPIC J — 유스케이스 실행. 결과는 감사 재현 메타데이터(input_hash·engine
    version)와 함께 상호작록으로 남는다. copilot은 gate/evidence 테이블에
    절대 쓰지 않으므로 근거 링크 없는 제안이 증적이 되는 경로가 없다."""
    if template_id not in TEMPLATE_IDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown template '{template_id}'")
    fa_case = None
    if body.fa_case_id is not None:
        fa_case = db.get(FaCase, body.fa_case_id)
        if fa_case is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "fa_case not found")

    def compute() -> tuple[int, dict]:
        result, snapshot, input_hash, proposals = run_copilot(
            db, template_id, body.usecase, text=body.text, fa_case=fa_case
        )
        interaction = AsicCopilotInteraction(
            business_id=f"COPL-{template_id[:3].upper()}-{body.usecase[:8].upper()}-{uuid.uuid4().hex[:8]}",
            template_id=template_id,
            usecase=body.usecase,
            input_snapshot=snapshot,
            input_hash=input_hash,
            result=result,
            engine_version=ENGINE_VERSION,
            accepted_proposals=[],
            created_by=user.username,
        )
        db.add(interaction)
        db.flush()
        record_audit(db, user=user, action="create", entity_type="asic_copilot_interaction",
                     entity_id=interaction.id, correlation_id=correlation_id,
                     payload={"usecase": body.usecase, "abstain": result.get("abstain")})
        return status.HTTP_201_CREATED, CopilotInteractionRead.model_validate(
            interaction
        ).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result


@router.get("/templates/{template_id}/copilot", response_model=list[CopilotInteractionRead])
def list_copilot_interactions(template_id: str, db: Annotated[Session, Depends(get_db)]):
    return (
        db.query(AsicCopilotInteraction)
        .filter_by(template_id=template_id)
        .order_by(AsicCopilotInteraction.created_at.desc())
        .limit(50)
        .all()
    )


@router.get("/copilot/interactions/{interaction_id}/proposals/{pid}/diff")
def proposal_diff_text(
    interaction_id: uuid.UUID,
    pid: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_COPILOT)],
):
    """수용기준 2 — UI는 이 diff 문자열을 그대로 보여주고, 수락 시 그 sha256을
    돌려보낸다. 서버가 재계산해 대조하므로 '사용자가 본 것'과 '검증 대상'이
    항상 같은 바이트다."""
    it = db.get(AsicCopilotInteraction, interaction_id)
    if it is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "interaction not found")
    prop = next((p for p in (it.result or {}).get("proposals", []) if p.get("pid") == pid), None)
    if prop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"proposal '{pid}' not found")
    diff = proposal_diff(prop.get("diff_base") or "", prop.get("text", ""))
    return {"pid": pid, "diff": diff, "sha256": hashlib.sha256(diff.encode()).hexdigest()}


@router.post("/copilot/interactions/{interaction_id}/proposals/accept",
             response_model=CopilotInteractionRead)
def accept_copilot_proposal(
    interaction_id: uuid.UUID,
    body: ProposalAccept,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(CAN_DESIGN)],
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)],
):
    """제안 수락 기록 — diff 해시 대조가 강제된다. 수락은 '기록'일 뿐 실제
    적용(요구사항 등록, FA 가설 채택, 시험 변경)은 도메인 엔드포인트에서
    인간이 수행한다 (AI가 승인자가 아님)."""
    it = db.get(AsicCopilotInteraction, interaction_id)
    if it is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "interaction not found")
    prop = next((p for p in (it.result or {}).get("proposals", []) if p.get("pid") == body.pid), None)
    if prop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"proposal '{body.pid}' not found")
    if any(a.get("pid") == body.pid for a in it.accepted_proposals):
        raise HTTPException(status.HTTP_409_CONFLICT, "proposal already accepted")
    expected = hashlib.sha256(
        proposal_diff(prop.get("diff_base") or "", prop.get("text", "")).encode()
    ).hexdigest()
    if body.diff_sha256 != expected:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "diff 해시가 일치하지 않습니다 — 원문 대비 diff를 확인한 뒤 다시 수락하세요 (수용기준 2)",
        )

    def compute() -> tuple[int, dict]:
        it.accepted_proposals = list(it.accepted_proposals) + [{
            "pid": body.pid,
            "accepted_by": user.username,
            "accepted_at": utcnow().isoformat(),
            "diff_sha256": body.diff_sha256,
            "kind": prop.get("kind"),
        }]
        flag_modified(it, "accepted_proposals")
        record_audit(db, user=user, action="update",
                     entity_type="asic_copilot_interaction", entity_id=it.id,
                     correlation_id=correlation_id, payload={"accepted": body.pid})
        return status.HTTP_200_OK, CopilotInteractionRead.model_validate(it).model_dump(mode="json")

    result = idempotent_write(
        db, request=request, idempotency_key=idempotency_key, user=user, compute=compute
    )
    db.commit()
    return result
