import { useTranslation } from "react-i18next";
import { enumLabel } from "../i18n";
import type { Requirement } from "../lib/api";
import { useTwinStore } from "../store";
import { seedTr } from "../lib/seedL10n";

const SAFETY_COLOR: Record<string, string> = {
  QM: "#64748b",
  ASIL_A: "#22c55e",
  ASIL_B: "#eab308",
  ASIL_C: "#f97316",
  ASIL_D: "#ef4444",
};

export function RequirementsPanel({
  requirements,
  onSelect,
}: {
  requirements: Requirement[];
  onSelect: (requirement: Requirement) => void;
}) {
  const { t, i18n } = useTranslation();
  const selectedId = useTwinStore((s) => s.selectedRequirementId);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <h3 style={{ margin: 0 }}>{t("panels.requirements")}</h3>
      {requirements.map((r) => (
        <div
          key={r.id}
          onClick={() => onSelect(r)}
          style={{
            padding: "8px 10px",
            borderRadius: 6,
            cursor: "pointer",
            border: r.id === selectedId ? "2px solid #ff6b35" : "1px solid #334155",
            background: r.id === selectedId ? "#1e293b" : "transparent",
          }}
        >
          <div style={{ fontSize: 12, opacity: 0.7 }}>{r.business_id}</div>
          <div>{seedTr(r.text, i18n.resolvedLanguage)}</div>
          <div style={{ display: "flex", gap: 6, marginTop: 4, fontSize: 11 }}>
            <span
              style={{
                background: SAFETY_COLOR[r.safety_class] ?? "#64748b",
                color: "white",
                padding: "1px 6px",
                borderRadius: 4,
              }}
            >
              {r.safety_class}
            </span>
            <span style={{ opacity: 0.7 }}>{enumLabel(t, "verification", r.verification_method)}</span>
            <span style={{ opacity: 0.7 }}>· {enumLabel(t, "reqStatus", r.status)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
