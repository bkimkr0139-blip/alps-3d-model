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
  parameters: Record<string, unknown> | null;
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

// -- Defect → FailureAnalysis → CAPA (HANDOFF §5 item 4) -----------------------

export interface Defect {
  id: string;
  business_id: string;
  lot_id: string;
  defect_class: string;
  severity: "minor" | "major" | "critical";
  quantity: number;
  unit_id: string | null;
  note: string | null;
  created_by: string;
  created_at: string;
}

export interface FailureAnalysis {
  id: string;
  business_id: string;
  defect_id: string;
  method: string;
  findings: string;
  analyst: string;
  analyzed_at: string;
  // Human-entered, evidence-based — never AI-derived (§7). Absent/false is a
  // legitimate "not confirmed yet" state, not a missing value.
  root_cause: string | null;
  root_cause_confirmed: boolean;
  evidence: { kind: string; business_id: string; note?: string | null }[] | null;
  created_by: string;
  created_at: string;
}

export type CapaStatus =
  | "draft"
  | "pending_review"
  | "approved"
  | "rejected"
  | "implemented"
  | "effectiveness_verified"
  | "closed";

export interface Capa {
  id: string;
  business_id: string;
  failure_analysis_id: string;
  title: string;
  capa_type: "corrective" | "preventive" | "both";
  description: string;
  owner: string;
  due_date: string | null;
  status: CapaStatus;
  submitted_by: string | null;
  submitted_at: string | null;
  verification_test_run_id: string | null;
  verification_note: string | null;
  closed_at: string | null;
  created_by: string;
  created_at: string;
}

export interface CapaEvent {
  id: string;
  business_id: string;
  capa_id: string;
  event_type: "submitted" | "approved" | "rejected" | "implemented" | "effectiveness_verified" | "closed";
  actor: string;
  actor_roles: string[];
  comment: string | null;
  evidence: Record<string, unknown> | null;
  occurred_at: string;
}

// -- AN-04 DOE / optimization (response surface + candidate comparison) -------

export interface ProcessOperationDto {
  id: string;
  business_id: string;
  name: string;
  seq_no: number;
  equipment: string | null;
  window: { parameter: string; unit: string | null; min: number; max: number }[] | null;
}

export interface DoeTargetBand {
  min: number;
  max: number;
  unit: string | null;
  source: string;
}

export interface DoeObservation {
  lot_business_id: string;
  process_run_business_id: string;
  parameter_value: number;
  ctq_value: number;
  out_of_window: boolean;
  window_findings: Record<string, unknown>[] | null;
}

export interface DoeFit {
  slope: number;
  intercept: number;
  r_squared: number;
  direction: "increasing" | "decreasing" | "flat";
  n_observations: number;
}

export interface DoeCandidate {
  parameter_value: number;
  predicted_ctq: number;
  in_window: boolean;
  meets_target: boolean | null;
  distance_to_target_center: number | null;
  rank: number | null;
  source: "observed" | "grid";
}

export interface DoeStudy {
  id: string;
  business_id: string;
  variant_id: string;
  operation_id: string;
  parameter: string;
  parameter_unit: string | null;
  metric: string;
  metric_unit: string | null;
  target_band: DoeTargetBand | null;
  observations: DoeObservation[];
  fit: DoeFit;
  candidates: DoeCandidate[];
  constraint_violations: DoeObservation[];
  disclaimer: string;
  created_at: string;
}

export interface ProcessParameterInfo {
  parameter: string;
  unit: string | null;
  n_points: number;
  operation_business_ids: string[];
}

export interface ControlChartPoint {
  lot_business_id: string;
  process_run_business_id: string;
  operation: string;
  seq_no: number;
  cavity_label: string;
  started_at: string;
  value: number;
  excluded_from_limits: boolean;
  exclusion_reason: string | null;
  violations: string[];
}

export interface ControlChart {
  variant_id: string;
  parameter: string;
  unit: string | null;
  n_points: number;
  n_basis: number;
  center_line: number | null;
  sigma: number | null;
  lcl: number | null;
  ucl: number | null;
  points: ControlChartPoint[];
  rule_hits: string[];
  note: string;
}

