"""STEP -> glTF/GLB conversion: OCP (OCCT bindings) tessellates, trimesh exports.

Avoids conda-only `pythonocc-core` — `cadquery-ocp` is pip-installable and
wraps the same OCCT kernel (§8.3 CAD row).

Assembly-aware since the fixture became a named XCAF assembly: part names are
read back with STEPCAFControl_Reader and each solid becomes its own glTF node
carrying a PBR material chosen from its name (metal dome → stainless, contact
→ gold, …). Only a total CAF read failure falls back to the old plain-reader
merged-mesh path.
"""

import io
import tempfile

import numpy as np
import trimesh
from OCP.BRep import BRep_Tool
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.STEPControl import STEPControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.collections import Sequence_TDF_Label
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from trimesh.visual.material import PBRMaterial

LINEAR_DEFLECTION = 0.02  # mm — near-CAD tessellation for a photoreal viewer
ANGULAR_DEFLECTION = 0.2  # rad — keeps large curved surfaces smooth

# First keyword hit (case-insensitive, checked against the STEP part name)
# wins. Factors must be proper floats — trimesh's exporter drops ints.
# Keyword order matters: "encoder frame" must be checked before anything a
# more generic keyword would grab first.
MATERIAL_BY_KEYWORD: list[tuple[str, PBRMaterial]] = [
    ("metal dome", PBRMaterial(name="stainless_steel", baseColorFactor=[0.75, 0.76, 0.78, 1.0],
                               metallicFactor=1.0, roughnessFactor=0.25, doubleSided=True)),
    ("contact", PBRMaterial(name="gold", baseColorFactor=[0.94, 0.78, 0.35, 1.0],
                            metallicFactor=1.0, roughnessFactor=0.2)),
    ("encoder frame", PBRMaterial(name="aluminum", baseColorFactor=[0.64, 0.66, 0.68, 1.0],
                                  metallicFactor=0.9, roughnessFactor=0.35)),
    ("shaft", PBRMaterial(name="stainless_shaft", baseColorFactor=[0.78, 0.79, 0.81, 1.0],
                          metallicFactor=1.0, roughnessFactor=0.2)),
    ("detent", PBRMaterial(name="spring_steel", baseColorFactor=[0.55, 0.58, 0.66, 1.0],
                           metallicFactor=1.0, roughnessFactor=0.3)),
    # MEMS pressure-sensor interior (industrial absolute construction).
    # These entries MUST precede "substrate"/"die": the scan takes the first
    # matching keyword, and e.g. "Substrate Bond Pads" contains "substrate"
    # while "Die Bond Pads" contains "die".
    ("bond wire", PBRMaterial(name="gold_bond_wire", baseColorFactor=[0.94, 0.78, 0.35, 1.0],
                              metallicFactor=1.0, roughnessFactor=0.2)),
    ("seal ring", PBRMaterial(name="kovar_seal", baseColorFactor=[0.70, 0.68, 0.66, 1.0],
                              metallicFactor=0.95, roughnessFactor=0.35)),
    ("diaphragm", PBRMaterial(name="si_membrane", baseColorFactor=[0.44, 0.52, 0.63, 1.0],
                              metallicFactor=0.85, roughnessFactor=0.12)),
    ("die attach", PBRMaterial(name="silver_epoxy", baseColorFactor=[0.56, 0.57, 0.60, 1.0],
                               metallicFactor=0.7, roughnessFactor=0.45)),
    ("die bond pad", PBRMaterial(name="aluminum_pad", baseColorFactor=[0.88, 0.89, 0.91, 1.0],
                                 metallicFactor=0.95, roughnessFactor=0.3)),
    ("bond pad", PBRMaterial(name="eni_gold_pad", baseColorFactor=[0.92, 0.85, 0.55, 1.0],
                             metallicFactor=1.0, roughnessFactor=0.22)),
    ("substrate", PBRMaterial(name="fr4_green", baseColorFactor=[0.05, 0.12, 0.08, 1.0],
                              metallicFactor=0.0, roughnessFactor=0.6)),
    ("die", PBRMaterial(name="silicon", baseColorFactor=[0.32, 0.34, 0.4, 1.0],
                        metallicFactor=0.9, roughnessFactor=0.15)),
    ("lid", PBRMaterial(name="nickel_cap", baseColorFactor=[0.72, 0.73, 0.76, 1.0],
                        metallicFactor=1.0, roughnessFactor=0.3)),
    ("solder", PBRMaterial(name="solder", baseColorFactor=[0.8, 0.82, 0.85, 1.0],
                           metallicFactor=0.85, roughnessFactor=0.4)),
    ("port", PBRMaterial(name="ppa_natural", baseColorFactor=[0.85, 0.83, 0.75, 1.0],
                         metallicFactor=0.0, roughnessFactor=0.45)),
    # Terminals/pins on real ALPS parts are stamped copper alloy (phosphor
    # bronze) — the earlier silver-brass tint read as bare tin plate, not as
    # the warm copper the physical parts show.
    ("terminal", PBRMaterial(name="copper_terminal", baseColorFactor=[0.80, 0.45, 0.28, 1.0],
                             metallicFactor=1.0, roughnessFactor=0.32)),
    ("plunger", PBRMaterial(name="pom_white", baseColorFactor=[0.92, 0.92, 0.9, 1.0],
                            metallicFactor=0.0, roughnessFactor=0.4)),
    # Subtle translucency (0.85, not 0.55): a strongly transparent cap renders
    # with three.js BLEND depth-sorting artifacts — at angles where the cap
    # overlaps the body it looked like the housing was see-through. Single-
    # sided + near-opaque keeps the epoxy look without the ghosting.
    ("epoxy", PBRMaterial(name="epoxy_seal", baseColorFactor=[0.9, 0.92, 0.95, 0.85],
                          metallicFactor=0.0, roughnessFactor=0.25, alphaMode="BLEND")),
    # AirInput module. "pcb" must be checked before "electrode": the PCB
    # part's Component-matching name is "Capacitive Electrode PCB", which
    # contains both substrings — list order (not name substring position)
    # decides which keyword wins, so "pcb" has to come first or the whole
    # board would render as bare copper instead of an FR4 substrate.
    ("pcb", PBRMaterial(name="fr4_green_pcb", baseColorFactor=[0.05, 0.12, 0.08, 1.0],
                        metallicFactor=0.0, roughnessFactor=0.6)),
    ("electrode", PBRMaterial(name="copper_electrode", baseColorFactor=[0.80, 0.50, 0.30, 1.0],
                              metallicFactor=1.0, roughnessFactor=0.35)),
    ("asic", PBRMaterial(name="mold_compound_black", baseColorFactor=[0.08, 0.08, 0.09, 1.0],
                         metallicFactor=0.0, roughnessFactor=0.4)),
    ("resistor", PBRMaterial(name="chip_resistor", baseColorFactor=[0.1, 0.1, 0.11, 1.0],
                             metallicFactor=0.2, roughnessFactor=0.5)),
    ("capacitor", PBRMaterial(name="mlcc_ceramic", baseColorFactor=[0.72, 0.62, 0.45, 1.0],
                              metallicFactor=0.0, roughnessFactor=0.45)),
    ("connector", PBRMaterial(name="connector_nylon", baseColorFactor=[0.88, 0.87, 0.85, 1.0],
                              metallicFactor=0.0, roughnessFactor=0.4)),
    # Same single-sided near-opaque BLEND treatment as "epoxy" above, for the
    # same reason (avoid three.js depth-sort ghosting on a translucent cap).
    ("lens", PBRMaterial(name="pc_lens", baseColorFactor=[0.85, 0.9, 0.95, 0.8],
                         metallicFactor=0.0, roughnessFactor=0.15, alphaMode="BLEND")),
    # Molded LCP reads glossy, not chalky — 0.42 keeps a soft specular sweep
    # across the housing faces instead of the flat matte wash that made the
    # case read as untextured gray clay under bright fill light.
    ("housing", PBRMaterial(name="lcp_black", baseColorFactor=[0.04, 0.04, 0.045, 1.0],
                            metallicFactor=0.0, roughnessFactor=0.42)),
    ("base", PBRMaterial(name="pbt_black", baseColorFactor=[0.06, 0.06, 0.065, 1.0],
                         metallicFactor=0.0, roughnessFactor=0.42)),
    # Rotary-encoder mechanism stack (RK09-style): the dial is the user-facing
    # molded knob, the rotor hub is stainless like the shaft it drives, the
    # stand-offs are the same molded PBT family as the base, the retaining
    # washer is spring steel like the detent. "Wiper Contacts" already hits
    # "contact" → gold further up, so no entry is needed for it here.
    ("dial", PBRMaterial(name="pom_black", baseColorFactor=[0.05, 0.05, 0.055, 1.0],
                         metallicFactor=0.0, roughnessFactor=0.45)),
    ("rotor hub", PBRMaterial(name="stainless_steel", baseColorFactor=[0.78, 0.79, 0.81, 1.0],
                              metallicFactor=1.0, roughnessFactor=0.25)),
    ("stand-off", PBRMaterial(name="pbt_molded", baseColorFactor=[0.06, 0.06, 0.065, 1.0],
                              metallicFactor=0.0, roughnessFactor=0.45)),
    ("washer", PBRMaterial(name="spring_steel", baseColorFactor=[0.55, 0.58, 0.66, 1.0],
                           metallicFactor=1.0, roughnessFactor=0.3)),
]
NEUTRAL_MATERIAL = PBRMaterial(name="neutral", baseColorFactor=[0.62, 0.65, 0.68, 1.0],
                               metallicFactor=0.1, roughnessFactor=0.5)


