import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from temporalio import activity

from fs_model import predict_bridge_transfer, predict_detent_curve, predict_fs_curve

TOOL_VERSION = "analytical-mech-model-v2"

# One default set per model_type; a run's own parameters override these.
# model_type also picks the metric naming family — the correlation API
# (app/correlation.py) parses the same prefixes, so the two lists must stay
# in sync:
#   fs_dome         → force_mN_at_x_<x>     (mm, mN)   [tact switch]
#   detent_torque   → torque_mNm_at_deg_<x> (deg, mN·m) [rotary encoder]
#   bridge_transfer → vout_mv_at_kpa_<x>    (kPa, mV)  [MEMS pressure sensor]
MODEL_DEFAULTS = {
    "fs_dome": {
        "dome_thickness_mm": 0.10,
        "dome_diameter_mm": 6.0,
        "stroke_max_mm": 0.35,
        "num_points": 15,
    },
    "detent_torque": {
        "detent_count": 12,
        "peak_torque_mNm": 3.5,
        "angle_span_deg": 90.0,
        "num_points": 15,
    },
    "bridge_transfer": {
        "supply_voltage_v": 3.0,
        "sensitivity_mv_per_v_per_kpa": 0.8,
        "pressure_min_kpa": 40.0,
        "pressure_max_kpa": 400.0,
        "num_points": 15,
    },
}

# model_type → (metric prefix, y_unit)
MODEL_METRICS = {
    "fs_dome": ("force_mN_at_x", "mN"),
    "detent_torque": ("torque_mNm_at_deg", "mN·m"),
    "bridge_transfer": ("vout_mv_at_kpa", "mV"),
}


@activity.defn(name="run_mech_model_activity")
def run_mech_model_activity(simulation_run_id: str) -> None:
    from sqlalchemy.orm import Session

    from app.db import engine
    from app.models.simulation import ResultMetric, RunStatus, SimulationRun

    with Session(bind=engine) as db:
        run = db.get(SimulationRun, simulation_run_id)
        if run is None:
            raise ValueError(f"simulation_run {simulation_run_id} not found")

        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        run.tool_version = TOOL_VERSION
        db.commit()

        try:
            params = dict(run.parameters or {})
            model_type = params.pop("model_type", "fs_dome")
            defaults = MODEL_DEFAULTS.get(model_type)
            if defaults is None:
                raise ValueError(
                    f"unknown model_type {model_type!r} "
                    f"(expected one of {sorted(MODEL_DEFAULTS)})"
                )
            params = {**defaults, **params}
            metric_prefix, y_unit = MODEL_METRICS[model_type]

            if model_type == "fs_dome":
                xs, ys = predict_fs_curve(
                    dome_thickness_mm=params["dome_thickness_mm"],
                    dome_diameter_mm=params["dome_diameter_mm"],
                    stroke_max_mm=params["stroke_max_mm"],
                    num_points=int(params["num_points"]),
                )
            elif model_type == "detent_torque":
                xs, ys = predict_detent_curve(
                    detent_count=int(params["detent_count"]),
                    peak_torque_mNm=params["peak_torque_mNm"],
                    angle_span_deg=params["angle_span_deg"],
                    num_points=int(params["num_points"]),
                )
            else:  # bridge_transfer
                xs, ys = predict_bridge_transfer(
                    supply_voltage_v=params["supply_voltage_v"],
                    sensitivity_mv_per_v_per_kpa=params["sensitivity_mv_per_v_per_kpa"],
                    pressure_min_kpa=params["pressure_min_kpa"],
                    pressure_max_kpa=params["pressure_max_kpa"],
                    num_points=int(params["num_points"]),
                )

            for x, y in zip(xs, ys):
                name = f"{metric_prefix}_{x:.4f}"
                db.add(
                    ResultMetric(
                        business_id=f"{run.business_id}-{name}",
                        simulation_run_id=run.id,
                        name=name,
                        value=y,
                        unit=y_unit,
                        created_by="mech-model-worker",
                    )
                )

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
