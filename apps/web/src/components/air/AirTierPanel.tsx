import { useTranslation } from "react-i18next";
import type { FieldGridPayload, SurrogatePayload, ReplayPayload } from "../../lib/air";
import type { SimulationRun, CorrelationRecord } from "../../lib/api";

// 고정밀 Solver ↔ 실시간 Surrogate 이원화 공시 (지시서 ⑤): both tiers'
// provenance numbers side by side, with the standing disclosure that the
// surrogate is NOT evidence and correlation numbers are pipeline checks,
// never accuracy claims (지시서 §13 — 감지 정확도 완료 주장 금지).
export function AirTierPanel({
  field,
  surrogate,
  correlation,
}: {
  field: FieldGridPayload | null;
  surrogate: SurrogatePayload | null;
  correlation: CorrelationRecord | null;
}) {
  const { t } = useTranslation();
  const holdout = surrogate ? Object.values(surrogate.channels)[0]?.holdout : undefined;
  const gloveHoldout = surrogate ? Object.values(surrogate.glove_channels)[0]?.holdout : undefined;
  return (
    <div style={{ display: "grid", gap: 10, fontSize: 12 }}>
      <div style={{ border: "1px solid var(--alps-border-strong)", borderRadius: 6, padding: 8 }}>
        <div style={{ fontWeight: 600, color: "var(--alps-attention)" }}>{t("air.tier.solver")}</div>
        {field ? (
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 4 }}>
            <tbody>
              <tr><td style={td}>{t("air.tier.cell")}</td><td style={td}>{field.cell_mm} mm</td></tr>
              <tr><td style={td}>{t("air.tier.grid")}</td><td style={td}>{field.grid_shape.join(" × ")}</td></tr>
              <tr><td style={td}>{t("air.tier.sweeps")}</td><td style={td}>{field.baseline_sweeps}{field.baseline_converged ? " ✓" : " ⚠"}</td></tr>
              <tr><td style={td}>{t("air.tier.touchDc")}</td><td style={td}>{Object.values(field.touch_pose_channels_fF).reduce((a, b) => a + b, 0).toFixed(4)} fF</td></tr>
            </tbody>
          </table>
        ) : (
          <div style={{ opacity: 0.6 }}>{t("air.slice.unavailable")}</div>
        )}
      </div>
      <div style={{ border: "1px solid var(--alps-border-strong)", borderRadius: 6, padding: 8 }}>
        <div style={{ fontWeight: 600, color: "var(--alps-info)" }}>{t("air.tier.surrogate")}</div>
        {surrogate ? (
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 4 }}>
            <tbody>
              <tr><td style={td}>DOE</td><td style={td}>{surrogate.doe.grid}, bare {surrogate.doe.n_bare} / glove {surrogate.doe.n_glove}</td></tr>
              <tr><td style={td}>{t("air.tier.holdoutRmse")}</td><td style={td}>{holdout ? `${(holdout.rmse_fF * 1000).toFixed(2)} mfF` : "—"}</td></tr>
              <tr><td style={td}>{t("air.tier.holdoutMax")}</td><td style={td}>{holdout ? `${(holdout.max_err_fF * 1000).toFixed(2)} mfF` : "—"}</td></tr>
              <tr><td style={td}>{t("air.tier.gloveRmse")}</td><td style={td}>{gloveHoldout ? `${(gloveHoldout.rmse_fF * 1000).toFixed(2)} mfF` : "—"}</td></tr>
            </tbody>
          </table>
        ) : (
          <div style={{ opacity: 0.6 }}>{t("air.slice.unavailable")}</div>
        )}
      </div>
      {correlation && (
        <div style={{ border: "1px solid var(--alps-border-strong)", borderRadius: 6, padding: 8 }}>
          <div style={{ fontWeight: 600, color: "#a78bfa" }}>{t("air.tier.correlation")}</div>
          <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 4 }}>
            <tbody>
              <tr><td style={td}>RMSE</td><td style={td}>{correlation.rmse.toExponential(2)}</td></tr>
              <tr><td style={td}>r</td><td style={td}>{correlation.correlation_coefficient.toFixed(4)}</td></tr>
              {correlation.extrapolation_warning && (
                <tr><td style={td}>⚠</td><td style={td}>{t("air.tier.extrapWarning")}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ fontSize: 11, opacity: 0.6, lineHeight: 1.5 }}>{t("air.tier.disclosure")}</div>
    </div>
  );
}

// AirScenarioTable — §11.2 GOLD replay verdicts: expected bounds embedded
// beside actual measured values, pass computed worker-side (never by the UI).
export function AirScenarioTable({
  replays,
  activeId,
  onSelect,
}: {
  replays: { run: SimulationRun; payload: ReplayPayload }[];
  activeId: string | null;
  onSelect: (scenarioId: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
      <thead>
        <tr>
          <th style={th}>{t("air.scn.scenario")}</th>
          <th style={th}>{t("air.scn.engine")}</th>
          <th style={th}>{t("air.scn.result")}</th>
          <th style={th}>{t("air.scn.detail")}</th>
        </tr>
      </thead>
      <tbody>
        {replays.map(({ run, payload: p }) => {
          const selected = p.scenario_id === activeId;
          return (
            <tr
              key={run.id}
              onClick={() => onSelect(p.scenario_id)}
              style={{ cursor: "pointer", background: selected ? "rgba(249,115,22,0.12)" : "transparent" }}
            >
              <td style={td}>{p.scenario_id}</td>
              <td style={td}>{p.engine}</td>
              <td style={{ ...td, color: p.pass ? "#4ade80" : "#f87171" }}>
                {p.pass ? t("air.scn.pass") : t("air.scn.fail")}
              </td>
              <td style={td}>
                {`v1ft=${p.actual.v1.false_trigger_ticks} v2ft=${p.actual.v2.false_trigger_ticks} first=${p.actual.v2.first_nonidle_tick ?? "—"}`}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const td: React.CSSProperties = { padding: "3px 6px", borderBottom: "1px solid var(--alps-border-base)", verticalAlign: "top" };
const th: React.CSSProperties = { textAlign: "left", padding: "3px 6px", color: "var(--alps-text-muted)", fontWeight: 500 };
