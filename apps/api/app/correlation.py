"""Predicted-vs-measured correlation (§5.3). Runs synchronously in the API
request — unlike CAD/SPICE/mech-model this is cheap arithmetic, not a job
worth a Temporal workflow (§8.3: "PoC 과설계 방지")."""

import numpy as np

# Metric naming contract per mech model_type (apps/workers/mech-model/
# activities.py MODEL_METRICS — keep the two tables in sync). Each prefix
# carries the (x_unit, y_unit) pair its curve is expressed in; a run must
# contain exactly one curve family and its measurements must use the same
# units.
CURVE_FAMILIES: dict[str, tuple[str, str]] = {
    "force_mN_at_x": ("mm", "mN"),  # fs_dome (tact switch F–S curve)
    "torque_mNm_at_deg": ("deg", "mN·m"),  # detent_torque (rotary encoder)
    "vout_mv_at_kpa": ("kPa", "mV"),  # bridge_transfer (MEMS pressure sensor)
}


def extract_predicted_curve(metrics: list) -> tuple[np.ndarray, np.ndarray, str, str]:
    """Parse a simulation run's curve metrics into (xs, ys, x_unit, y_unit)."""
    points: list[tuple[float, float]] = []
    family: str | None = None
    for m in metrics:
        for prefix in CURVE_FAMILIES:
            if not m.name.startswith(f"{prefix}_"):
                continue
            if family is not None and family != prefix:
                raise ValueError(
                    f"simulation run mixes curve metric families {family!r} and {prefix!r}"
                )
            family = prefix
            points.append((float(m.name[len(prefix) + 1 :]), m.value))
            break
    if family is None:
        raise ValueError(
            "simulation run has no curve metrics "
            f"({' / '.join(f'{p}_*' for p in CURVE_FAMILIES)}) to correlate against"
        )
    points.sort()
    xs, ys = (np.array(a) for a in zip(*points))
    x_unit, y_unit = CURVE_FAMILIES[family]
    return xs, ys, x_unit, y_unit


def compute_correlation(pred_x: np.ndarray, pred_y: np.ndarray, meas_x: np.ndarray, meas_y: np.ndarray) -> dict:
    order = np.argsort(meas_x)
    meas_x, meas_y = meas_x[order], meas_y[order]

    overlap_min = max(pred_x.min(), meas_x.min())
    overlap_max = min(pred_x.max(), meas_x.max())
    if overlap_min >= overlap_max:
        raise ValueError(
            f"predicted range [{pred_x.min()}, {pred_x.max()}] and measured range "
            f"[{meas_x.min()}, {meas_x.max()}] do not overlap"
        )

    mask = (pred_x >= overlap_min) & (pred_x <= overlap_max)
    eval_x = pred_x[mask]
    eval_pred_y = pred_y[mask]
    eval_meas_y = np.interp(eval_x, meas_x, meas_y)

    errors = eval_pred_y - eval_meas_y
    rmse = float(np.sqrt(np.mean(errors**2)))
    mae = float(np.mean(np.abs(errors)))
    max_error = float(np.max(np.abs(errors)))
    correlation_coefficient = (
        float(np.corrcoef(eval_pred_y, eval_meas_y)[0, 1]) if len(eval_x) >= 2 else float("nan")
    )

    # §5.3: predicted points outside what the measurement actually covered
    # are extrapolation, not validated prediction — flag it.
    predicted_range = pred_x.max() - pred_x.min()
    covered_fraction = (overlap_max - overlap_min) / predicted_range if predicted_range > 0 else 1.0
    extrapolation_warning = bool(covered_fraction < 0.9)

    return {
        "rmse": rmse,
        "mae": mae,
        "max_error": max_error,
        "correlation_coefficient": correlation_coefficient,
        "extrapolation_warning": extrapolation_warning,
        "overlap_x_min": float(overlap_min),
        "overlap_x_max": float(overlap_max),
    }
