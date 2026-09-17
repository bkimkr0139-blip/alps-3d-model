"""Generates a synthetic multi-part MEMS pressure-sensor STEP assembly
(HSPPAD-style absolute piezoresistive die in a seam-welded lidded package
with a pressure port) as a named XCAF assembly — same conventions as
generate_sample_step.py (Z-up, mm, absolute coordinates baked into each
solid, STEPCAFControl_Writer so part names survive the STEP round trip).

"Package Substrate", "Silicon Die", "Metal Lid", "Pressure Port" and
"Solder Balls" must exactly match the seeded Component names in
scripts/seed_golden_dataset.py — the viewer maps GLB node names to components
by name.

The interior parts complete the industrial absolute-pressure construction.
The previous model had two defects against any real CAD: the Metal Lid's
walls started 0.35 mm above the substrate (seated on nothing — the die top
was the cavity floor and the lid touched only air), and the die was a
featureless box. The rework models how such a sensor is actually built:

- Seal Ring — Kovar ring standing on the substrate; the Metal Lid
  seam-welds onto it (the lid's bottom face now lands ON the ring).
- Die Attach Epoxy — silver-filled epoxy film under the die.
- Silicon Die — reworked: its top face carries an etched cavity that acts
  as the sealed reference vacuum of an absolute sensor.
- Sensing Diaphragm — thin membrane plate bonded over the etched cavity
  opening (wafer-level cap construction); port pressure acts on it from
  above through the lid hole.
- Piezo Bridge Resistors — four Wheatstone strain bars at the diaphragm
  edge (drawn at readable scale, like every MEMS cutaway diagram).
- Die Bond Pads (aluminium, on the die) / Substrate Bond Pads (Ni-Au, on
  the substrate) — the four landing pads, one bridge bond each.
- Au Bond Wires — four ball/stitch wires swept as Bezier tubes from die
  pads down to substrate pads.

Film/wire/pad thicknesses are exaggerated a few times over reality
(~25 µm wires, ~1 µm metallisation) so the interior reads in the exploded
view — same visual-scale policy as the encoder's knurl flutes. The new
parts are visual detail, deliberately NOT seeded components (no DB
migration needed).
"""

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipe
from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeSphere,
)
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.Geom import Geom_BezierCurve
from OCP.collections import Array1_gp_Pnt
from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt

from generate_sample_step import write_step_assembly

HALF = 2.5  # 5.0 × 5.0 mm package
SUB_TOP = 0.5
ATTACH_TOP = 0.54  # 40 µm attach film
DIE_BOT = ATTACH_TOP
DIE_TOP = DIE_BOT + 0.35  # 0.89
CAVITY_BOT = DIE_TOP - 0.08  # etched cavity floor
DIAPHRAGM_TOP = DIE_TOP + 0.01  # cap plate proud of the die face
RING_TOP = 0.62  # seal ring height above the substrate
LID_TOP = 1.85
PORT_TOP = 2.65
WIRE_R = 0.03  # ~25 µm real wire, doubled for visibility
DIE_HALF = 1.2
RING_OUTER = 1.98
RING_INNER = 1.62
LID_CAVITY = 1.9  # lid wall inner face — ring outer tucks under it


def _build_substrate():
    return BRepPrimAPI_MakeBox(gp_Pnt(-HALF, -HALF, 0.0), gp_Pnt(HALF, HALF, SUB_TOP)).Shape()


def _build_solder_balls():
    # 4×4 BGA grid at 1.27 mm pitch, fused into one solid
    balls = None
    for ix in range(4):
        for iy in range(4):
            center = gp_Pnt(-1.905 + ix * 1.27, -1.905 + iy * 1.27, 0.0)
            ball = BRepPrimAPI_MakeSphere(center, 0.25).Shape()
            balls = ball if balls is None else BRepAlgoAPI_Fuse(balls, ball).Shape()
    return balls


