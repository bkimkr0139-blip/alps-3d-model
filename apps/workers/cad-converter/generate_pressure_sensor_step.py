"""Generates a synthetic multi-part MEMS pressure-sensor STEP assembly
(HSPPAD-style piezoresistive die in a lidded package with a pressure port)
as a named XCAF assembly — same conventions as generate_sample_step.py
(Z-up, mm, absolute coordinates baked into each solid, STEPCAFControl_Writer
so part names survive the STEP round trip).

"Package Substrate", "Silicon Die", "Metal Lid", "Pressure Port" and
"Solder Balls" must exactly match the seeded Component names in
scripts/seed_golden_dataset.py — the viewer maps GLB node names to components
by name. Materials come from convert.py MATERIAL_BY_KEYWORD keywords
("substrate" → FR4, "die" → silicon, "lid" → nickel cap, "port" → PPA,
"solder" → solder).
"""

from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeSphere,
)
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

from generate_sample_step import write_step_assembly

HALF = 2.5  # 5.0 × 5.0 mm package
SUB_TOP = 0.5
DIE_TOP = 0.85
LID_TOP = 1.85
PORT_TOP = 2.65


def _build_substrate():
    return BRepPrimAPI_MakeBox(gp_Pnt(-HALF, -HALF, 0.0), gp_Pnt(HALF, HALF, SUB_TOP)).Shape()


def _build_die():
    return BRepPrimAPI_MakeBox(gp_Pnt(-1.2, -1.2, SUB_TOP), gp_Pnt(1.2, 1.2, DIE_TOP)).Shape()


def _build_lid():
    outer = BRepPrimAPI_MakeBox(gp_Pnt(-2.1, -2.1, DIE_TOP), gp_Pnt(2.1, 2.1, LID_TOP)).Shape()
    # Cavity open at the bottom (over the die)
    cavity = BRepPrimAPI_MakeBox(gp_Pnt(-1.9, -1.9, DIE_TOP), gp_Pnt(1.9, 1.9, LID_TOP - 0.1)).Shape()
    lid = BRepAlgoAPI_Cut(outer, cavity).Shape()
    # Pressure inlet hole through the lid top, aligned with the port
    hole = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, DIE_TOP), gp_Dir(0, 0, 1)), 0.45, LID_TOP - DIE_TOP + 0.2
    ).Shape()
    return BRepAlgoAPI_Cut(lid, hole).Shape()


def _build_port():
    tube = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, LID_TOP), gp_Dir(0, 0, 1)), 0.8, PORT_TOP - LID_TOP
    ).Shape()
    bore = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, LID_TOP - 0.2), gp_Dir(0, 0, 1)), 0.45, PORT_TOP - LID_TOP + 0.4
    ).Shape()
    return BRepAlgoAPI_Cut(tube, bore).Shape()


def _build_solder_balls():
    # 4×4 BGA grid at 1.27 mm pitch, fused into one solid
    balls = None
    for ix in range(4):
        for iy in range(4):
            center = gp_Pnt(-1.905 + ix * 1.27, -1.905 + iy * 1.27, 0.0)
            ball = BRepPrimAPI_MakeSphere(center, 0.25).Shape()
            balls = ball if balls is None else BRepAlgoAPI_Fuse(balls, ball).Shape()
    return balls


def build_assembly_parts() -> list[tuple[str, object]]:
    return [
        ("Package Substrate", _build_substrate()),
        ("Silicon Die", _build_die()),
        ("Metal Lid", _build_lid()),
        ("Pressure Port", _build_port()),
        ("Solder Balls", _build_solder_balls()),
    ]


if __name__ == "__main__":
    import sys

    out_path = sys.argv[1] if len(sys.argv) > 1 else "mems_sensor_asm.step"
    parts = build_assembly_parts()
    write_step_assembly(parts, out_path)
    print(f"wrote {out_path} ({len(parts)} parts)")