export interface AnomalyExplanation {
  variant_id: string;
  parameter: string;
  hypothesis: string;
  facts_used: string[];
  model: string;
  disclaimer: string;
  generated_at: string;
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
  listLotDefects: (lotId: string) => request<Defect[]>(`/api/v1/lots/${lotId}/defects`),
  listFailureAnalyses: (defectId: string) =>
    request<FailureAnalysis[]>(`/api/v1/defects/${defectId}/failure-analyses`),
  createFailureAnalysis: (
    defectId: string,
    body: {
      business_id: string;
      method: string;
      findings: string;
      analyst: string;
      analyzed_at: string;
      root_cause?: string | null;
      root_cause_confirmed?: boolean;
    }
  ) =>
    request<FailureAnalysis>(`/api/v1/defects/${defectId}/failure-analyses`, {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Idempotency-Key": body.business_id },
    }),
  listProcessOperations: () => request<ProcessOperationDto[]>("/api/v1/process-operations"),
  listDoeStudies: (variantId: string) => request<DoeStudy[]>(`/api/v1/twins/${variantId}/doe-studies`),
  runDoeStudy: (body: {
    business_id: string;
    variant_id: string;
    operation_id: string;
    parameter: string;
    metric?: "peak" | "mean";
    target_band?: { min: number; max: number; unit?: string };
    candidate_grid_size?: number;
  }) =>
    request<DoeStudy>("/api/v1/doe-studies", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Idempotency-Key": body.business_id },
    }),
  listCapas: (faId: string) => request<Capa[]>(`/api/v1/failure-analyses/${faId}/capas`),
  createCapa: (
    faId: string,
    body: {
      business_id: string;
      title: string;
      capa_type: "corrective" | "preventive" | "both";
      description: string;
      owner: string;
      due_date?: string | null;
    }
  ) =>
    request<Capa>(`/api/v1/failure-analyses/${faId}/capas`, {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Idempotency-Key": body.business_id },
    }),
  getCapa: (capaId: string) => request<Capa>(`/api/v1/capas/${capaId}`),
  listCapaEvents: (capaId: string) => request<CapaEvent[]>(`/api/v1/capas/${capaId}/events`),
  submitCapa: (capaId: string, comment?: string) =>
    request<Capa>(`/api/v1/capas/${capaId}/submit`, {
      method: "POST",
      body: JSON.stringify({ business_id: `${capaId}-submit-${Date.now()}`, comment }),
    }),
  decideCapa: (capaId: string, decision: "approved" | "rejected", comment: string) =>
    request<Capa>(`/api/v1/capas/${capaId}/decisions`, {
      method: "POST",
      body: JSON.stringify({ business_id: `${capaId}-decision-${Date.now()}`, decision, comment }),
    }),
  implementCapa: (capaId: string, comment?: string) =>
    request<Capa>(`/api/v1/capas/${capaId}/implement`, {
      method: "POST",
      body: JSON.stringify({ business_id: `${capaId}-implement-${Date.now()}`, comment }),
    }),
  verifyCapaEffectiveness: (capaId: string, testRunId: string, comment?: string) =>
    request<Capa>(`/api/v1/capas/${capaId}/verify-effectiveness`, {
      method: "POST",
      body: JSON.stringify({ business_id: `${capaId}-verify-${Date.now()}`, test_run_id: testRunId, comment }),
    }),
  closeCapa: (capaId: string, comment?: string) =>
    request<Capa>(`/api/v1/capas/${capaId}/close`, {
      method: "POST",
      body: JSON.stringify({ business_id: `${capaId}-close-${Date.now()}`, comment }),
    }),
  listProcessParameters: (variantId: string) =>
    request<ProcessParameterInfo[]>(`/api/v1/twins/${variantId}/process-parameters`),
  controlChart: (variantId: string, parameter: string) =>
    request<ControlChart>(
      `/api/v1/twins/${variantId}/control-chart?parameter=${encodeURIComponent(parameter)}`,
    ),
  anomalyExplanation: (variantId: string, parameter: string) =>
    request<AnomalyExplanation>("/api/v1/ai/anomaly-explanation", {
      method: "POST",
      body: JSON.stringify({ variant_id: variantId, parameter }),
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

// --- ASIC Twin v1.1 (지시서 v1.1 R1: EPIC A/E/F/G + 게이트 폐루프) ----------
// The ASIC workbench READS the golden dataset through these endpoints; the
// gate report is rendered verbatim (blockers are computed server-side and
// never hand-authored in the UI — asic_gate_policy.py).

export interface AsicChainBlock {
  key: string;
  kind: "sensor" | "analog" | "mixed" | "digital" | "io" | "power";
  label: string;
  params: Record<string, number | string>;
  error_budget: Record<string, number>;
  requirement_ids?: string[];
}

export interface AsicSignalChain {
  id: string;
  business_id: string;
  template_id: string;
  revision: number;
  status: string;
  blocks: AsicChainBlock[];
  source_class: string;
  supersedes_id: string | null;
  content_hash: string;
  note: string | null;
  created_by: string;
  created_at: string;
}

export interface AsicCornerOutput {
  output: string;
  unit: string | null;
  nominal: number;
  p50: number;
  p95: number;
  p99: number;
  violation_rate: number;
  spec_min: number | null;
  spec_max: number | null;
  corners: { corner: string; temp_c: number; mean: number }[];
  hist: { edges: number[]; counts: number[] } | null;
}

export interface AsicCornerStudy {
  id: string;
  business_id: string;
  signal_chain_id: string;
  kind: string;
  n_draws: number;
  seed: number;
  spec: { output: string; nominal?: number | null; min?: number | null; max?: number | null; unit?: string | null }[];
  result: {
    per_output: AsicCornerOutput[];
    model_ood: boolean;
    ood_reason: string[];
    n_draws_total: number;
    temperatures_c: number[];
    disclosure: string;
  } | null;
  tool_version: string;
  source_class: string;
  status: string;
  created_by: string;
  created_at: string;
}

export interface AsicMeasurementRun {
  id: string;
  business_id: string;
  template_id: string;
  equipment_id: string;
  equipment_type: string;
  equipment_model: string | null;
  firmware: string | null;
  calibration_expires_at: string | null;
  program_revision: string | null;
  operator: string | null;
  executed_at: string | null;
  file_hash: string;
  status: string;
  points: { name: string; value: number; unit?: string | null; raw_value?: number | null; raw_unit?: string | null; site?: number | null; temperature_c?: number | null }[] | null;
  findings: { code: string; detail?: string }[] | null;
  lot_ref: string | null;
  created_by: string;
  created_at: string;
}

export interface AsicQualResult {
  id: string;
  business_id: string;
  plan_id: string;
  group: string;
  method: string;
  condition: Record<string, unknown>;
  samples: string;
  lots: string[] | null;
  status: "pending" | "pass" | "fail";
  failed_param: string | null;
  fa_case_id: string | null;
  waiver_ref: string | null;
  waiver_expires_at: string | null;
  created_at: string;
}

export interface AsicQualPlan {
  id: string;
  business_id: string;
  template_id: string;
  grade: string;
  policy_version: string;
  standard_version: string | null;
  status: string;
  note: string | null;
  results: AsicQualResult[];
  created_by: string;
  created_at: string;
}

export interface AsicSafetyItem {
  id: string;
  business_id: string;
  template_id: string;
  level: "safety_goal" | "fsr" | "tsr" | "hw_req";
  parent_id: string | null;
  title: string;
  asil: string | null;
  safety_mechanism: string | null;
  diagnostic_coverage_pct: number | null;
  safe_state: string | null;
  response_time_ms: number | null;
  created_by: string;
  created_at: string;
}

export interface AsicFmedaItem {
  id: string;
  business_id: string;
  safety_item_id: string;
  failure_mode: string;
  distribution_pct: number;
  dc_pct: number | null;
  fit_rate: number | null;
  source_ref: string | null;
  source_hash: string | null;
  formula_version: string | null;
  note: string | null;
  created_at: string;
}

export interface AsicFaultInjection {
  id: string;
  business_id: string;
  safety_item_id: string;
  method: string;
  stimulus: string;
  expected: string;
  observed: string;
  status: string;
  executed_by: string | null;
  executed_at: string | null;
  created_at: string;
}

export interface AsicFaCase {
  id: string;
  business_id: string;
  template_id: string;
  scope: string;
  lot_ref: string | null;
  symptom: string;
  repro_condition: string | null;
  status: string;
  observations: { fact: string; source?: string | null }[] | null;
  hypotheses: { text: string; confirm_tests?: string[]; excluded?: boolean; exclusion_basis?: string | null }[] | null;
  root_cause: string | null;
  root_cause_confirmed: boolean;
  cause_class: string | null;
  location: Record<string, unknown> | null;
  analysts: string[] | null;
  closed_at: string | null;
  created_by: string;
  created_at: string;
}

export interface AsicFaEvent {
  id: string;
  business_id: string;
  case_id: string;
  event_type: string;
  actor: string;
  actor_roles: string[];
  comment: string | null;
  occurred_at: string;
}

export interface AsicEco {
  id: string;
  business_id: string;
  fa_case_id: string | null;
  template_id: string;
  trigger: string;
  title: string;
  description: string | null;
  design_rev_from: string | null;
  design_rev_to: string | null;
  mask_revision: string | null;
  test_program_revision: string | null;
  impact: Record<string, unknown>[] | null;
  status: string;
  regression_run_ids: string[] | null;
  verification_note: string | null;
  verification_run_id: string | null;
  closed_at: string | null;
  created_by: string;
  created_at: string;
}

export interface AsicGateReport {
  template_id: string;
  gate_id: string;
  policy_version: string;
  status: "pass" | "blocked";
  blockers: { code: string; detail: string; evidence: string[] }[];
  readiness: string;
  readiness_reachable: boolean;
  checks: { check_id: string; status: string; actual: unknown; target: unknown; evidence_refs: string[] }[];
  evaluated_at: string;
}

// ── ASIC Twin v1.1 R2 (EPIC B·C·D·H + P1-08 report) ────────────────────────

export interface AsicTradeStudy {
  id: string;
  business_id: string;
  template_id: string;
  title: string;
  option_ids: string[];
  weights: Record<string, number>;
  annual_volume: number;
  status: string;
  decision: { option_id: string; rationale: string; residual_risks?: string[] } | null;
  result: {
    ranking: string[];
    per_option: {
      option_id: string;
      business_id: string;
      foundry: string;
      node: string;
      package: string;
      nre_total: number | null;
      nre_tbd_components: string[];
      unit_cost_total: number | null;
      unit_tbd_components: string[];
      schedule_weeks_total: number | null;
      score: { score: number | null; partial_score: number | null; complete: boolean; tbd_axes: string[] };
    }[];
    tbd_note: string;
  } | null;
  created_at: string;
}

export interface AsicToolRun {
  id: string;
  business_id: string;
  template_id: string;
  design_revision: number;
  tool: string;
  tool_version: string;
  runner_class: string; // real_adapter | mock
  input_hash: string;
  output_hash: string | null;
  exit_code: number;
  lineage_id: string;
  status: string;
  created_at: string;
}

export interface AsicFlowTotals {
  item_count: number;
  total_duration_s: number;
  wall_time_s_per_die: number;
  cost_per_die: number | null;
}

export interface AsicFlowCoverage {
  per_class: Record<string, number>;
  uncovered_classes: string[];
  aggregate_avg_pct: number;
  unlinked_items: number;
}

export interface AsicTestFlowAnalysis {
  tool_version: string;
  template_id: string;
  silicon_revisions: string[];
  per_target: Record<
    string,
    {
      flow_id: string;
      business_id: string;
      program_revision: number;
      silicon_revision: string;
      totals: AsicFlowTotals;
      coverage: AsicFlowCoverage;
      compatibility: { compatible: boolean; mismatches: string[] };
    }
  >;
  cross_target: {
    duplicates: { name: string; same_limits: boolean; drop_candidate: boolean; reason: string }[];
    coverage_gaps: { defect_class: string; sort_coverage_pct: number; final_coverage_pct: number; reason: string }[];
  } | null;
  tbd_note: string;
}

export interface AsicWaferMap {
  id: string;
  business_id: string;
  lot_ref: string | null;
  wafer_ref: string | null;
  grid: { rows: number; cols: number };
  analysis: {
    yield_pct: number;
    retest_rate_pct: number;
    fail_rate_pct: number;
    confusion: { overkill_count: number; escaped_underkill: number } | null;
  } | null;
  source_class: string;
  created_at: string;
}

export interface AsicPartner {
  id: string;
  business_id: string;
  name: string;
  kind: string; // foundry | osat | subcon | material
  status: string; // approved | conditional | suspended
  approved_at: string | null;
}

export interface AsicLotTraveler {
  id: string;
  business_id: string;
  lot_ref: string;
  parent_lot_refs: string[] | null;
  silicon_revision: string | null;
  mask_rev: string | null;
  package_rev: string | null;
  current_partner_id: string | null;
  status: string;
  steps: { partner_business_id: string; step: string; result: string; recorded_at: string }[];
  created_at: string;
}

export interface AsicEvidenceReport {
  report_version: string;
  template_id: string;
  lang: string;
  generated_at: string;
  title: string;
  notes: string[];
  sections: { key: string; title: string; rows: { label: string; value: unknown }[]; source_class?: string }[];
}

export const asicApi = {
  listSignalChains: (templateId: string) =>
    request<AsicSignalChain[]>(`/api/v1/asic/templates/${templateId}/signal-chains`),
  listCornerStudies: (templateId: string) =>
    request<AsicCornerStudy[]>(`/api/v1/asic/templates/${templateId}/corner-studies`),
  listMeasurementRuns: (templateId: string) =>
    request<AsicMeasurementRun[]>(`/api/v1/asic/templates/${templateId}/measurement-runs`),
  listQualificationPlans: (templateId: string) =>
    request<AsicQualPlan[]>(`/api/v1/asic/templates/${templateId}/qualification-plans`),
  listSafetyItems: (templateId: string) =>
    request<AsicSafetyItem[]>(`/api/v1/asic/templates/${templateId}/safety-items`),
  listFmedaItems: (templateId: string) =>
    request<AsicFmedaItem[]>(`/api/v1/asic/templates/${templateId}/fmeda-items`),
  listFaultInjections: (templateId: string) =>
    request<AsicFaultInjection[]>(`/api/v1/asic/templates/${templateId}/fault-injections`),
  listFaCases: (templateId: string) =>
    request<AsicFaCase[]>(`/api/v1/asic/templates/${templateId}/fa-cases`),
  listFaEvents: (caseId: string) =>
    request<AsicFaEvent[]>(`/api/v1/asic/fa-cases/${caseId}/events`),
  listEcos: (templateId: string) => request<AsicEco[]>(`/api/v1/asic/templates/${templateId}/ecos`),
  gateReport: (templateId: string) =>
    request<AsicGateReport>(`/api/v1/asic/gate-report/${templateId}`),
  // R2 — CAN_COST-restricted money views degrade to "error" live state for
  // roles without the group (loadLive is allSettled, never fatal)
  listTradeStudies: (templateId: string) =>
    request<AsicTradeStudy[]>(`/api/v1/asic/templates/${templateId}/trade-studies`),
  listToolRuns: (templateId: string) =>
    request<AsicToolRun[]>(`/api/v1/asic/templates/${templateId}/tool-runs`),
  testFlowAnalysis: (templateId: string) =>
    request<AsicTestFlowAnalysis>(`/api/v1/asic/templates/${templateId}/test-flow-analysis`),
  listWaferMaps: (templateId: string) =>
    request<AsicWaferMap[]>(`/api/v1/asic/templates/${templateId}/wafer-maps`),
  listPartners: () => request<AsicPartner[]>(`/api/v1/asic/partners`),
  listLotTravelers: (templateId: string) =>
    request<AsicLotTraveler[]>(`/api/v1/asic/templates/${templateId}/lot-travelers`),
  evidenceReport: (templateId: string, lang: string) =>
    request<AsicEvidenceReport>(
      `/api/v1/asic/templates/${templateId}/evidence-report?lang=${lang}`,
    ),
};
