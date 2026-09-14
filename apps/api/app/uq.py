"""Uncertainty quantification (§SL-03 lite): seeded Latin-Hypercube Monte
Carlo over a variant's prediction-model inputs.

The physics comes from the mech worker's own analytical model
(`apps/workers/mech-model/fs_model.py`) — loaded here by file path so the
math has exactly one source of truth. That module imports only numpy, which
the API venv already ships.

Same seed + same inputs ⇒ identical results (MV-05). Distributions come from
the caller and carry their `source`; the API never invents material numbers
or tolerances (지시서 금지 #1).
"""

import importlib.util
import math
from pathlib import Path

import numpy as np

_MECH_FS_MODEL_PATH = (
    Path(__file__).resolve().parents[2] / "workers" / "mech-model" / "fs_model.py"
)

# metric extractor per model_type: (metric_name, unit, fn(samples) -> float)
_MODEL_FUNCS = {
    "fs_dome": ("peak_force_mN", "mN"),
    "detent_torque": ("peak_torque_mNm", "mN·m"),
    "bridge_transfer": ("fullscale_output_mv", "mV"),
}


def _load_fs_model():
    if not _MECH_FS_MODEL_PATH.exists():
        raise RuntimeError(f"mech model module not found at {_MECH_FS_MODEL_PATH}")
    spec = importlib.util.spec_from_file_location("alps_mech_fs_model", _MECH_FS_MODEL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def supported_model_types() -> list[str]:
    return list(_MODEL_FUNCS)


def metric_for(model_type: str) -> tuple[str, str]:
    return _MODEL_FUNCS[model_type]


def _sample_input(rng: np.random.Generator, distribution: str, params: dict, n: int) -> np.ndarray:
    """LHS stratified samples: one draw per stratum of [0,1), shuffled, then
    transformed through the distribution's inverse CDF."""
    u = (rng.permutation(n) + rng.random(n)) / n
    if distribution == "uniform":
        lo, hi = float(params["min"]), float(params["max"])
        return lo + (hi - lo) * u
    if distribution == "triangular":
        lo, mode, hi = float(params["min"]), float(params["mode"]), float(params["max"])
        # inverse CDF of the triangular distribution
        fc = (mode - lo) / (hi - lo)
        return np.where(
            u < fc,
            lo + np.sqrt(u * (hi - lo) * (mode - lo)),
            hi - np.sqrt((1 - u) * (hi - lo) * (hi - mode)),
        )
    if distribution == "normal":
        mean, sd = float(params["mean"]), float(params["sd"])
        if sd <= 0:
            raise ValueError("normal distribution needs sd > 0")
        return mean + sd * _probit(u)
    raise ValueError(f"unsupported distribution: {distribution}")


def _probit(u: np.ndarray) -> np.ndarray:
    """Inverse standard-normal CDF via the Acklam approximation — scipy is
    not an API dependency."""
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    u = np.clip(u, 1e-7, 1 - 1e-7)
    low = u < 0.02425
    high = u > 1 - 0.02425
    central = ~(low | high)
    x = np.empty_like(u)
    uu = u[central]
    q = uu - 0.5
    r = q * q
    x[central] = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    )
    uu = u[low]
    q = np.sqrt(-2 * np.log(uu))
    x[low] = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    )
    uu = u[high]
    q = np.sqrt(-2 * np.log(1 - uu))
    x[high] = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    )
    return x


