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
import { RequirementsPanel } from "./components/RequirementsPanel";
import { SimulationPanel } from "./components/SimulationPanel";
import { SweepChart } from "./components/SweepChart";
import { TestCorrelationPanel } from "./components/TestCorrelationPanel";
import { GatePanel } from "./components/GatePanel";
import { AssistantPanel } from "./components/AssistantPanel";

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
  const [centerTab, setCenterTab] = useState<"model" | "bench" | "sysmodel" | "proc" | "air">("model");

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

      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr 340px", gap: 16, height: "68vh" }}>
        <div style={{ overflowY: "auto" }}>
          <RequirementsPanel requirements={requirements} onSelect={selectRequirement} />
        </div>
        <div style={{ minHeight: 0, display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", gap: 14, marginBottom: 8 }}>
            {(["model", "bench", "sysmodel", "proc", "air"] as const).map((tab) => (
              <h3
                key={tab}
                onClick={() => setCenterTab(tab)}
                style={{
                  marginTop: 0,
                  marginBottom: 0,
                  cursor: "pointer",
                  opacity: centerTab === tab ? 1 : 0.55,
                  borderBottom: centerTab === tab ? "2px solid #f97316" : "2px solid transparent",
                  paddingBottom: 2,
                }}
              >
                {tab === "model"
                  ? t("panels.viewer3d")
                  : tab === "bench"
                    ? t("panels.testbench")
                    : tab === "sysmodel"
                      ? t("panels.sysmodel")
                      : tab === "proc"
                        ? t("panels.proctwin")
                        : t("panels.air")}
              </h3>
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
            ) : (
              <ProcessTwin
                key={variantId ?? "none"}
                variantId={variantId}
                productBusinessId={product?.business_id}
              />
            )}
          </div>
        </div>
        <div style={{ overflowY: "auto" }}>
          <SimulationPanel runs={runs} />
        </div>
      </div>

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
