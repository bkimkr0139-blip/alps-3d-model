"""Generates a synthetic multi-part SMT tact-switch STEP assembly to stand in
for a real customer CAD file (§18: "자료가 없을 경우 합성 데이터로 UI/플랫폼
기능만 검증"). Written as a named XCAF assembly (STEPCAFControl_Writer) so the
part names survive the STEP round trip and the converter can emit one named,
PBR-materialized mesh per part.

Seven parts, modeled on a 4.5×4.5 mm SMD tact switch (Z-up, mm, absolute
coordinates baked into each solid). "Metal Dome", "Switch Housing" and
"Contact Pad" must exactly match the seeded Component names in
scripts/seed_golden_dataset.py — the viewer maps GLB node names to components
by name. This is deliberately enough geometry to exercise assembly
tessellation, per-part materials and bbox/volume metadata — not a validated
switch mechanical design.
"""

import math
import sys

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
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
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

HOUSING_HALF = 2.25  # 4.5 × 4.5 mm body
HOUSING_TOP = 3.0
POCKET_RADIUS = 1.8  # Ø3.6 dome pocket, depth 1.0 from the top face
POCKET_FLOOR = HOUSING_TOP - 1.0  # z = 2.0


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


def _horizontal_edge_above(z: float):
    def check(curve: BRepAdaptor_Curve) -> bool:
        # Any point on the line works: a horizontal edge has constant Z
        return curve.GetType() == GeomAbs_Line and abs(curve.Line().Direction().Z()) < 1e-6 and (
            curve.Line().Location().Z() > z
        )

    return check


def _build_housing():
    housing = BRepPrimAPI_MakeBox(
        gp_Pnt(-HOUSING_HALF, -HOUSING_HALF, 0.0),
        gp_Pnt(HOUSING_HALF, HOUSING_HALF, HOUSING_TOP),
    ).Shape()
    # Dome pocket opening the top face (the plunger enters through it, so no
    # separate through-hole is needed)
    pocket = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, POCKET_FLOOR), gp_Dir(0, 0, 1)), POCKET_RADIUS, 1.0
    ).Shape()
    housing = BRepAlgoAPI_Cut(housing, pocket).Shape()
    housing = _fillet_edges(housing, 0.15, _circular_edge_at_z(POCKET_FLOOR))
    return _fillet_edges(housing, 0.3, _vertical_edges)


def _build_contact_pad():
    # Gold pad on the pocket floor, under the dome
    return BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, POCKET_FLOOR), gp_Dir(0, 0, 1)), 1.5, 0.08
    ).Shape()


def _build_metal_dome():
    # Spherical cap: base circle Ø3.55 rests on the contact pad (z≈2.08),
    # apex ≈ z 2.58 — a snap dome, not a validated membrane design.
    # OCCT MakeSphere angle1/angle2 are LATITUDES FROM THE EQUATOR
    # ([-pi/2, pi/2]), not polar angles — the cap runs from the base circle's
    # latitude up to the pole (pi/2).
    dome_radius = 3.4
    center_z = -0.82
    base_latitude = math.asin((2.08 - center_z) / dome_radius)  # ≈1.0196 rad
    return BRepPrimAPI_MakeSphere(
        gp_Ax2(gp_Pnt(0, 0, center_z), gp_Dir(0, 0, 1)),
        dome_radius,
        base_latitude,
        math.pi / 2,
    ).Shape()


def _build_plunger():
    stem = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, 2.58), gp_Dir(0, 0, 1)), 0.7, 0.92
    ).Shape()  # z 2.58..3.50 — reaches the dome apex
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
        ("Metal Dome", _build_metal_dome()),
        ("Plunger", _build_plunger()),
        ("Epoxy Seal", _build_epoxy_seal()),
        ("Terminal 1", _build_terminal(-1)),
        ("Terminal 2", _build_terminal(1)),
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
