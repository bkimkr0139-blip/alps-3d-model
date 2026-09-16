import { useTranslation } from "react-i18next";
import { bg, border, text, status, accent, radius, fontMono, emboss, tracking } from "./tokens";

// Shared UI kit for the whole twin — the primitives that used to live only in
// the ASIC workbench (asicUi.tsx, now a re-export shim) plus the canvas-overlay
// HUD family (HudPanel/HudChip/StatusBadge) that cockpit, bench and the
// production line render over their 3D canvases.
//
// Two standing rules the kit encodes:
//  §5.1  status is never colour alone — a mark/wording always rides along;
//  §15   backend provenance is always visible (LiveChip / ConfidenceBadge).

export const card: React.CSSProperties = {
  border: `1px solid ${border.base}`,
  borderRadius: radius.md,
  padding: 12,
  background: bg.metalPanel,
  boxShadow: emboss.panel,
};

// Table headers read like instrument panel silkscreen: uppercase, tracked,
// hairline-ruled.
export const th: React.CSSProperties = {
  textAlign: "left",
  fontSize: 10,
  color: text.faint,
  fontWeight: 600,
  padding: "4px 8px",
  borderBottom: `1px solid ${border.base}`,
  whiteSpace: "nowrap",
  textTransform: "uppercase",
  letterSpacing: tracking.micro,
};

export const td: React.CSSProperties = {
  fontSize: 11,
  padding: "4px 8px",
  borderBottom: `1px solid ${border.subtle}`,
  verticalAlign: "top",
};

