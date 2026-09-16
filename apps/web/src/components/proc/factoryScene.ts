import type { ControlChart, LotCard, ProcessOperationDto, ProcessParameterInfo } from "../../lib/api";

// Data-driven production-line scene — same idiom as edaScene.ts: plain data
// arrays + a pure builder, so the viewer stays dumb and the state mapping
// stays testable. All status comes from real control-chart data; nothing is
// invented here (§: the twin is only a twin while it is data-connected).

/** Station health, mirroring the control-chart legend semantics exactly:
 *  `in_control` = blue points only, `rule_hit` = rule-violation points
 *  (amber in the chart), `excluded` = points excluded from the limit basis
 *  (red in the chart), `idle` = no chart data for any of its parameters. */
export type StationStatus = "in_control" | "rule_hit" | "excluded" | "idle";

export interface StationParam {
  parameter: string;
  unit: string | null;
  ruleHits: number;
  excluded: number;
}

export interface FactoryStation {
  key: string; // ProcessOperationDto.business_id
  name: string; // operation name, rendered as-is (backend data)
  seq: number;
  equipment: string | null;
  status: StationStatus;
  params: StationParam[];
}

export interface FactoryLotDot {
  businessId: string;
  disposition: LotCard["disposition"];
}

export interface FactorySceneSpec {
  stations: FactoryStation[];
  /** Lots in production order (produced_at) — the conveyor is a timeline,
   *  not a station claim: a dot's position never asserts where a lot was
   *  made, only its order and disposition. */
  lots: FactoryLotDot[];
}

/** Map raw operations + per-parameter control charts to station health.
 *  A parameter belongs to a station when its operation_business_ids include
 *  the operation; a station's status is the worst of its parameters. */
export function aggregateStations(
  ops: ProcessOperationDto[],
  paramInfos: ProcessParameterInfo[],
  charts: Map<string, ControlChart>
): FactoryStation[] {
  return [...ops]
    .sort((a, b) => a.seq_no - b.seq_no)
    .map((op) => {
      const params: StationParam[] = [];
      for (const pi of paramInfos) {
        if (!pi.operation_business_ids.includes(op.business_id)) continue;
        const chart = charts.get(pi.parameter);
        if (!chart) continue;
        params.push({
          parameter: pi.parameter,
          unit: pi.unit,
          ruleHits: chart.points.filter((p) => p.violations.length > 0).length,
          excluded: chart.points.filter((p) => p.excluded_from_limits).length,
        });
      }
      const status: StationStatus =
        params.length === 0
          ? "idle"
          : params.some((p) => p.excluded > 0)
            ? "excluded"
            : params.some((p) => p.ruleHits > 0)
              ? "rule_hit"
              : "in_control";
      return { key: op.business_id, name: op.name, seq: op.seq_no, equipment: op.equipment, status, params };
    });
}

/** Line layout: stations evenly spaced along x in seq order; the conveyor
 *  spine runs in front of them; lot dots ride it in production order. */
export function buildFactoryScene(stations: FactoryStation[], lots: LotCard[]): FactorySceneSpec & { spacing: number } {
  const spacing = 6;
  const ordered = [...lots]
    .sort((a, b) => a.produced_at.localeCompare(b.produced_at))
    .map((l) => ({ businessId: l.business_id, disposition: l.disposition }));
  return { stations, lots: ordered, spacing };
}

export const stationX = (index: number, count: number, spacing: number): number =>
  (index - (count - 1) / 2) * spacing;
