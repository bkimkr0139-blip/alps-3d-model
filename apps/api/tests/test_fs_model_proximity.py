"""Regression tests for the AirInput vertical-slice physics stand-in
(``predict_proximity_capacitance`` / ``derive_asic_gesture_summary`` in
``apps/workers/mech-model/fs_model.py``). Pure numpy math — no DB, no API,
safe to run alongside the rest of the shared pytest DB-backed suite.

fs_model.py has no dependency on the API app, so it's imported directly by
adding the mech-model worker directory to sys.path (mirrors how
activities.py adds apps/api to sys.path in the other direction)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "workers" / "mech-model"))

from fs_model import derive_asic_gesture_summary, predict_proximity_capacitance  # noqa: E402


def test_proximity_capacitance_is_monotonically_decreasing():
    _, delta_c_fF = predict_proximity_capacitance(num_points=25)
    assert all(a > b for a, b in zip(delta_c_fF, delta_c_fF[1:]))


def test_cover_increases_effective_standoff_and_lowers_delta_c():
    distance_mm, bare = predict_proximity_capacitance(
        cover_thickness_mm=0.0, cover_dielectric_constant=1.0, is_glove=False, num_points=11
    )
    _, covered = predict_proximity_capacitance(
        cover_thickness_mm=1.5, cover_dielectric_constant=4.0, is_glove=False, num_points=11
    )
    assert len(distance_mm) == len(bare) == len(covered)
    for b, c in zip(bare, covered):
        assert c < b


def test_glove_increases_effective_standoff_and_lowers_delta_c():
    _, bare = predict_proximity_capacitance(
        cover_thickness_mm=0.0, cover_dielectric_constant=1.0, is_glove=False, num_points=11
    )
    _, gloved = predict_proximity_capacitance(
        cover_thickness_mm=0.0, cover_dielectric_constant=1.0, is_glove=True, num_points=11
    )
    for b, g in zip(bare, gloved):
        assert g < b


def test_cover_and_glove_stack_for_even_lower_delta_c():
    """Both standoff contributions apply together, not just individually."""
    _, cover_only = predict_proximity_capacitance(
        cover_thickness_mm=1.0, cover_dielectric_constant=4.0, is_glove=False, num_points=11
    )
    _, cover_and_glove = predict_proximity_capacitance(
        cover_thickness_mm=1.0, cover_dielectric_constant=4.0, is_glove=True, num_points=11
    )
    for c, cg in zip(cover_only, cover_and_glove):
        assert cg < c


def test_larger_electrode_area_scales_up_delta_c():
    _, small = predict_proximity_capacitance(electrode_area_mm2=50.0, num_points=11)
    _, large = predict_proximity_capacitance(electrode_area_mm2=200.0, num_points=11)
    for s, l in zip(small, large):
        assert l > s


def test_asic_summary_glove_reduces_max_reliable_distance():
    distance_bare, delta_c_bare = predict_proximity_capacitance(is_glove=False)
    bare_summary = derive_asic_gesture_summary(distance_bare, delta_c_bare)

    distance_glove, delta_c_glove = predict_proximity_capacitance(is_glove=True)
    glove_summary = derive_asic_gesture_summary(distance_glove, delta_c_glove)

    assert glove_summary["max_reliable_distance_mm"] <= bare_summary["max_reliable_distance_mm"]
    assert 0.0 <= bare_summary["max_reliable_distance_mm"] <= distance_bare[-1]
    assert 0.0 <= glove_summary["max_reliable_distance_mm"] <= distance_glove[-1]


def test_asic_summary_raw_counts_track_delta_c_linearly():
    distance_mm, delta_c_fF = predict_proximity_capacitance(num_points=9)
    summary = derive_asic_gesture_summary(
        distance_mm, delta_c_fF, gain_counts_per_fF=10.0, offset_counts=100.0, threshold_counts=150.0
    )
    for dc, rc in zip(delta_c_fF, summary["raw_counts"]):
        assert rc == 100.0 + 10.0 * dc
    # detected exactly where raw_count crosses the fixed threshold
    for rc, d in zip(summary["raw_counts"], summary["detected"]):
        assert d == (rc >= 150.0)
