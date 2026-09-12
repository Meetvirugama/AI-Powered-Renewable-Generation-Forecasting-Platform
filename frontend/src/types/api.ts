// Mirrors backend/schemas/*.py exactly. When the backend schema changes, change this
// file in the same commit — an approximate type here is worse than none, because tsc
// will confidently validate the wrong shape.

export interface PlantMetadata {
  tilt_deg?: number | null;
  azimuth_deg?: number | null;
  hub_height_m?: number | null;
  rotor_diameter_m?: number | null;
  technology?: string | null;
  power_curve?: string | number[] | null;
}

export interface Plant {
  id: string;
  name: string;
  type: "solar" | "wind";
  lat: number;
  lon: number;
  avc_mw: number;
  pool_id: string | null;
  metadata_json: PlantMetadata | null;
}

export interface PlantsResponse {
  plants: Plant[];
  total: number;
}

// --- forecast ---------------------------------------------------------------

export interface BlockForecast {
  /** 1-indexed, 1..96. JS arrays are 0-indexed — index with .find(), not [n]. */
  block_no: number;
  /** UTC. Never render this to a user. */
  valid_time: string;
  /** Already IST. Prefer this over recomputing from block_no. */
  ist_time: string;
  p05: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  p95: number;
}

export interface ForecastResponse {
  plant_id: string;
  date: string;
  model_name: string;
  blocks: BlockForecast[];
}

// --- dsm --------------------------------------------------------------------

export interface BlockDSMResult {
  block_no: number;
  expected_penalty_inr: number;
  p50_penalty_inr: number;
  schedule_mw: number;
  deviation_pct_at_p50: number;
}

export interface DSMResponse {
  plant_id: string;
  date: string;
  rule_version: string;
  x_value: number;
  total_expected_penalty_inr: number;
  total_p50_penalty_inr: number;
  blocks: BlockDSMResult[];
}

export interface DSMRequest {
  plant_id: string;
  date: string;
  schedule_mw: number[];
  rule_year?: number;
  freq_hz?: number;
  ncd_inr?: number;
}

// --- optimize ---------------------------------------------------------------

export interface ActionCard {
  type: "curtailment" | "reserve_flag";
  block_no: number;
  mw: number;
  reason: string;
  inr_impact: number;
}

export interface BatteryDispatchBlock {
  block_no: number;
  charge_mw: number;
  discharge_mw: number;
  soc_mwh: number;
}

export interface OptimizeResponse {
  plant_id: string;
  date: string;
  rule_version: string;
  naive_total_inr: number;
  optimised_total_inr: number;
  savings_inr: number;
  savings_pct: number;
  /** Length 96. */
  optimised_schedule: number[];
  /** Length 96. */
  naive_schedule: number[];
  battery_dispatch: BatteryDispatchBlock[];
  action_cards: ActionCard[];
}

export interface OptimizeRequest {
  plant_id: string;
  date: string;
  rule_year?: number;
  freq_hz?: number;
  ncd_inr?: number;
  battery_capacity_mwh?: number | null;
}

// --- pooling ----------------------------------------------------------------

export interface PlantPoolAllocation {
  plant_id: string;
  individual_penalty_inr: number;
  allocated_penalty_inr: number;
  savings_inr: number;
}

export interface PoolingResponse {
  pool_id: string;
  date: string;
  individual_total_inr: number;
  pooled_total_inr: number;
  savings_inr: number;
  savings_pct: number;
  allocations: PlantPoolAllocation[];
}

export interface PoolingRequest {
  pool_id: string;
  date: string;
  rule_year?: number;
  freq_hz?: number;
  ncd_inr?: number;
}

// --- rag --------------------------------------------------------------------

export interface Citation {
  clause: string;
  page: number | null;
  doc: string;
  url: string | null;
  section: string | null;
  snippet: string | null;
}

export interface RAGMeta {
  llm_model: string | null;
  cached: boolean;
  latency_ms: number | null;
  retrieved_chunks: number;
  /**
   * 'numbers_stripped' means the copilot produced a rupee figure the DSM engine did
   * not, and it was removed server-side. Surface this in the UI whenever it is not
   * 'pass' — hiding it undermines the product's core claim.
   */
  guardrail: "pass" | "numbers_stripped" | "fallback_template";
}

export interface RAGQueryResponse {
  answer: string;
  citations: Citation[];
  engine_values: Record<string, unknown> | null;
  meta: RAGMeta;
}

export interface RAGQueryRequest {
  question: string;
  plant_id?: string;
  block_no?: number;
  date?: string;
  rule_year?: number;
  /** DSM engine output for the block. The copilot explains these; it never invents them. */
  context?: Record<string, unknown>;
}

// --- dashboard --------------------------------------------------------------

export interface DashboardBriefing {
  title: string;
  summary: string;
  risk_level: string;
  total_expected_penalty_inr: number;
  potential_savings_inr: number;
}

/**
 * GET /dashboard/{plant_id}. Note the plant fields are FLAT — the backend does not
 * nest a Plant object — and there is no `optimize` key. Action cards arrive as
 * `actions`; the full optimiser payload comes from POST /optimize separately.
 */
export interface DashboardResponse {
  plant_id: string;
  plant_name: string;
  date: string;
  avc_mw: number;
  forecast: ForecastResponse;
  dsm_summary: DSMResponse;
  actions: ActionCard[];
  pooling_benefit: PoolingResponse | null;
  briefing: DashboardBriefing;
}

// --- health -----------------------------------------------------------------

export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
}
