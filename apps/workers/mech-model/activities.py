import sys
from dataclasses import replace
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

# Per-model-type tool provenance (§6.2: every result card shows the tool
# version that produced it — a field-solver result must never display the
# analytic model's version string and vice versa).
MODEL_TOOL_VERSIONS = {
    "electrostatic_field": "fd-electrostatic-solver-v1",
    "surrogate_train": "surrogate-rbf-trainer-v1",
    "sensitivity_volume": "sensitivity-volume-v1",
    "algorithm_replay": "asic-algo-replay-v1",
}

# One default set per model_type; a run's own parameters override these.
# The legacy model_types also pick the metric naming family — the
# correlation API (app/correlation.py) parses the same prefixes, so the two
# lists must stay in sync (4-place contract):
#   fs_dome               → force_mN_at_x_<x>       (mm, mN)   [tact switch]
#   detent_torque         → torque_mNm_at_deg_<x>   (deg, mN·m) [rotary encoder]
#   bridge_transfer       → vout_mv_at_kpa_<x>      (kPa, mV)  [MEMS pressure sensor]
#   proximity_capacitance → delta_c_fF_at_d_<x>     (mm, fF)   [AirInput P1 slice]
#
# The NEW field-twin model types do NOT ride the legacy dispatch: only
# electrostatic_field emits a correlation-compatible curve (same
# delta_c_fF_at_d family — no contract change), while surrogate_train /
# sensitivity_volume / algorithm_replay write their own named metrics and
# JSON artifacts. Their real output is the artifact, not metric rows.
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
    # --- AirInput 3D Interaction Field Twin (§6.2 two-tier architecture) ---
    "electrostatic_field": {
        "electrode_area_mm2": 100.0,
        "cover_thickness_mm": 1.0,
        "cover_dielectric_constant": 4.0,
        "split_ring": False,
        "is_glove": False,
        "distance_min_mm": 0.0,
        "distance_max_mm": 40.0,
        "num_points": 13,
        "cell_mm": 1.0,  # production resolution — grid study in field_model docstring
    },
    "surrogate_train": {
        "electrode_area_mm2": 100.0,
        "cover_thickness_mm": 1.0,
        "cover_dielectric_constant": 4.0,
        "split_ring": False,
        "cell_mm": 1.0,
    },
    # Sensitivity volume consumes the PROMOTED surrogate payload (embedded by
    # the seed script from the surrogate_train run's artifact) — the volume
    # grid is surrogate-tier by construction and labeled as such.
    "sensitivity_volume": {
        "surrogate_payload": None,  # required
    },
    # Replay consumes the scenario catalog + one tier input, also embedded:
    # surrogate_payload for surrogate-engine scenarios, curve/distance for
    # sweep_interp, geometry for solver.
    "algorithm_replay": {
        "scenario_id": None,  # required
        "surrogate_payload": None,
        "curve": None,  # {"distance_mm": [...], "delta_c_fF": [...]} for sweep_interp
        "geometry": None,  # solver-engine geometry overrides (ground_plate etc.)
    },
}

# model_type → (metric prefix, y_unit) — CURVE-emitting types ONLY. The
# correlation API parses these prefixes against CURVE_FAMILIES; a name
# collision or a missing entry here breaks the 4-place contract (worker /
# correlation / lib/curve.ts / i18n). Non-curve types must never emit
# metric names starting with one of these prefixes.
CURVE_METRICS = {
    "fs_dome": ("force_mN_at_x", "mN"),
    "detent_torque": ("torque_mNm_at_deg", "mN·m"),
    "bridge_transfer": ("vout_mv_at_kpa", "mV"),
    "proximity_capacitance": ("delta_c_fF_at_d", "fF"),
    "electrostatic_field": ("delta_c_fF_at_d", "fF"),  # same family — no contract change
}


def _field_geometry(params: dict):
    from field_model import GeometrySpec

    ground_plate = params.get("ground_plate")
    if ground_plate is not None and len(ground_plate) == 5:
        ground_plate = tuple(float(v) for v in ground_plate)
    return GeometrySpec(
        electrode_area_mm2=float(params["electrode_area_mm2"]),
        cover_thickness_mm=float(params["cover_thickness_mm"]),
        cover_eps_r=float(params["cover_dielectric_constant"]),
        split_ring=bool(params.get("split_ring", False)),
        ground_plate=ground_plate,
    )