def _material_for(name: str) -> PBRMaterial:
    lowered = name.lower()
    for keyword, material in MATERIAL_BY_KEYWORD:
        if keyword in lowered:
            return material
    return NEUTRAL_MATERIAL


def _new_xcaf_doc():
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    app = XCAFApp_Application.GetApplication_s()
    return app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)[0]


def _label_name(label: TDF_Label) -> str | None:
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    return None


def _load_xcaf_parts(step_bytes: bytes) -> list[tuple[str, object]] | None:
    """Named solids from a STEP file via XCAF, or None if the CAF read fails
    outright. Plain (non-CAF) STEP files read fine here too — their labels
    just come back unnamed and get 'Part N' + the neutral material."""
    try:
        doc = _new_xcaf_doc()
        reader = STEPCAFControl_Reader()
        if reader.ReadStream("input.step", io.BytesIO(step_bytes)) != IFSelect_RetDone:
            return None
        if not reader.Transfer(doc):
            return None

        shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        free_shapes = Sequence_TDF_Label()
        shape_tool.GetFreeShapes(free_shapes)

        parts: list[tuple[str, object]] = []
        for i in range(1, free_shapes.Length() + 1):
            root = free_shapes.Value(i)
            if shape_tool.IsAssembly_s(root):
                components = Sequence_TDF_Label()
                shape_tool.GetComponents_s(root, components)
                for j in range(1, components.Length() + 1):
                    referred = TDF_Label()
                    label = (
                        referred
                        if shape_tool.GetReferredShape_s(components.Value(j), referred)
                        else components.Value(j)
                    )
                    shape = shape_tool.GetShape_s(label)
                    if shape is not None and not shape.IsNull():
                        parts.append((_label_name(label) or f"Part {len(parts) + 1}", shape))
            else:
                shape = shape_tool.GetShape_s(root)
                if shape is not None and not shape.IsNull():
                    parts.append((_label_name(root) or f"Part {len(parts) + 1}", shape))
        return parts or None
    except Exception:
        return None


