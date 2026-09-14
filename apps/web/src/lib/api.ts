import { keycloak } from "./keycloak";

// Relative, same-origin — the local gateway (or the public tunnel) proxies
// /api/* to the FastAPI backend. See infra/nginx/local-gateway.conf.
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  await keycloak.updateToken(30).catch(() => keycloak.login());
  const resp = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${keycloak.token}`,
      ...(init?.headers ?? {}),
    },
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status} ${path}: ${body}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

// Binary variant of request() — same auth, arrayBuffer body. Used for
// artifacts streamed through the API (never presigned MinIO URLs from the
// browser — see ThreeViewer / the M7 gotcha in AGENTS.md).
async function requestBinary(path: string): Promise<ArrayBuffer> {
  await keycloak.updateToken(30).catch(() => keycloak.login());
  const resp = await fetch(path, {
    headers: { Authorization: `Bearer ${keycloak.token}` },
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status} ${path}: ${body}`);
  }
  return resp.arrayBuffer();
}

export interface Product {
  id: string;
  business_id: string;
  name: string;
}

export interface Variant {
  id: string;
  business_id: string;
  product_id: string;
  name: string;
}

export interface Requirement {
  id: string;
  business_id: string;
  variant_id: string;
  text: string;
  verification_method: string;
  safety_class: string;
  status: string;
}

export interface ComponentDto {
  id: string;
  business_id: string;
  variant_id: string;
  name: string;
  artifact_version_id: string | null;
}

export interface TwinGraph {
  variant_id: string;
  nodes: { id: string; type: "requirement" | "component"; business_id: string; label: string }[];
  edges: { id: string; source: string; target: string; target_type: string }[];
}

export interface SimulationRun {
  id: string;
  business_id: string;
  variant_id: string;
  run_type: string;
  status: string;
  output_artifact_version_id: string | null;
  tool_version: string | null;
  error_message: string | null;
  metrics: { name: string; value: number; unit: string | null }[];
}

export interface Measurement {
  id: string;
  business_id: string;
  test_run_id: string;
  x_value: number;
  y_value: number;
  x_unit: string;
  y_unit: string;
}

export interface CorrelationRecord {
  id: string;
  business_id: string;
  simulation_run_id: string;
  test_run_id: string;
  rmse: number;
  mae: number;
  max_error: number;
  correlation_coefficient: number;
  extrapolation_warning: boolean;
  overlap_x_min: number;
  overlap_x_max: number;
}

export interface Gate {
  id: string;
  business_id: string;
  variant_id: string;
  baseline_id: string;
  name: string;
  status: "draft" | "pending_review" | "approved" | "rejected" | "conditionally_approved";
  required_roles: string[];
  evidence_checklist: { passed: boolean; missing: string[]; checklist: Record<string, boolean> } | null;
  submitted_by: string | null;
  submitted_at: string | null;
}

export interface GateComment {
  id: string;
  business_id: string;
  gate_id: string;
  author: string;
  text: string;
  created_at: string;
}

export interface GateDecision {
  id: string;
  business_id: string;
  gate_id: string;
  decision: "approved" | "rejected" | "conditionally_approved";
  actor: string;
  actor_roles: string[];
  comment: string;
  decided_at: string;
}

export interface AssistantDisplayBlock {
  type: string;
  text?: string;
}

export interface PendingActionInfo {
  action_id: string;
  tool: string;
  tool_use_id: string;
  args: Record<string, unknown>;
  summary_args: string;
}

export interface AssistantChatResponse {
  display: AssistantDisplayBlock[];
  pending_action: PendingActionInfo | null;
  thread: unknown[];
}

export interface AssistantActionResult {
  action_id: string;
  tool: string;
  status: "executed" | "failed" | "cancelled";
  result?: unknown;
  detail?: unknown;
}

// --- Model Canvas (지시서 ①②④: impact paths / system model / model card) ---

export interface EvidenceRef {
  kind: "simulation_run" | "test_run";
  business_id: string;
  note?: string | null;
}

export interface ImpactPaths {
  variant_id: string;
  nodes: { label: string; domain: string }[];
  edges: {
    id: string;
    business_id: string;
    source: string;
    source_domain: string;
    target: string;
    target_domain: string;
    relation_type: string;
    mechanism: string | null;
    evidence: EvidenceRef[];
    confidence: number | null;
    provenance: "imported" | "rule_derived" | "ai_inferred" | "human_approved";
  }[];
}

export interface ModelElementDto {
  id: string;
  business_id: string;
  variant_id: string;
  name: string;
  domain: "mechanical" | "electrical" | "control" | "kansei";
  equation_text: string | null;
  description: string | null;
  unit: string | null;
  geometry_component_id: string | null;
  position: { x: number; y: number } | null;
}

export interface ModelLinkDto {
  id: string;
  business_id: string;
  source_element_id: string;
  target_element_id: string;
  signal: string;
  unit: string | null;
  kind: string;
  unit_conversion: string | null;
}

export interface PortContractDto {
  id: string;
  business_id: string;
  element_id: string;
  name: string;
  direction: "in" | "out" | "inout";
  quantity: string;
  unit: string;
  range_min: number | null;
  range_max: number | null;
  timing_semantics: string | null;
  created_by: string;
  created_at: string;
}

