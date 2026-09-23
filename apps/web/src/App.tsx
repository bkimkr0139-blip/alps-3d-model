import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Product, type Variant, type Requirement, type ComponentDto, type TwinGraph, type SimulationRun } from "./lib/api";
import { initKeycloak, keycloak } from "./lib/keycloak";
import { useTwinStore } from "./store";
import { LanguageSwitcher } from "./i18n/LanguageSwitcher";
import { OnboardingGuide } from "./components/OnboardingGuide";
import { ThreeViewer } from "./components/ThreeViewer";
import { TestBench } from "./components/TestBench";
import { SystemModelView } from "./components/SystemModel";
import { ProcessTwin } from "./components/ProcessTwin";
import { AirInputStudio } from "./components/air/AirInputStudio";
import { EdaTraining } from "./components/eda/EdaTraining";
import { AsicProgram } from "./components/asic/AsicProgram";
import { SystemDocs } from "./components/SystemDocs";
import { RequirementsPanel } from "./components/RequirementsPanel";
import { SimulationPanel } from "./components/SimulationPanel";
import { SweepChart } from "./components/SweepChart";
import { TestCorrelationPanel } from "./components/TestCorrelationPanel";
import { GatePanel } from "./components/GatePanel";
import { AssistantPanel } from "./components/AssistantPanel";
import { AxosFeedbackWidget } from "./components/AxosFeedbackWidget";
import { CockpitHud } from "./components/cockpit/CockpitHud";
import { GlassDrawer } from "./ui/GlassDrawer";
import { useIsMobile } from "./ui/useIsMobile";
import { bg, border, text, tabColor, font, emboss, tracking } from "./ui/tokens";

type CenterTab = "model" | "bench" | "sysmodel" | "proc" | "air" | "eda" | "asic" | "docs";

// Per-tab color identity so the bar reads at a glance instead of needing the
// label text parsed — same "icon (shape) + text together, never colour
// alone" rule the process-monitoring chart legend already follows (§5.1),
// just applied to navigation instead of a status legend. Tabs right of the
// dividers (see STANDALONE_TABS / DOCS_TABS) are NOT views onto the selected
// product/variant — standalone modules and reference docs.
const PRODUCT_TWIN_TABS: { tab: CenterTab; color: string }[] = [
  { tab: "model", color: tabColor.model },
  { tab: "bench", color: tabColor.bench },
  { tab: "sysmodel", color: tabColor.sysmodel },
  { tab: "proc", color: tabColor.proc },
  { tab: "air", color: tabColor.air },
];
const STANDALONE_TABS: { tab: CenterTab; color: string }[] = [
  { tab: "eda", color: tabColor.eda },
  { tab: "asic", color: tabColor.asic },
];
// Reference material, not a work module — slate on purpose so it reads as
// "meta" next to the colored functional tabs.
const DOCS_TABS: { tab: CenterTab; color: string }[] = [{ tab: "docs", color: tabColor.docs }];

function tabLabel(tab: CenterTab, t: (key: string) => string): string {
  switch (tab) {
    case "model":
      return t("panels.viewer3d");
    case "bench":
      return t("panels.testbench");
    case "sysmodel":
      return t("panels.sysmodel");
    case "proc":
      return t("panels.proctwin");
    case "air":
      return t("panels.air");
    case "eda":
      return t("panels.eda");
    case "asic":
      return t("panels.asic");
    case "docs":
      return t("panels.docs");
  }
}

// Shared micro-caption for the control bar — the same label style on the
// context selects and on the two tab groups is what makes the bar read as
// one navigation system rather than two separate widgets. Uppercase with
// loosened tracking, like instrument front-panel silkscreen.
const captionStyle: React.CSSProperties = {
  fontSize: 9,
  color: text.faint,
  textTransform: "uppercase",
  letterSpacing: tracking.wider,
  fontWeight: 600,
};

// One shared control spec (height / radius / font) for every control in the
// bar — selects and tab pills were previously two different widget families.
// Brushed-metal face with a lit top edge, per the shared emboss recipe.
const selectStyle: React.CSSProperties = {
  padding: "6px 10px",
  borderRadius: 6,
  background: bg.metalRaise,
  color: text.bright,
  border: `1px solid ${border.strong}`,
  boxShadow: emboss.lift,
  fontFamily: "inherit",
  fontSize: 13,
};