def _load_step_shape(step_bytes: bytes):
    """Plain fallback reader (no names, merged shape)."""
    with tempfile.NamedTemporaryFile(suffix=".step", delete=True) as f:
        f.write(step_bytes)
        f.flush()
        reader = STEPControl_Reader()
        status = reader.ReadFile(f.name)
        if status != 1:  # IFSelect_RetDone
            raise ValueError(f"STEP read failed (status={status})")
        reader.TransferRoots()
        return reader.OneShape()


def _tessellate_to_trimesh(shape) -> trimesh.Trimesh:
    BRepMesh_IncrementalMesh(shape, LINEAR_DEFLECTION, False, ANGULAR_DEFLECTION, True)

    all_vertices: list[np.ndarray] = []
    all_faces: list[np.ndarray] = []
    vertex_offset = 0

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is not None:
            transform = location.Transformation()
            n_nodes = triangulation.NbNodes()
            verts = np.empty((n_nodes, 3))
            for i in range(1, n_nodes + 1):
                pnt = triangulation.Node(i).Transformed(transform)
                verts[i - 1] = (pnt.X(), pnt.Y(), pnt.Z())

            # Poly_Triangulation stores raw indices without regard to the
            # face's TopAbs_Orientation. A face made REVERSED by a boolean
            # Cut/Fuse (very common — e.g. the housing's pocket wall) — or,
            # it turns out, just one of a plain BRepPrimAPI_MakeBox's own six
            # faces; box primitives are not uniformly FORWARD — keeps the
            # underlying surface's natural winding, which is backwards
            # relative to the solid's outward normal. Left uncorrected,
            # three.js's default backface culling makes that triangle
            # invisible from outside and visible only from inside — at some
            # rotation angles the camera ray grazes straight through it,
            # reading as "the body went see-through". Flip two indices to
            # restore outward winding whenever the face is REVERSED.
            reversed_face = face.Orientation() == TopAbs_REVERSED
            n_tris = triangulation.NbTriangles()
            faces = np.empty((n_tris, 3), dtype=np.int64)
            for i in range(1, n_tris + 1):
                tri = triangulation.Triangle(i)
                a, b, c = tri.Get()
                if reversed_face:
                    a, b = b, a
                faces[i - 1] = (a - 1 + vertex_offset, b - 1 + vertex_offset, c - 1 + vertex_offset)

            all_vertices.append(verts)
            all_faces.append(faces)
            vertex_offset += n_nodes
        explorer.Next()

    if not all_vertices:
        raise ValueError("STEP file produced no tessellated faces")

    return trimesh.Trimesh(
        vertices=np.vstack(all_vertices), faces=np.vstack(all_faces), process=False
    )


