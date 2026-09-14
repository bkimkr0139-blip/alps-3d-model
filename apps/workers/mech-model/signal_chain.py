"""ASIC behavioral chain + detection algorithms + deterministic replay.

Bridges 지시서 ③ (ASIC 신호 ↔ 실제 알고리즘 판정) and ⑦ (테스트의 3D 시뮬레이션
구현 — the GOLD scenario replays). Everything here operates on a ΔC(t)
series produced by an engine (solver / surrogate / sweep_interp) and is
byte-for-byte deterministic for a fixed seed — replays are reproducible
evidence of pipeline behavior, never of sensor accuracy (지시서 §13).

Chain (disclosed behavioral model, illustrative constants):
    ΔC [fF] → offset+gain → +noise(σ, seeded) → 10-bit quantize+clip
            → 4-tap causal moving average → counts stream

v1_fixed_threshold — P1-compatible: absolute fixed thresholds, no baseline,
no debounce. With cfg=noiseless legacy (σ=0, no quantizer, MA=1, thresholds
= P1's) the detected sequence matches fs_model.derive_asic_gesture_summary
point-for-point (pytest-pinned). States: IDLE / NEAR / TOUCH (P1's binary
``detected`` ≡ NEAR∪TOUCH).

v2_baseline_hysteresis — EMA baseline + enter/exit hysteresis RELATIVE to
the baseline + 3-of-5 debounce per transition. The anti-chatter answer to
the noise scenario (GOLD-04): v1 false-triggers on noise spikes, v2 must
not — the money comparison the replay artifacts carry as expected/actual.

Threshold provenance rule: a ΔC threshold is ALWAYS derived from the ASIC
counts config as (threshold_counts − offset)/gain — thresholds are never
invented as free-floating fF numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

ADC_MAX_COUNTS = 1023.0  # 10-bit
TICK_PERIOD_S = 0.05  # 20 Hz scenario sampling (disclosed)

STATES = ("IDLE", "NEAR", "TOUCH")


@dataclass(frozen=True)
class AsicConfig:
    """Disclosed behavioral ASIC configuration (counts domain)."""

    gain_counts_per_fF: float
    offset_counts: float
    near_threshold_counts: float
    touch_threshold_counts: float | None  # None = binary chain (legacy P1)
    noise_sigma_counts: float = 0.0
    adc_bits: int | None = 10
    ma_taps: int = 4
    # v2 baseline/hysteresis/debounce parameters (counts domain). The NEAR
    # bands sit at ~3.6σ/1.6σ of the MA-attenuated noise (σ50 counts →
    # σ≈25 after the 4-tap MA) so 3-of-5 debounce + hysteresis stay silent
    # in the noise scenario while a real approach (+500 counts) commits
    # within a few ticks.
    ema_alpha: float = 0.15
    enter_near_counts: float = 90.0
    exit_near_counts: float = 40.0
    enter_touch_counts: float = 500.0  # v2 touch is ABSOLUTE (touch_threshold)
    exit_touch_counts: float = 250.0  # hold while ≥ touch_threshold − 250
    debounce_window: int = 5
    debounce_votes: int = 3

    def as_payload(self) -> dict:
        return asdict(self)

    def dc_threshold_fF(self, counts: float) -> float:
        """The provenance rule: ΔC threshold derived from counts config."""
        return (counts - self.offset_counts) / self.gain_counts_per_fF


# FD-driven runs: counts config chosen so the SOLVER's disclosed signal
# scale (touch ΔC ≈ 0.084 fF, gap 6.7 mm ≈ 0.006 fF) spans the ADC
# meaningfully — touch ≈ 856 counts vs 10-bit full scale 1023; NEAR trips
# around ~7 mm hover. σ=10 counts ≈ 1 ADC LSB-ish behavior noise.
DEFAULT_FIELD_ASIC = AsicConfig(
    gain_counts_per_fF=9000.0,
    offset_counts=100.0,
    near_threshold_counts=150.0,
    touch_threshold_counts=600.0,
    noise_sigma_counts=10.0,
)

# Legacy P1 equivalence config: EXACTLY fs_model's chain (float counts, no
# quantizer, no MA, no noise) with P1's seeded variant constants
# (gain 50, offset 200, threshold 260).
LEGACY_P1_ASIC = AsicConfig(
    gain_counts_per_fF=50.0,
    offset_counts=200.0,
    near_threshold_counts=260.0,
    touch_threshold_counts=None,
    noise_sigma_counts=0.0,
    adc_bits=None,
    ma_taps=1,
)


def _quantize_clip(x: np.ndarray, adc_bits: int | None) -> np.ndarray:
    if adc_bits is None:
        return x
    full = float(2**adc_bits - 1)
    return np.clip(np.floor(x), 0.0, full)


def simulate_counts(dc_series: np.ndarray, cfg: AsicConfig, seed: int | None = None) -> np.ndarray:
    """ΔC series → noisy quantized MA-smoothed counts. Deterministic per seed;
    seed=None ⇒ the noiseless (truth) path used for false-trigger truthing."""
    dc = np.asarray(dc_series, dtype=np.float64)
    raw = cfg.offset_counts + cfg.gain_counts_per_fF * dc
    if cfg.noise_sigma_counts > 0.0 and seed is not None:
        rng = np.random.default_rng(seed)
        raw = raw + rng.normal(0.0, cfg.noise_sigma_counts, size=dc.shape)
    q = _quantize_clip(raw, cfg.adc_bits)
    if cfg.ma_taps > 1:
        kernel = np.ones(cfg.ma_taps) / cfg.ma_taps
        q = np.convolve(q, kernel, mode="full")[: len(q)]  # causal MA
    return q


def run_v1(counts: np.ndarray, cfg: AsicConfig) -> list[str]:
    """Fixed absolute thresholds — P1-compatible decision surface."""
    states = []
    for c in counts:
        if cfg.touch_threshold_counts is not None and c >= cfg.touch_threshold_counts:
            states.append("TOUCH")
        elif c >= cfg.near_threshold_counts:
            states.append("NEAR")
        else:
            states.append("IDLE")
    return states


def run_v2(counts: np.ndarray, cfg: AsicConfig) -> tuple[list[str], list[float]]:
    """EMA baseline + Schmitt hysteresis + 3-of-5 debounce.

    Bands (the disclosed v2 design):
    - NEAR is RELATIVE to the trailing EMA baseline — enter at baseline +
      enter_near_counts, hold while ≥ baseline + exit_near_counts. The
      relative band is what defeats slow drift (temperature, cover aging).
    - TOUCH is an ABSOLUTE band — enter at touch_threshold_counts, hold
      while ≥ touch_threshold_counts − exit margin. An absolute band is
      required because on a slow approach the EMA baseline trails the
      signal closely enough to eat a relative touch band.
    - A candidate state change commits only after it holds ≥
      debounce_votes of the last debounce_window ticks — isolated noise
      spikes never flip state (the GOLD-04 defense).
    """
    n = len(counts)
    if n == 0:
        return [], []
    baseline = np.empty(n)
    baseline[0] = counts[0]
    for i in range(1, n):
        baseline[i] = cfg.ema_alpha * counts[i] + (1.0 - cfg.ema_alpha) * baseline[i - 1]

    touch_exit = (
        cfg.touch_threshold_counts - cfg.exit_touch_counts
        if cfg.touch_threshold_counts is not None
        else None
    )

    def demand(i: int, current: str) -> str:
        c = counts[i]
        delta = c - baseline[i]
        if current == "TOUCH":
            if touch_exit is not None and c >= touch_exit:
                return "TOUCH"
            if delta >= cfg.exit_near_counts:
                return "NEAR"
            return "IDLE"
        if current == "NEAR":
            if touch_exit is not None and c >= cfg.touch_threshold_counts:
                return "TOUCH"
            if delta >= cfg.exit_near_counts:
                return "NEAR"
            return "IDLE"
        # IDLE
        if touch_exit is not None and c >= cfg.touch_threshold_counts:
            return "TOUCH"
        if delta >= cfg.enter_near_counts:
            return "NEAR"
        return "IDLE"

    states: list[str] = []
    current = "IDLE"
    history: list[str] = []
    for i in range(n):
        want = demand(i, current)
        history.append(want)
        if want != current:
            lo = max(0, i - cfg.debounce_window + 1)
            if history[lo : i + 1].count(want) >= cfg.debounce_votes:
                current = want
        states.append(current)
    return states, [float(b) for b in baseline]


def _state_rank(s: str) -> int:
    return STATES.index(s)


def summarize(states: list[str], truth_states: list[str]) -> dict:
    """False triggers (algo detects where noiseless truth is IDLE), missed
    detections (truth detects where algo stays IDLE) and chatter (state
    transitions — the v1-on-noise signature)."""
    false_triggers = sum(
        1 for a, t in zip(states, truth_states) if a != "IDLE" and t == "IDLE"
    )
    missed = sum(1 for a, t in zip(states, truth_states) if a == "IDLE" and t != "IDLE")
    changes = sum(1 for i in range(1, len(states)) if states[i] != states[i - 1])
    first_detect = next((i for i, s in enumerate(states) if s != "IDLE"), None)
    return {
        "false_trigger_ticks": false_triggers,
        "missed_ticks": missed,
        "state_changes": changes,
        "first_nonidle_tick": first_detect,
    }


def run_replay(
    scenario: dict,
    engine: str,
    dc_eval,  # callable(tick dict) -> dict[channel, dc_fF]
    cfg: AsicConfig = DEFAULT_FIELD_ASIC,
    seed: int = 20260914,
    ood_eval=None,  # callable(tick) -> bool | None (None: engine has no OOD concept)
) -> dict:
    """One deterministic replay of one scenario through the full chain.

    ``dc_eval`` abstracts the tier (solver solves live, surrogate evaluates
    the RBF payload, sweep_interp interpolates the variant's center curve —
    wired in activities.py). Returns the ``airinput.replay.v1`` payload with
    expected/actual embedded (C9: the catalog lives once, in scenarios.py).
    """
    ticks = scenario["ticks"]
    dc_rows = [dc_eval(t) for t in ticks]
    channels = list(dc_rows[0].keys())
    total_dc = [float(sum(row.values())) for row in dc_rows]

    counts_noisy = simulate_counts(np.array(total_dc), cfg, seed)
    counts_truth = simulate_counts(np.array(total_dc), cfg, None)
    truth_states = run_v1(counts_truth, cfg)

    v1_states = run_v1(counts_noisy, cfg)
    v2_states, v2_baseline = run_v2(counts_noisy, cfg)

    ood_flags = (
        [bool(ood_eval(t)) for t in ticks] if ood_eval is not None else None
    )
    ood_any = any(ood_flags) if ood_flags else False

    dc_thresholds = {
        "near_fF": round(cfg.dc_threshold_fF(cfg.near_threshold_counts), 6),
        "touch_fF": (
            round(cfg.dc_threshold_fF(cfg.touch_threshold_counts), 6)
            if cfg.touch_threshold_counts is not None
            else None
        ),
    }

    actual = {
        "v1": summarize(v1_states, truth_states),
        "v2": summarize(v2_states, truth_states),
        "ood_flagged": ood_any,
    }
    expected = scenario["expected"]

    # Flat access into actual for the _min/_max bound vocabulary.
    def lookup(path: str):
        node: object = actual
        for part in path.split("."):
            node = node[part]  # type: ignore[index]
        return node

    comparisons = {}
    ok = True

    for key, bound in expected.items():
        if key.endswith("_min"):
            got = lookup(key[:-4])
            comparisons[key] = {"expected_min": bound, "actual": got, "ok": got >= bound}
        elif key.endswith("_max"):
            got = lookup(key[:-4])
            comparisons[key] = {"expected_max": bound, "actual": got, "ok": got <= bound}
        else:
            got = lookup(key)
            comparisons[key] = {"expected": bound, "actual": got, "ok": got == bound}
        ok = ok and comparisons[key]["ok"]

    def tick_records() -> list[dict]:
        rows = []
        for i, t in enumerate(ticks):
            rows.append(
                {
                    "t_ms": int(round(i * TICK_PERIOD_S * 1000)),
                    "x_mm": t["x_mm"],
                    "y_mm": t["y_mm"],
                    "gap_mm": t["gap_mm"],
                    "is_glove": t["is_glove"],
                    "dc_fF": {ch: round(dc_rows[i][ch], 6) for ch in channels},
                    "counts_truth": round(float(counts_truth[i]), 3),
                    "counts": round(float(counts_noisy[i]), 3),
                    "baseline_v2": round(v2_baseline[i], 3),
                    "truth": truth_states[i],
                    "v1": v1_states[i],
                    "v2": v2_states[i],
                    **({"ood": ood_flags[i]} if ood_flags is not None else {}),
                }
            )
        return rows

    return {
        "schema": "airinput.replay.v1",
        "tier": "replay",
        "disclosure": (
            "Deterministic behavioral replay (seeded ASIC chain + fixed "
            "algorithms) over an engine-tier ΔC trace — validates the "
            "pipeline and the algorithm comparison, never sensor accuracy."
        ),
        "scenario_id": scenario["id"],
        "scenario_description": scenario["description"],
        "engine": engine,
        "seed": seed,
        "tick_period_s": TICK_PERIOD_S,
        "asic_config": cfg.as_payload(),
        "dc_thresholds_derived": dc_thresholds,
        "channels": channels,
        "expected": expected,
        "comparisons": comparisons,
        "pass": ok,
        "actual": actual,
        "ticks": tick_records(),
    }