def _named_metric(db, run, name: str, value, unit: str) -> None:
    from app.models.simulation import ResultMetric

    db.add(
        ResultMetric(
            business_id=f"{run.business_id}-{name}",
            simulation_run_id=run.id,
            name=name,
            value=value,
            unit=unit,
            created_by="mech-model-worker",
        )
    )


@activity.defn(name="run_mech_model_activity")
def run_mech_model_activity(simulation_run_id: str) -> None:
    from sqlalchemy.orm import Session

    from app.db import engine
    from app.models.simulation import ResultMetric, RunStatus, SimulationRun

    with Session(bind=engine) as db:
        run = db.get(SimulationRun, simulation_run_id)
        if run is None:
            raise ValueError(f"simulation_run {simulation_run_id} not found")

        params = dict(run.parameters or {})
        model_type = params.pop("model_type", "fs_dome")
        defaults = MODEL_DEFAULTS.get(model_type)
        if defaults is None:
            raise ValueError(
                f"unknown model_type {model_type!r} "
                f"(expected one of {sorted(MODEL_DEFAULTS)})"
            )
        params = {**defaults, **params}

        run.status = RunStatus.RUNNING
        run.started_at = datetime.now(timezone.utc)
        run.tool_version = MODEL_TOOL_VERSIONS.get(model_type, TOOL_VERSION)
        db.commit()

        try:
            curve_family = CURVE_METRICS.get(model_type)
            xs: list | None = None
            ys: list | None = None

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
            elif model_type == "proximity_capacitance":
                xs, ys = predict_proximity_capacitance(
                    electrode_area_mm2=params["electrode_area_mm2"],
                    cover_thickness_mm=params["cover_thickness_mm"],
                    cover_dielectric_constant=params["cover_dielectric_constant"],
                    is_glove=bool(params["is_glove"]),
                    distance_min_mm=params["distance_min_mm"],
                    distance_max_mm=params["distance_max_mm"],
                    num_points=int(params["num_points"]),
                )
            elif model_type == "electrostatic_field":
                xs, ys = run_field_curve(db, run, params)
            elif model_type == "surrogate_train":
                run_surrogate_train(db, run, params)
            elif model_type == "sensitivity_volume":
                run_sensitivity_volume(db, run, params)
            elif model_type == "algorithm_replay":
                run_algorithm_replay(db, run, params)

            if curve_family is not None and xs is not None:
                metric_prefix, y_unit = curve_family
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
                    _named_metric(
                        db, run, "max_reliable_distance_mm", summary["max_reliable_distance_mm"], "mm"
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


def _input_version(db, run):
    from app.models.artifact import ArtifactVersion

    if run.input_artifact_version_id is None:
        return None
    return db.get(ArtifactVersion, run.input_artifact_version_id)


def run_field_curve(db, run, params: dict) -> None:
    """electrostatic_field — FD solver ΔC(d) curve + field-grid artifact.

    Emits the SAME delta_c_fF_at_d curve family as the P1 analytic model
    (the correlation flow works unchanged), but every number comes from the
    discretized Laplace solve; the artifact carries the potential slice the
    web renders as the field heatmap.
    """
    import numpy as np

    from artifacts import write_run_artifact
    from field_model import GeometrySpec, FingerState, delta_c_self_fF, predict_field_curve, solve_potential, build_environment

    geom = _field_geometry(params)
    xs, ys = predict_field_curve(
        electrode_area_mm2=float(params["electrode_area_mm2"]),
        cover_thickness_mm=float(params["cover_thickness_mm"]),
        cover_eps_r=float(params["cover_dielectric_constant"]),
        split_ring=bool(params["split_ring"]),
        is_glove=bool(params["is_glove"]),
        distance_min_mm=float(params["distance_min_mm"]),
        distance_max_mm=float(params["distance_max_mm"]),
        num_points=int(params["num_points"]),
        cell_mm=float(params["cell_mm"]),
    )

    # Per-channel split + potential slice from one representative solve
    # (touch pose, bare, center) — the visualization payload.
    cell_mm = float(params["cell_mm"])
    baseline_cache: dict = {}
    per_ch, sol = delta_c_self_fF(
        geom, FingerState(0.0, 0.0, 0.0, bool(params["is_glove"])), cell_mm, baseline_cache,
        want_potential_slice=True,
    )
    env = build_environment(geom, cell_mm)
    base = solve_potential(env, None)

    payload = {
        "schema": "airinput.field-grid.v1",
        "tier": "solver",
        "disclosure": (
            "3D finite-difference Laplace solve (red-black SOR) over "
            "idealized geometry with DISCLOSED illustrative constants — "
            "not validated against a commercial FEM/BEM solver; correlation "
            "numbers from this run are pipeline checks, never accuracy "
            "claims (지시서 §13)."
        ),
        "layout": geom.layout,
        "cell_mm": cell_mm,
        "grid_shape": list(sol.grid_shape),
        "baseline_sweeps": base.sweeps,
        "baseline_converged": base.converged,
        "curve": {
            "distance_mm": [round(float(x), 4) for x in xs],
            "delta_c_total_fF": [round(float(y), 6) for y in ys],
        },
        "touch_pose_channels_fF": per_ch,
        "potential_slice_y_mid": sol.potential_slice,
        "slice_note": "electric potential [V] on the y=0 plane at the touch pose; downsampled for transport",
    }
    version = write_run_artifact(
        db, run, _input_version(db, run), payload, "field-grid.json",
        MODEL_TOOL_VERSIONS["electrostatic_field"],
    )
    run.output_artifact_version_id = version.id

    _named_metric(db, run, "field_touch_delta_c_fF", float(sum(per_ch.values())), "fF")
    _named_metric(db, run, "field_cell_mm", cell_mm, "mm")
    _named_metric(db, run, "field_solver_converged", 1 if sol.converged else 0, "flag")
    # Largest gap where the FD signal still clears the P1 legacy threshold —
    # computed with the LEGACY ASIC config for cross-tier comparability only.
    # The field-twin runs don't carry the legacy count keys (they're the
    # proximity_capacitance defaults), so fall back explicitly.
    legacy = MODEL_DEFAULTS["proximity_capacitance"]
    counts = (
        float(params.get("offset_counts", legacy["offset_counts"]))
        + float(params.get("gain_counts_per_fF", legacy["gain_counts_per_fF"])) * np.asarray(ys)
    )
    idx = np.flatnonzero(counts >= float(params.get("threshold_counts", legacy["threshold_counts"])))
    _named_metric(
        db, run, "field_max_reliable_distance_legacy_mm", float(xs[int(idx[-1])]) if idx.size else 0.0, "mm"
    )
    # Hand the swept curve back to the generic writer above, which emits the
    # delta_c_fF_at_d_* rows the correlation flow (extract_predicted_curve)
    # parses — the docstring contract this function previously dropped.
    return xs, ys


def run_surrogate_train(db, run, params: dict) -> None:
    """surrogate_train — DOE the FD solver, fit RBF, emit TS-parity payload."""
    from artifacts import write_run_artifact
    from surrogate import train_surrogates

    geom = _field_geometry(params)
    payload = train_surrogates(
        geom,
        cell_mm=float(params["cell_mm"]),
        progress=lambda i, n, p: activity.heartbeat(
            {"doe_progress": i, "doe_total": n, "pose": [p.x_mm, p.y_mm, p.gap_mm]}
        ),
    )
    version = write_run_artifact(
        db, run, _input_version(db, run), payload, "surrogate.json",
        MODEL_TOOL_VERSIONS["surrogate_train"],
    )
    run.output_artifact_version_id = version.id

    for ch, m in payload["channels"].items():
        _named_metric(db, run, f"surrogate_holdout_rmse_{ch.lower()}_ff", m["holdout"]["rmse_fF"], "fF")
        _named_metric(db, run, f"surrogate_holdout_mae_{ch.lower()}_ff", m["holdout"]["mae_fF"], "fF")
    _named_metric(db, run, "surrogate_n_train", payload["doe"]["n_bare"] + payload["doe"]["n_glove"], "count")


def run_sensitivity_volume(db, run, params: dict) -> None:
    """sensitivity_volume — dense surrogate-tier 3D detect/no-detect grid.

    The 감지영역/Dead Zone overlay's data source: ΔC over a dense pose grid
    evaluated on the PROMOTED surrogate (embedded payload), compared against
    the ASIC-derived ΔC thresholds (provenance rule — never invented fF).
    """
    import numpy as np

    from artifacts import write_run_artifact
    from signal_chain import DEFAULT_FIELD_ASIC
    from surrogate import eval_surrogate

    payload = params.get("surrogate_payload")
    if not payload:
        raise ValueError("sensitivity_volume requires parameters.surrogate_payload")

    cfg = DEFAULT_FIELD_ASIC
    near_dc = cfg.dc_threshold_fF(cfg.near_threshold_counts)
    touch_dc = (
        cfg.dc_threshold_fF(cfg.touch_threshold_counts)
        if cfg.touch_threshold_counts is not None
        else None
    )

    xs = [round(float(v), 3) for v in np.linspace(-20.0, 20.0, 17)]
    ys = [round(float(v), 3) for v in np.linspace(-16.0, 16.0, 13)]
    gaps = [round(float(v), 3) for v in np.linspace(0.0, 28.0, 8)]

    dc_flat: list[float] = []
    near_mask: list[int] = []
    touch_mask: list[int] = []
    center_near_gap = 0.0
    center_touch_gap = 0.0
    for gap in gaps:
        for y in ys:
            for x in xs:
                ch = eval_surrogate(payload, x, y, gap, False)
                dc = float(sum(ch.values()))
                dc_flat.append(dc)
                near_mask.append(1 if dc >= near_dc else 0)
                touch_mask.append(1 if touch_dc is not None and dc >= touch_dc else 0)

    def center_boundary(mask: list[int]) -> float:
        # along the center column (x≈0, y≈0), the largest gap still detected
        best = 0.0
        xi = min(range(len(xs)), key=lambda k: abs(xs[k]))
        yi = min(range(len(ys)), key=lambda k: abs(ys[k]))
        for gi, gap in enumerate(gaps):
            i = (gi * len(ys) + yi) * len(xs) + xi
            if mask[i]:
                best = float(gap)
        return best

    center_near_gap = center_boundary(near_mask)
    center_touch_gap = center_boundary(touch_mask)

    vol_payload = {
        "schema": "airinput.sensitivity-volume.v1",
        "tier": "surrogate",
        "disclosure": (
            "감지영역 grid evaluated on the RBF surrogate (NOT the reference "
            "solver) — interactive visualization tier. Thresholds derived "
            "from the ASIC counts config; near "
            f"{round(near_dc, 6)} fF / touch {round(touch_dc, 6) if touch_dc else None} fF."
        ),
        "axes": {"x_mm": xs, "y_mm": ys, "gap_mm": gaps},
        "delta_c_fF": [round(v, 6) for v in dc_flat],
        "detect_near": near_mask,
        "detect_touch": touch_mask,
        "thresholds_fF": {"near": round(near_dc, 6), "touch": round(touch_dc, 6) if touch_dc else None},
        "asic_config": cfg.as_payload(),
        "layout_note": "flat arrays, x-major within y within gap (gap outer)",
        "center_detection_gap_mm": {"near": round(center_near_gap, 3), "touch": round(center_touch_gap, 3)},
    }
    version = write_run_artifact(
        db, run, _input_version(db, run), vol_payload, "sensitivity-volume.json",
        MODEL_TOOL_VERSIONS["sensitivity_volume"],
    )
    run.output_artifact_version_id = version.id

    _named_metric(db, run, "volume_detect_fraction", sum(near_mask) / len(near_mask), "ratio")
    _named_metric(db, run, "volume_center_near_gap_mm", round(center_near_gap, 3), "mm")
    _named_metric(db, run, "volume_center_touch_gap_mm", round(center_touch_gap, 3), "mm")


def run_algorithm_replay(db, run, params: dict) -> None:
    """algorithm_replay — GOLD scenario through ASIC chain + both algorithms."""
    import numpy as np

    from artifacts import write_run_artifact
    from field_model import FingerState, delta_c_self_fF
    from scenarios import scenario_by_id
    from signal_chain import DEFAULT_FIELD_ASIC, run_replay
    from surrogate import eval_surrogate, is_ood

    scenario_id = params.get("scenario_id")
    if not scenario_id:
        raise ValueError("algorithm_replay requires parameters.scenario_id")
    # the layout picks scenario details too (GOLD-04's IDLE hold gap differs
    # between the solid pad and the split ring)
    scenario = scenario_by_id(scenario_id, split_ring=bool(params.get("split_ring")))
    seed = int(scenario.get("seed", 20260914))
    cfg = DEFAULT_FIELD_ASIC
    overrides = scenario.get("asic_overrides")
    if overrides:
        cfg = replace(DEFAULT_FIELD_ASIC, **overrides)

    engine = scenario["engine"]
    ticks = scenario["ticks"]
    ood_eval = None

    if engine == "surrogate":
        payload = params.get("surrogate_payload")
        if not payload:
            raise ValueError(f"{scenario_id} (surrogate engine) requires parameters.surrogate_payload")

        def dc_eval(t):
            return eval_surrogate(payload, t["x_mm"], t["y_mm"], t["gap_mm"], t["is_glove"])

        ood_eval = lambda t: is_ood(t["x_mm"], t["y_mm"], t["gap_mm"])  # noqa: E731
    elif engine == "solver":
        geometry = {**(params.get("geometry") or {}), "split_ring": params.get("split_ring", False)}
        geom = _field_geometry({**geometry, "electrode_area_mm2": params["electrode_area_mm2"],
                                "cover_thickness_mm": params["cover_thickness_mm"],
                                "cover_dielectric_constant": params["cover_dielectric_constant"]})
        cache: dict = {}

        def dc_eval(t):
            dc, _ = delta_c_self_fF(
                geom, FingerState(t["x_mm"], t["y_mm"], t["gap_mm"], t["is_glove"]),
                float(params.get("cell_mm", 1.0)), cache,
            )
            activity.heartbeat({"scenario": scenario_id, "tick_done": dc_eval.solve_idx})
            dc_eval.solve_idx += 1  # type: ignore[attr-defined]
            return dc

        dc_eval.solve_idx = 0  # type: ignore[attr-defined]
    elif engine == "sweep_interp":
        curve = params.get("curve")
        if not curve:
            raise ValueError(f"{scenario_id} (sweep_interp engine) requires parameters.curve")
        if any(abs(t["x_mm"]) > 1e-9 or abs(t["y_mm"]) > 1e-9 for t in ticks):
            raise ValueError("sweep_interp is a center-only tier — scenario has lateral offsets")
        dist = np.asarray(curve["distance_mm"], dtype=float)
        vals = np.asarray(curve["delta_c_fF"], dtype=float)

        def dc_eval(t):
            return {"E1": float(np.interp(t["gap_mm"], dist, vals))}
    else:
        raise ValueError(f"unknown engine {engine!r}")

    result = run_replay(scenario, engine, dc_eval, cfg=cfg, seed=seed, ood_eval=ood_eval)
    result["variant_parameters_note"] = {
        k: params.get(k) for k in ("electrode_area_mm2", "cover_thickness_mm", "cover_dielectric_constant", "split_ring")
    }
    version = write_run_artifact(
        db, run, _input_version(db, run), result, "replay.json",
        MODEL_TOOL_VERSIONS["algorithm_replay"],
    )
    run.output_artifact_version_id = version.id

    sid = scenario_id.split("-")[0] + "-" + scenario_id.split("-")[1]  # e.g. "GOLD-01"
    _named_metric(db, run, f"replay_{sid.lower()}_v1_false_triggers", result["actual"]["v1"]["false_trigger_ticks"], "count")
    _named_metric(db, run, f"replay_{sid.lower()}_v2_false_triggers", result["actual"]["v2"]["false_trigger_ticks"], "count")
    _named_metric(db, run, f"replay_{sid.lower()}_v2_first_detect_tick", result["actual"]["v2"]["first_nonidle_tick"] if result["actual"]["v2"]["first_nonidle_tick"] is not None else -1, "tick")
    _named_metric(db, run, f"replay_{sid.lower()}_pass", 1 if result["pass"] else 0, "flag")