// <label> wrapper for a real form control (selects) — caption text activates
// the control, which is what you want there.
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={captionStyle}>{label}</span>
      {children}
    </label>
  );
}

// Plain div variant for tab groups — a <label> would forward caption clicks
// to the first tab button.
function NavGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={captionStyle}>{label}</span>
      {children}
    </div>
  );
}

// App-wide dark/light chrome switch. The store persists the choice and
// mirrors it onto <html data-theme>, which flips the --alps-* CSS variables
// the whole inline-styled UI is built from. Icon is inline SVG in
// currentColor so it reads identically in both themes (no emoji variance).
function ThemeToggle() {
  const { t } = useTranslation();
  const uiTheme = useTwinStore((s) => s.uiTheme);
  const setUiTheme = useTwinStore((s) => s.setUiTheme);
  const toLight = uiTheme === "dark";
  return (
    <button
      onClick={() => setUiTheme(toLight ? "light" : "dark")}
      aria-label={toLight ? t("app.toLight") : t("app.toDark")}
      title={toLight ? t("app.toLight") : t("app.toDark")}
      style={{
        width: 32,
        height: 32,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: 6,
        background: bg.metalRaise,
        border: `1px solid ${border.strong}`,
        boxShadow: emboss.lift,
        color: text.body,
      }}
    >
      {toLight ? (
        // Sun: circle + eight rays.
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <circle cx="8" cy="8" r="3.2" />
          {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => {
            const r = (a * Math.PI) / 180;
            return (
              <line
                key={a}
                x1={8 + 5.2 * Math.cos(r)}
                y1={8 + 5.2 * Math.sin(r)}
                x2={8 + 6.8 * Math.cos(r)}
                y2={8 + 6.8 * Math.sin(r)}
              />
            );
          })}
        </svg>
      ) : (
        // Moon: crescent via a cut-out circle.
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden fill="currentColor">
          <path d="M10.8 2.2a6 6 0 1 0 3 8.9A6.8 6.8 0 0 1 10.8 2.2Z" />
        </svg>
      )}
    </button>
  );
}

function TabButton({
  label,
  active,
  color,
  onClick,
}: {
  label: string;
  active: boolean;
  color: string;
  onClick: () => void;
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 10px",
        borderRadius: 6,
        border: "1px solid",
        borderColor: active ? `color-mix(in srgb, ${color} 53%, transparent)` : "transparent",
        // Embossed key cap: inactive keys sit slightly raised on the metal
        // bar; the active key glows in its own identity color with an LED
        // pip that brightens (the dot is the tab's status LED). Tints compose
        // via color-mix because the identity colors are theme variables.
        background: active
          ? `linear-gradient(180deg, color-mix(in srgb, ${color} 18%, transparent) 0%, color-mix(in srgb, ${color} 9%, transparent) 100%)`
          : "var(--alps-keycap)",
        boxShadow: active
          ? `inset 0 1px 0 color-mix(in srgb, ${color} 33%, transparent), inset 0 0 8px color-mix(in srgb, ${color} 15%, transparent), 0 1px 2px rgba(2,6,23,0.5)`
          : `inset 0 1px 0 ${border.rim}, 0 1px 2px rgba(2,6,23,0.4)`,
        color: active ? text.bright : text.muted,
        fontFamily: "inherit",
        fontWeight: active ? 600 : 400,
        fontSize: 13,
        textShadow: active ? `0 0 10px color-mix(in srgb, ${color} 40%, transparent)` : "none",
        cursor: "pointer",
        whiteSpace: "nowrap",
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: color,
          flexShrink: 0,
          boxShadow: active ? `0 0 7px ${color}` : "none",
          transition: "box-shadow 150ms ease",
        }}
      />
      {label}
    </button>
  );
}

// Keep the breakpoint in sync with the mobile media query in index.css,
// which flattens the inline grids — this hook handles what CSS cannot:
// heights and panel ordering of the top-level layout.

