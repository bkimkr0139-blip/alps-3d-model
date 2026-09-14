"""Generates a synthetic AirInput capacitive proximity-sensor module STEP
assembly (electrode PCB + ASIC + cover lens, in a puck-style enclosure) as a
named XCAF assembly — same conventions as generate_sample_step.py (Z-up, mm,
absolute coordinates baked into each solid, STEPCAFControl_Writer so part
names survive the STEP round trip).

"Capacitive Electrode PCB" and "Cover Lens" must exactly match the seeded
Component names in scripts/seed_golden_dataset.py — the viewer maps GLB node
names to components by name.

Unlike the other three products, geometry here is genuinely per-variant, not
one shared fixture: Electrode Layout A/B (AGENTS.md "AirInput vertical
slice") differ in real physical ways, not just simulation parameters —
Variant A is a solid center pad (electrode_area_mm2=100), Variant B is a
larger split-ring guard electrode (electrode_area_mm2=160) under a thicker/
lower-permittivity cover. A split ring (not a bigger solid disc) is the
realistic topology here: a closed conductive loop around/near a sense
electrode acts as a shorted turn, so real guard-ring traces are always cut
once — modeled below as a radial notch through the ring.
"""

import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

from generate_sample_step import _fillet_edges, _vertical_edges, write_step_assembly

# Housing/PCB layout shared by both variants (a 34 x 28 mm puck-style module,
# in line with real automotive capacitive proximity/gesture sensor pucks) —
# only the electrode shape and cover-lens thickness genuinely differ between
# variants (see build_assembly_parts). Every part below was hand-checked to
# clear every other part's bounding box with margin (no TACT-style terminal/
# housing interpenetration) at both variants' electrode extents.
HOUSING_X, HOUSING_Y = 17.0, 14.0  # outer half-extents
WALL = 1.5
FLOOR_T = 1.2
Z_TOP = 6.5
INNER_X, INNER_Y = HOUSING_X - WALL, HOUSING_Y - WALL

PCB_X, PCB_Y = 15.0, 12.0  # half-extents (30 x 24 mm board)
PCB_Z0, PCB_Z1 = FLOOR_T, FLOOR_T + 1.6  # rests on the floor, 1.6 mm FR4

ELECTRODE_CENTER = (5.0, 0.0)
PAD_T = 0.08
SPLIT_RING_OUTER_R = 8.5

ASIC_CENTER = (-9.0, 4.0)
RESISTOR_CENTER = (-9.0, 1.0)
CAPACITOR_CENTER = (-9.0, -1.5)
CONNECTOR_CENTER = (-11.0, -8.0)


def _build_housing():
    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(-HOUSING_X, -HOUSING_Y, 0.0), gp_Pnt(HOUSING_X, HOUSING_Y, Z_TOP)
    ).Shape()
    # Open-top cavity (cut extends past Z_TOP so no floating membrane is left
    # at the rim by floating-point rounding) — the Cover Lens caps it, seated
    # flush with the housing's top face, not a separately-modeled lid part.
    cavity = BRepPrimAPI_MakeBox(
        gp_Pnt(-INNER_X, -INNER_Y, FLOOR_T), gp_Pnt(INNER_X, INNER_Y, Z_TOP + 0.1)
    ).Shape()
    housing = BRepAlgoAPI_Cut(outer, cavity).Shape()
    return _fillet_edges(housing, 1.0, _vertical_edges)


def _build_pcb():
    return BRepPrimAPI_MakeBox(
        gp_Pnt(-PCB_X, -PCB_Y, PCB_Z0), gp_Pnt(PCB_X, PCB_Y, PCB_Z1)
    ).Shape()


