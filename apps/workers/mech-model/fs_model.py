"""Analytical prediction curves for the mech-model worker.

Each model type keeps the same (xs, ys) return shape but describes a
different physical characteristic, selected per simulation run via the
``model_type`` parameter:

- ``fs_dome``         — Force–Stroke curve of a TACT switch metal dome (mm, mN)
- ``detent_torque``   — detent torque of a rotary encoder (deg, mN·m)
- ``bridge_transfer`` — ratiometric output of a piezoresistive MEMS
  pressure-sensor bridge (kPa, mV)

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