export interface SystemModel {
  variant_id: string;
  elements: ModelElementDto[];
  links: ModelLinkDto[];
  ports: PortContractDto[];
}

export interface ReviewFindingDto {
  id: string;
  business_id: string;
  run_no: number;
  category: string;
  severity: "error" | "warning" | "suggestion";
  title: string;
  detail: string | null;
  evidence: { kind: string; business_id: string; note?: string }[] | null;
  resolution: string | null;
  status: "open" | "resolved" | "accepted";
  provenance: string;
  created_by: string;
  created_at: string;
}

export interface ReviewRunDto {
  variant_id: string;
  run_no: number;
  findings: ReviewFindingDto[];
}

export interface UQAnalysisDto {
  id: string;
  business_id: string;
  variant_id: string;
  model_type: "fs_dome" | "detent_torque" | "bridge_transfer";
  n_samples: number;
  seed: number;
  inputs: { name: string; distribution: string; params: Record<string, number>; unit: string | null; source: string }[];
  metric_name: string;
  metric_unit: string;
  target_band: { min: number; max: number; unit: string | null; source: string | null };
  results: {
    mean: number;
    sd: number;
    p05: number;
    p50: number;
    p95: number;
    min: number;
    max: number;
    hist: { bin_edges: number[]; counts: number[] };
    violation_prob: number;
    violation_count: number;
    target_band: { min: number; max: number; unit: string };
  };
  created_by: string;
  created_at: string;
}

export interface GapAnalysisDto {
  correlation_id: string;
  residuals: { x: number[]; residual: number[]; measured: number[]; predicted: number[] };
  stats: {
    n_points: number;
    x_unit: string;
    y_unit: string;
    mean: number;
    sd: number;
    min: number;
    max: number;
    slope_per_x_unit: number;
    x_span: number;
  };
  candidates: {
    cause: string;
    confidence: string;
    title: string;
    detail: string;
    evidence: { kind: string; business_id: string }[];
  }[];
}

export interface ValidityBound {
  parameter: string;
  unit: string | null;
  min: number;
  max: number;
}

export interface ModelCardDto {
  id: string;
  business_id: string;
  variant_id: string;
  title: string;
  purpose: string;
  equation_text: string | null;
  assumptions: string[] | null;
  evidence: EvidenceRef[] | null;
  validity_envelope: ValidityBound[] | null;
  trust_state: "draft" | "verified" | "validated_for_purpose" | "approved_for_reuse" | "retired";
  notes: string | null;
  created_by: string;
  created_at: string;
}

// Threads are opaque: the server returns the canonical JSON array and the
// client echoes it back untouched (thinking blocks must survive replay).
export const assistantApi = {
  chat: (messages: unknown[], uiLanguage: string) =>
    request<AssistantChatResponse>("/api/v1/assistant/chat", {
      method: "POST",
      body: JSON.stringify({ messages, ui_language: uiLanguage }),
    }),
  confirm: (actionId: string) =>
    request<AssistantActionResult>(`/api/v1/assistant/actions/${actionId}/confirm`, { method: "POST" }),
  cancel: (actionId: string) =>
    request<AssistantActionResult>(`/api/v1/assistant/actions/${actionId}/cancel`, { method: "POST" }),
};

// -- Process Twin (TACT Product–Process Twin 지시서 P1 vertical slice) ---------

export interface LotCard {
  id: string;
  business_id: string;
  variant_id: string;
  mold_id: string;
  cavity_id: string;
  material_lot_id: string | null;
  work_order_id: string | null;
  produced_at: string;
  quantity: number | null;
  disposition: "ok" | "quarantine" | "reject";
  notes: string | null;
  cavity_label: string;
  defect_count: number;
  out_of_window_runs: number;
  created_at: string;
}

export interface GenealogyProcessRun {
  business_id: string;
  operation: string;
  operation_business_id: string;
  seq_no: number;
  equipment: string | null;
  setpoint: Record<string, unknown> | null;
  actual: Record<string, unknown> | null;
  out_of_window: boolean;
  window_findings: { parameter: string; actual: number; min: number; max: number; unit: string | null }[] | null;
  started_at: string;
}

export interface LotGenealogy {
  lot: LotCard;
  mold: { id: string; business_id: string; name: string; tool_revision: string; process: string | null };
  cavity: { id: string; business_id: string; cavity_no: number; label: string };
  process_runs: GenealogyProcessRun[];
  test_runs: { id: string; business_id: string; executed_at: string; measurement_count: number; y_unit: string | null }[];
  defects: { business_id: string; defect_class: string; severity: "minor" | "major" | "critical"; quantity: number; note: string | null }[];
}

export interface CavityCtqStats {
  cavity_id: string;
  cavity_label: string;
  lot_count: number;
  n_values: number;
  mean: number | null;
  sd: number | null;
  cp: number | null;
  cpk: number | null;
}

export interface CavityComparison {
  variant_id: string;
  metric: string;
  unit: string;
  cavities: CavityCtqStats[];
  drift_suspected: boolean;
  check_note: string | null;
}

