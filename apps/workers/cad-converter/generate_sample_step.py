"""Generates a synthetic multi-part SMT tact-switch STEP assembly to stand in
for a real customer CAD file (§18: "자료가 없을 경우 합성 데이터로 UI/플랫폼
기능만 검증"). Written as a named XCAF assembly (STEPCAFControl_Writer) so the
part names survive the STEP round trip and the converter can emit one named,
PBR-materialized mesh per part.

Ten parts, modeled on a 4.5×4.5 mm SMD tact switch (Z-up, mm, absolute
coordinates baked into each solid). "Metal Dome", "Switch Housing" and
"Contact Pad" must exactly match the seeded Component names in
scripts/seed_golden_dataset.py — the viewer maps GLB node names to components
by name. This is deliberately enough geometry to exercise assembly
tessellation, per-part materials and bbox/volume metadata — not a validated
switch mechanical design.

The interior parts complete the industry-standard 4-terminal construction.
The previous model had three defects against a real tact-switch CAD: the
housing was a solid block (the mechanism sat in a top pocket of a solid
body — no molded cup), the dome rim was electrically connected to nothing
(a real dome rests on stationary contact legs that extend the terminals
inward), and there were only 2 terminals where a 4.5 mm SMD part has 4:

- Switch Housing — reworked into a molded cup: 0.5 mm floor, 0.35 mm walls,
  with an integral centre column supporting the well floor and a ring cavity
  between column and walls that carries the contacts.
- Stationary Contacts — four stamped legs in the ring cavity, rising from
  the floor and bending inward so their tips sit just under the dome rim
  (drawn at readable scale like every cutaway diagram).
- Metal Dome — its base rim now RESTS on those tips, 0.12 mm above the
  centre pad: the visible snap gap (matches ThreeViewer's DOME_TRAVEL_MM).
- Terminal 1–4 — gull-wing terminals on all four sides; 1/2 pair with the
  legs under their inner ends the way a real stamped lead frame does.

"Stationary Contacts" and "Terminal 3/4" are visual detail, deliberately NOT
seeded components (no DB migration needed — same policy as the encoder's
knurl flutes and the pressure sensor's interior).
"""

import math
import sys

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeSphere,
)
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf

HOUSING_HALF = 2.25  # 4.5 × 4.5 mm body
HOUSING_TOP = 3.0
POCKET_RADIUS = 1.8  # Ø3.6 dome well, depth 1.0 from the top face
POCKET_FLOOR = HOUSING_TOP - 1.0  # z = 2.0
# Molded cup: hollowed underside leaves a 0.5 mm floor and 0.35 mm walls;
# the ring cavity between the wall inner face and the centre column carries
# the stationary-contact legs.
INNER_HALF = 1.9
FLOOR_TOP = 0.5
COLUMN_R = 1.55  # supports the well floor under the centre pad (r 1.5)
# Stamped stationary-contact leg (+x profile): foot on the cavity floor,
# riser up the cavity, inward shelf whose top face meets the dome rim.
LEG_HALF_W = 0.3
LEG_TIP_HALF_W = 0.22  # the tip nears the Ø3.6 well wall — narrower ribbon
LEG_T = 0.08
LEG_TIP_TOP = DOME_BASE_Z = 2.2  # rim rests here; 0.12 over the pad top
DOME_R = 3.4
DOME_RIM_R = 1.775  # Ø3.55 base circle
DOME_CENTER_Z = DOME_BASE_Z - math.sqrt(DOME_R**2 - DOME_RIM_R**2)  # ≈ -0.70
DOME_APEX_Z = DOME_CENTER_Z + DOME_R  # ≈ 2.70 — the plunger stem seats here


def _fillet_edges(shape, radius: float, predicate) -> object:
    """Fillet every edge matching predicate; fall back to the unfilleted
    solid on any failure — fillets are cosmetic and must never block
    fixture generation.

    This OCP binding does not build lazily on Add()/IsDone() the way older
    OCCT wrappers do — IsDone() silently reads as False (and Shape() would
    raise) until Build() is called explicitly. Without this, EVERY fillet in
    this file was a no-op (verified: _build_housing() produced the same
    unfilleted 8-face box-with-hole before and after this fix)."""
    try:
        fillet = BRepFilletAPI_MakeFillet(shape)
        added = 0
        explorer = TopExp_Explorer(shape, TopAbs_EDGE)
        while explorer.More():
            edge = TopoDS.Edge(explorer.Current())
            curve = BRepAdaptor_Curve(edge)
            if predicate(curve):
                fillet.Add(radius, edge)
                added += 1
            explorer.Next()
        if added:
            fillet.Build()
            if fillet.IsDone():
                return fillet.Shape()
    except Exception:
        pass
    return shape


def _vertical_edges(curve: BRepAdaptor_Curve) -> bool:
    return curve.GetType() == GeomAbs_Line and abs(curve.Line().Direction().Z()) > 0.999


