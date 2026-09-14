"""Field-solver tests for the AirInput 3D Interaction Field Twin
(``apps/workers/mech-model/field_model.py``). Pure numpy — no DB, no API.

What these tests CAN claim (지시서 §13 discipline): discretization
correctness (thin structures never vanish), an analytic parallel-plate
sanity case, physical monotonicity/ordering, and bit-exact determinism.
What they do NOT claim: absolute accuracy against a commercial FEM/BEM
solver — the module docstring discloses that limit.

Tests run at cell_mm=1.5 (not the production 1.0) to keep the suite fast;
the grid study in the module docstring pins production resolution."""

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "workers" / "mech-model"))

from field_model import (  # noqa: E402
    ASIC_PADDLE_CENTER,
    ASIC_PADDLE_HALF,
    EPS0_FF_PER_MM,
    FingerState,
    GeometrySpec,
    StaticEnvironment,
    build_environment,
    delta_c_self_fF,
    predict_field_curve,
    solve_potential,
)

GEOM = GeometrySpec(electrode_area_mm2=100.0, cover_thickness_mm=1.0, cover_eps_r=4.0, split_ring=False)


def test_thin_structures_never_vanish_from_the_grid():
    """Regression for the center-in-band bug: the 0.08 mm copper layer and
    the ASIC paddle fell between cell centers and silently disappeared
    (electrode mask == 0 → Q == 0 → everything read as 'no sensor')."""
    env = build_environment(GEOM, 1.5)
    assert int(env.electrode_mask.sum()) > 0
    assert (env.fixed & env.electrode_mask).sum() == env.electrode_mask.sum()

    ax, ay = ASIC_PADDLE_CENTER
    X, Y = np.meshgrid(env.xs, env.ys, indexing="ij")
    paddle_xy = (np.abs(X - ax) <= ASIC_PADDLE_HALF) & (np.abs(Y - ay) <= ASIC_PADDLE_HALF)
    paddle_cells = paddle_xy[:, :, None] & env.fixed
    assert paddle_cells.any()  # the QFN ground shield made it onto the grid
    # …on the same z-layer(s) the electrode snapped to (same copper band)
    assert (paddle_cells.any(axis=(0, 1)) & env.electrode_mask.any(axis=(0, 1))).any()


def test_parallel_plate_analytic_sanity():
    """Uniform-gap plate pair: FD charge must reproduce the cell-center
    analytic Q = ε0·A/(d_eff) with d_eff = (nz−1)·h (Dirichlet at cell
    centers) to within 2% — validates the charge-integration magnitude
    end-to-end (harmonic-mean faces, exposed-face selection, ε0 units)."""
    h, n = 1.0, 10
    eps = np.ones((n, n, n))
    fixed = np.zeros((n, n, n), dtype=bool)
    potential = np.zeros((n, n, n))
    fixed[:, :, 0] = True
    potential[:, :, 0] = 1.0
    fixed[:, :, n - 1] = True  # grounded counter-plate
    channel = np.zeros((n, n, n), dtype=bool)
    channel[:, :, 0] = True
    env = StaticEnvironment(
        geom=GEOM,
        h=h,
        eps=eps,
        fixed=fixed,
        potential=potential,
        electrode_mask=channel,
        channel_masks={"E1": channel},
        shape=(n, n, n),
        xs=(np.arange(n) - (n - 1) / 2) * h,
        ys=(np.arange(n) - (n - 1) / 2) * h,
        zs=(np.arange(n) + 0.5) * h,
    )
    sol = solve_potential(env, None)
    expected = EPS0_FF_PER_MM * (n * n) * (1.0 / (n - 1)) * h
    assert abs(sol.channel_q_ff["E1"] - expected) / expected < 0.02
    assert sol.converged


def test_field_curve_monotone_nonincreasing_with_physical_tail():
    ds, cs = predict_field_curve(num_points=5, distance_max_mm=20.0, cell_mm=1.5)
    assert ds == sorted(ds)
    assert all(a >= b for a, b in zip(cs, cs[1:]))  # non-increasing overall…
    assert cs[0] > 10 * cs[-1]  # …with a real near-range signal


