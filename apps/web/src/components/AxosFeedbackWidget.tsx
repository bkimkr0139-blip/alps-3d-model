import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { feedbackApi } from "../lib/api";
import type { FeedbackSummary } from "../lib/api";
import { screenContextOf } from "../lib/screenContext";
import { bg, border, emboss, font, radius, status, text, tracking, accent } from "../ui/tokens";

// AXOS 피드백 버튼 — 우측 고정 토글 탭 + Context Drawer + 제출 모달.
// 하이퐁 IOC 포털의 AXOS 피드백 버튼 이식 지시서를 ALPS 스택(Vite+TS, Tailwind
// 없음 → 토큰 인라인 스타일)에 맞춰 이식한 것. 구조·동작은 지시서 그대로:
//   1) 전역 1회 마운트, 모든 화면에서 우측 중앙 세로 "AXOS" 탭
//   2) 탭 클릭 → Context Drawer(화면 목적 + 최근 피드백 5건)
//   3) 피드백 제출 → 현재 경로·메뉴·필터·화면버전·제출자·시각 자동 기록 모달
//   4) 접수 성공 1.4초 표시 후 초기화
// 레코드는 ALPS 루트 feedback/의 FB-####.json(axos-si feedback.py와 같은
// 스키마) — 웹 접수는 폐루프의 또 하나의 채널이다.

const BUTTON_Z = 1150; // AssistantPanel FAB가 1000 — 위 계층, 오른쪽 가장자리라 시각 충돌 없음
const OVERLAY_Z = 1200;
const DRAWER_Z = 1201;
const MODAL_Z = 1300;

// 서버(레코드)는 상/중/하 정규 어휘, UI는 지시서의 4단계 — 접수 시 사상.
const PRIORITY_MAP: Record<string, string> = { urgent: "상", high: "상", normal: "중", low: "하" };

const STATUS_COLOR: Record<string, string> = {
  접수: status.info,
  개발큐: status.attention,
  개발중: accent.primary,
  반영완료: status.ok,
};

function chipFor(color: string) {
  return {
    color,
    background: `color-mix(in srgb, ${color} 13%, transparent)`,
    border: `1px solid color-mix(in srgb, ${color} 38%, transparent)`,
    borderRadius: radius.pill,
    padding: "1px 7px",
    fontSize: 11,
    fontWeight: 600,
    whiteSpace: "nowrap" as const,
  };
}

const fieldLabel: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: tracking.micro,
  textTransform: "uppercase",
  color: text.muted,
  margin: "12px 0 4px",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  background: bg.raise,
  border: `1px solid ${border.base}`,
  borderRadius: radius.sm,
  color: text.bright,
  font: "inherit",
  fontSize: 13,
  padding: "7px 9px",
  resize: "vertical",
};

const captionStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: tracking.wider,
  textTransform: "uppercase",
  color: text.faint,
  margin: "0 0 8px",
};

function LayersIcon() {
  // lucide-react 의존 대신 인라인 SVG(layers 아이콘 형상) — 신규 패키지 없음.
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m12 2 8.5 4.77L12 11.54 3.5 6.77 12 2Z" />
      <path d="m3.5 11.77 8.5 4.77 8.5-4.77" />
      <path d="m3.5 16.77 8.5 4.77 8.5-4.77" />
    </svg>
  );
}

function StatusChip({ value, label }: { value: string; label: string }) {
  return <span style={chipFor(STATUS_COLOR[value] ?? status.idle)}>{label}</span>;
}

interface SubmitModalProps {
  route: string;
  menu: string;
  filters: Record<string, string>;
  screenVersion: string;
  onClose: () => void;
  onSubmitted: () => void;
}

