import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from temporalio import activity

from fs_model import (
    derive_asic_gesture_summary,
    predict_bridge_transfer,
    predict_detent_curve,
    predict_fs_curve,
    predict_proximity_capacitance,
)

TOOL_VERSION = "analytical-mech-model-v2"

# One default set per model_type; a run's own parameters override these.
# model_type also picks the metric naming family — the correlation API
# (app/correlation.py) parses the same prefixes, so the two lists must stay
# in sync:
#   fs_dome               → force_mN_at_x_<x>       (mm, mN)   [tact switch]
#   detent_torque         → torque_mNm_at_deg_<x>   (deg, mN·m) [rotary encoder]
#   bridge_transfer       → vout_mv_at_kpa_<x>      (kPa, mV)  [MEMS pressure sensor]
#   proximity_capacitance → delta_c_fF_at_d_<x>     (mm, fF)   [AirInput proximity sensor]
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
    "proximity_capacitance": {
        "electrode_area_mm2": 100.0,
        "cover_thickness_mm": 1.0,
        "cover_dielectric_constant": 4.0,
        "is_glove": False,
        "distance_min_mm": 0.0,
        "distance_max_mm": 40.0,
        "num_points": 21,
        # ASIC behavioral stand-in (§IF-03) — see fs_model.derive_asic_gesture_summary.
        "gain_counts_per_fF": 50.0,
        "offset_counts": 200.0,
        "threshold_counts": 260.0,
    },
}

# model_type → (metric prefix, y_unit)
MODEL_METRICS = {
    "fs_dome": ("force_mN_at_x", "mN"),
    "detent_torque": ("torque_mNm_at_deg", "mN·m"),
    "bridge_transfer": ("vout_mv_at_kpa", "mV"),
    "proximity_capacitance": ("delta_c_fF_at_d", "fF"),
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
            elif model_type == "bridge_transfer":
                xs, ys = predict_bridge_transfer(
                    supply_voltage_v=params["supply_voltage_v"],
                    sensitivity_mv_per_v_per_kpa=params["sensitivity_mv_per_v_per_kpa"],
                    pressure_min_kpa=params["pressure_min_kpa"],
                    pressure_max_kpa=params["pressure_max_kpa"],
                    num_points=int(params["num_points"]),
                )
            else:  # proximity_capacitance
                xs, ys = predict_proximity_capacitance(
                    electrode_area_mm2=params["electrode_area_mm2"],
                    cover_thickness_mm=params["cover_thickness_mm"],
                    cover_dielectric_constant=params["cover_dielectric_constant"],
                    is_glove=bool(params["is_glove"]),
                    distance_min_mm=params["distance_min_mm"],
                    distance_max_mm=params["distance_max_mm"],
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

            if model_type == "proximity_capacitance":
                # ASIC behavioral + threshold gesture-decision summary
                # (§IF-03/IF-04 stand-in) — a couple of bonus named metrics
                # alongside the swept ΔC curve, same pattern as the SPICE
                # worker's worst_case_logic_low_margin next to v_out_rc_*.
                summary = derive_asic_gesture_summary(
                    xs,
                    ys,
                    gain_counts_per_fF=params["gain_counts_per_fF"],
                    offset_counts=params["offset_counts"],
                    threshold_counts=params["threshold_counts"],
                )
                db.add(
                    ResultMetric(
                        business_id=f"{run.business_id}-max-reliable-distance",
                        simulation_run_id=run.id,
                        name="max_reliable_distance_mm",
                        value=summary["max_reliable_distance_mm"],
                        unit="mm",
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