def test_glove_and_ground_plate_both_reduce_signal():
    cache: dict = {}
    bare, _ = delta_c_self_fF(GEOM, FingerState(0, 0, 2.0), 1.5, cache)
    glove, _ = delta_c_self_fF(GEOM, FingerState(0, 0, 2.0, True), 1.5, cache)
    assert glove["E1"] < bare["E1"]  # porous-knit standoff dominates (disclosed ε1.3)

    plate_geom = GeometrySpec(
        100.0, 1.0, 4.0, False, ground_plate=(0.0, 0.0, 12.5, 12.0, 10.0)
    )
    shunted, _ = delta_c_self_fF(
        plate_geom, FingerState(0, 0, 2.0), 1.5, cache
    )
    assert shunted["E1"] < bare["E1"]  # §11.2 금속/접지: grounded guard shunts field


def test_layout_b_half_ring_channels_partition_the_electrode():
    geom_b = GeometrySpec(160.0, 1.2, 3.2, split_ring=True)
    env = build_environment(geom_b, 1.5)
    e1, e2 = env.channel_masks["E1"], env.channel_masks["E2"]
    assert not (e1 & e2).any()  # disjoint halves
    assert (e1 | e2).sum() == env.electrode_mask.sum()  # union == whole ring
    cache: dict = {}
    dc, _ = delta_c_self_fF(geom_b, FingerState(0, 0, 2.0), 1.5, cache)
    assert dc["E1"] > 0 and dc["E2"] > 0


def test_bit_exact_determinism():
    a = delta_c_self_fF(GEOM, FingerState(0, 0, 2.0), 1.5)
    b = delta_c_self_fF(GEOM, FingerState(0, 0, 2.0), 1.5)
    assert a[0] == b[0]
    assert a[1].channel_q_ff == b[1].channel_q_ff
    assert a[1].sweeps == b[1].sweeps


def test_edge_finger_weaker_than_center():
    cache: dict = {}
    center, _ = delta_c_self_fF(GEOM, FingerState(0, 0, 2.0), 1.5, cache)
    edge, _ = delta_c_self_fF(GEOM, FingerState(12.0, 0.0, 2.0), 1.5, cache)
    assert edge["E1"] < center["E1"]  # 가장자리 감도 저하 (§11.2)


def test_curve_slice_collection_builds_the_pose_library():
    """slices_out collects one y=0 slice per curve solve — the gap axis of
    the artifact's pose library comes free with the curve (no extra
    solves), and slice_stride=2 downsamples for transport."""
    slices: list = []
    predict_field_curve(num_points=4, distance_max_mm=18.0, cell_mm=1.5, slices_out=slices, slice_stride=2)
    assert len(slices) == 4
    gaps = [s["pose"]["gap_mm"] for s in slices]
    assert gaps == sorted(gaps) and gaps[0] == 0.0
    assert all(s["pose"]["x_mm"] == 0.0 and s["pose"]["y_mm"] == 0.0 for s in slices)
    rows = len(slices[0]["slice"]["values"])
    cols = len(slices[0]["slice"]["values"][0])
    assert cols < rows  # z axis is the shorter one after stride-2 downsampling
    # Solved fields: bounded by the Dirichlet range and genuinely pose-
    # dependent (the display's premise — the slice must change with pose).
    for s in slices:
        flat = [v for row in s["slice"]["values"] for v in row]
        assert min(flat) >= 0.0 and max(flat) <= 1.0
    assert slices[0]["slice"]["values"] != slices[-1]["slice"]["values"]


def test_slice_stride_controls_transport_resolution():
    _, coarse = delta_c_self_fF(GEOM, FingerState(0, 0, 0.0), 1.5, want_potential_slice=True, slice_stride=3)
    _, fine = delta_c_self_fF(GEOM, FingerState(0, 0, 0.0), 1.5, want_potential_slice=True, slice_stride=1)
    nx = build_environment(GEOM, 1.5).shape[0]
    assert len(fine.potential_slice["values"]) == nx  # stride 1 keeps every x cell
    # numpy's ::3 keeps ceil(n/3) rows
    assert len(coarse.potential_slice["values"]) == (nx + 2) // 3


def test_lateral_slice_sweep_follows_radius():
    from field_model import lateral_slice_sweep

    out = lateral_slice_sweep(GEOM, [0.0, 6.0, 12.0], gap_mm=0.0, cell_mm=1.5)
    assert [s["pose"]["x_mm"] for s in out] == [6.0, 12.0]  # r=0 skipped (gap sweep covers center)
    assert all(s["pose"]["y_mm"] == 0.0 for s in out)
    # Off-center solves stay valid fields (same Dirichlet range) and differ
    # from the centered touch solve — the display's premise.
    _, center = delta_c_self_fF(GEOM, FingerState(0, 0, 0.0), 1.5, want_potential_slice=True)
    assert out[0]["slice"]["values"] != center.potential_slice["values"]