export function Chip({ color, children, title }: { color: string; children: React.ReactNode; title?: string }) {
  return (
    <span
      title={title}
      style={{
        fontSize: 10,
        fontFamily: fontMono,
        padding: "1px 7px",
        borderRadius: radius.pill,
        border: `1px solid color-mix(in srgb, ${color} 33%, transparent)`,
        background: `color-mix(in srgb, ${color} 10%, transparent)`,
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
    <Chip color={kind === "synthetic_fixture" ? status.synthetic : status.attention} title={t("asic.conf.title")}>
      {kind === "synthetic_fixture" ? "◈ " : "△ "}
      {t(`asic.conf.${kind}` as never)}
    </Chip>
  );
}

export function GateDot({ status: gate }: { status: "pass" | "blocked" }) {
  return (
    <span
      title={gate}
      style={{
        width: 9,
        height: 9,
        borderRadius: 9,
        background: gate === "pass" ? status.ok : status.violation,
        display: "inline-block",
        flexShrink: 0,
      }}
    />
  );
}

// KPI tile: a sunken readout well with a mono value — the number sits in the
// panel the way a meter reading sits in its bezel.
export function Kpi({ label, value, color = accent.kpi }: { label: string; value: string | number; color?: string }) {
  return (
    <div style={{ background: bg.metalWell, borderRadius: radius.sm, padding: "5px 9px", minWidth: 84, boxShadow: emboss.well }}>
      <div style={{ fontSize: 10, color: text.faint, whiteSpace: "nowrap", textTransform: "uppercase", letterSpacing: tracking.micro }}>{label}</div>
      <div style={{ fontSize: 14, fontFamily: fontMono, fontWeight: 500, color }}>{value}</div>
    </div>
  );
}

export function SectionCard({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{ ...card, marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, fontSize: 13, color: text.bright, fontWeight: 600, letterSpacing: tracking.micro }}>{title}</h3>
        {right}
      </div>
      {children}
    </div>
  );
}

// Embossed instrument key: a brushed-metal face with a lit top edge when at
// rest; when active the key glows in its own status color and the label
// brightens. `:hover`/`:active` polish (press travel, sheen) lives in
// index.css so every button in the app inherits it for free.
export const btn = (active: boolean, color: string = status.info): React.CSSProperties => ({
  fontSize: 11,
  padding: "4px 10px",
  borderRadius: radius.sm,
  border: `1px solid ${active ? color : border.strong}`,
  background: active
    ? `linear-gradient(180deg, color-mix(in srgb, ${color} 20%, transparent) 0%, color-mix(in srgb, ${color} 12%, transparent) 100%)`
    : bg.metalRaise,
  boxShadow: active
    ? `inset 0 1px 0 color-mix(in srgb, ${color} 27%, transparent), inset 0 0 6px color-mix(in srgb, ${color} 13%, transparent), 0 1px 2px rgba(2,6,23,0.5)`
    : emboss.lift,
  color: active ? text.bright : text.body,
  textShadow: active ? `0 0 8px color-mix(in srgb, ${color} 33%, transparent)` : "none",
  cursor: "pointer",
});

// Provenance strip for backend-backed panels: where the rows came from and
// that they are demo/synthetic (§15 — the twin never passes as a cert body).
export function LiveChip({ state }: { state: "ready" | "empty" | "error" | "loading" }) {
  const { t } = useTranslation();
  if (state === "ready") return <Chip color={status.ok} title={t("asic.live.title")}>◉ {t("asic.live.backend")}</Chip>;
  if (state === "error") return <Chip color={status.violation} title={t("asic.live.errTitle")}>✕ {t("asic.live.error")}</Chip>;
  if (state === "loading") return <Chip color={status.info} title={t("asic.live.title")}>… {t("asic.live.backend")}</Chip>;
  return <Chip color={status.idle} title={t("asic.live.title")}>○ {t("asic.live.none")}</Chip>;
}

// ── Canvas-overlay HUD family ──────────────────────────────────────────────
// Every 3D canvas in the app keeps its controls as DOM absolutely positioned
// over the <Canvas> (no drei <Html> — that is a settled perf/idiom choice).
// HudPanel/HudChip are the shared look so overlays across tabs read as one
// system: same glass, same mono chips, same corner insets.

export type HudCorner = "top-left" | "top-right" | "bottom-left" | "bottom-right";

const cornerPos: Record<HudCorner, React.CSSProperties> = {
  "top-left": { top: 10, left: 10 },
  "top-right": { top: 10, right: 10 },
  "bottom-left": { bottom: 10, left: 10 },
  "bottom-right": { bottom: 10, right: 10 },
};

export function HudPanel({
  corner = "top-left",
  width,
  children,
  style,
}: {
  corner?: HudCorner;
  width?: number | string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div
      style={{
        position: "absolute",
        ...cornerPos[corner],
        width,
        maxWidth: "calc(100% - 20px)",
        maxHeight: "calc(100% - 20px)",
        overflowY: "auto",
        background: bg.hud,
        border: `1px solid ${border.strong}`,
        boxShadow: `inset 0 1px 0 ${border.rim}, 0 4px 16px rgba(2, 6, 23, 0.5)`,
        borderRadius: radius.md,
        backdropFilter: "blur(8px)",
        padding: 10,
        zIndex: 5,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// Mono chip with an opaque-enough backdrop to stay readable over moving 3D.
export function HudChip({
  color,
  children,
  title,
  style,
}: {
  color: string;
  children: React.ReactNode;
  title?: string;
  style?: React.CSSProperties;
}) {
  return (
    <span
      title={title}
      style={{
        fontSize: 10,
        fontFamily: fontMono,
        padding: "2px 8px",
        borderRadius: radius.pill,
        border: `1px solid color-mix(in srgb, ${color} 40%, transparent)`,
        background: "var(--alps-hud-chip)",
        color,
        whiteSpace: "nowrap",
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        ...style,
      }}
    >
      {children}
    </span>
  );
}

// Unified status badge: mark + wording together, never colour alone. Covers
// lot disposition (● ok / ▲ quarantine / ✕ reject), gate readiness, station
// health — anywhere the twin shows a health state on a dark surface.
const STATUS_MARK = { ok: "●", attention: "▲", violation: "✕", idle: "○" } as const;
const STATUS_COLOR = { ok: status.okAlt, attention: status.attention, violation: status.violation, idle: status.idle } as const;
export type KitStatus = keyof typeof STATUS_MARK;

export function StatusBadge({ status: s, label }: { status: KitStatus; label: string }) {
  return (
    <Chip color={STATUS_COLOR[s]}>
      {STATUS_MARK[s]} {label}
    </Chip>
  );
}

export function statusColor(s: KitStatus): string {
  return STATUS_COLOR[s];
}
