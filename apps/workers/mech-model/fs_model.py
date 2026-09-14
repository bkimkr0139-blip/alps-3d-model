"""Analytical prediction curves for the mech-model worker.

Each model type keeps the same (xs, ys) return shape but describes a
different physical characteristic, selected per simulation run via the
``model_type`` parameter:

- ``fs_dome``         — Force–Stroke curve of a TACT switch metal dome (mm, mN)
- ``detent_torque``   — detent torque of a rotary encoder (deg, mN·m)
- ``bridge_transfer`` — ratiometric output of a piezoresistive MEMS
  pressure-sensor bridge (kPa, mV)
- ``proximity_capacitance`` — self-capacitance change ΔC of an AirInput
  proximity electrode vs. finger/glove approach distance (mm, fF)

These are deliberately simple illustrative placeholders shaped to look like
the real curves — NOT validated FEA/behavioral models. See §FR-05: PoC
allows one representative scenario end-to-end; a real FEA model or FMU would
slot in with the same return shape, so this is a straightforward swap later,
not a rewrite.
"""

import numpy as np


def predict_fs_curve(
    dome_thickness_mm: float,
    dome_diameter_mm: float,
    stroke_max_mm: float = 0.35,
    num_points: int = 15,
) -> tuple[list[float], list[float]]:
    f_peak = 250.0 * (dome_thickness_mm / 0.10) ** 2.5 * (6.0 / dome_diameter_mm)
    f_valley = f_peak * 0.35
    f0 = f_peak * 0.05
    f_bottom = f_peak * 1.3
    x_peak = 0.35 * stroke_max_mm
    x_click = 0.55 * stroke_max_mm

    xs = np.linspace(0, stroke_max_mm, num_points)
    ys = np.empty_like(xs)
    for i, x in enumerate(xs):
        if x <= x_peak:
            t = x / x_peak
            ys[i] = f0 + (f_peak - f0) * t**1.5
        elif x <= x_click:
            t = (x - x_peak) / (x_click - x_peak)
            ys[i] = f_peak - (f_peak - f_valley) * t
        else:
            t = (x - x_click) / (stroke_max_mm - x_click)
            ys[i] = f_valley + (f_bottom - f_valley) * t**3

    return xs.tolist(), ys.tolist()


def predict_detent_curve(
    detent_count: int,
    peak_torque_mNm: float,
    angle_span_deg: float = 90.0,
    num_points: int = 15,
) -> tuple[list[float], list[float]]:
    """Detent torque vs rotation angle. Torque is zero on a detent and peaks
    halfway to the next one, giving ``detent_count`` equal wells per
    revolution (|sin| with ``detent_count`` half-periods per 360°)."""
    theta_deg = np.linspace(0.0, angle_span_deg, num_points)
    ys = peak_torque_mNm * np.abs(np.sin(np.deg2rad(theta_deg) * detent_count / 2.0))
    return theta_deg.tolist(), ys.tolist()


def predict_bridge_transfer(
    supply_voltage_v: float,
    sensitivity_mv_per_v_per_kpa: float,
    pressure_min_kpa: float = 40.0,
    pressure_max_kpa: float = 400.0,
    num_points: int = 15,
) -> tuple[list[float], list[float]]:
    """Ratiometric piezoresistive bridge: linear Vout vs absolute pressure,
    the standard datasheet transfer curve of a MEMS pressure sensor."""
    pressure_kpa = np.linspace(pressure_min_kpa, pressure_max_kpa, num_points)
    vout_mv = sensitivity_mv_per_v_per_kpa * supply_voltage_v * pressure_kpa
    return pressure_kpa.tolist(), vout_mv.tolist()


# --- AirInput vertical slice (proximity_capacitance) -----------------------
#
# Illustrative shape constants for the ΔC(d) fringing-field decay below —
# NOT measured/datasheet values, NOT a solver output. Disclosed here per
# HANDOFF.md §7 ("시뮬레이션 숫자·물성·공차·규격값 임의 생성 금지" — any
# invented physical constant must be labeled as a disclosed synthetic
# simplification, exactly like fs_dome's f_peak/f_valley/f0 shape constants
# above). A real §IF-02 electrostatic FEM/BEM solver would replace all of
# this with an actual boundary-value solve over the real electrode/cover/
# finger geometry and material permittivities.
_C0_FF_PER_MM2 = 0.6  # baseline self-capacitance fringing coefficient (fF/mm²) at zero standoff
_D0_MM = 6.0  # characteristic decay length of the fringing field (mm)
_N_DECAY = 2.0  # decay exponent (near-field fringing falls off faster than 1/d)
_GLOVE_STANDOFF_MM = 1.5  # extra effective standoff added by a "typical" glove


