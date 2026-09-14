"""ASIC signal-chain and replay tests for the AirInput 3D Interaction Field
Twin (``apps/workers/mech-model/signal_chain.py`` + ``scenarios.py``).
Pure numpy — no DB, no FD solves (analytic ΔC series stand in for the
solver/surrogate tiers).

Pinned here: the v1_fixed_threshold chain stays point-for-point identical
to P1's ``derive_asic_gesture_summary`` on the legacy config; the v2
baseline+hysteresis chain completes the GOLD-01 cycle and stays silent
under GOLD-04's hostile noise; thresholds are DERIVED from counts config;
replays are byte-identical for a fixed seed and carry the disclosed schema."""

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "workers" / "mech-model"))

from artifacts import dump_payload  # noqa: E402
from fs_model import predict_proximity_capacitance  # noqa: E402
from scenarios import scenario_gold01, scenario_gold04  # noqa: E402
from signal_chain import (  # noqa: E402
    DEFAULT_FIELD_ASIC,
    LEGACY_P1_ASIC,
    AsicConfig,
    run_replay,
    run_v1,
    run_v2,
    simulate_counts,
    summarize,
)


def _gold01_dc() -> np.ndarray:
    """Analytic ΔC trace matching GOLD-01's tick plan (28→0→28 approach)."""
    gaps = np.concatenate(
        [[28.0] * 6, np.linspace(28.0, 0.0, 30), [0.0] * 10, np.linspace(0.0, 28.0, 30), [28.0] * 6]
    )
    dc = np.where(gaps <= 5.0, 0.084 * (1 - gaps / 6.0) ** 2 + 0.004, 0.004 * np.exp(-(gaps - 5.0) / 6.0))
    return np.clip(dc, 0.0007, None)


def test_v1_matches_legacy_p1_point_for_point():
    """P1 compatibility: on the legacy config (σ=0, no quantizer, MA=1,
    touch=None) run_v1's detected ticks must be EXACTLY P1's threshold
    chain — the same 21 detected poses, same order."""
    _, dcs = predict_proximity_capacitance()
    legacy_counts = LEGACY_P1_ASIC.offset_counts + LEGACY_P1_ASIC.gain_counts_per_fF * np.array(dcs)
    v1_states = run_v1(legacy_counts, LEGACY_P1_ASIC)
    legacy_detected = legacy_counts >= 260.0
    mine = [s != "IDLE" for s in v1_states]
    assert mine == list(legacy_detected)
    assert sum(mine) == 21


def test_gold04_hostile_noise_v1_chatters_v2_stays_silent():
    cfg = AsicConfig(**{**DEFAULT_FIELD_ASIC.__dict__, "noise_sigma_counts": 50.0})
    dc = np.full(60, 0.002)  # deep-IDLE hold at gap 12 mm
    counts = simulate_counts(dc, cfg, 20260914)
    truth = run_v1(simulate_counts(dc, cfg, None), cfg)
    s1 = summarize(run_v1(counts, cfg), truth)
    v2, _ = run_v2(counts, cfg)
    s2 = summarize(v2, truth)
    assert s1["false_trigger_ticks"] >= 1  # fixed threshold chatters…
    assert s2["false_trigger_ticks"] == 0  # …baseline+debounce does not
    assert s2["state_changes"] == 0


def test_single_spike_rejected_by_debounce():
    counts = np.full(30, 120.0)
    counts[15] = 320.0  # one +200-count spike — above NEAR enter alone
    v2, _ = run_v2(counts, DEFAULT_FIELD_ASIC)
    assert set(v2) == {"IDLE"}


def test_gold01_v2_completes_the_full_cycle():
    counts = simulate_counts(_gold01_dc(), DEFAULT_FIELD_ASIC, 20260914)
    truth = run_v1(simulate_counts(_gold01_dc(), DEFAULT_FIELD_ASIC, None), DEFAULT_FIELD_ASIC)
    v2, _ = run_v2(counts, DEFAULT_FIELD_ASIC)
    s2 = summarize(v2, truth)
    assert s2["first_nonidle_tick"] <= 40
    assert s2["false_trigger_ticks"] == 0
    assert "TOUCH" in set(v2[30:46])  # commits during the approach
    assert v2[-1] == "IDLE"  # fully releases after retreat


