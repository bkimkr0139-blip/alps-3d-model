import { useTranslation } from "react-i18next";
import { enumLabel } from "../i18n";
import type { SimulationRun } from "../lib/api";

export function SimulationPanel({ runs }: { runs: SimulationRun[] }) {
  const { t } = useTranslation();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <h3 style={{ margin: 0 }}>{t("panels.simulation")}</h3>
      {runs.length === 0 && <div style={{ opacity: 0.6 }}>{t("simulation.empty")}</div>}
      {runs.map((run) => (
        <div key={run.id} style={{ border: "1px solid #334155", borderRadius: 6, padding: 10 }}>
          {/* §6.2: every result card must show tool/model version, status,
              executor and evidence — never a bare number. */}
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
            <span>{run.business_id}</span>
            <span>{enumLabel(t, "runStatus", run.status)}</span>
          </div>
          <div style={{ fontSize: 11, opacity: 0.7 }}>
            {enumLabel(t, "runType", run.run_type)} · {t("simulation.toolPrefix")} {run.tool_version ?? "—"}
          </div>
          {run.error_message && (
            <div style={{ color: "#ef4444", fontSize: 12, marginTop: 4 }}>{run.error_message}</div>
          )}
          {run.metrics.length > 0 && (
            <table style={{ width: "100%", marginTop: 6, fontSize: 12 }}>
              <tbody>
                {run.metrics.map((m) => (
                  <tr key={m.name}>
                    <td style={{ opacity: 0.7 }}>{m.name}</td>
                    <td style={{ textAlign: "right" }}>
                      {m.value.toLocaleString()} {m.unit ?? ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </div>
  );
}
