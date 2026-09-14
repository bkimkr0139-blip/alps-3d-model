"""Real-time RBF surrogate over the FD field solver — the §6.2 "fast" tier.

Deliberate separation (지시서 ⑤): ``field_model`` is the reference solver
(seconds per pose, runs in the worker); this module fits a Gaussian-RBF
interpolant to a fixed Design-of-Experiments sweep of solver results so the
web client can evaluate arbitrary finger poses in microseconds. The
surrogate is an INTERPOLATOR OF THE DISCLOSED SOLVER, never an independent
source of truth — every artifact it produces carries tier="surrogate", the
DOE envelope, and the solver provenance it was trained on.

NOT an LLM, NOT evidence: it never feeds gates or compliance claims (지시서
금지 목록). Poses outside the DOE envelope are flagged OOD by the caller
(유효범위 밖 예측은 정상 표시 금지) — see ``is_ood``.

TS-parity contract: the artifact stores the kernel centers, weights, mean,
length-scale, and output clamp as flat float arrays. The browser evaluates

    pred = mean + Σ w_i · exp(−‖x′ − c′_i‖² / (2·ℓ²))
    pred = clamp(pred, pred_log_lo, pred_log_hi);  ΔC = 10^pred

with x′ the pose normalized into [0,1] per axis (same formula as
``eval_channel`` here). Targets are trained in log10 space (disclosed
``target_transform``) so relative error is uniform across the ~2 decades of
ΔC magnitude; a 1e-6 fF floor guards log10(0), and the output clamp is the
disclosed bounded-interpolator guard against envelope-edge overshoot.

All constants below (λ, ℓ, DOE grid, seed) are disclosed illustrative
choices of the interpolator design, not measured sensor properties.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from field_model import FingerState, GeometrySpec, delta_c_self_fF

RIDGE_LAMBDA = 1e-6
KERNEL_L2 = 0.35  # Gaussian length-scale in NORMALIZED [0,1] coordinates
# (≈ the mean DOE grid spacing 1/3 in x/y and 1/5 in z — disclosed choice)
DC_FLOOR_FF = 1e-6
TARGET_TRANSFORM = "log10_floor_1e-6"
DOE_SEED = 20260914

# DOE envelope (mm) — the surrogate's validity envelope. Outside ⇒ OOD.
# The gap range MUST include 0 (contact): touch is the sensor's primary
# operating point — a DOE starting at 2 mm would flag every real touch
# as out-of-validity (caught by the GOLD-01 replay smoke).
DOE_X_MM = (-20.0, 20.0)
DOE_Y_MM = (-16.0, 16.0)
DOE_Z_MM = (0.0, 28.0)  # z = air gap between finger/glove and touch surface

_GRID_N = (4, 4, 6)


def _grid_points() -> list[tuple[float, float, float]]:
    xs = np.linspace(*DOE_X_MM, _GRID_N[0])
    ys = np.linspace(*DOE_Y_MM, _GRID_N[1])
    zs = np.linspace(*DOE_Z_MM, _GRID_N[2])
    return [(float(x), float(y), float(z)) for x in xs for y in ys for z in zs]


def doe_poses() -> tuple[list[FingerState], list[FingerState]]:
    """Deterministic DOE: the bare-finger grid plus a glove subset.

    Returns (train_and_holdout_bare, glove_subset). The glove subset takes
    every 6th grid point (16) plus two opposite corners (18) — enough to
    cover the space with a separate glove model instead of polluting the
    bare model with a boolean 4th dimension.
    """
    pts = _grid_points()
    bare = [FingerState(x, y, z, False) for (x, y, z) in pts]
    glove_idx = list(range(0, len(pts), 6))
    corners = [1, _GRID_N[0] * _GRID_N[1] * _GRID_N[2] - 1]
    glove_idx = sorted(set(glove_idx + corners))
    glove = [FingerState(*pts[i], True) for i in glove_idx]
    return bare, glove


def split_holdout(n: int, n_holdout: int, seed: int = DOE_SEED) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic seeded holdout split → (train_idx, holdout_idx)."""
    rng = np.random.default_rng(seed)
    perm = rng.permutation(n)
    return perm[n_holdout:], perm[:n_holdout]


def _normalize(pose: tuple[float, float, float]) -> np.ndarray:
    x = (pose[0] - DOE_X_MM[0]) / (DOE_X_MM[1] - DOE_X_MM[0])
    y = (pose[1] - DOE_Y_MM[0]) / (DOE_Y_MM[1] - DOE_Y_MM[0])
    z = (pose[2] - DOE_Z_MM[0]) / (DOE_Z_MM[1] - DOE_Z_MM[0])
    return np.array([x, y, z], dtype=np.float64)


