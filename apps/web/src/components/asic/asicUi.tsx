import { useTranslation } from "react-i18next";

// Shared UI primitives for the ASIC workbench (AsicProgram + asicLive panels).
// Same slate palette / monospace-chip idiom as the rest of the twin.

export const card: React.CSSProperties = {
  border: "1px solid #1e293b",
  borderRadius: 8,
  padding: 12,
  background: "#0b1220",
};

export const th: React.CSSProperties = {
  textAlign: "left",
  fontSize: 10,
  color: "#64748b",
  fontWeight: 500,
  padding: "4px 8px",
  borderBottom: "1px solid #1e293b",
  whiteSpace: "nowrap",
};

export const td: React.CSSProperties = {
  fontSize: 11,
  padding: "4px 8px",
  borderBottom: "1px solid #141c2e",
  verticalAlign: "top",
};

export function Chip({ color, children, title }: { color: string; children: React.ReactNode; title?: string }) {
  return (
    <span
      title={title}
      style={{
        fontSize: 10,
        fontFamily: "monospace",
        padding: "1px 7px",
        borderRadius: 9,
        border: `1px solid ${color}55`,
        background: `${color}18`,
        color,
        whiteSpace: "nowrap",
        display: "inline-block",
      }}
    >
      {children}
    </span>
  );
}

// §15.3 — evidence status must never be color alone: icon + wording.
export function ConfidenceBadge({ kind }: { kind: "educational_estimate" | "synthetic_fixture" }) {
  const { t } = useTranslation();
  return (
    <Chip color={kind === "synthetic_fixture" ? "#a78bfa" : "#fbbf24"} title={t("asic.conf.title")}>
      {kind === "synthetic_fixture" ? "◈ " : "△ "}
      {t(`asic.conf.${kind}` as never)}
    </Chip>
  );
}

export function GateDot({ status }: { status: "pass" | "blocked" }) {
  return <span title={status} style={{ width: 9, height: 9, borderRadius: 9, background: status === "pass" ? "#34d399" : "#f87171", display: "inline-block", flexShrink: 0 }} />;
}

export function Kpi({ label, value, color = "#67e8f9" }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ background: "#0f172a", borderRadius: 6, padding: "5px 9px", minWidth: 84 }}>
      <div style={{ fontSize: 10, color: "#64748b", whiteSpace: "nowrap" }}>{label}</div>
      <div style={{ fontSize: 14, fontFamily: "monospace", color }}>{value}</div>
    </div>
  );
}

export function SectionCard({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{ ...card, marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, fontSize: 13, color: "#e2e8f0" }}>{title}</h3>
        {right}
      </div>
      {children}
    </div>
  );
}

export const btn = (active: boolean, color = "#38bdf8"): React.CSSProperties => ({
  fontSize: 11,
  padding: "4px 10px",
  borderRadius: 6,
  border: `1px solid ${active ? color : "#334155"}`,
  background: active ? `${color}22` : "#0f172a",
  color: active ? "#e2e8f0" : "#94a3b8",
  cursor: "pointer",
});

// Provenance strip for backend-backed panels: where the rows came from and
// that they are demo/synthetic (§15 — the twin never passes as a cert body).
export function LiveChip({ state }: { state: "ready" | "empty" | "error" | "loading" }) {
  const { t } = useTranslation();
  if (state === "ready") return <Chip color="#34d399" title={t("asic.live.title")}>◉ {t("asic.live.backend")}</Chip>;
  if (state === "error") return <Chip color="#f87171" title={t("asic.live.errTitle")}>✕ {t("asic.live.error")}</Chip>;
  if (state === "loading") return <Chip color="#38bdf8" title={t("asic.live.title")}>… {t("asic.live.backend")}</Chip>;
  return <Chip color="#64748b" title={t("asic.live.title")}>○ {t("asic.live.none")}</Chip>;
}