function SubmitModal({ route, menu, filters, screenVersion, onClose, onSubmitted }: SubmitModalProps) {
  const { t } = useTranslation();
  const [category, setCategory] = useState("화면개선");
  const [priority, setPriority] = useState("normal");
  const [title, setTitle] = useState("");
  const [asIs, setAsIs] = useState("");
  const [toBe, setToBe] = useState("");
  const [effect, setEffect] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  // 성공 화면 1.4초 → 모달 닫힘 + 폼 초기화(성공 화면이 곧 리셋 트리거).
  useEffect(() => {
    if (!done) return;
    const timer = window.setTimeout(() => {
      setDone(false);
      setTitle("");
      setAsIs("");
      setToBe("");
      setEffect("");
      setBusy(false);
      onSubmitted();
    }, 1400);
    return () => window.clearTimeout(timer);
  }, [done, onSubmitted]);

  const canSubmit = !busy && title.trim() !== "" && asIs.trim() !== "";

  function submit() {
    if (!canSubmit) return;
    setBusy(true);
    setError("");
    feedbackApi
      .submit({
        title: title.trim(),
        as_is: asIs.trim(),
        to_be: toBe.trim(),
        expected_effect: effect.trim(),
        category,
        priority: PRIORITY_MAP[priority] ?? "중",
        source_route: route,
        source_menu: menu,
        applied_filters: filters,
        screen_version: screenVersion,
        data_reference_time: new Date().toISOString(),
        org: "",
      })
      .then(() => setDone(true))
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
        setBusy(false);
      });
  }

  // key는 i18n 리터럴 키 — as const로 t() 타입 검사를 통과시킨다.
  const categories = [
    { value: "화면개선", key: "axos.catScreen" },
    { value: "데이터오류", key: "axos.catData" },
    { value: "컨설팅·운영", key: "axos.catConsult" },
    { value: "개발요청", key: "axos.catDev" },
    { value: "미정의규칙", key: "axos.catRule" },
  ] as const;
  const priorities = [
    { value: "urgent", key: "axos.priUrgent" },
    { value: "high", key: "axos.priHigh" },
    { value: "normal", key: "axos.priNormal" },
    { value: "low", key: "axos.priLow" },
  ] as const;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: MODAL_Z,
        background: "rgba(2, 6, 14, 0.55)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        style={{
          width: 440, maxWidth: "92vw", maxHeight: "88vh", overflowY: "auto",
          background: bg.card, border: `1px solid ${border.strong}`,
          borderRadius: radius.md, boxShadow: emboss.panel, padding: "18px 20px",
        }}
      >
        {done ? (
          <div style={{ textAlign: "center", padding: "34px 8px" }}>
            <div
              aria-hidden="true"
              style={{
                width: 46, height: 46, margin: "0 auto 14px", borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center",
                color: status.ok,
                background: `color-mix(in srgb, ${status.ok} 14%, transparent)`,
                border: `1px solid color-mix(in srgb, ${status.ok} 40%, transparent)`,
              }}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="m5 12.5 4.5 4.5L19 7.5" />
              </svg>
            </div>
            <div style={{ fontSize: 16, fontWeight: 800, color: text.bright }}>{t("axos.success")}</div>
            <div style={{ marginTop: 8, fontSize: 13, color: text.muted }}>{t("axos.successNote")}</div>
          </div>
        ) : (
          <>
            <div style={{ fontSize: 15, fontWeight: 800, color: text.bright }}>{t("axos.formTitle")}</div>
            <div style={{ marginTop: 6, fontSize: 12, color: text.faint }}>
              {t("axos.formAutoNote")}
              <span style={{ fontFamily: font.mono, fontSize: 11, color: text.muted }}>
                {" · "}{route} · {menu}
              </span>
            </div>

            <label style={fieldLabel} htmlFor="axos-fb-category">{t("axos.category")}</label>
            <select
              id="axos-fb-category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              style={inputStyle}
            >
              {categories.map((c) => (
                <option key={c.value} value={c.value}>{t(c.key)}</option>
              ))}
            </select>

            <label style={fieldLabel} htmlFor="axos-fb-title">
              {t("axos.titleLabel")} <span style={{ color: accent.primary, textTransform: "none" }}>({t("axos.required")})</span>
            </label>
            <input
              id="axos-fb-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={120}
              style={inputStyle}
            />

            <label style={fieldLabel} htmlFor="axos-fb-asis">
              {t("axos.asIsLabel")} <span style={{ color: accent.primary, textTransform: "none" }}>({t("axos.required")})</span>
            </label>
            <textarea
              id="axos-fb-asis"
              value={asIs}
              onChange={(e) => setAsIs(e.target.value)}
              rows={3}
              maxLength={2000}
              style={inputStyle}
            />

            <label style={fieldLabel} htmlFor="axos-fb-tobe">{t("axos.toBeLabel")}</label>
            <textarea
              id="axos-fb-tobe"
              value={toBe}
              onChange={(e) => setToBe(e.target.value)}
              rows={3}
              maxLength={2000}
              style={inputStyle}
            />

            <label style={fieldLabel} htmlFor="axos-fb-effect">{t("axos.effectLabel")}</label>
            <textarea
              id="axos-fb-effect"
              value={effect}
              onChange={(e) => setEffect(e.target.value)}
              rows={2}
              maxLength={1000}
              style={inputStyle}
            />

            <label style={fieldLabel} htmlFor="axos-fb-priority">{t("axos.priority")}</label>
            <select
              id="axos-fb-priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              style={{ ...inputStyle, marginBottom: 16 }}
            >
              {priorities.map((p) => (
                <option key={p.value} value={p.value}>{t(p.key)}</option>
              ))}
            </select>

            {error !== "" && (
              <div style={{ marginBottom: 12, fontSize: 12, color: status.violation, wordBreak: "break-all" }}>
                {error}
              </div>
            )}

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                type="button"
                onClick={onClose}
                style={{
                  font: "inherit", fontSize: 13, fontWeight: 600, cursor: "pointer",
                  color: text.muted, background: bg.raise,
                  border: `1px solid ${border.base}`, borderRadius: radius.sm, padding: "8px 14px",
                }}
              >
                {t("axos.close")}
              </button>
              <button
                type="button"
                onClick={submit}
                disabled={!canSubmit}
                style={{
                  font: "inherit", fontSize: 13, fontWeight: 700, cursor: canSubmit ? "pointer" : "default",
                  color: "#eaf9ff",
                  background: "linear-gradient(180deg, color-mix(in srgb, var(--alps-info) 62%, #061724), color-mix(in srgb, var(--alps-info) 50%, #061724))",
                  border: `1px solid color-mix(in srgb, var(--alps-info) 55%, ${border.strong})`,
                  borderRadius: radius.sm, padding: "8px 18px",
                  opacity: canSubmit ? 1 : 0.55,
                }}
              >
                {busy ? t("axos.submitting") : t("axos.submit")}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export function AxosFeedbackWidget({
  tab,
  getFilters,
  screenVersion = "w7",
}: {
  tab: string;
  /** 제출 시점의 적용 필터 스냅샷(현재 제품·변량). */
  getFilters: () => Record<string, string>;
  screenVersion?: string;
}) {
  const { t } = useTranslation();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [recent, setRecent] = useState<FeedbackSummary[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  const ctx = screenContextOf(tab);

  // 드로어가 열릴 때마다 이 화면 경로의 최근 피드백 5건(최신 우선).
  useEffect(() => {
    if (!drawerOpen) return;
    let alive = true;
    feedbackApi
      .listByRoute(ctx.route, 5)
      .then((items) => {
        if (alive) { setRecent(items); setLoadFailed(false); }
      })
      .catch(() => { if (alive) setLoadFailed(true); });
    return () => { alive = false; };
  }, [drawerOpen, ctx.route, refreshTick]);

  const onSubmitted = useCallback(() => {
    setModalOpen(false);
    setRefreshTick((n) => n + 1);
  }, []);

  // 미선택(빈 문자열) 필터는 페이로드에서 뺀다 — 기록은 "적용된 필터"만.
  const filters: Record<string, string> = {};
  for (const [key, value] of Object.entries(getFilters())) {
    if (value !== "") filters[key] = value;
  }
  const menuLabel = t(ctx.menuKey);

  const statusLabel = (value: string) => {
    switch (value) {
      case "접수": return t("axos.stReceived");
      case "개발큐": return t("axos.stQueued");
      case "개발중": return t("axos.stProgress");
      case "반영완료": return t("axos.stDone");
      default: return value;
    }
  };
  const priorityLabel = (value: string) => {
    switch (value) {
      case "상": return t("axos.priHigh");
      case "중": return t("axos.priNormal");
      case "하": return t("axos.priLow");
      default: return value;
    }
  };

  return (
    <>
      {/* 1) 우측 고정 세로 토글 탭 — 전역 1회 마운트, 모든 화면 */}
      <button
        type="button"
        aria-label={t("axos.drawerTitle")}
        onClick={() => { setDrawerOpen(true); setRecent(null); setLoadFailed(false); }}
        style={{
          position: "fixed", right: 0, top: "50%", transform: "translateY(-50%)",
          zIndex: BUTTON_Z,
          writingMode: "vertical-rl",
          display: "flex", alignItems: "center", gap: 7,
          padding: "16px 7px",
          font: "inherit", fontSize: 12, fontWeight: 800, letterSpacing: tracking.wider,
          color: "#eaf9ff",
          background: "linear-gradient(180deg, color-mix(in srgb, var(--alps-info) 62%, #061724), color-mix(in srgb, var(--alps-info) 46%, #061724))",
          border: `1px solid color-mix(in srgb, var(--alps-info) 55%, ${border.strong})`,
          borderRight: "none",
          borderRadius: `${radius.md}px 0 0 ${radius.md}px`,
          boxShadow: emboss.lift,
          cursor: "pointer",
        }}
      >
        <LayersIcon />
        AXOS
      </button>

      {drawerOpen && (
        <>
          {/* 오버레이 클릭 → 닫기. 드로어는 형제 요소라 자체 클릭은 전파 차단 불필요. */}
          <div
            onClick={() => setDrawerOpen(false)}
            style={{ position: "fixed", inset: 0, zIndex: OVERLAY_Z, background: "rgba(2, 6, 14, 0.45)" }}
          />
          {/* 2) Context Drawer — 우측 슬라이드인, w-80/max-85vw 상당 */}
          <aside
            role="complementary"
            aria-label={t("axos.drawerTitle")}
            style={{
              position: "fixed", right: 0, top: 0, bottom: 0, zIndex: DRAWER_Z,
              width: 320, maxWidth: "85vw",
              background: bg.hud, backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)",
              borderLeft: `1px solid ${border.strong}`,
              boxShadow: "-18px 0 40px rgba(0, 0, 0, 0.35)",
              padding: "18px 18px 20px",
              overflowY: "auto",
              display: "flex", flexDirection: "column",
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 15, fontWeight: 800, color: text.bright, display: "flex", alignItems: "center", gap: 7 }}>
                  <span style={{ color: "var(--alps-info)" }}><LayersIcon /></span>
                  {t("axos.drawerTitle")}
                </div>
                <div style={{ marginTop: 6, fontSize: 12, color: text.muted, lineHeight: 1.5 }}>
                  {t("axos.drawerSubtitle")}
                </div>
              </div>
              <button
                type="button"
                aria-label={t("axos.close")}
                onClick={() => setDrawerOpen(false)}
                style={{
                  font: "inherit", fontSize: 16, lineHeight: 1, cursor: "pointer",
                  color: text.muted, background: "transparent", border: "none", padding: 4,
                }}
              >
                ✕
              </button>
            </div>

            {/* 화면 목적 — Context Drawer의 자동 컨텍스트 */}
            <div style={{ marginTop: 18 }}>
              <div style={captionStyle}>{t("axos.screenContext")}</div>
              <div
                style={{
                  background: bg.raise, border: `1px solid ${border.base}`,
                  borderRadius: radius.sm, padding: "10px 12px",
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 700, color: text.bright }}>{menuLabel}</div>
                <div style={{ marginTop: 4, fontSize: 12, color: text.muted, lineHeight: 1.55 }}>
                  {t(ctx.purposeKey)}
                </div>
              </div>
            </div>

            {/* 최근 피드백 5건 — 이 화면 경로 기준, 최신 우선 */}
            <div style={{ marginTop: 18, flex: 1 }}>
              <div style={captionStyle}>{t("axos.recent")}</div>
              {loadFailed ? (
                <div style={{ fontSize: 12, color: status.violation }}>{t("axos.loadFailed")}</div>
              ) : recent !== null && recent.length === 0 ? (
                <div style={{ fontSize: 12, color: text.faint }}>{t("axos.recentEmpty")}</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {(recent ?? []).map((fb) => (
                    <div
                      key={fb.id}
                      style={{
                        background: bg.raise, border: `1px solid ${border.base}`,
                        borderRadius: radius.sm, padding: "9px 11px",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontFamily: font.mono, fontSize: 11, color: accent.id, fontWeight: 700 }}>{fb.id}</span>
                        <StatusChip value={fb.status} label={statusLabel(fb.status)} />
                        <span style={{ marginLeft: "auto", fontSize: 11, color: text.faint }}>
                          {(fb.created_at || "").slice(0, 10)}
                        </span>
                      </div>
                      <div style={{ marginTop: 5, fontSize: 13, fontWeight: 600, color: text.bright, lineHeight: 1.45 }}>
                        {fb.title}
                      </div>
                      <div style={{ marginTop: 3, fontSize: 11, color: text.faint }}>
                        {fb.category} · {t("axos.priority")} {priorityLabel(fb.priority)}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 3) 제출 모달 진입 */}
            <button
              type="button"
              onClick={() => setModalOpen(true)}
              style={{
                marginTop: 18, font: "inherit", fontSize: 13, fontWeight: 800, cursor: "pointer",
                color: "#eaf9ff", padding: "10px 0",
                background: "linear-gradient(180deg, color-mix(in srgb, var(--alps-info) 62%, #061724), color-mix(in srgb, var(--alps-info) 50%, #061724))",
                border: `1px solid color-mix(in srgb, var(--alps-info) 55%, ${border.strong})`,
                borderRadius: radius.sm,
              }}
            >
              {t("axos.submitCta")}
            </button>
          </aside>
        </>
      )}

      {modalOpen && (
        <SubmitModal
          route={ctx.route}
          menu={menuLabel}
          filters={filters}
          screenVersion={screenVersion}
          onClose={() => setModalOpen(false)}
          onSubmitted={onSubmitted}
        />
      )}
    </>
  );
}
