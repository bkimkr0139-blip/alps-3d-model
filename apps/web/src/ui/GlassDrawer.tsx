import { useTranslation } from "react-i18next";
import { bg, border, text } from "./tokens";
import { useIsMobile } from "./useIsMobile";

// Canvas-overlay side drawer. The cockpit keeps its side context
// (requirements / simulation results) as glass drawers floating OVER the 3D
// canvas instead of grid columns — resizing the canvas would retrigger
// Bounds' fit and visibly jerk the camera, while an overlay leaves the
// canvas box untouched. The strip of cockpit HUD chips sits above (top:10),
// so drawers start just below it.
export function GlassDrawer({
  side,
  width = 360,
  top = 52,
  title,
  onClose,
  children,
}: {
  side: "left" | "right";
  width?: number;
  top?: number;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  // At the 820px breakpoint the overlay becomes an inline block — a floating
  // pane over a canvas the phone fills edge-to-edge just hides the twin.
  const mobile = useIsMobile();
  return (
    <div
      role="complementary"
      aria-label={title}
      style={
        mobile
          ? {
              position: "relative",
              width: "100%",
              maxHeight: 460,
              marginTop: 8,
              display: "flex",
              flexDirection: "column",
              background: bg.hud,
              border: `1px solid ${border.strong}`,
              borderRadius: 8,
              overflow: "hidden",
            }
          : {
              position: "absolute",
              top,
              [side]: 10,
              bottom: 10,
              width,
              maxWidth: "calc(100% - 20px)",
              display: "flex",
              flexDirection: "column",
              background: bg.hud,
              border: `1px solid ${border.strong}`,
              borderRadius: 8,
              backdropFilter: "blur(8px)",
              zIndex: 6,
              overflow: "hidden",
            }
      }
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, padding: "8px 10px", borderBottom: `1px solid ${border.base}` }}>
        <span style={{ fontSize: 11, color: text.muted, textTransform: "uppercase", letterSpacing: 0.5 }}>{title}</span>
        <button onClick={onClose} aria-label={t("cockpit.close")} style={{ padding: "2px 9px", borderRadius: 6 }}>
          ✕
        </button>
      </div>
      <div style={{ overflowY: "auto", padding: 10, minHeight: 0 }}>{children}</div>
    </div>
  );
}