def _outer_vertical_edges(curve: BRepAdaptor_Curve) -> bool:
    """Vertical edges at the four OUTER corners only. The hollowed cup also
    creates inner-wall corner edges whose 0.35 mm walls are too thin for a
    0.3 mm fillet on both faces — filleting those would fail and the
    fallback above would then drop every fillet, including the outer ones."""
    return _vertical_edges(curve) and max(
        abs(curve.Line().Location().X()), abs(curve.Line().Location().Y())
    ) > HOUSING_HALF - 0.1


def _horizontal_edge_above(z: float):
    def check(curve: BRepAdaptor_Curve) -> bool:
        # Any point on the line works: a horizontal edge has constant Z
        return curve.GetType() == GeomAbs_Line and abs(curve.Line().Direction().Z()) < 1e-6 and (
            curve.Line().Location().Z() > z
        )

    return check


def _circular_edge_at_z(z: float):
    """Matches the pocket-floor-to-wall edge for filleting. A real molded
    part always rounds this reentrant corner — sharp internal corners
    concentrate stress and cause sink marks / mold-release problems; leaving
    it sharp is a modeling shortcut, not an industry-standard representation
    of how this part would actually be made."""

    def check(curve: BRepAdaptor_Curve) -> bool:
        if curve.GetType() != GeomAbs_Circle:
            return False
        return abs(curve.Circle().Location().Z() - z) < 1e-6

    return check


def _rotated_z(shape, angle: float) -> object:
    """Copy of `shape` rotated about the world Z axis (for the ±y legs and
    terminals, stamped from the same +x die)."""
    trsf = gp_Trsf()
    trsf.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), angle)
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def _build_housing():
    housing = BRepPrimAPI_MakeBox(
        gp_Pnt(-HOUSING_HALF, -HOUSING_HALF, 0.0),
        gp_Pnt(HOUSING_HALF, HOUSING_HALF, HOUSING_TOP),
    ).Shape()
    # Dome well opening the top face (the plunger enters through it, so no
    # separate through-hole is needed)
    pocket = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, POCKET_FLOOR), gp_Dir(0, 0, 1)), POCKET_RADIUS, 1.0
    ).Shape()
    housing = BRepAlgoAPI_Cut(housing, pocket).Shape()
    # Hollow the underside into the molded cup — this is what gives the
    # mechanism an interior at all (the contacts live in the ring cavity).
    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(-INNER_HALF, -INNER_HALF, FLOOR_TOP),
        gp_Pnt(INNER_HALF, INNER_HALF, POCKET_FLOOR),
    ).Shape()
    housing = BRepAlgoAPI_Cut(housing, inner).Shape()
    # Fuse the centre column back so the well floor under the contact pad
    # (r 1.5) is supported by material instead of spanning the cavity.
    column = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, FLOOR_TOP), gp_Dir(0, 0, 1)), COLUMN_R, POCKET_FLOOR - FLOOR_TOP
    ).Shape()
    housing = BRepAlgoAPI_Fuse(housing, column).Shape()
    housing = _fillet_edges(housing, 0.15, _circular_edge_at_z(POCKET_FLOOR))
    return _fillet_edges(housing, 0.3, _outer_vertical_edges)


def _build_contact_pad():
    # Gold pad on the well floor, under the dome centre — the contact the
    # snapped-through dome closes against.
    return BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, POCKET_FLOOR), gp_Dir(0, 0, 1)), 1.5, 0.08
    ).Shape()


def _contact_leg() -> object:
    """One stamped stationary-contact leg (+x profile): foot on the cavity
    floor reaching back to the wall inner face, riser up the cavity, and an
    inward shelf whose top face (z = LEG_TIP_TOP) meets the dome rim. Tip
    geometry clears both the column (r 1.55) and the Ø3.6 well wall."""
    foot = BRepPrimAPI_MakeBox(
        gp_Pnt(COLUMN_R, -LEG_HALF_W, FLOOR_TOP),
        gp_Pnt(INNER_HALF, LEG_HALF_W, FLOOR_TOP + LEG_T),
    ).Shape()
    riser = BRepPrimAPI_MakeBox(
        gp_Pnt(1.62, -LEG_TIP_HALF_W, FLOOR_TOP + LEG_T),
        gp_Pnt(1.70, LEG_TIP_HALF_W, LEG_TIP_TOP - LEG_T),
    ).Shape()
    tip = BRepPrimAPI_MakeBox(
        gp_Pnt(1.62, -LEG_TIP_HALF_W, LEG_TIP_TOP - LEG_T),
        gp_Pnt(1.78, LEG_TIP_HALF_W, LEG_TIP_TOP),
    ).Shape()
    return BRepAlgoAPI_Fuse(BRepAlgoAPI_Fuse(foot, riser).Shape(), tip).Shape()


