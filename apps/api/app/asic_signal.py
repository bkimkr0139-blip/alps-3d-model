"""Deterministic mixed-signal chain evaluation for EPIC A (지시서 §4).

An EDUCATIONAL transfer model, not physics: the chain output is the sensor
block's nominal value propagated through each block's declared error budget
(offset/gain/noise/drift), sampled per corner temperature with a fixed seed
(지시서 §12: 회귀는 결정론적 시드). Source class stays SYNTHETIC and the tool
version says what it is — this must never be presented as SPICE/TCAD output
(지시서 §15: 브라우저 시각화는 시뮬레이션 툴을 대체하지 않는다).
"""

import hashlib
import math
import random

TOOL_VERSION = "asic-signal-chain-v1"

# Corner temperatures per AEC-Q100 grade — mirrors the frontend GRADE_TEMP.
GRADE_TEMP: dict[str, tuple[float, ...]] = {
    "G0": (-40.0, 25.0, 85.0, 150.0),
    "G1": (-40.0, 25.0, 85.0, 125.0),
    "G2": (-40.0, 25.0, 85.0, 105.0),
}
CORNERS = ("tt", "ff", "ss")  # typical / fast / slow — educational naming


def derive_seed(business_id: str) -> int:
    # signed 31-bit — PostgreSQL INTEGER range (unsigned hashes overflow it)
    return int.from_bytes(hashlib.sha256(business_id.encode()).digest()[:4], "big") % (2**31)


def _quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, round(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def evaluate_chain(
    blocks: list[dict],
    spec: list[dict],
    kind: str,
    n_draws: int,
    seed: int,
    template_grade: str = "G1",
) -> dict:
    """Sample the chain n_draws times per (corner × temperature) and score
    each spec output. Returns the result dict stored on CornerStudy.result.

    Each spec limit carries its own `nominal` (e.g. sensitivity 100 mA/A vs
    INL 1.0 LSB) — the block budgets are normalized against the sensor's
    nominal and re-scaled per output, so one sweep scores every output on its
    own scale.
    """

    rng = random.Random(seed)
    # total error scale = RMS sum of each block's declared budget components
    budget_sigma = 0.0
    budget_offset = 0.0
    sensor_nominal = None
    drift_per_c = 0.0
    calib_range: tuple[float, float] | None = None
    for b in blocks:
        eb = b.get("error_budget") or {}
        params = b.get("params") or {}
        if sensor_nominal is None and b.get("kind") == "sensor":
            sensor_nominal = float(params.get("nominal", 0.0)) or None
        if "calib_min" in params and "calib_max" in params:
            calib_range = (float(params["calib_min"]), float(params["calib_max"]))
        sigma = math.sqrt(
            sum(float(eb.get(k) or 0.0) ** 2 for k in ("offset", "gain_error", "inl", "dnl", "noise"))
        )
        budget_sigma = math.sqrt(budget_sigma**2 + sigma**2)
        budget_offset += float(eb.get("offset") or 0.0)
        drift_per_c += float(eb.get("drift") or 0.0)
    if sensor_nominal is None:
        sensor_nominal = (
            float((blocks[0].get("params") or {}).get("nominal", 0.0)) if blocks else 0.0
        ) or None

    # relative error model: budgets are declared in the sensor's units, so a
    # 1.2 LSB spread means something different for a 100 A reading and a 1 LSB
    # INL figure — express all as a fraction of nominal (or 2% fallback).
    denom = abs(sensor_nominal) if sensor_nominal else 1.0
    rel_sigma = budget_sigma / denom if sensor_nominal else 0.02
    rel_offset = budget_offset / denom if sensor_nominal else 0.0
    rel_drift = drift_per_c / denom if sensor_nominal else 0.0
    abs_floor = budget_sigma * 0.05  # keeps zero-centered outputs (offset) non-degenerate

    temps = GRADE_TEMP.get(template_grade, GRADE_TEMP["G1"])
    draw = 200 if kind == "corner" else max(100, n_draws)

    per_output = []
    any_ood = False
    ood_reasons: list[str] = []
    for limit in spec:
        out = limit.get("output", "out")
        center = float(limit.get("nominal") or sensor_nominal or 0.0)
        smin = limit.get("min")
        smax = limit.get("max")
        unit = limit.get("unit")
        samples: list[float] = []
        corners_summary = []
        for corner_idx, corner in enumerate(CORNERS):
            corner_scale = 1.0 + (corner_idx - 1) * 0.15  # ff wider, ss shifted — educational
            for temp in temps:
                # OOD: sampling temperature outside the model's calibrated range
                if calib_range and not (calib_range[0] <= temp <= calib_range[1]):
                    any_ood = True
                    reason = (
                        f"{out}: 시험 온도 {temp:g}°C 가 보정 범위 "
                        f"[{calib_range[0]:g}, {calib_range[1]:g}]°C를 벗어납니다"
                    )
                    if reason not in ood_reasons:
                        ood_reasons.append(reason)
                drift = center * rel_drift * (temp - 25.0)
                sigma_out = center * rel_sigma * corner_scale + abs_floor * corner_scale
                corner_vals = []
                for _ in range(draw):
                    v = (
                        center
                        + center * rel_offset * corner_scale
                        + drift
                        + rng.gauss(0.0, sigma_out)
                    )
                    corner_vals.append(v)
                    samples.append(v)
                corners_summary.append(
                    {
                        "corner": corner,
                        "temp_c": temp,
                        "mean": round(sum(corner_vals) / len(corner_vals), 4),
                    }
                )
        samples.sort()
        if smin is not None and smax is not None and smax > smin:
            violations = sum(1 for v in samples if v < smin or v > smax)
        else:
            violations = 0
        # display histogram over the pooled draws (24 bins) — lets the UI draw
        # the REAL sampled distribution instead of inventing one from quantiles
        lo, hi = samples[0], samples[-1]
        bw = (hi - lo) / 24 if hi > lo else 1.0
        counts = [0] * 24
        for v in samples:
            counts[min(23, max(0, int((v - lo) / bw)))] += 1
        per_output.append(
            {
                "output": out,
                "unit": unit,
                "nominal": center,
                "p50": round(_quantile(samples, 0.50), 4),
                "p95": round(_quantile(samples, 0.95), 4),
                "p99": round(_quantile(samples, 0.99), 4),
                "violation_rate": round(violations / len(samples), 6) if samples else 0.0,
                "spec_min": smin,
                "spec_max": smax,
                "corners": corners_summary,
                "hist": {"edges": [round(lo + i * bw, 4) for i in range(25)], "counts": counts},
            }
        )

    return {
        "per_output": per_output,
        "model_ood": any_ood,
        "ood_reason": ood_reasons,
        "n_draws_total": draw * len(CORNERS) * len(temps) * len(spec),
        "temperatures_c": list(temps),
        "disclosure": "교육용 오류예산 전파 모델 (SYNTHETIC) — SPICE/TCAD 대체 아님",
    }
