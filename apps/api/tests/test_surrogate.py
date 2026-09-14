"""Surrogate tests for the AirInput fast tier
(``apps/workers/mech-model/surrogate.py``). Pure numpy — no DB, no FD solves.

The full-DOE training (96 solver solves ≈ 6 min) is exercised live by the
seed script's RUN-SURROGATE-01; these tests pin the contracts the browser
depends on: the fitting math interpolates a smooth field, the serialized
payload reproduces ``eval_fF`` EXACTLY (the TS-parity formula), the output
clamp holds, the OOD flag bounds each axis, and the DOE/split are
deterministic — including gap 0 (contact) being inside the envelope."""

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "workers" / "mech-model"))

import surrogate as sur  # noqa: E402
from field_model import FingerState  # noqa: E402
from surrogate import (  # noqa: E402
    ChannelSurrogate,
    _fit_one,
    doe_poses,
    eval_surrogate,
    is_ood,
    split_holdout,
)


def _smooth_field(pose: FingerState) -> float:
    """Synthetic stand-in for the solver's ΔC: smooth, monotone in gap."""
    return 0.084 * np.exp(-pose.gap_mm / 8.0) * (1.0 + 0.1 * pose.x_mm / 20.0)


def _fit_on_grid():
    pts = [
        FingerState(x, y, z)
        for x in np.linspace(*sur.DOE_X_MM, 5)
        for y in np.linspace(*sur.DOE_Y_MM, 5)
        for z in np.linspace(*sur.DOE_Z_MM, 6)
    ]
    vals = np.array([_smooth_field(p) for p in pts])
    tr, ho = split_holdout(len(pts), 12)
    return pts, vals, tr, ho


def test_fit_interpolates_a_smooth_field():
    pts, vals, tr, ho = _fit_on_grid()
    model = _fit_one("E1", [pts[i] for i in tr], vals[tr], [pts[i] for i in ho], vals[ho])
    assert model.n_train == len(tr)
    span = vals.max() - vals.min()
    assert model.holdout_max_err_ff < 0.05 * span
    assert model.holdout_rmse_ff <= model.holdout_max_err_ff
    assert model.holdout_mae_ff <= model.holdout_rmse_ff


def test_serialized_payload_evaluates_exactly_like_eval_fF():
    """TS-parity: the browser gets centers/weights/mean/l2/clamp and applies
    the documented formula — it must land on the identical number."""
    pts, vals, tr, ho = _fit_on_grid()
    model = _fit_one("E1", [pts[i] for i in tr], vals[tr], [pts[i] for i in ho], vals[ho])
    payload = {
        "channel": model.channel,
        "centers_norm": [[float(v) for v in c] for c in model.centers_norm],
        "weights": [float(w) for w in model.weights],
        "mean": model.mean,
        "l2": model.l2,
        "lam": model.lam,
        "pred_log_lo": model.pred_log_lo,
        "pred_log_hi": model.pred_log_hi,
    }
    for pose in (pts[0], FingerState(3.3, -7.1, 13.7), FingerState(0.0, 0.0, 0.0, True)):
        via_payload = eval_surrogate({"channels": {"E1": payload}, "glove_channels": {"E1": payload}},
                                     pose.x_mm, pose.y_mm, pose.gap_mm, pose.is_glove)["E1"]
        assert via_payload == model.eval_fF((pose.x_mm, pose.y_mm, pose.gap_mm))


def test_output_clamp_bounds_the_prediction():
    pts, vals, tr, ho = _fit_on_grid()
    model = _fit_one("E1", [pts[i] for i in tr], vals[tr], [pts[i] for i in ho], vals[ho])
    # tighten the clamp below the natural data max → eval must respect it
    clamped = ChannelSurrogate(**{**model.__dict__, "pred_log_hi": model.pred_log_hi - 1.0})
    worst = max(clamped.eval_fF((p.x_mm, p.y_mm, p.gap_mm)) for p in pts)
    assert worst <= 10.0 ** (model.pred_log_hi - 1.0) + 1e-12
    # and the floor: a far-corner prediction can't go below 10**pred_log_lo
    assert 10.0 ** model.pred_log_lo - 1e-12 <= model.eval_fF((0.0, 0.0, 0.0))


def test_ood_flag_bounds_each_axis_inclusively():
    x0, x1 = sur.DOE_X_MM
    y0, y1 = sur.DOE_Y_MM
    z0, z1 = sur.DOE_Z_MM
    assert not is_ood(0.0, 0.0, 0.0)  # contact is IN envelope (regression)
    assert not is_ood(x0, y0, z0) and not is_ood(x1, y1, z1)  # corners inclusive
    assert is_ood(x1 + 0.1, 0.0, 5.0)  # x out
    assert is_ood(0.0, y1 + 0.1, 5.0)  # y out
    assert is_ood(0.0, 0.0, z1 + 0.1)  # gap out (GOLD-05 z=35)
    assert is_ood(0.0, 0.0, -0.1)  # below contact


def test_doe_and_holdout_split_are_deterministic():
    bare_a, glove_a = doe_poses()
    bare_b, glove_b = doe_poses()
    assert bare_a == bare_b and glove_a == glove_b
    assert len(bare_a) == 96 and len(glove_a) == 18
    assert any(p.gap_mm == 0.0 for p in bare_a)  # contact operating point present
    tr, ho = split_holdout(96, 14)
    tr2, ho2 = split_holdout(96, 14)
    assert list(tr) == list(tr2) and list(ho) == list(ho2)
    assert set(tr) & set(ho) == set() and len(tr) + len(ho) == 96
