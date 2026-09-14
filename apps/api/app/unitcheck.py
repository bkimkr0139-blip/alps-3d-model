"""Unit-dimension compatibility (§SM-01 / MV-02 lite).

A small closed vocabulary maps unit strings to physical dimensions. Checks:

- same dimension, same unit            → ok
- same dimension, different unit       → conversion_required; SM-01 demands
  an explicit conversion statement on the link (`unit_conversion`) before
  it saves
- different dimensions                 → error (rejected at the router)
- unknown unit on either side          → warning (cannot verify, but saves)

The frontend mirrors the dimension table in `apps/web/src/lib/units.ts` —
keep the two in sync when adding units.
"""

from dataclasses import dataclass

# normalized unit string → physical dimension
UNIT_DIMENSIONS: dict[str, str] = {
    # length / displacement
    "mm": "length", "m": "length", "um": "length", "cm": "length",
    # force
    "n": "force", "mn": "force", "kn": "force", "kgf": "force",
    # torque
    "mnm": "torque", "n·m": "torque", "nm": "torque", "nmm": "torque",
    # voltage
    "v": "voltage", "mv": "voltage", "uv": "voltage", "kv": "voltage",
    # current
    "a": "current", "ma": "current", "ua": "current",
    # pressure
    "kpa": "pressure", "pa": "pressure", "mpa": "pressure", "bar": "pressure", "psi": "pressure",
    # angle
    "deg": "angle", "°": "angle", "rad": "angle",
    # time
    "s": "time", "ms": "time", "us": "time", "ns": "time",
    # frequency
    "hz": "frequency", "khz": "frequency", "mhz": "frequency",
    # mass
    "g": "mass", "kg": "mass", "mg": "mass",
    # resistance
    "ohm": "resistance", "kohm": "resistance", "ω": "resistance",
    # dimensionless
    "": "dimensionless", "%": "dimensionless", "ratio": "dimensionless",
    "ea": "dimensionless", "count": "dimensionless", "v/v": "voltage_ratio",
    "mv/v/kpa": "voltage_ratio", "mv/v": "voltage_ratio",
}


def normalize_unit(unit: str | None) -> str:
    """Lowercase, strip and squeeze so " mN·m ", "mN·m" and "mn·m" agree.
    Note mN·m normalizes to "mn·m" — mapped explicitly below."""
    if unit is None:
        return ""
    cleaned = unit.strip().lower().replace(" ", "")
    return {"mn·m": "mnm", "n·m": "nm", "mn·mm": "nmm", "ω": "ω", "ohm": "ohm"}.get(cleaned, cleaned)


def unit_dimension(unit: str | None) -> str | None:
    """Physical dimension of a unit string, or None when unknown/absent.

    None (no unit declared) must not resolve to the dimensionless "" entry —
    an absent unit is "unknown", not a declared dimensionless quantity."""
    if unit is None:
        return None
    return UNIT_DIMENSIONS.get(normalize_unit(unit))


@dataclass
class UnitCheck:
    # "ok" | "warning" | "conversion_required" | "error"
    level: str
    message: str


def check_link_units(
    link_unit: str | None,
    source_port_unit: str | None,
    target_port_unit: str | None,
    source_name: str,
    target_name: str,
    has_conversion: bool = False,
) -> UnitCheck:
    """Compatibility of a link's declared unit with its endpoint ports.

    Precedence: dimension conflict → error; same dimension but different
    units without an explicit conversion → conversion_required; unknown
    units → warning (unverifiable but savable); otherwise ok.
    """
    src_dim = unit_dimension(source_port_unit)
    dst_dim = unit_dimension(target_port_unit)
    link_dim = unit_dimension(link_unit)

    if src_dim and dst_dim and src_dim != dst_dim:
        return UnitCheck(
            "error",
            f"dimension mismatch: '{source_name}' outputs {source_port_unit} ({src_dim}) "
            f"but '{target_name}' expects {target_port_unit} ({dst_dim})",
        )
    if link_dim and (src_dim or dst_dim) and link_dim not in (src_dim, dst_dim, None):
        return UnitCheck(
            "error",
            f"link unit '{link_unit}' ({link_dim}) does not match the endpoint "
            f"dimension {src_dim or dst_dim}",
        )
    for name, u, d in ((source_name, source_port_unit, src_dim), (target_name, target_port_unit, dst_dim)):
        if u is not None and d is None:
            return UnitCheck("warning", f"unknown unit '{u}' on '{name}' — cannot verify compatibility")
    if link_unit is not None and link_dim is None and link_unit.strip() != "":
        return UnitCheck("warning", f"unknown link unit '{link_unit}' — cannot verify compatibility")

    effective = [u for u in (source_port_unit, target_port_unit, link_unit) if u]
    dims = {unit_dimension(u) for u in effective}
    units = {normalize_unit(u) for u in effective}
    if len(dims) == 1 and len(units) > 1:
        if has_conversion:
            return UnitCheck("ok", "")
        return UnitCheck(
            "conversion_required",
            f"same dimension but different units ({', '.join(sorted(effective))}) — "
            f"SM-01 requires an explicit unit_conversion statement on the link",
        )
    return UnitCheck("ok", "")