def _volume_mm3(shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return float(props.Mass())


def _convert_assembly(parts: list[tuple[str, object]]) -> tuple[bytes, dict]:
    scene = trimesh.Scene()
    bbox_min = np.full(3, np.inf)
    bbox_max = np.full(3, -np.inf)
    total_volume = 0.0
    total_vertices = 0
    total_triangles = 0
    part_stats: list[dict] = []

    for name, shape in parts:
        mesh = _tessellate_to_trimesh(shape)
        mesh.visual = trimesh.visual.TextureVisuals(material=_material_for(name))
        scene.add_geometry(mesh, node_name=name, geom_name=name)

        lo, hi = mesh.bounds
        bbox_min = np.minimum(bbox_min, lo)
        bbox_max = np.maximum(bbox_max, hi)
        total_volume += _volume_mm3(shape)
        triangles = int(mesh.faces.shape[0])
        total_vertices += int(mesh.vertices.shape[0])
        total_triangles += triangles
        part_stats.append({"name": name, "triangle_count": triangles})

    glb_bytes = trimesh.exchange.gltf.export_glb(scene)
    metadata = {
        "bbox_min_mm": bbox_min.tolist(),
        "bbox_max_mm": bbox_max.tolist(),
        "volume_mm3": float(total_volume),
        "vertex_count": int(total_vertices),
        "triangle_count": int(total_triangles),
        "part_count": len(parts),
        "parts": part_stats,
        "tessellation": {
            "linear_deflection_mm": LINEAR_DEFLECTION,
            "angular_deflection_rad": ANGULAR_DEFLECTION,
        },
    }
    return glb_bytes, metadata


def _convert_merged(step_bytes: bytes) -> tuple[bytes, dict]:
    """Fallback: single merged mesh, exactly the pre-assembly behavior."""
    shape = _load_step_shape(step_bytes)
    mesh = _tessellate_to_trimesh(shape)

    glb_bytes = trimesh.exchange.gltf.export_glb(mesh)
    bbox_min, bbox_max = mesh.bounds

    metadata = {
        "bbox_min_mm": bbox_min.tolist(),
        "bbox_max_mm": bbox_max.tolist(),
        "volume_mm3": _volume_mm3(shape),
        "vertex_count": int(mesh.vertices.shape[0]),
        "triangle_count": int(mesh.faces.shape[0]),
        "part_count": 1,
    }
    return glb_bytes, metadata


def convert_step_to_glb(step_bytes: bytes) -> tuple[bytes, dict]:
    parts = _load_xcaf_parts(step_bytes)
    if parts is None:
        return _convert_merged(step_bytes)
    return _convert_assembly(parts)


if __name__ == "__main__":
    import sys

    with open(sys.argv[1], "rb") as f:
        glb, meta = convert_step_to_glb(f.read())
    out_path = sys.argv[2] if len(sys.argv) > 2 else "out.glb"
    with open(out_path, "wb") as f:
        f.write(glb)
    print(meta)
