"""Generates a synthetic multi-part rotary-encoder STEP assembly (RK09K-style
incremental encoder with integrated push switch) as a named XCAF assembly —
same conventions as generate_sample_step.py (Z-up, mm, absolute coordinates
baked into each solid, STEPCAFControl_Writer so part names survive the STEP
round trip).

"Encoder Frame", "Shaft", "Detent Spring", "Contact Rotor", "Contact Stator"
and "Base" must exactly match the seeded Component names in
scripts/seed_golden_dataset.py — the viewer maps GLB node names to components
by name. Materials come from convert.py MATERIAL_BY_KEYWORD keywords
("encoder frame" → aluminum, "shaft" → stainless, "detent" → spring steel,
"contact" → gold, "terminal" → silver, "base" → PBT).
"""

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

from generate_sample_step import _fillet_edges, _vertical_edges, write_step_assembly

HALF = 6.25  # 12.5 × 12.5 mm body
FRAME_BOTTOM = 1.5
FRAME_TOP = 10.5
WALL = 1.0


def _build_base():
    return BRepPrimAPI_MakeBox(gp_Pnt(-HALF, -HALF, 0.0), gp_Pnt(HALF, HALF, FRAME_BOTTOM)).Shape()


def _build_frame():
    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(-HALF, -HALF, FRAME_BOTTOM), gp_Pnt(HALF, HALF, FRAME_TOP)
    ).Shape()
    # Open-top cavity: the frame is four walls; the shaft enters through it
    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(-HALF + WALL, -HALF + WALL, FRAME_BOTTOM), gp_Pnt(HALF - WALL, HALF - WALL, FRAME_TOP)
    ).Shape()
    frame = BRepAlgoAPI_Cut(outer, inner).Shape()
    return _fillet_edges(frame, 0.6, _vertical_edges)


def _build_shaft():
    # Ø6 × 13 mm stainless shaft rising out of the frame top
    return BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, FRAME_TOP), gp_Dir(0, 0, 1)), 3.0, 13.0
    ).Shape()


def _build_detent_spring():
    # Thin leaf spring pressing on the rotor hub, with a small mounting boss
    leaf = BRepPrimAPI_MakeBox(gp_Pnt(-2.0, 3.6, 2.0), gp_Pnt(2.0, 3.9, 8.0)).Shape()
    boss = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 4.9, 2.0), gp_Dir(0, 0, 1)), 1.0, 0.3
    ).Shape()
    return BRepAlgoAPI_Fuse(leaf, boss).Shape()


def _build_contact_stator():
    return BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, 4.0), gp_Dir(0, 0, 1)), 5.0, 0.25
    ).Shape()


def _build_contact_rotor():
    return BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, 4.35), gp_Dir(0, 0, 1)), 4.4, 0.3
    ).Shape()


def _build_terminal(index: int) -> object:
    # Three through-hole pins protruding below the base, along the front edge
    x = (-3.5, 0.0, 3.5)[index]
    return BRepPrimAPI_MakeBox(gp_Pnt(x - 0.5, -5.7, -1.5), gp_Pnt(x + 0.5, -5.3, 1.0)).Shape()


def build_assembly_parts() -> list[tuple[str, object]]:
    return [
        ("Base", _build_base()),
        ("Encoder Frame", _build_frame()),
        ("Shaft", _build_shaft()),
        ("Detent Spring", _build_detent_spring()),
        ("Contact Stator", _build_contact_stator()),
        ("Contact Rotor", _build_contact_rotor()),
        ("Terminal A", _build_terminal(0)),
        ("Terminal B", _build_terminal(1)),
        ("Terminal C", _build_terminal(2)),
    ]


if __name__ == "__main__":
    import sys

    out_path = sys.argv[1] if len(sys.argv) > 1 else "rotary_encoder_asm.step"
    parts = build_assembly_parts()
    write_step_assembly(parts, out_path)
    print(f"wrote {out_path} ({len(parts)} parts)")