def predict_proximity_capacitance(
    electrode_area_mm2: float = 100.0,
    cover_thickness_mm: float = 1.0,
    cover_dielectric_constant: float = 4.0,
    is_glove: bool = False,
    distance_min_mm: float = 0.0,
    distance_max_mm: float = 40.0,
    num_points: int = 21,
) -> tuple[list[float], list[float]]:
    """Self-capacitance change ΔC(d) of a single AirInput electrode as a
    finger (bare or gloved) approaches from ``distance_max_mm`` down to
    ``distance_min_mm``.

    This stands in for the real §IF-02 electrostatic field model (quasi-
    static FEM/BEM solve of electrode potential/boundary conditions/material
    permittivity) — it is a deliberately simple inverse-power fringing decay,
    not a validated field solve, exactly the same disclosure fs_dome/
    detent_torque/bridge_transfer above carry for their own domains. A real
    solver drops in later with the same ``(distance_mm[], delta_c_fF[])``
    return shape.

    Model, disclosed:
        ΔC(d) = C0 / (1 + (d_eff / D0) ** N)
        d_eff = d + cover_thickness_mm / cover_dielectric_constant
                  + (GLOVE_STANDOFF_MM if is_glove else 0)

    - ``C0`` scales with ``electrode_area_mm2`` via the illustrative
      ``_C0_FF_PER_MM2`` coefficient — a bigger electrode couples more
      fringing field at zero standoff, not a fitted/measured sensitivity.
    - The cover is modeled as a series dielectric slab: a cover of thickness
      ``cover_thickness_mm`` and relative permittivity
      ``cover_dielectric_constant`` is electrically equivalent, in the usual
      parallel-plate/series-capacitor sense, to an extra
      ``cover_thickness_mm / cover_dielectric_constant`` mm of air standoff —
      a textbook simplification, not a fringing-aware solve of the actual
      cover geometry.
    - A glove adds a fixed extra standoff (``_GLOVE_STANDOFF_MM``) rather
      than any specific glove's measured thickness/permittivity.

    ΔC(d) is strictly monotonically decreasing in ``d`` for these parameters
    (higher ``d_eff`` ⇒ smaller ΔC), and any increase in ``d_eff`` (from a
    thicker/lower-permittivity cover, or a glove) shifts the whole curve down
    at every nominal distance — see the regression tests in
    ``apps/api/tests/test_fs_model_proximity.py``.
    """
    c0_ff = _C0_FF_PER_MM2 * electrode_area_mm2
    cover_standoff_mm = cover_thickness_mm / cover_dielectric_constant
    glove_standoff_mm = _GLOVE_STANDOFF_MM if is_glove else 0.0

    distance_mm = np.linspace(distance_min_mm, distance_max_mm, num_points)
    d_eff_mm = distance_mm + cover_standoff_mm + glove_standoff_mm
    delta_c_fF = c0_ff / (1.0 + (d_eff_mm / _D0_MM) ** _N_DECAY)
    return distance_mm.tolist(), delta_c_fF.tolist()


def derive_asic_gesture_summary(
    distance_mm: list[float],
    delta_c_fF: list[float],
    gain_counts_per_fF: float = 50.0,
    offset_counts: float = 200.0,
    threshold_counts: float = 260.0,
) -> dict:
    """§IF-03 ASIC behavioral model + threshold gesture decision, reduced to
    summary numbers (not a full Feature/State timeline — see §IF-04, out of
    scope for this vertical slice).

    ``raw_count = ΔC · gain + offset`` is a fixed illustrative linear
    ADC-count transform standing in for a real calibrated ASIC Gain/offset/
    ADC behavioral model. ``detected`` is a plain fixed-threshold crossing
    standing in for the real §IF-04 Algorithm Twin's Feature/State/Threshold
    gesture decision (no debounce, no state machine, no confidence score).

    Returns ``raw_counts`` (ADC counts, same length/order as the inputs),
    ``detected`` (bool per point), and ``max_reliable_distance_mm``: the
    farthest distance in the swept range at which ``raw_count`` is still at
    or above ``threshold_counts``, found by linear interpolation of the
    swept curve (not a fresh analytic solve — mirrors the SPICE worker's
    ``worst_case_logic_low_margin``, which is likewise read off its swept
    array). Two edge cases are clamped rather than left undefined: if the
    threshold is never reached anywhere in the sweep (e.g. a thick cover
    plus a glove), ``max_reliable_distance_mm`` is reported as
    ``distance_mm[0]`` (i.e. not reliably detectable within the modeled
    range); if it is exceeded even at the farthest swept point,
    it is reported as ``distance_mm[-1]``.
    """
    raw_counts = [offset_counts + gain_counts_per_fF * dc for dc in delta_c_fF]
    detected = [rc >= threshold_counts for rc in raw_counts]

    raw_arr = np.asarray(raw_counts, dtype=float)
    dist_arr = np.asarray(distance_mm, dtype=float)
    if raw_arr.max() < threshold_counts:
        max_reliable_distance_mm = float(dist_arr[0])
    elif raw_arr.min() >= threshold_counts:
        max_reliable_distance_mm = float(dist_arr[-1])
    else:
        # raw_counts is monotonically decreasing in distance (ΔC decays with
        # distance and the ASIC transform above is linear increasing), so
        # reversing both arrays gives np.interp the increasing xp it needs.
        max_reliable_distance_mm = float(np.interp(threshold_counts, raw_arr[::-1], dist_arr[::-1]))

    return {
        "raw_counts": raw_counts,
        "detected": detected,
        "max_reliable_distance_mm": max_reliable_distance_mm,
    }