@dataclass
class ChannelSurrogate:
    """One RBF channel model — also the TS-parity payload shape.

    ``pred_log_lo/hi`` clamp the raw log10 prediction into the physically
    realizable range (ΔC cannot exceed the contact-over-center training
    maximum; below-floor predictions are just "no signal"). Without the
    clamp the Gaussian RBF overshoots at envelope-edge holdout points —
    observed max error 0.4 fF on an 0.084 fF max signal, which would bloom
    the sensitivity volume's detect mask. Disclosed bounded-interpolator
    design; the browser applies the identical clamp.
    """

    channel: str
    centers_norm: np.ndarray  # (m, 3)
    weights: np.ndarray  # (m,)
    mean: float  # log10-space training mean
    l2: float
    lam: float
    pred_log_lo: float
    pred_log_hi: float
    n_train: int
    holdout_rmse_ff: float
    holdout_mae_ff: float
    holdout_max_err_ff: float

    def kernel(self, x_norm: np.ndarray) -> np.ndarray:
        d = self.centers_norm - x_norm[None, :]
        return np.exp(-np.sum(d * d, axis=1) / (2.0 * self.l2 * self.l2))

    def eval_fF(self, pose: tuple[float, float, float]) -> float:
        pred = self.mean + float(np.dot(self.weights, self.kernel(_normalize(pose))))
        pred = min(max(pred, self.pred_log_lo), self.pred_log_hi)
        return float(10.0**pred)


def _fit_one(
    channel: str,
    train_poses: list[FingerState],
    train_values: np.ndarray,  # ΔC in fF, log10-floored inside
    holdout_poses: list[FingerState],
    holdout_values: np.ndarray,
) -> ChannelSurrogate:
    C = np.array([_normalize((p.x_mm, p.y_mm, p.gap_mm)) for p in train_poses])
    y = np.log10(np.maximum(train_values, DC_FLOOR_FF))
    mean = float(np.mean(y))
    # Disclosed output clamp: the realized ΔC range is [floor, max train +
    # 0.25 decades] — see ChannelSurrogate.pred_log_lo/hi.
    pred_log_lo = float(np.log10(DC_FLOOR_FF))
    pred_log_hi = float(np.max(y) + 0.25)
    d2 = np.sum((C[:, None, :] - C[None, :, :]) ** 2, axis=2)
    K = np.exp(-d2 / (2.0 * KERNEL_L2 * KERNEL_L2))
    w = np.linalg.solve(K + RIDGE_LAMBDA * np.eye(len(C)), y - mean)

    def raw_log(pose: FingerState) -> float:
        xn = _normalize((pose.x_mm, pose.y_mm, pose.gap_mm))
        k = np.exp(-np.sum((C - xn[None, :]) ** 2, axis=1) / (2.0 * KERNEL_L2 * KERNEL_L2))
        return mean + float(np.dot(w, k))

    def err(vectors: list[FingerState], vals: np.ndarray) -> tuple[float, float, float]:
        if len(vectors) == 0:
            return (0.0, 0.0, 0.0)
        pred = np.array(
            [10.0 ** min(max(raw_log(p), pred_log_lo), pred_log_hi) for p in vectors]
        )
        e = pred - vals
        return (
            float(np.sqrt(np.mean(e**2))),
            float(np.mean(np.abs(e))),
            float(np.max(np.abs(e))),
        )

    rmse, mae, mx = err(holdout_poses, holdout_values)
    return ChannelSurrogate(
        channel=channel,
        centers_norm=C,
        weights=w,
        mean=mean,
        l2=KERNEL_L2,
        lam=RIDGE_LAMBDA,
        pred_log_lo=pred_log_lo,
        pred_log_hi=pred_log_hi,
        n_train=len(train_poses),
        holdout_rmse_ff=rmse,
        holdout_mae_ff=mae,
        holdout_max_err_ff=mx,
    )


def is_ood(x_mm: float, y_mm: float, gap_mm: float) -> bool:
    """Outside the DOE envelope ⇒ the prediction must never display as a
    normal result (GOLD-05 hover z=35 is the pinned scenario)."""
    return not (
        DOE_X_MM[0] <= x_mm <= DOE_X_MM[1]
        and DOE_Y_MM[0] <= y_mm <= DOE_Y_MM[1]
        and DOE_Z_MM[0] <= gap_mm <= DOE_Z_MM[1]
    )