def _build_die_attach():
    # Silver-filled epoxy squeeze-out: slightly larger than the die footprint.
    return BRepPrimAPI_MakeBox(
        gp_Pnt(-1.25, -1.25, SUB_TOP), gp_Pnt(1.25, 1.25, ATTACH_TOP)
    ).Shape()


def _build_die():
    # Silicon die with the etched reference cavity in its top face — the
    # membrane plate ("Sensing Diaphragm") bonds over the opening.
    die = BRepPrimAPI_MakeBox(
        gp_Pnt(-DIE_HALF, -DIE_HALF, DIE_BOT), gp_Pnt(DIE_HALF, DIE_HALF, DIE_TOP)
    ).Shape()
    cavity = BRepPrimAPI_MakeBox(
        gp_Pnt(-0.6, -0.6, CAVITY_BOT), gp_Pnt(0.6, 0.6, DIE_TOP)
    ).Shape()
    return BRepAlgoAPI_Cut(die, cavity).Shape()


def _build_diaphragm():
    # Membrane cap plate covering the cavity opening (1.36 mm square, 10 µm
    # drawn thickness) — seals the reference vacuum underneath it.
    return BRepPrimAPI_MakeBox(
        gp_Pnt(-0.68, -0.68, DIE_TOP), gp_Pnt(0.68, 0.68, DIAPHRAGM_TOP)
    ).Shape()


def _build_piezo_resistors():
    # Four Wheatstone strain bars at the diaphragm edge, mid-side N/E/S/W,
    # oriented along the edge they straddle. Drawn at readable scale — real
    # implanted resistors are microns.
    bars = None
    for sx, sy, w, d in ((0.45, 0.0, 0.05, 0.18), (-0.45, 0.0, 0.05, 0.18),
                         (0.0, 0.45, 0.18, 0.05), (0.0, -0.45, 0.18, 0.05)):
        bar = BRepPrimAPI_MakeBox(
            gp_Pnt(sx - w / 2, sy - d / 2, DIAPHRAGM_TOP),
            gp_Pnt(sx + w / 2, sy + d / 2, DIAPHRAGM_TOP + 0.015),
        ).Shape()
        bars = bar if bars is None else BRepAlgoAPI_Fuse(bars, bar).Shape()
    return bars


def _build_die_bond_pads():
    # Four aluminium pads on the die top face, edge-midpoints.
    pads = None
    for px, py in ((1.05, 0.0), (-1.05, 0.0), (0.0, 1.05), (0.0, -1.05)):
        pad = BRepPrimAPI_MakeBox(
            gp_Pnt(px - 0.125, py - 0.09, DIE_TOP),
            gp_Pnt(px + 0.125, py + 0.09, DIE_TOP + 0.015),
        ).Shape()
        pads = pad if pads is None else BRepAlgoAPI_Fuse(pads, pad).Shape()
    return pads


def _build_substrate_bond_pads():
    # Four Ni-Au pads on the substrate top, in the corridor between the die
    # edge (1.2) and the seal ring inner face (1.62).
    pads = None
    for px, py in ((1.38, 0.0), (-1.38, 0.0), (0.0, 1.38), (0.0, -1.38)):
        pad = BRepPrimAPI_MakeBox(
            gp_Pnt(px - 0.13, py - 0.09, SUB_TOP),
            gp_Pnt(px + 0.13, py + 0.09, SUB_TOP + 0.015),
        ).Shape()
        pads = pad if pads is None else BRepAlgoAPI_Fuse(pads, pad).Shape()
    return pads


