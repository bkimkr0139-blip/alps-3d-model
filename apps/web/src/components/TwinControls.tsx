import { useTranslation } from "react-i18next";
import { CYCLES_TO_SATURATION, rankedStress, stressCss } from "../lib/stress";
import { useTwinStore } from "../store";

const MAX_CYCLES = 200_000;

// Overlay for the S04 3D viewer: drive the digital twin (actuation, vehicle
// vibration) and scrub the stress time-lapse. The 3D animator reads the same
// zustand state each frame, so slider drags repaint the model live.
export function TwinControls() {
  const { t } = useTranslation();
  const actuated = useTwinStore((s) => s.actuated);
  const vibration = useTwinStore((s) => s.vibration);
  const cycles = useTwinStore((s) => s.cycles);
  const setActuated = useTwinStore((s) => s.setActuated);
  const setVibration = useTwinStore((s) => s.setVibration);
  const setCycles = useTwinStore((s) => s.setCycles);

  const hotspots = rankedStress(Object.keys(CYCLES_TO_SATURATION), cycles, vibration).slice(0, 5);

  const buttonStyle = (on: boolean) => ({
    padding: "5px 10px",
    borderRadius: 6,
    border: "1px solid",
    borderColor: on ? "#f97316" : "#334155",
    background: on ? "#7c2d12" : "#1e293b",
    color: "white",
    fontSize: 12,
    cursor: "pointer",
  });

  return (
    <div
      style={{
        position: "absolute",
        top: 10,
        right: 10,
        width: 230,
        background: "rgba(15, 23, 42, 0.88)",
        border: "1px solid #334155",
        borderRadius: 8,
        padding: 10,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        fontSize: 12,
      }}
    >
      <div style={{ fontWeight: 600 }}>{t("twin.title")}</div>
      <div style={{ display: "flex", gap: 6 }}>
        <button style={buttonStyle(actuated)} onClick={() => setActuated(!actuated)}>
          {actuated ? t("twin.actuated") : t("twin.actuate")}
        </button>
        <button style={buttonStyle(vibration)} onClick={() => setVibration(!vibration)}>
          {t("twin.vibration")}
        </button>
      </div>
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ opacity: 0.8 }}>
          {t("twin.cycles")}: {cycles.toLocaleString()}
        </span>
        <input
          type="range"
          min={0}
          max={MAX_CYCLES}
          step={1000}
          value={Math.min(cycles, MAX_CYCLES)}
          onChange={(e) => setCycles(Number(e.target.value))}
          style={{ accentColor: "#f97316" }}
        />
      </label>
      {vibration && (
        <div style={{ color: "#fbbf24", fontSize: 11 }}>
          {t("twin.vibrationAccumulating")}
        </div>
      )}
      <div>
        <div style={{ opacity: 0.8, marginBottom: 4 }}>{t("twin.stressTitle")}</div>
        {hotspots.length === 0 ? (
          <div style={{ opacity: 0.55 }}>{t("twin.stressHint")}</div>
        ) : (
          hotspots.map(({ kind, stress }) => (
            <div key={kind} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
              <span style={{ width: 70, opacity: 0.8 }}>
                {(t as (k: string) => string)(`twin.part.${kind}`)}
              </span>
              <span
                style={{
                  flex: 1,
                  height: 7,
                  borderRadius: 4,
                  background: "#334155",
                  overflow: "hidden",
                }}
              >
                <span
                  style={{
                    display: "block",
                    height: "100%",
                    width: `${Math.round(stress * 100)}%`,
                    background: stressCss(stress),
                  }}
                />
              </span>
              <span style={{ width: 38, textAlign: "right" }}>{Math.round(stress * 100)}%</span>
            </div>
          ))
        )}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ opacity: 0.55, fontSize: 10, maxWidth: 150 }}>{t("twin.stressNote")}</span>
        <button
          style={buttonStyle(false)}
          onClick={() => {
            setActuated(false);
            setVibration(false);
            setCycles(0);
          }}
        >
          {t("twin.reset")}
        </button>
      </div>
    </div>
  );
}
