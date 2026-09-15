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
import { RequirementsPanel } from "./components/RequirementsPanel";
import { SimulationPanel } from "./components/SimulationPanel";
import { SweepChart } from "./components/SweepChart";
import { TestCorrelationPanel } from "./components/TestCorrelationPanel";
import { GatePanel } from "./components/GatePanel";
import { AssistantPanel } from "./components/AssistantPanel";

type CenterTab = "model" | "bench" | "sysmodel" | "proc" | "air" | "eda";

// Per-tab color identity so the bar reads at a glance instead of needing the
// label text parsed — same "icon (shape) + text together, never colour
// alone" rule the process-monitoring chart legend already follows (§5.1),
// just applied to navigation instead of a status legend. "eda" is visually
// split off from the rest with a divider below: it is the one tab that is
// NOT a view onto the selected product/variant (see edaMode) — a standalone
// training module, not another twin.
const PRODUCT_TWIN_TABS: { tab: CenterTab; color: string }[] = [
  { tab: "model", color: "#60a5fa" },
  { tab: "bench", color: "#fbbf24" },
  { tab: "sysmodel", color: "#a78bfa" },
  { tab: "proc", color: "#4ade80" },
  { tab: "air", color: "#22d3ee" },
];
const STANDALONE_TABS: { tab: CenterTab; color: string }[] = [{ tab: "eda", color: "#f97316" }];

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
  }
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
        borderColor: active ? color : "transparent",
        background: active ? `${color}22` : "transparent",
        color: active ? "#f1f5f9" : "#94a3b8",
        fontFamily: "inherit",
        fontWeight: active ? 600 : 400,
        fontSize: 13,
        cursor: "pointer",
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
      {label}
    </button>
  );
}

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
  const variantId = useTwinStore((s) => s.variantId);
  const setVariantId = useTwinStore((s) => s.setVariantId);
  const setSelectedComponentId = useTwinStore((s) => s.setSelectedComponentId);
  const setSelectedRequirementId = useTwinStore((s) => s.setSelectedRequirementId);

  const [products, setProducts] = useState<Product[]>([]);
  const [product, setProduct] = useState<Product | null>(null);
  const [variants, setVariants] = useState<Variant[]>([]);
  const [centerTab, setCenterTab] = useState<CenterTab>("model");

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

  // EDA 교육 탭은 제품/변량 데이터와 무관한 자립 훈련 모듈이므로 좌우 사이드
  // 패널·하단 비교/상관/게이트 프레임·어시스턴트를 접어 중앙에 전폭을 내준다.
  const edaMode = centerTab === "eda";

  return (
    <div style={{ minHeight: "100vh", background: "#020617", color: "#e2e8f0", padding: 20, fontFamily: "system-ui, sans-serif" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 20 }}>{t("app.title")}</h1>
          <div style={{ opacity: 0.6, fontSize: 13 }}>{product?.name}</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <LanguageSwitcher />
          <select
            value={product?.id ?? ""}
            onChange={(e) => {
              const p = products.find((x) => x.id === e.target.value);
              if (p) selectProduct(p);
            }}
            style={{ padding: "6px 10px", borderRadius: 6, background: "#1e293b", color: "white", border: "1px solid #334155" }}
          >
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <select
            value={variantId ?? ""}
            onChange={(e) => {
              clearSelection();
              setVariantId(e.target.value);
            }}
            style={{ padding: "6px 10px", borderRadius: 6, background: "#1e293b", color: "white", border: "1px solid #334155" }}
          >
            {variants.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
          <span style={{ fontSize: 13, opacity: 0.7 }}>{keycloak.tokenParsed?.preferred_username}</span>
          <button onClick={() => keycloak.logout()} style={{ padding: "6px 10px", borderRadius: 6 }}>
            {t("app.logout")}
          </button>
        </div>
      </header>

      <OnboardingGuide
        variantId={variantId}
        requirements={requirements}
        components={components}
        graph={graph}
        runs={runs}
        mechRun={mechRun}
      />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: edaMode ? "1fr" : "320px 1fr 340px",
          gap: 16,
          height: "68vh",
        }}
      >
        {!edaMode && (
          <div style={{ overflowY: "auto" }}>
            <RequirementsPanel requirements={requirements} onSelect={selectRequirement} />
          </div>
        )}
        <div style={{ minHeight: 0, display: "flex", flexDirection: "column" }}>
          <div role="tablist" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 4, marginBottom: 8 }}>
            {PRODUCT_TWIN_TABS.map(({ tab, color }) => (
              <TabButton
                key={tab}
                label={tabLabel(tab, t as (k: string) => string)}
                color={color}
                active={centerTab === tab}
                onClick={() => setCenterTab(tab)}
              />
            ))}
            {/* Divider: everything left of it is a view onto the selected
                product/variant; everything right of it (currently just EDA
                training) is a standalone module that ignores both. */}
            <div style={{ width: 1, alignSelf: "stretch", background: "#334155", margin: "2px 4px" }} />
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
          <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
            {centerTab === "model" ? (
              <ThreeViewer components={components} />
            ) : centerTab === "bench" ? (
              <TestBench product={product} runs={runs} />
            ) : centerTab === "sysmodel" ? (
              <SystemModelView key={variantId ?? "none"} variantId={variantId} />
            ) : centerTab === "air" ? (
              <AirInputStudio key={variantId ?? "none"} variantId={variantId} runs={runs} />
            ) : centerTab === "eda" ? (
              <EdaTraining />
            ) : (
              <ProcessTwin
                key={variantId ?? "none"}
                variantId={variantId}
                productBusinessId={product?.business_id}
              />
            )}
          </div>
        </div>
        {!edaMode && (
          <div style={{ overflowY: "auto" }}>
            <SimulationPanel runs={runs} />
          </div>
        )}
      </div>

      {!edaMode && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
            {compareRuns.length > 0 && (
              <div style={{ border: "1px solid #334155", borderRadius: 8, padding: 12 }}>
                <h3 style={{ marginTop: 0 }}>{t("panels.sweep")}</h3>
                <SweepChart runsByVariant={compareRuns} />
              </div>
            )}
            <div style={{ border: "1px solid #334155", borderRadius: 8, padding: 12 }}>
              <h3 style={{ marginTop: 0 }}>{t("panels.correlation")}</h3>
              <TestCorrelationPanel mechRun={mechRun} />
            </div>
          </div>

          <div style={{ marginTop: 16, border: "1px solid #334155", borderRadius: 8, padding: 12 }}>
            <h3 style={{ marginTop: 0 }}>{t("panels.gate")}</h3>
            <GatePanel variantId={variantId} />
          </div>

          <AssistantPanel />
        </>
      )}
    </div>
  );
}

export default function App() {
  const { t } = useTranslation();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    initKeycloak().then(() => setReady(true));
  }, []);

  if (!ready) return <div style={{ padding: 40, color: "white" }}>{t("app.signingIn")}</div>;
  return <Workbench />;
}