def _bond_wire(p0: gp_Pnt, p1: gp_Pnt) -> object:
    # Ball/stitch loop as a quadratic Bezier spine swept with a circular
    # profile (BRepPrimAPI_MakePipe) — the STEP-side twin of the ASIC
    # package twin's Au tube wires.
    mid = gp_Pnt((p0.X() + p1.X()) / 2, (p0.Y() + p1.Y()) / 2, max(p0.Z(), p1.Z()) + 0.06)
    pts = Array1_gp_Pnt(1, 3)
    pts.SetValue(1, p0)
    pts.SetValue(2, mid)
    pts.SetValue(3, p1)
    spine = BRepBuilderAPI_MakeWire(
        BRepBuilderAPI_MakeEdge(Geom_BezierCurve(pts)).Edge()
    ).Wire()
    tangent = gp_Dir(mid.X() - p0.X(), mid.Y() - p0.Y(), mid.Z() - p0.Z())
    profile = BRepBuilderAPI_MakeWire(
        BRepBuilderAPI_MakeEdge(gp_Circ(gp_Ax2(p0, tangent), WIRE_R)).Edge()
    ).Wire()
    return BRepOffsetAPI_MakePipe(spine, profile).Shape()


def _build_bond_wires():
    wires = None
    for dx, dy in ((1.05, 0.0), (-1.05, 0.0), (0.0, 1.05), (0.0, -1.05)):
        start = gp_Pnt(dx, dy, DIE_TOP + 0.015)
        end = gp_Pnt(1.38 if dy == 0 else 0.0, 0.0 if dy == 0 else 1.38, SUB_TOP + 0.015)
        if dx < 0 or dy < 0:
            end = gp_Pnt(-1.38 if dy == 0 else 0.0, 0.0 if dy == 0 else -1.38, SUB_TOP + 0.015)
        w = _bond_wire(start, end)
        wires = w if wires is None else BRepAlgoAPI_Fuse(wires, w).Shape()
    return wires


def _build_seal_ring():
    # Kovar ring standing on the substrate; the lid lands on its top face
    # (seam-weld line), its outer edge tucked under the lid wall footprint.
    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(-RING_OUTER, -RING_OUTER, SUB_TOP), gp_Pnt(RING_OUTER, RING_OUTER, RING_TOP)
    ).Shape()
    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(-RING_INNER, -RING_INNER, SUB_TOP - 0.1),
        gp_Pnt(RING_INNER, RING_INNER, RING_TOP + 0.1),
    ).Shape()
    return BRepAlgoAPI_Cut(outer, inner).Shape()


def _build_lid():
    # Nickel lid seated ON the seal ring (bottom face at RING_TOP, not
    # floating above the substrate): four walls around a cavity that clears
    # the die, wires and ring, with the pressure inlet hole through the top.
    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(-2.1, -2.1, RING_TOP), gp_Pnt(2.1, 2.1, LID_TOP)
    ).Shape()
    cavity = BRepPrimAPI_MakeBox(
        gp_Pnt(-LID_CAVITY, -LID_CAVITY, RING_TOP), gp_Pnt(LID_CAVITY, LID_CAVITY, LID_TOP - 0.1)
    ).Shape()
    lid = BRepAlgoAPI_Cut(outer, cavity).Shape()
    # Pressure inlet hole through the lid top, aligned with the port and
    # opening onto the diaphragm below.
    hole = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, RING_TOP), gp_Dir(0, 0, 1)), 0.45, LID_TOP - RING_TOP + 0.2
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


def build_assembly_parts() -> list[tuple[str, object]]:
    return [
        ("Package Substrate", _build_substrate()),
        ("Solder Balls", _build_solder_balls()),
        ("Substrate Bond Pads", _build_substrate_bond_pads()),
        ("Die Attach Epoxy", _build_die_attach()),
        ("Silicon Die", _build_die()),
        ("Sensing Diaphragm", _build_diaphragm()),
        ("Piezo Bridge Resistors", _build_piezo_resistors()),
        ("Die Bond Pads", _build_die_bond_pads()),
        ("Au Bond Wires", _build_bond_wires()),
        ("Seal Ring", _build_seal_ring()),
        ("Metal Lid", _build_lid()),
        ("Pressure Port", _build_port()),
    ]


if __name__ == "__main__":
    import sys

    out_path = sys.argv[1] if len(sys.argv) > 1 else "mems_sensor_asm.step"
    parts = build_assembly_parts()
    write_step_assembly(parts, out_path)
    print(f"wrote {out_path} ({len(parts)} parts)")
