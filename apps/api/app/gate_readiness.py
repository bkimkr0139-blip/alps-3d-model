"""Gate submission readiness check (§12.2: "승인 전 필수 증적 누락 시 Gate
차단"). Pure read-only query over what the vertical slice already produced —
no new state, just a checklist a Gate submission is blocked on."""

from sqlalchemy.orm import Session

from app.models.baseline import Baseline
from app.models.requirement import Requirement, RequirementTraceLink
from app.models.simulation import RunStatus, RunType, SimulationRun
from app.models.test import CorrelationRecord

CORRELATION_MIN_R = 0.9


def check_gate_readiness(db: Session, *, variant_id, baseline_id) -> dict:
    checklist: dict[str, bool] = {}

    baseline = db.get(Baseline, baseline_id)
    checklist["baseline_exists"] = baseline is not None and str(baseline.variant_id) == str(variant_id)

    requirements = db.query(Requirement).filter_by(variant_id=variant_id).all()
    traced_requirement_ids = {
        link.requirement_id
        for link in db.query(RequirementTraceLink)
        .filter(RequirementTraceLink.requirement_id.in_([r.id for r in requirements]))
        .all()
    } if requirements else set()
    checklist["all_requirements_traced"] = bool(requirements) and all(
        r.id in traced_requirement_ids for r in requirements
    )

    runs = db.query(SimulationRun).filter_by(variant_id=variant_id).all()
    checklist["spice_analysis_succeeded"] = any(
        r.run_type == RunType.SPICE_ANALYSIS and r.status == RunStatus.SUCCEEDED for r in runs
    )
    mech_runs = [r for r in runs if r.run_type == RunType.MECH_MODEL and r.status == RunStatus.SUCCEEDED]
    checklist["mech_model_succeeded"] = bool(mech_runs)

    correlations = (
        db.query(CorrelationRecord)
        .filter(CorrelationRecord.simulation_run_id.in_([r.id for r in mech_runs]))
        .all()
        if mech_runs
        else []
    )
    checklist["correlation_computed"] = bool(correlations)
    checklist["correlation_within_tolerance"] = any(
        c.correlation_coefficient >= CORRELATION_MIN_R and not c.extrapolation_warning for c in correlations
    )

    missing = [name for name, ok in checklist.items() if not ok]
    return {"checklist": checklist, "passed": not missing, "missing": missing}