def _build_electrode(electrode_area_mm2: float, split_ring: bool):
    ex, ey = ELECTRODE_CENTER
    z0, z1 = PCB_Z1, PCB_Z1 + PAD_T
    if not split_ring:
        radius = math.sqrt(electrode_area_mm2 / math.pi)
        return BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(ex, ey, z0), gp_Dir(0, 0, 1)), radius, PAD_T
        ).Shape()

    outer_r = SPLIT_RING_OUTER_R
    inner_r = math.sqrt(outer_r**2 - electrode_area_mm2 / math.pi)
    outer = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(ex, ey, z0), gp_Dir(0, 0, 1)), outer_r, PAD_T).Shape()
    inner = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(ex, ey, z0), gp_Dir(0, 0, 1)), inner_r, PAD_T).Shape()
    ring = BRepAlgoAPI_Cut(outer, inner).Shape()
    notch = BRepPrimAPI_MakeBox(
        gp_Pnt(ex - 0.75, ey + inner_r - 0.5, z0 - 0.05),
        gp_Pnt(ex + 0.75, ey + outer_r + 0.5, z1 + 0.05),
    ).Shape()
    return BRepAlgoAPI_Cut(ring, notch).Shape()


def _build_asic():
    x, y = ASIC_CENTER
    return BRepPrimAPI_MakeBox(
        gp_Pnt(x - 1.5, y - 1.5, PCB_Z1), gp_Pnt(x + 1.5, y + 1.5, PCB_Z1 + 0.9)
    ).Shape()


def _build_resistor():
    x, y = RESISTOR_CENTER
    return BRepPrimAPI_MakeBox(
        gp_Pnt(x - 0.8, y - 0.4, PCB_Z1), gp_Pnt(x + 0.8, y + 0.4, PCB_Z1 + 0.45)
    ).Shape()


def _build_capacitor():
    x, y = CAPACITOR_CENTER
    return BRepPrimAPI_MakeBox(
        gp_Pnt(x - 0.8, y - 0.4, PCB_Z1), gp_Pnt(x + 0.8, y + 0.4, PCB_Z1 + 0.45)
    ).Shape()


def _build_connector():
    x, y = CONNECTOR_CENTER
    return BRepPrimAPI_MakeBox(
        gp_Pnt(x - 3.0, y - 1.5, PCB_Z1), gp_Pnt(x + 3.0, y + 1.5, PCB_Z1 + 2.0)
    ).Shape()


def _build_lens(cover_thickness_mm: float):
    # 0.2 mm clearance inside the housing's inner cavity on every side — a
    # real seated lens, not sized to exactly coincide with the wall (that
    # earlier TACT terminal bug was exactly this kind of zero-clearance fit).
    clear = 0.2
    x0, y0 = INNER_X - clear, INNER_Y - clear
    return BRepPrimAPI_MakeBox(
        gp_Pnt(-x0, -y0, Z_TOP - cover_thickness_mm), gp_Pnt(x0, y0, Z_TOP)
    ).Shape()


def build_assembly_parts(
    electrode_area_mm2: float, cover_thickness_mm: float, split_ring: bool
) -> list[tuple[str, object]]:
    return [
        ("AirInput Housing", _build_housing()),
        ("Capacitive Electrode PCB", _build_pcb()),
        (
            "Split-Ring Electrode" if split_ring else "Electrode Pad",
            _build_electrode(electrode_area_mm2, split_ring),
        ),
        ("Capacitive Sensing ASIC", _build_asic()),
        ("Filter Resistor", _build_resistor()),
        ("Decoupling Capacitor", _build_capacitor()),
        ("FPC Connector", _build_connector()),
        ("Cover Lens", _build_lens(cover_thickness_mm)),
    ]


# Variant A/B electrode/cover numbers must match AIRINPUT_VARIANTS in
# scripts/seed_golden_dataset.py (and AGENTS.md's documented values) exactly
# — this is real per-variant geometry, not illustrative-only metadata.
VARIANTS = {
    "a": dict(electrode_area_mm2=100.0, cover_thickness_mm=1.0, split_ring=False),
    "b": dict(electrode_area_mm2=160.0, cover_thickness_mm=1.2, split_ring=True),
}


if __name__ == "__main__":
    import sys

    variant = sys.argv[1] if len(sys.argv) > 1 else "a"
    out_path = sys.argv[2] if len(sys.argv) > 2 else f"airinput_sensor_{variant}.step"
    parts = build_assembly_parts(**VARIANTS[variant])
    write_step_assembly(parts, out_path)
    print(f"wrote {out_path} ({len(parts)} parts)")
