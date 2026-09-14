import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  api,
  type ComponentDto,
  type CorrelationRecord,
  type Gate,
  type Requirement,
  type SimulationRun,
  type TwinGraph,
} from "../lib/api";

// Single global flag on purpose — for a PoC, per-variant dismiss state is
// overkill (noted in AGENTS.md). localStorage is a per-viewer convenience.
const DISMISS_KEY = "alps-onboarding-dismissed";

type StepId =
  | "variant"
  | "requirements"
  | "trace"
  | "model3d"
  | "spice"
  | "mech"
  | "correlation"
  | "gate";

/** First-time-user strip: derives the work state from data Workbench already
 * fetched (+ one gates fetch, + one correlations fetch when an F-S run
 * succeeded) and highlights the first unfinished step as the next action. */
export function OnboardingGuide({
  variantId,
  requirements,
  components,
  graph,
  runs,
  mechRun,
}: {
  variantId: string | null;
  requirements: Requirement[];
  components: ComponentDto[];
  graph: TwinGraph | null;
  runs: SimulationRun[];
  mechRun: SimulationRun | null;
}) {
  const { t } = useTranslation();
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(DISMISS_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [gates, setGates] = useState<Gate[]>([]);
  const [correlations, setCorrelations] = useState<CorrelationRecord[]>([]);

  useEffect(() => {
    if (!variantId) return;
    let cancelled = false;
    api.listGates(variantId).then((g) => !cancelled && setGates(g)).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [variantId]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!mechRun || mechRun.status !== "succeeded") {
        setCorrelations([]);
        return;
      }
      try {
        const c = await api.listCorrelations(mechRun.id);
        if (!cancelled) setCorrelations(c);
      } catch {
        // keep whatever we had — the guide is informational only
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [mechRun]);

  if (dismissed) {
    return (
      <div style={{ marginBottom: 8, textAlign: "right" }}>
        <button
          onClick={() => {
            setDismissed(false);
            try {
              localStorage.removeItem(DISMISS_KEY);
            } catch {
              // private window etc. — dismissing just won't persist
            }
          }}
          style={{ padding: "4px 10px", borderRadius: 6, fontSize: 12, opacity: 0.8 }}
        >
          {t("onboarding.show")}
        </button>
      </div>
    );
  }

  const tracedCount = requirements.filter((r) => graph?.edges.some((e) => e.source === r.id)).length;
  const currentGate = gates[0] ?? null;
  const gateDecided = currentGate
    ? currentGate.status !== "draft" && currentGate.status !== "pending_review"
    : false;

  const steps: { id: StepId; done: boolean; label: string }[] = [
    { id: "variant", done: variantId != null, label: t("onboarding.steps.variant.label") },
    {
      id: "requirements",
      done: requirements.length > 0,
      label: t("onboarding.steps.requirements.label", { n: requirements.length }),
    },
    {
      id: "trace",
      done: requirements.length > 0 && tracedCount === requirements.length,
      label: `${t("onboarding.steps.trace.label")} (${tracedCount}/${requirements.length})`,
    },
    { id: "model3d", done: components.some((c) => c.artifact_version_id), label: t("onboarding.steps.model3d.label") },
    {
      id: "spice",
      done: runs.some((r) => r.run_type === "spice_analysis" && r.status === "succeeded"),
      label: t("onboarding.steps.spice.label"),
    },
    {
      id: "mech",
      done: runs.some((r) => r.run_type === "mech_model" && r.status === "succeeded"),
      label: t("onboarding.steps.mech.label"),
    },
    { id: "correlation", done: correlations.length > 0, label: t("onboarding.steps.correlation.label") },
    { id: "gate", done: gateDecided, label: t("onboarding.steps.gate.label") },
  ];

  const next = steps.find((s) => !s.done) ?? null;
  const gateHintKey =
    currentGate == null
      ? "none"
      : currentGate.status === "draft"
        ? "draft"
        : currentGate.status === "pending_review"
          ? "pending"
          : "decided";
  const nextHint =
    next == null
      ? null
      : next.id === "gate"
        ? t(`onboarding.gateHints.${gateHintKey}`)
        : t(`onboarding.steps.${next.id}.hint`);

  return (
    <div
      style={{
        marginBottom: 16,
        border: "1px solid #334155",
        borderRadius: 8,
        padding: "10px 12px",
        background: "#0b1222",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 13 }}>{t("onboarding.title")}</strong>
        <button
          onClick={() => {
            setDismissed(true);
            try {
              localStorage.setItem(DISMISS_KEY, "1");
            } catch {
              // private window etc. — hiding still works for this session
            }
          }}
          style={{ padding: "4px 10px", borderRadius: 6, fontSize: 12, background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155" }}
        >
          {t("onboarding.dismiss")}
        </button>
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
        {steps.map((s) => (
          <span
            key={s.id}
            title={t(`onboarding.steps.${s.id}.hint`)}
            style={{
              fontSize: 12,
              padding: "3px 8px",
              borderRadius: 999,
              border: s.done
                ? "1px solid #14532d"
                : s === next
                  ? "1px solid #b45309"
                  : "1px solid #334155",
              background: s.done ? "#052e16" : s === next ? "#451a03" : "transparent",
              color: s.done ? "#4ade80" : s === next ? "#fbbf24" : "#94a3b8",
            }}
          >
            {s.done ? "✓" : s === next ? "→" : "·"} {s.label}
          </span>
        ))}
      </div>

      {nextHint && (
        <div style={{ marginTop: 8, fontSize: 12, color: "#fbbf24" }}>
          {t("onboarding.nextAction")} {nextHint}
        </div>
      )}
    </div>
  );
}
