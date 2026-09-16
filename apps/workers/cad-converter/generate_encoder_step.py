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

The newer parts (Dial, Rotor Hub, Wiper Contacts, Stator Stand-offs,
Retaining Washer) complete the real RK09-style mechanism stack: the dial
sleeves the shaft, the hub couples the contact rotor to the shaft, the
wipers bridge rotor→stator, the stand-offs carry the stator off the base,
and the wave washer retains the stack. They are visual/mechanical detail —
deliberately NOT seeded components (no DB migration needed).
"""

import math

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

from generate_sample_step import _fillet_edges, _vertical_edges, write_step_assembly

HALF = 6.25  # 12.5 × 12.5 mm body
FRAME_BOTTOM = 1.5
FRAME_TOP = 10.5
WALL = 1.0
SHAFT_TOP = FRAME_TOP + 13.0  # shaft runs 10.5 → 23.5


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


def _build_dial() -> object:
    # Ø11.6 knurled control dial sleeving the shaft: a solid cap with a
    # socket that recesses the shaft top, and 16 fluted grip cylinders
    # around the skirt (real user-facing knob, previously missing).
    body = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, 16.5), gp_Dir(0, 0, 1)), 5.8, 7.0
    ).Shape()
    socket = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, 19.0), gp_Dir(0, 0, 1)), 3.05, 4.5
    ).Shape()
    dial = BRepAlgoAPI_Cut(body, socket).Shape()
    for i in range(16):
        a = i * math.pi / 8.0
        flute = BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(5.55 * math.cos(a), 5.55 * math.sin(a), 17.2), gp_Dir(0, 0, 1)),
            0.38,
            5.6,
        ).Shape()
        dial = BRepAlgoAPI_Fuse(dial, flute).Shape()
    return dial


def _build_rotor_hub() -> object:
    # Stainless hub coupling the contact rotor to the shaft: rises from the
    # rotor top through the frame bushing line (z 10.5) where the shaft
    # begins — the previously floating rotor now has its drive member.
    hub = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, 4.65), gp_Dir(0, 0, 1)), 1.7, 5.85
    ).Shape()
    collar = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, 4.65), gp_Dir(0, 0, 1)), 2.4, 0.75
    ).Shape()
    return BRepAlgoAPI_Fuse(hub, collar).Shape()


def _build_wiper_contacts() -> object:
    # Pair of gold contact fingers riding on the rotor underside, pressing
    # onto the stator disc — the actual potentiometer/switch connection.
    fingers = None
    for sx in (-3.3, 3.3):
        f = BRepPrimAPI_MakeBox(
            gp_Pnt(sx - 0.45, -0.18, 4.05), gp_Pnt(sx + 0.45, 0.18, 4.5)
        ).Shape()
        fingers = f if fingers is None else BRepAlgoAPI_Fuse(fingers, f).Shape()
    return fingers


def _build_stator_standoffs() -> object:
    # Three PBT posts carrying the contact stator disc off the base (the
    # disc previously floated mid-air). Angles chosen clear of the detent
    # spring (+Y leaf) and the wiper plane (X axis).
    posts = None
    for a in (math.pi / 6, math.pi * 5 / 6, math.pi * 3 / 2):
        p = BRepPrimAPI_MakeCylinder(
            gp_Ax2(gp_Pnt(3.6 * math.cos(a), 3.6 * math.sin(a), FRAME_BOTTOM), gp_Dir(0, 0, 1)),
            0.7,
            2.5,
        ).Shape()
        posts = p if posts is None else BRepAlgoAPI_Fuse(posts, p).Shape()
    return posts


def _build_retaining_washer() -> object:
    # Spring-steel wave washer retaining the rotor stack on the shaft line.
    outer = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, 8.6), gp_Dir(0, 0, 1)), 3.4, 0.2
    ).Shape()
    inner = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(0, 0, 8.55), gp_Dir(0, 0, 1)), 1.75, 0.3
    ).Shape()
    return BRepAlgoAPI_Cut(outer, inner).Shape()


def build_assembly_parts() -> list[tuple[str, object]]:
    return [
        ("Base", _build_base()),
        ("Encoder Frame", _build_frame()),
        ("Shaft", _build_shaft()),
        ("Detent Spring", _build_detent_spring()),
        ("Contact Stator", _build_contact_stator()),
        ("Contact Rotor", _build_contact_rotor()),
        ("Rotor Hub", _build_rotor_hub()),
        ("Wiper Contacts", _build_wiper_contacts()),
        ("Stator Stand-offs", _build_stator_standoffs()),
        ("Retaining Washer", _build_retaining_washer()),
        ("Dial", _build_dial()),
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