export interface RootCauseCandidate {
  cause: "process_out_of_window" | "cavity_bias" | "material_lot" | "insufficient_data";
  title: string;
  confidence: string;
  detail: string;
  evidence: { kind: string; business_id: string | null; note: string }[];
}

export interface RootCauseHypothesis {
  lot_id: string;
  lot_business_id: string;
  candidates: RootCauseCandidate[];
  disclaimer: string;
}

export const api = {
  listProducts: () => request<Product[]>("/api/v1/products"),
  listVariants: (productId: string) => request<Variant[]>(`/api/v1/products/${productId}/variants`),
  listRequirements: (variantId: string) =>
    request<Requirement[]>(`/api/v1/variants/${variantId}/requirements`),
  listComponents: (variantId: string) =>
    request<ComponentDto[]>(`/api/v1/variants/${variantId}/components`),
  twinGraph: (variantId: string) => request<TwinGraph>(`/api/v1/twins/${variantId}/graph`),
  impactPaths: (variantId: string) => request<ImpactPaths>(`/api/v1/twins/${variantId}/impact-paths`),
  systemModel: (variantId: string) => request<SystemModel>(`/api/v1/twins/${variantId}/system-model`),
  modelCard: (variantId: string) => request<ModelCardDto | null>(`/api/v1/twins/${variantId}/model-card`),
  latestModelReview: (variantId: string) =>
    request<ReviewRunDto | null>(`/api/v1/twins/${variantId}/model-review`),
  runModelReview: (variantId: string) =>
    request<ReviewRunDto>(`/api/v1/twins/${variantId}/model-review`, { method: "POST" }),
  latestUQ: (variantId: string) => request<UQAnalysisDto | null>(`/api/v1/twins/${variantId}/uq`),
  gapAnalysis: (correlationId: string) =>
    request<GapAnalysisDto>(`/api/v1/correlations/${correlationId}/gap-analysis`),
  listLots: (variantId: string) => request<LotCard[]>(`/api/v1/twins/${variantId}/lots`),
  lotGenealogy: (lotId: string) => request<LotGenealogy>(`/api/v1/lots/${lotId}/genealogy`),
  cavityCompare: (variantId: string, spec?: { lsl?: number; usl?: number }) => {
    const params = new URLSearchParams({ variant_id: variantId });
    if (spec?.lsl !== undefined) params.set("spec_lsl", String(spec.lsl));
    if (spec?.usl !== undefined) params.set("spec_usl", String(spec.usl));
    return request<CavityComparison>(`/api/v1/cavities/compare?${params.toString()}`);
  },
  rootCauseHypotheses: (lotId: string) =>
    request<RootCauseHypothesis>("/api/v1/ai/root-cause-hypotheses", {
      method: "POST",
      body: JSON.stringify({ lot_id: lotId }),
    }),
  listSimulationRuns: (variantId: string) =>
    request<SimulationRun[]>(`/api/v1/variants/${variantId}/simulation-runs`),
  artifactDownloadUrl: (artifactVersionId: string) =>
    request<{ download_url: string }>(`/api/v1/artifacts/versions/${artifactVersionId}/download-url`),
  artifactContent: (artifactVersionId: string) =>
    requestBinary(`/api/v1/artifacts/versions/${artifactVersionId}/content`),
  listMeasurements: (testRunId: string) =>
    request<Measurement[]>(`/api/v1/test-runs/${testRunId}/measurements`),
  listCorrelations: (simulationRunId: string) =>
    request<CorrelationRecord[]>(`/api/v1/simulation-runs/${simulationRunId}/correlations`),
  listGates: (variantId: string) => request<Gate[]>(`/api/v1/variants/${variantId}/gates`),
  createGate: (body: { business_id: string; variant_id: string; baseline_id: string; name: string }) =>
    request<Gate>("/api/v1/gates", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Idempotency-Key": body.business_id },
    }),
  submitGate: (gateId: string) => request<Gate>(`/api/v1/gates/${gateId}/submit`, { method: "POST" }),
  listGateComments: (gateId: string) => request<GateComment[]>(`/api/v1/gates/${gateId}/comments`),
  addGateComment: (gateId: string, text: string) =>
    request<GateComment>(`/api/v1/gates/${gateId}/comments`, {
      method: "POST",
      body: JSON.stringify({ business_id: `${gateId}-comment-${Date.now()}`, text }),
    }),
  listGateDecisions: (gateId: string) => request<GateDecision[]>(`/api/v1/gates/${gateId}/decisions`),
  decideGate: (gateId: string, decision: "approved" | "rejected" | "conditionally_approved", comment: string) =>
    request<GateDecision>(`/api/v1/gates/${gateId}/decisions`, {
      method: "POST",
      body: JSON.stringify({ business_id: `${gateId}-decision-${Date.now()}`, decision, comment }),
    }),
  latestActiveBaseline: (variantId: string) =>
    request<{ id: string; business_id: string; status: string }[]>(`/api/v1/variants/${variantId}/baselines`).then(
      (baselines) => baselines.find((b) => b.status === "active") ?? null
    ),
};