def _build_stationary_contacts():
    # Four legs (±x, ±y) fused into one part — in a real switch they are the
    # inward extensions of the terminal lead frame, and the dome rim rests
    # on all four tips.
    legs = None
    for k in range(4):
        leg = _rotated_z(_contact_leg(), k * math.pi / 2)
        legs = leg if legs is None else BRepAlgoAPI_Fuse(legs, leg).Shape()
    return legs


def _build_metal_dome():
    # Spherical cap whose base rim rests on the four contact tips at
    # DOME_BASE_Z — 0.12 above the pad top, the visible snap gap the dome
    # travels when it snaps through onto the pad. OCCT MakeSphere
    # angle1/angle2 are LATITUDES FROM THE EQUATOR ([-pi/2, pi/2]), not
    # polar angles — the cap runs from the base circle's latitude up to the
    # pole (pi/2).
    base_latitude = math.asin((DOME_BASE_Z - DOME_CENTER_Z) / DOME_R)
    return BRepPrimAPI_MakeSphere(
        gp_Ax2(gp_Pnt(0, 0, DOME_CENTER_Z), gp_Dir(0, 0, 1)),
        DOME_R,
        base_latitude,
        math.pi / 2,
    ).Shape()


def _build_plunger():
    stem = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, DOME_APEX_Z), gp_Dir(0, 0, 1)), 0.7, 3.5 - DOME_APEX_Z
    ).Shape()  # seats on the dome apex, reaches the housing top
    head = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, 3.5), gp_Dir(0, 0, 1)), 1.3, 0.75
    ).Shape()  # z 3.50..4.25 — the pressable button above the body
    plunger = BRepAlgoAPI_Fuse(stem, head).Shape()
    return _fillet_edges(plunger, 0.2, _horizontal_edge_above(4.2))


def _build_epoxy_seal():
    # Translucent seal capping the plunger head (rendered with alpha blend)
    return BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, 4.25), gp_Dir(0, 0, 1)), 1.5, 0.25
    ).Shape()


def _build_terminal(side: int):
    """L-profile SMD gull-wing terminal at the base of one side wall
    (`side` = -1/+1). Both segments stay at |x| >= HOUSING_HALF, touching
    the housing's outer wall face but never crossing into its interior —
    an earlier version had the inner "leg" running from the wall inward to
    x=1.85, 0.4 mm inside the solid housing box. That's invisible with an
    opaque housing but shows up as a plainly-wrong interpenetration the
    moment the housing is rendered translucent (see ThreeViewer's body-
    opacity control) — a real SMD gull-wing lead sits entirely outside the
    package, foot flat on the PCB and a short riser flush against the
    package wall, which is what this now models."""
    foot = BRepPrimAPI_MakeBox(
        gp_Pnt(side * 2.55, -0.6, 0.0), gp_Pnt(side * HOUSING_HALF, 0.6, 0.25)
    ).Shape()
    riser = BRepPrimAPI_MakeBox(
        gp_Pnt(side * HOUSING_HALF, -0.6, 0.0), gp_Pnt(side * (HOUSING_HALF + 0.05), 0.6, 0.9)
    ).Shape()
    return BRepAlgoAPI_Fuse(foot, riser).Shape()


def build_assembly_parts() -> list[tuple[str, object]]:
    return [
        ("Switch Housing", _build_housing()),
        ("Contact Pad", _build_contact_pad()),
        ("Stationary Contacts", _build_stationary_contacts()),
        ("Metal Dome", _build_metal_dome()),
        ("Plunger", _build_plunger()),
        ("Epoxy Seal", _build_epoxy_seal()),
        ("Terminal 1", _build_terminal(-1)),
        ("Terminal 2", _build_terminal(1)),
        # +90° about Z maps the ±x terminal profiles onto the −y/+y sides.
        ("Terminal 3", _rotated_z(_build_terminal(-1), math.pi / 2)),
        ("Terminal 4", _rotated_z(_build_terminal(1), math.pi / 2)),
    ]


def write_step_assembly(parts: list[tuple[str, object]], path: str) -> None:
    # XCAF document + named assembly labels, so part names survive the STEP
    # round trip (read back by the converter's STEPCAFControl_Reader).
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    app = XCAFApp_Application.GetApplication_s()
    doc = app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)[0]
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    asm = shape_tool.NewShape()
    TDataStd_Name.Set_s(asm, TCollection_ExtendedString("TACT_SWITCH_ASM"))
    for name, solid in parts:
        label = shape_tool.AddShape(solid, False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))
        shape_tool.AddComponent(asm, label, TopLoc_Location())
    shape_tool.UpdateAssemblies()

    writer = STEPCAFControl_Writer()
    if not writer.Transfer(doc):
        raise RuntimeError("STEP assembly transfer failed")
    status = writer.Write(path)
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP write failed: {status}")


if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "tact_switch_asm.step"
    parts = build_assembly_parts()
    write_step_assembly(parts, out_path)
    print(f"wrote {out_path} ({len(parts)} parts)")