function useTwinData(variantId: string | null) {
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [components, setComponents] = useState<ComponentDto[]>([]);
  const [graph, setGraph] = useState<TwinGraph | null>(null);
  const [runs, setRuns] = useState<SimulationRun[]>([]);

  useEffect(() => {
    if (!variantId) return;
    api.listRequirements(variantId).then(setRequirements);
    api.listComponents(variantId).then(setComponents);
    api.twinGraph(variantId).then(setGraph);
    api.listSimulationRuns(variantId).then(setRuns);
  }, [variantId]);

  return { requirements, components, graph, runs };
}

function Workbench() {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const variantId = useTwinStore((s) => s.variantId);
  const setVariantId = useTwinStore((s) => s.setVariantId);
  const setSelectedComponentId = useTwinStore((s) => s.setSelectedComponentId);
  const setSelectedRequirementId = useTwinStore((s) => s.setSelectedRequirementId);

  const [products, setProducts] = useState<Product[]>([]);
  const [product, setProduct] = useState<Product | null>(null);
  const [variants, setVariants] = useState<Variant[]>([]);
  const [centerTab, setCenterTab] = useState<CenterTab>("model");
  // Cockpit drawers (model tab, desktop): requirements / simulation results
  // float OVER the 3D canvas instead of flanking it as grid columns — a
  // column toggle would resize the canvas and retrigger the Bounds fit,
  // visibly jerking the camera. Default closed; the HUD sync chip keeps the
  // requirement link visible either way.
  const [leftDrawer, setLeftDrawer] = useState(false);
  const [rightDrawer, setRightDrawer] = useState(false);

  // Selection from another product/variant must not leak into the new one —
  // ids would match no mesh/requirement and leave a stale highlight.
  function clearSelection() {
    setSelectedComponentId(null);
    setSelectedRequirementId(null);
  }

  function selectProduct(p: Product) {
    setProduct(p);
    setVariants([]);
    clearSelection();
    api.listVariants(p.id).then((vs) => {
      setVariants(vs);
      if (vs[0]) setVariantId(vs[0].id);
    });
  }

  useEffect(() => {
    api.listProducts().then(async (loaded) => {
      setProducts(loaded);
      if (loaded[0]) selectProduct(loaded[0]);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { requirements, components, graph, runs } = useTwinData(variantId);
  const mechRun = runs.find((r) => r.run_type === "mech_model") ?? null;

  // Cross-variant comparison (§12.2: "Variant 2개 이상을 동일 축과 동일 단위로
  // 비교") needs every variant's latest SPICE run, not just the selected one.
  const [compareRuns, setCompareRuns] = useState<{ label: string; run: SimulationRun }[]>([]);
  useEffect(() => {
    if (variants.length === 0) return;
    Promise.all(
      variants.map(async (v) => {
        const runs = await api.listSimulationRuns(v.id);
        const latestSpice = runs.find((r) => r.run_type === "spice_analysis" && r.status === "succeeded");
        return latestSpice ? { label: v.name, run: latestSpice } : null;
      })
    ).then((results) => setCompareRuns(results.filter((r): r is { label: string; run: SimulationRun } => r !== null)));
  }, [variants]);

  function selectRequirement(req: Requirement) {
    setSelectedRequirementId(req.id);
    const edge = graph?.edges.find((e) => e.source === req.id);
    setSelectedComponentId(edge ? edge.target : null);
  }

  function selectComponentFromStore(componentId: string | null) {
    if (!componentId) {
      setSelectedRequirementId(null);
      return;
    }
    const edge = graph?.edges.find((e) => e.target === componentId);
    setSelectedRequirementId(edge ? edge.source : null);
  }

  // ThreeViewer sets selectedComponentId directly via the store; mirror that
  // into selectedRequirementId here so both panels always agree (§6.2).
  const selectedComponentId = useTwinStore((s) => s.selectedComponentId);
  useEffect(() => {
    selectComponentFromStore(selectedComponentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedComponentId, graph]);

  // EDA 교육 탭·ASIC 9단계 작업 센터·시스템 문서 탭은 제품/변량 데이터와
  // 무관한 자립 모듈이므로 좌우 사이드 패널·온보딩 가이드·하단 비교/상관/
  // 게이트 프레임·어시스턴트를 접어 중앙에 전폭을 내준다.
  const standaloneMode = centerTab === "eda" || centerTab === "asic" || centerTab === "docs";
  // 시스템 문서는 플랫폼 관리자 전용(사용자 지시): 토큰의 realm 롤로 판정한다
  // — 새 관리자에게는 Keycloak에서 platform_admin 롤만 부여하면 된다. Workbench는
  // initKeycloak() 해결 후에 마운트되므로 tokenParsed는 항상 채워져 있다.
  const isAdmin = !!keycloak.tokenParsed?.realm_access?.roles?.includes("platform_admin");
  // 3D-first cockpit: the model tab (desktop) gives the twin the whole first
  // screen; every other product tab keeps the 3-column dashboard. Mobile
  // keeps the stacked flow — overlay drawers don't work at 820px widths.
  const cockpitMode = centerTab === "model" && !isMobile;

  return (
    <div style={{ minHeight: "100vh", background: bg.page, color: text.body, padding: isMobile ? 12 : 20, fontFamily: font.ui }}>
      <header
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 8,
          marginBottom: 10,
          padding: "10px 14px",
          borderRadius: 10,
          background: bg.metalHeader,
          border: `1px solid ${border.strong}`,
          boxShadow: `inset 0 1px 0 ${border.rim}, 0 2px 10px rgba(2,6,23,0.45)`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {/* Brand pip: a machined accent edge, the one strong-color element
              on the header — everything else stays graphite. */}
          <span
            aria-hidden
            style={{ width: 4, alignSelf: "stretch", minHeight: 34, borderRadius: 3, background: "linear-gradient(180deg, #ff8a50, #e05a1e)", boxShadow: "0 0 10px rgba(255,107,53,0.45)" }}
          />
          <div>
            <h1 style={{ margin: 0, fontSize: isMobile ? 16 : 19, fontWeight: 700, letterSpacing: "0.2px", color: text.bright }}>{t("app.title")}</h1>
            <div style={{ opacity: 0.62, fontSize: 12, letterSpacing: tracking.micro }}>{product?.name}</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {/* Language + theme live pinned at the top-right of the header —
              global settings, independent of what the nav bar below wraps. */}
          <LanguageSwitcher />
          <ThemeToggle />
          <span
            style={{
              fontSize: 12,
              fontFamily: font.mono,
              padding: "4px 10px",
              borderRadius: 6,
              background: bg.metalWell,
              border: `1px solid ${border.base}`,
              boxShadow: emboss.well,
              color: text.muted,
            }}
          >
            {keycloak.tokenParsed?.preferred_username}
          </span>
          <button
            onClick={() => keycloak.logout()}
            style={{
              padding: "6px 12px",
              borderRadius: 6,
              background: bg.metalRaise,
              border: `1px solid ${border.strong}`,
              boxShadow: emboss.lift,
              color: text.body,
            }}
          >
            {t("app.logout")}
          </button>
        </div>
      </header>

      {/* One navigation bar: what I'm looking at (product ▸ variant selects)
          and where I look from (view tabs / standalone module tabs) share
          the same control metrics and captions, so the header selects and
          the center tab bar read as a single hierarchy instead of two
          unrelated widgets. Product/variant dim + disable in standalone
          module mode — honest UI: EDA/ASIC ignore that context entirely. */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: isMobile ? 8 : 12, marginBottom: 12 }}>
        <span style={{ opacity: standaloneMode ? 0.45 : 1, transition: "opacity 150ms" }}>
          <Field label={t("nav.product")}>
            <select
              value={product?.id ?? ""}
              disabled={standaloneMode}
              aria-label={t("nav.product")}
              onChange={(e) => {
                const p = products.find((x) => x.id === e.target.value);
                if (p) selectProduct(p);
              }}
              style={isMobile ? { ...selectStyle, maxWidth: "46vw" } : selectStyle}
            >
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
        </span>
        <span style={{ opacity: standaloneMode ? 0.45 : 1, transition: "opacity 150ms" }}>
          <Field label={t("nav.variant")}>
            <select
              value={variantId ?? ""}
              disabled={standaloneMode}
              aria-label={t("nav.variant")}
              onChange={(e) => {
                clearSelection();
                setVariantId(e.target.value);
              }}
              style={isMobile ? { ...selectStyle, maxWidth: "46vw" } : selectStyle}
            >
              {variants.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </Field>
        </span>
        <div className="nav-divider" style={{ width: 1, alignSelf: "stretch", background: border.strong }} />
        <NavGroup label={t("nav.views")}>
          <div role="tablist" aria-label={t("nav.views")} style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {PRODUCT_TWIN_TABS.map(({ tab, color }) => (
              <TabButton
                key={tab}
                label={tabLabel(tab, t as (k: string) => string)}
                color={color}
                active={centerTab === tab}
                onClick={() => setCenterTab(tab)}
              />
            ))}
          </div>
        </NavGroup>
        {/* Everything right of this divider is a standalone module that
            ignores the product/variant context on the left. */}
        <div className="nav-divider" style={{ width: 1, alignSelf: "stretch", background: border.strong }} />
        <NavGroup label={t("nav.modules")}>
          <div role="tablist" aria-label={t("nav.modules")} style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {STANDALONE_TABS.map(({ tab, color }) => (
              <TabButton
                key={tab}
                label={tabLabel(tab, t as (k: string) => string)}
                color={color}
                active={centerTab === tab}
                onClick={() => setCenterTab(tab)}
              />
            ))}
          </div>
        </NavGroup>
        {/* Reference material is its own group: readable at any time, still
            independent of the product/variant context — 관리자 세션에서만
            렌더(플랫폼 관리자 전용 시스템 문서). */}
        {isAdmin && (
          <>
            <div className="nav-divider" style={{ width: 1, alignSelf: "stretch", background: border.strong }} />
            <NavGroup label={t("nav.docs")}>
              <div role="tablist" aria-label={t("nav.docs")} style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {DOCS_TABS.map(({ tab, color }) => (
                  <TabButton
                    key={tab}
                    label={tabLabel(tab, t as (k: string) => string)}
                    color={color}
                    active={centerTab === tab}
                    onClick={() => setCenterTab(tab)}
                  />
                ))}
              </div>
            </NavGroup>
          </>
        )}
        <div style={{ flex: 1 }} />
        {standaloneMode && (
          <span style={{ fontSize: 12, color: text.faint, paddingBottom: 8, maxWidth: 340 }}>
            ⓘ {t("nav.standaloneHint")}
          </span>
        )}
      </div>

      {/* The guide coaches the product/variant flow — noise in standalone
          modules (EDA/ASIC/docs get the full width instead). */}
      {!standaloneMode && (
        <OnboardingGuide
          variantId={variantId}
          requirements={requirements}
          components={components}
          graph={graph}
          runs={runs}
          mechRun={mechRun}
        />
      )}

      {cockpitMode ? (
        // The cockpit: the twin owns the first screen. Context (requirements,
        // results) lives in glass drawers floating over the canvas; the HUD
        // chip strip keeps gate/run/selection state on screen. The lower
        // sections (sweep/correlation/gate/assistant) still flow below, so
        // the page scrolls exactly like the other tabs.
        <div style={{ position: "relative", height: "calc(100vh - 200px)", minHeight: 480 }}>
          {/* controlsTop=52: TwinControls yields the top edge to the HUD chip strip */}
          <ThreeViewer components={components} controlsTop={52} />
          <CockpitHud
            productName={product?.name}
            variantName={variants.find((v) => v.id === variantId)?.name}
            variantId={variantId}
            runs={runs}
            requirements={requirements}
            components={components}
            leftOpen={leftDrawer}
            rightOpen={rightDrawer}
            onToggleLeft={() => setLeftDrawer((o) => !o)}
            onToggleRight={() => setRightDrawer((o) => !o)}
          />
          {leftDrawer && (
            <GlassDrawer side="left" title={t("panels.requirements")} onClose={() => setLeftDrawer(false)}>
              <RequirementsPanel requirements={requirements} onSelect={selectRequirement} />
            </GlassDrawer>
          )}
          {rightDrawer && (
            <GlassDrawer side="right" title={t("panels.simulation")} onClose={() => setRightDrawer(false)}>
              <SimulationPanel runs={runs} />
            </GlassDrawer>
          )}
        </div>
      ) : (
      <div
        style={{
          display: "grid",
          gridTemplateColumns: !isMobile && !standaloneMode ? "320px 1fr 340px" : "1fr",
          gap: 16,
          // Tab bar moved up into the nav bar — 62vh keeps the same viewport
          // share the center column had when it still carried the tabs. That
          // clamp is a 3-column dashboard concern only: standalone modules
          // (ASIC/EDA/docs) own the full page and flow naturally — the page
          // scrolls with the content open, like every other tab's lower
          // sections. On phones the rows stack (CSS flattens the columns) so
          // heights move onto the children and the page scrolls anyway.
          // The model tab on desktop is exempt too — it renders the cockpit
          // branch above instead of this grid.
          height: !isMobile && !standaloneMode ? "62vh" : undefined,
        }}
      >
        {!standaloneMode && (
          <div style={{ overflowY: "auto", ...(isMobile && { height: "42vh", order: 2 }) }}>
            <RequirementsPanel requirements={requirements} onSelect={selectRequirement} />
          </div>
        )}
        <div style={{ minHeight: 0, overflow: "hidden", ...(isMobile && !standaloneMode && { height: "58vh", order: 1, overflowY: "auto" }) }}>
          {centerTab === "model" ? (
              <ThreeViewer components={components} />
            ) : centerTab === "bench" ? (
              <TestBench product={product} variantName={variants.find((v) => v.id === variantId)?.name} runs={runs} components={components} />
            ) : centerTab === "sysmodel" ? (
              <SystemModelView key={variantId ?? "none"} variantId={variantId} />
            ) : centerTab === "air" ? (
              <AirInputStudio key={variantId ?? "none"} variantId={variantId} runs={runs} />
            ) : centerTab === "eda" ? (
              <EdaTraining />
            ) : centerTab === "asic" ? (
              <AsicProgram />
            ) : centerTab === "docs" ? (
              <SystemDocs />
            ) : (
              <ProcessTwin
                key={variantId ?? "none"}
                variantId={variantId}
                productBusinessId={product?.business_id}
              />
            )}
        </div>
        {!standaloneMode && (
          <div style={{ overflowY: "auto", ...(isMobile && { height: "42vh", order: 3 }) }}>
            <SimulationPanel runs={runs} />
          </div>
        )}
      </div>
      )}

      {!standaloneMode && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
            {compareRuns.length > 0 && (
              <div style={{ border: `1px solid ${border.strong}`, borderRadius: 8, padding: 12 }}>
                <h3 style={{ marginTop: 0 }}>{t("panels.sweep")}</h3>
                <SweepChart runsByVariant={compareRuns} />
              </div>
            )}
            <div style={{ border: `1px solid ${border.strong}`, borderRadius: 8, padding: 12 }}>
              <h3 style={{ marginTop: 0 }}>{t("panels.correlation")}</h3>
              <TestCorrelationPanel mechRun={mechRun} />
            </div>
          </div>

          <div style={{ marginTop: 16, border: `1px solid ${border.strong}`, borderRadius: 8, padding: 12 }}>
            <h3 style={{ marginTop: 0 }}>{t("panels.gate")}</h3>
            <GatePanel variantId={variantId} />
          </div>

          <AssistantPanel />
        </>
      )}

      {/* AXOS 피드백 버튼 — standalone 모드(EDA/ASIC/docs) 포함 전 화면에서 1회 마운트. */}
      <AxosFeedbackWidget
        tab={centerTab}
        getFilters={() => ({
          product: product?.name ?? "",
          variant: variants.find((v) => v.id === variantId)?.name ?? "",
        })}
      />
    </div>
  );
}

export default function App() {
  const { t } = useTranslation();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    initKeycloak().then(() => setReady(true));
  }, []);

  if (!ready) return <div style={{ padding: 40, color: "var(--alps-text-bright)" }}>{t("app.signingIn")}</div>;
  return <Workbench />;
}
