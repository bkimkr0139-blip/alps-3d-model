import { useTranslation } from "react-i18next";
import { CYCLES_TO_SATURATION, rankedStress, stressCss } from "../lib/stress";
import { useTwinStore } from "../store";
import { bg, border, accent } from "../ui/tokens";

const MAX_CYCLES = 200_000;

// Overlay for the S04 3D viewer: drive the digital twin (actuation, vehicle
// vibration) and scrub the stress time-lapse. The 3D animator reads the same
// zustand state each frame, so slider drags repaint the model live.
// `top` lets the cockpit shift the panel below its HUD chip strip without
// moving the canvas (a resize would retrigger the Bounds fit).
export function TwinControls({ top = 10 }: { top?: number }) {
  const { t } = useTranslation();
  const actuated = useTwinStore((s) => s.actuated);
  const vibration = useTwinStore((s) => s.vibration);
  const cycles = useTwinStore((s) => s.cycles);
  const bodyOpacity = useTwinStore((s) => s.bodyOpacity);
  const viewerBg = useTwinStore((s) => s.viewerBg);
  const explodeAmount = useTwinStore((s) => s.explodeAmount);
  const explodePlaying = useTwinStore((s) => s.explodePlaying);
  const setActuated = useTwinStore((s) => s.setActuated);
  const setVibration = useTwinStore((s) => s.setVibration);
  const setCycles = useTwinStore((s) => s.setCycles);
  const setBodyOpacity = useTwinStore((s) => s.setBodyOpacity);
  const setViewerBg = useTwinStore((s) => s.setViewerBg);
  const setExplodeAmount = useTwinStore((s) => s.setExplodeAmount);
  const setExplodePlaying = useTwinStore((s) => s.setExplodePlaying);
  const bumpViewReset = useTwinStore((s) => s.bumpViewReset);

  const hotspots = rankedStress(Object.keys(CYCLES_TO_SATURATION), cycles, vibration).slice(0, 5);

  const buttonStyle = (on: boolean) => ({
    padding: "5px 10px",
    borderRadius: 6,
    border: "1px solid",
    borderColor: on ? accent.orange : border.strong,
    background: on ? "#7c2d12" : bg.raise,
    color: on ? "white" : "var(--alps-text)",
    fontSize: 12,
    cursor: "pointer",
  });

  return (
    <div
      style={{
        position: "absolute",
        top,
        right: 10,
        width: 230,
        background: bg.hud,
        border: `1px solid ${border.strong}`,
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
      {/* Backdrop brightness: a dark-cased part disappears against the dark
          studio backdrop — the label names the backdrop clicking switches TO. */}
      <button
        style={buttonStyle(viewerBg === "light")}
        onClick={() => setViewerBg(viewerBg === "light" ? "dark" : "light")}
        aria-pressed={viewerBg === "light"}
      >
        {viewerBg === "light" ? t("twin.bgDark") : t("twin.bgLight")}
      </button>
      {/* 저장된 카메라를 버리고 정면 3/4 기본 시점으로 복귀(FB-0001) — 저장
          시점이 어긋났을 때의 탈출구. 캔버스 안 SavedCamera가 nonce를 구독한다. */}
      <button style={buttonStyle(false)} onClick={bumpViewReset}>
        {t("twin.viewReset")}
      </button>
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
          style={{ accentColor: accent.orange }}
        />
      </label>
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ opacity: 0.8 }}>
          {t("twin.bodyOpacity")}: {Math.round(bodyOpacity * 100)}%
        </span>
        <input
          type="range"
          min={0.15}
          max={1}
          step={0.05}
          value={bodyOpacity}
          onChange={(e) => setBodyOpacity(Number(e.target.value))}
          style={{ accentColor: accent.orange }}
        />
      </label>
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ opacity: 0.8 }}>
          {t("twin.explode")}: {Math.round(explodeAmount * 100)}%
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.02}
          value={explodeAmount}
          disabled={explodePlaying}
          onChange={(e) => setExplodeAmount(Number(e.target.value))}
          style={{ accentColor: accent.orange }}
        />
      </label>
      <button
        style={buttonStyle(explodePlaying)}
        onClick={() => {
          setExplodePlaying(!explodePlaying);
          // While playing, TwinAnimator drives the exploded amount itself
          // off wall-clock time, ignoring this slider entirely. Reset it to
          // fully assembled on both transitions so it never shows a stale
          // mid-cycle value once manual control resumes.
          setExplodeAmount(0);
        }}
      >
        {explodePlaying ? t("twin.explodeStop") : t("twin.explodePlay")}
      </button>
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
                  background: border.strong,
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
            setExplodePlaying(false);
            setExplodeAmount(0);
          }}
        >
          {t("twin.reset")}
        </button>
      </div>
    </div>
  );
}
