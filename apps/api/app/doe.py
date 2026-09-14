"""AN-04 DOE / optimization math: response-surface regression + candidate
ranking over already-persisted process-parameter vs. CTQ observations.

Runs synchronously in the API request — cheap numpy arithmetic on already-
computed/persisted data, not a job worth a Temporal workflow (§8.3 "PoC
과설계 방지"), same precedent as `app/correlation.py`.

Deliberately a degree-1 (linear) fit: FR-06 marks Bayesian Optimization
optional, and the demo process-twin dataset (a handful of production lots
per parameter) does not support a higher-order polynomial reliably — see
`fit_response_surface`'s minimum-observations guard. Kept pure/DB-free so it
can be unit tested against a synthetic dataset with a KNOWN linear
relationship (see tests/test_doe.py)."""

import numpy as np

MIN_OBSERVATIONS = 3


def fit_response_surface(xs: list[float], ys: list[float]) -> dict:
    """Least-squares linear fit ctq = slope * parameter + intercept.

    Raises ValueError if there isn't enough real data to fit anything
    meaningful (§7: never fabricate a coefficient from insufficient data) —
    fewer than MIN_OBSERVATIONS points, or the parameter never varied across
    the observed runs.
    """
    if len(xs) != len(ys):
        raise ValueError("xs and ys must be the same length")
    if len(xs) < MIN_OBSERVATIONS:
        raise ValueError(
            f"at least {MIN_OBSERVATIONS} process-run observations are required to fit a "
            f"response surface, found {len(xs)}"
        )
    x = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    if float(np.ptp(x)) <= 0:
        raise ValueError("the process parameter has no variance across observed runs — cannot fit a sensitivity trend")

    slope, intercept = (float(v) for v in np.polyfit(x, y, 1))

    r_squared = 0.0
    if float(np.std(y)) > 0:
        corr = float(np.corrcoef(x, y)[0, 1])
        if np.isfinite(corr):
            r_squared = corr**2

    if abs(slope) * float(np.ptp(x)) < 1e-9:
        direction = "flat"
    elif slope > 0:
        direction = "increasing"
    else:
        direction = "decreasing"

    return {
        "slope": slope,
        "intercept": intercept,
        "r_squared": r_squared,
        "direction": direction,
        "n_observations": len(xs),
    }


def predict(fit: dict, x: float) -> float:
    return fit["slope"] * x + fit["intercept"]


def candidate_grid(lo: float, hi: float, n: int) -> list[float]:
    """n evenly spaced hypothetical parameter *inputs* between lo and hi
    (inclusive). These are candidate settings to evaluate against the fitted
    surface, not measured/fabricated outputs — §7 only bans invented result
    numbers, not hypothetical inputs to a disclosed model."""
    if n < 2 or hi <= lo:
        return []
    step = (hi - lo) / (n - 1)
    return [lo + i * step for i in range(n)]


def rank_candidates(
    fit: dict,
    candidates_in: list[dict],
    *,
    window_min: float | None,
    window_max: float | None,
    target_min: float | None,
    target_max: float | None,
) -> list[dict]:
    """Evaluate + rank candidate parameter settings against the fitted
    surface (§FR-06 "후보안 비교"). `candidates_in`: [{"parameter_value",
    "source"}]. When a CTQ target band is supplied, candidates are ranked by
    (in-window first, meets-target first, closest to target center) — the
    ranking is a sort of already-computed numbers, never a solver picking a
    single "optimal" answer (§7 AN-04: AI가 단일 해를 임의 확정하지 않는다)."""
    target_center = (target_min + target_max) / 2.0 if target_min is not None and target_max is not None else None

    out = []
    for c in candidates_in:
        x = float(c["parameter_value"])
        y = predict(fit, x)
        in_window = True if window_min is None or window_max is None else (window_min <= x <= window_max)
        meets_target = None
        distance = None
        if target_min is not None and target_max is not None:
            meets_target = target_min <= y <= target_max
            distance = abs(y - target_center)
        out.append(
            {
                "parameter_value": x,
                "predicted_ctq": y,
                "in_window": bool(in_window),
                "meets_target": meets_target,
                "distance_to_target_center": distance,
                "source": c["source"],
            }
        )

    if target_center is not None:
        out.sort(key=lambda c: (not c["in_window"], not c["meets_target"], c["distance_to_target_center"]))
        for i, c in enumerate(out):
            c["rank"] = i + 1
    else:
        out.sort(key=lambda c: c["parameter_value"])
        for c in out:
            c["rank"] = None

    return out