def train_surrogates(
    geom: GeometrySpec,
    cell_mm: float = 1.0,
    progress=None,
) -> dict:
    """Solve the whole DOE with the FD solver and fit per-channel models.

    Returns the ``airinput.surrogate-rbf.v1`` artifact payload (JSON-safe).
    ``progress`` (optional callable) is called after each solve — the seed
    script passes it to keep a ~5-minute run visibly alive.
    """
    bare, glove = doe_poses()
    env_cache: dict = {}
    baseline_cache: dict = {}

    def solve_all(poses: list[FingerState]) -> tuple[list[dict[str, float]], list[str]]:
        vals: list[dict[str, float]] = []
        channels: list[str] = []
        for idx, p in enumerate(poses):
            dc, _ = delta_c_self_fF(geom, p, cell_mm, baseline_cache)
            vals.append(dc)
            channels = list(dc.keys())
            if progress is not None:
                progress(idx + 1, len(poses), p)
        return vals, channels

    bare_vals, channels = solve_all(bare)
    glove_vals, _ = solve_all(glove)

    def split_fit(sub_poses, sub_vals, n_holdout: int, seed: int) -> tuple[list[ChannelSurrogate], list[dict]]:
        tr, ho = split_holdout(len(sub_poses), n_holdout, seed)
        models = [
            _fit_one(
                ch,
                [sub_poses[i] for i in tr],
                np.array([sub_vals[i][ch] for i in tr]),
                [sub_poses[i] for i in ho],
                np.array([sub_vals[i][ch] for i in ho]),
            )
            for ch in channels
        ]
        holdout_records = [
            {
                "x_mm": sub_poses[i].x_mm,
                "y_mm": sub_poses[i].y_mm,
                "gap_mm": sub_poses[i].gap_mm,
                "is_glove": sub_poses[i].is_glove,
                **{ch: round(sub_vals[i][ch], 6) for ch in channels},
            }
            for i in ho
        ]
        return models, holdout_records

    bare_models, bare_holdout = split_fit(bare, bare_vals, 14, DOE_SEED)
    glove_models, glove_holdout = split_fit(glove, glove_vals, 4, DOE_SEED + 1)

    def channel_payload(m: ChannelSurrogate) -> dict:
        return {
            "channel": m.channel,
            "centers_norm": [[round(float(v), 6) for v in c] for c in m.centers_norm],
            "weights": [round(float(v), 8) for v in m.weights],
            "mean": round(m.mean, 8),
            "l2": m.l2,
            "lam": m.lam,
            "pred_log_lo": round(m.pred_log_lo, 6),
            "pred_log_hi": round(m.pred_log_hi, 6),
            "n_train": m.n_train,
            "holdout": {
                "rmse_fF": round(m.holdout_rmse_ff, 6),
                "mae_fF": round(m.holdout_mae_ff, 6),
                "max_err_fF": round(m.holdout_max_err_ff, 6),
            },
        }

    return {
        "schema": "airinput.surrogate-rbf.v1",
        "tier": "surrogate",
        "disclosure": (
            "RBF interpolator over the fd-electrostatic-solver DOE — "
            "interactive fast tier, NOT an independent measurement or "
            "evidence. Poses outside the DOE envelope are flagged OOD "
            "and must never display as normal results."
        ),
        "layout": geom.layout,
        "cell_mm": cell_mm,
        "target_transform": TARGET_TRANSFORM,
        "doe": {
            "seed": DOE_SEED,
            "grid": f"{_GRID_N[0]}x{_GRID_N[1]}x{_GRID_N[2]}",
            "n_bare": len(bare),
            "n_glove": len(glove),
            "ranges_mm": {"x": list(DOE_X_MM), "y": list(DOE_Y_MM), "gap": list(DOE_Z_MM)},
        },
        "channels": {m.channel: channel_payload(m) for m in bare_models},
        "glove_channels": {m.channel: channel_payload(m) for m in glove_models},
        "holdout_points": {"bare": bare_holdout, "glove": glove_holdout},
    }


def eval_surrogate(payload: dict, x_mm: float, y_mm: float, gap_mm: float, is_glove: bool) -> dict[str, float]:
    """Evaluate the artifact payload exactly as the browser does (parity
    reference for pytest): per-channel ΔC in fF. OOD checking is the
    CALLER's job via ``is_ood`` — this function must stay a pure formula."""
    table = payload["glove_channels"] if is_glove else payload["channels"]
    out = {}
    for ch, m in table.items():
        centers = np.array(m["centers_norm"], dtype=np.float64)
        w = np.array(m["weights"], dtype=np.float64)
        p = _normalize((x_mm, y_mm, gap_mm))
        d2 = np.sum((centers - p[None, :]) ** 2, axis=1)
        pred = m["mean"] + float(np.dot(w, np.exp(-d2 / (2.0 * m["l2"] * m["l2"]))))
        pred = min(max(pred, m["pred_log_lo"]), m["pred_log_hi"])
        out[ch] = float(10.0**pred)
    return out