def test_seeded_noise_is_reproducible_and_none_is_noiseless():
    dc = _gold01_dc()
    a = simulate_counts(dc, DEFAULT_FIELD_ASIC, 20260914)
    b = simulate_counts(dc, DEFAULT_FIELD_ASIC, 20260914)
    assert np.array_equal(a, b)
    assert simulate_counts(dc, DEFAULT_FIELD_ASIC, 42).tolist() != a.tolist()
    # seed=None is the exact noiseless truth path: quantize+clip, causal MA
    raw = DEFAULT_FIELD_ASIC.offset_counts + DEFAULT_FIELD_ASIC.gain_counts_per_fF * dc
    q = np.clip(np.floor(raw), 0.0, 2.0**10 - 1.0)
    kernel = np.ones(DEFAULT_FIELD_ASIC.ma_taps) / DEFAULT_FIELD_ASIC.ma_taps
    expected = np.convolve(q, kernel, mode="full")[: len(q)]
    assert np.array_equal(simulate_counts(dc, DEFAULT_FIELD_ASIC, None), expected)


def test_thresholds_are_derived_from_counts_config():
    """Provenance rule: ΔC thresholds come from (counts−offset)/gain, never
    invented in fF."""
    assert DEFAULT_FIELD_ASIC.dc_threshold_fF(600.0) == (600.0 - 100.0) / 9000.0
    assert LEGACY_P1_ASIC.dc_threshold_fF(260.0) == (260.0 - 200.0) / 50.0


def test_summarize_counts_false_missed_and_changes():
    truth = ["IDLE", "IDLE", "NEAR", "NEAR", "IDLE", "IDLE"]
    pred = ["IDLE", "IDLE", "IDLE", "NEAR", "NEAR", "IDLE"]
    s = summarize(pred, truth)
    assert s["false_trigger_ticks"] == 1  # tick 4: pred NEAR, truth IDLE
    assert s["missed_ticks"] == 1  # tick 2: truth NEAR, pred IDLE
    assert s["state_changes"] == 2
    assert s["first_nonidle_tick"] == 3


def test_replay_is_byte_identical_and_schema_guarded():
    """Fixed seed ⇒ byte-identical artifact payload (spice-worker 재생성
    계약); the payload carries the disclosed schema and the expected
    bounds live beside the actual verdicts."""
    sc = scenario_gold04()
    # apply the scenario's ASIC overrides, as activities.py does (σ=50 here)
    cfg = (
        AsicConfig(**{**DEFAULT_FIELD_ASIC.__dict__, **sc["asic_overrides"]})
        if sc["asic_overrides"]
        else DEFAULT_FIELD_ASIC
    )
    payload_a = run_replay(sc, "surrogate", lambda t: {"E1": 0.002}, cfg=cfg, seed=sc["seed"])
    payload_b = run_replay(sc, "surrogate", lambda t: {"E1": 0.002}, cfg=cfg, seed=sc["seed"])
    assert dump_payload(payload_a) == dump_payload(payload_b)

    assert payload_a["schema"] == "airinput.replay.v1"
    assert payload_a["scenario_id"] == sc["id"]
    assert payload_a["expected"] == sc["expected"]  # bounds embedded…
    assert payload_a["actual"] is not None  # …beside measured verdicts
    assert payload_a["pass"] is True  # GOLD-04's money outcome holds
    assert payload_a["ticks"], "tick rows must be embedded"
    tick = payload_a["ticks"][0]
    for key in ("t_ms", "x_mm", "y_mm", "gap_mm", "dc_fF", "counts_truth", "counts", "truth", "v1", "v2"):
        assert key in tick
    # A/B byte-difference: a different seed must change the noisy trace
    payload_c = run_replay(sc, "surrogate", lambda t: {"E1": 0.002}, cfg=cfg, seed=sc["seed"] + 1)
    assert dump_payload(payload_a) != dump_payload(payload_c)


def test_gold01_replay_with_analytic_dc_passes_its_own_bounds():
    sc = scenario_gold01()
    res = run_replay(sc, "surrogate", lambda t: {"E1": float(np.interp(t["gap_mm"], [0, 5, 28], [0.084, 0.03, 0.0007]))}, seed=sc["seed"])
    assert res["schema"] == "airinput.replay.v1"
    assert res["pass"] is True
    assert res["actual"]["v2"]["false_trigger_ticks"] == 0
    assert res["actual"]["v2"]["first_nonidle_tick"] <= sc["expected"]["v2.first_nonidle_tick_max"]
