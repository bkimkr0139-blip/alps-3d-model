import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Gate, type SimulationRun, type Requirement, type ComponentDto } from "../../lib/api";
import { enumLabel } from "../../i18n";
import { useTwinStore } from "../../store";
import { HudChip, btn } from "../../ui/kit";
import { accent, status as statusColor } from "../../ui/tokens";

// Cockpit HUD strip — the chip line-up floating over the 3D twin on the
// model tab. It keeps the data-connectedness of the twin visible even with
// the side drawers closed (§: the twin is only a twin while its links to
// requirements / simulation / gate state are on screen). All data comes from
// APIs the shell already loads — the only new call is listGates.
const GATE_CHIP: Record<Gate["status"], { color: string; mark: string }> = {
  approved: { color: statusColor.ok, mark: "✓" },
  conditionally_approved: { color: statusColor.attention, mark: "△" },
  pending_review: { color: statusColor.info, mark: "○" },
  draft: { color: statusColor.idle, mark: "○" },
  rejected: { color: statusColor.violation, mark: "✕" },
};

const RUN_CHIP: Record<string, { color: string; mark: string }> = {
  succeeded: { color: statusColor.ok, mark: "●" },
  running: { color: statusColor.info, mark: "⚙" },
  queued: { color: statusColor.idle, mark: "⏳" },
  failed: { color: statusColor.violation, mark: "✕" },
};

export function CockpitHud({
  productName,
  variantName,
  variantId,
  runs,
  requirements,
  components,
  leftOpen,
  rightOpen,
  onToggleLeft,
  onToggleRight,
}: {
  productName?: string;
  variantName?: string;
  variantId: string | null;
  runs: SimulationRun[];
  requirements: Requirement[];
  components: ComponentDto[];
  leftOpen: boolean;
  rightOpen: boolean;
  onToggleLeft: () => void;
  onToggleRight: () => void;
}) {
  const { t } = useTranslation();
  const [gate, setGate] = useState<Gate | null>(null);
  const selectedComponentId = useTwinStore((s) => s.selectedComponentId);
  const selectedRequirementId = useTwinStore((s) => s.selectedRequirementId);

  // Runs list arrives newest-first from the API, so the first hit per type is
  // the latest run of that type.
  const mechRun = runs.find((r) => r.run_type === "mech_model");
  const spiceRun = runs.find((r) => r.run_type === "spice_analysis");

  useEffect(() => {
    setGate(null);
    if (!variantId) return;
    api
      .listGates(variantId)
      .then((gs) => setGate(gs[0] ?? null))
      .catch(() => {});
  }, [variantId]);

  const component = components.find((c) => c.id === selectedComponentId);
  const requirement = requirements.find((r) => r.id === selectedRequirementId);

  const gateChip = gate ? GATE_CHIP[gate.status] : null;

  return (
    <div
      style={{
        position: "absolute",
        top: 10,
        left: 10,
        right: 10,
        display: "flex",
        gap: 6,
        flexWrap: "wrap",
        alignItems: "center",
        zIndex: 7,
        // The strip is a headline over the canvas, not a click sink — only
        // the sync chip and the toggles take pointers.
        pointerEvents: "none",
      }}
    >
      {(productName || variantName) && (
        <HudChip color={statusColor.info} title={t("nav.product")}>
          {productName}
          {variantName ? ` ▸ ${variantName}` : ""}
        </HudChip>
      )}
      {gateChip && gate && (
        <HudChip
          color={gateChip.color}
          title={gate.evidence_checklist && !gate.evidence_checklist.passed ? `${t("cockpit.evidenceMissing")} (${gate.evidence_checklist.missing.length})` : t("cockpit.gate")}
        >
          {gateChip.mark} {t("cockpit.gate")} · {enumLabel(t, "gateStatus", gate.status)}
        </HudChip>
      )}
      {mechRun && (
        <RunChip run={mechRun} />
      )}
      {spiceRun && (
        <RunChip run={spiceRun} />
      )}
      <HudChip
        color={component ? accent.primary : statusColor.idle}
        title={t("cockpit.sync")}
        style={{ pointerEvents: "auto", cursor: "pointer" }}
      >
        <span
          role="status"
          aria-label={t("cockpit.sync")}
          onClick={onToggleLeft}
        >
          ◎ {t("cockpit.sync")} ·{" "}
          {component
            ? requirement
              ? t("cockpit.synced", { req: requirement.business_id, comp: component.name })
              : component.name
            : t("cockpit.noSelection")}
        </span>
      </HudChip>
      <span style={{ flex: 1 }} />
      <span style={{ display: "flex", gap: 6, pointerEvents: "auto" }}>
        <button style={btn(leftOpen, statusColor.info)} aria-pressed={leftOpen} aria-label={t("cockpit.showRequirements")} onClick={onToggleLeft}>
          {t("cockpit.showRequirements")}
        </button>
        <button style={btn(rightOpen, statusColor.info)} aria-pressed={rightOpen} aria-label={t("cockpit.showSimulation")} onClick={onToggleRight}>
          {t("cockpit.showSimulation")}
        </button>
      </span>
    </div>
  );
}

function RunChip({ run }: { run: SimulationRun }) {
  const { t } = useTranslation();
  const chip = RUN_CHIP[run.status] ?? { color: statusColor.idle, mark: "○" };
  return (
    <HudChip color={chip.color} title={`${run.business_id}${run.tool_version ? ` · ${run.tool_version}` : ""}`}>
      {chip.mark} {enumLabel(t, "runType", run.run_type)} · {enumLabel(t, "runStatus", run.status)}
    </HudChip>
  );
}
