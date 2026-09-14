// Unit-dimension vocabulary — a mirror of the API's `app/unitcheck.py`.
// The backend is authoritative (it rejects/accepts link creation); this copy
// exists only to show the same verdict inline in the canvas UI. Keep the two
// in sync when adding units (see AGENTS.md M9).

const UNIT_DIMENSIONS: Record<string, string> = {
  mm: "length", m: "length", um: "length", cm: "length",
  n: "force", mn: "force", kn: "force", kgf: "force",
  mnm: "torque", "n·m": "torque", nm: "torque", nmm: "torque",
  v: "voltage", mv: "voltage", uv: "voltage", kv: "voltage",
  a: "current", ma: "current", ua: "current",
  kpa: "pressure", pa: "pressure", mpa: "pressure", bar: "pressure", psi: "pressure",
  deg: "angle", "°": "angle", rad: "angle",
  s: "time", ms: "time", us: "time", ns: "time",
  hz: "frequency", khz: "frequency", mhz: "frequency",
  g: "mass", kg: "mass", mg: "mass",
  ohm: "resistance", kohm: "resistance", "ω": "resistance",
  "": "dimensionless", "%": "dimensionless", ratio: "dimensionless",
  ea: "dimensionless", count: "dimensionless", "v/v": "voltage_ratio",
  "mv/v/kpa": "voltage_ratio", "mv/v": "voltage_ratio",
};

const ALIASES: Record<string, string> = { "mn·m": "mnm", "n·m": "nm", "mn·mm": "nmm" };

function normalize(unit: string | null | undefined): string {
  if (!unit) return "";
  const cleaned = unit.trim().toLowerCase().replace(/\s+/g, "");
  return ALIASES[cleaned] ?? cleaned;
}

export function unitDimension(unit: string | null | undefined): string | null {
  return UNIT_DIMENSIONS[normalize(unit)] ?? null;
}

export type LinkUnitCheck = {
  level: "ok" | "warning" | "conversion_required" | "error";
  message: string;
};

/** Same verdict as the API's check_link_units — shown inline while drawing. */
export function checkLinkUnits(
  linkUnit: string | null | undefined,
  sourcePortUnit: string | null | undefined,
  targetPortUnit: string | null | undefined,
  hasConversion: boolean
): LinkUnitCheck {
  const srcDim = unitDimension(sourcePortUnit);
  const dstDim = unitDimension(targetPortUnit);
  const linkDim = unitDimension(linkUnit);

  if (srcDim && dstDim && srcDim !== dstDim) {
    return { level: "error", message: `dimension mismatch: ${sourcePortUnit} ↔ ${targetPortUnit}` };
  }
  if (linkDim && (srcDim || dstDim) && linkDim !== srcDim && linkDim !== dstDim) {
    return { level: "error", message: `link unit '${linkUnit}' does not match endpoint dimension` };
  }
  for (const [u, d] of [
    [sourcePortUnit, srcDim],
    [targetPortUnit, dstDim],
  ] as const) {
    if (u != null && d === null) return { level: "warning", message: `unknown unit '${u}' — cannot verify` };
  }
  const effective = [sourcePortUnit, targetPortUnit, linkUnit].filter((u): u is string => !!u);
  const dims = new Set(effective.map(unitDimension));
  const units = new Set(effective.map(normalize));
  if (dims.size === 1 && units.size > 1) {
    if (hasConversion) return { level: "ok", message: "" };
    return {
      level: "conversion_required",
      message: `same dimension, different units (${effective.join(", ")}) — unit_conversion required`,
    };
  }
  return { level: "ok", message: "" };
}