def run_lhs_monte_carlo(
    model_type: str,
    inputs: list[dict],
    n_samples: int,
    seed: int,
    target_band: dict,
) -> dict:
    """Sample the inputs, evaluate the prediction model, summarize the metric
    distribution and the probability of falling outside `target_band`."""
    module = _load_fs_model()
    metric_name, metric_unit = _MODEL_FUNCS[model_type]
    n = int(n_samples)
    rng = np.random.default_rng(seed)

    columns = {
        inp["name"]: _sample_input(rng, inp["distribution"], inp.get("params") or {}, n)
        for inp in inputs
    }

    if model_type == "fs_dome":
        ys = np.array([module.predict_fs_curve(float(columns["dome_thickness_mm"][i]),
                                               float(columns["dome_diameter_mm"][i]))[1] for i in range(n)])
        metric = ys.max(axis=1)
    elif model_type == "detent_torque":
        ys = np.array([module.predict_detent_curve(int(round(columns["detent_count"][i])),
                                                   float(columns["peak_torque_mNm"][i]))[1] for i in range(n)])
        metric = ys.max(axis=1)
    else:  # bridge_transfer
        ys = np.array([module.predict_bridge_transfer(float(columns["supply_voltage_v"][i]),
                                                      float(columns["sensitivity_mv_per_v_per_kpa"][i]))[1]
                       for i in range(n)])
        metric = ys.max(axis=1)

    band_min, band_max = float(target_band["min"]), float(target_band["max"])
    violations = (metric < band_min) | (metric > band_max)

    # All summary values are plain Python floats — numpy scalars must never
    # reach SQLAlchemy JSONB columns (see AGENTS.md M4 gotcha).
    hist_edges = np.linspace(float(metric.min()), float(metric.max()), 21)
    counts, _ = np.histogram(metric, bins=hist_edges)
    pct = lambda q: float(np.percentile(metric, q))  # noqa: E731
    return {
        "mean": float(metric.mean()),
        "sd": float(metric.std(ddof=1)) if n > 1 else 0.0,
        "p05": pct(5),
        "p50": pct(50),
        "p95": pct(95),
        "min": float(metric.min()),
        "max": float(metric.max()),
        "hist": {"bin_edges": [float(e) for e in hist_edges], "counts": [int(c) for c in counts]},
        "violation_prob": float(violations.mean()),
        "violation_count": int(violations.sum()),
        "target_band": {"min": band_min, "max": band_max, "unit": target_band.get("unit", metric_unit)},
    }


def sensitivity_ranking(inputs: list[dict], n_samples: int, seed: int, model_type: str) -> list[dict]:
    """Cheap one-at-a-time sensitivity: for each input, the metric range when
    sweeping that input alone across its distribution support (others at
    nominal). Returns a normalized 0..1 share per input — indicative only."""
    module = _load_fs_model()
    _, base = _MODEL_FUNCS[model_type]
    lows, highs = [], []
    for inp in inputs:
        p = inp.get("params") or {}
        if inp["distribution"] == "uniform":
            lo, hi = float(p["min"]), float(p["max"])
        elif inp["distribution"] == "triangular":
            lo, hi = float(p["min"]), float(p["max"])
        else:  # normal: ±3σ
            lo, hi = float(p["mean"]) - 3 * float(p["sd"]), float(p["mean"]) + 3 * float(p["sd"])
        lows.append(lo)
        highs.append(hi)
    nominal = [math.sqrt(lo * hi) if lo > 0 else (lo + hi) / 2 for lo, hi in zip(lows, highs)]
    names = [inp["name"] for inp in inputs]

    def evaluate(values: list[float]) -> float:
        kwargs = dict(zip(names, values))
        if model_type == "fs_dome":
            return float(max(module.predict_fs_curve(kwargs["dome_thickness_mm"], kwargs["dome_diameter_mm"])[1]))
        if model_type == "detent_torque":
            return float(max(module.predict_detent_curve(int(round(kwargs["detent_count"])), kwargs["peak_torque_mNm"])[1]))
        return float(max(module.predict_bridge_transfer(kwargs["supply_voltage_v"], kwargs["sensitivity_mv_per_v_per_kpa"])[1]))

    base_value = evaluate(nominal)
    spread: dict[str, float] = {}
    for i, name in enumerate(names):
        low_vals = list(nominal)
        high_vals = list(nominal)
        low_vals[i] = lows[i]
        high_vals[i] = highs[i]
        spread[name] = abs(evaluate(high_vals) - evaluate(low_vals))
    total = sum(spread.values()) or 1.0
    return [
        {"name": name, "share": round(s / total, 3), "unit": base}
        for name, s in sorted(spread.items(), key=lambda kv: -kv[1])
    ]
