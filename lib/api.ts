/**
 * Typed client for the FlexiGrid backend.
 *
 * The dashboard probes /health on load. When the backend answers, every run
 * goes through the real pipeline (local LLM → RAG → MCP tools → optimizer →
 * critic) and the UI renders the returned trace verbatim. When it does not,
 * the UI falls back to the clearly-labelled offline simulation in engine.ts.
 */

export type BackendHealth = {
  status: string;
  llm: { live: boolean; base_url: string; model: string | null; last_error: string | null };
  embeddings: { backend: string | null; model: string | null };
  corpus: { chunks: number; fingerprint: string };
  elia_live: boolean;
};

export type BackendEvidence = {
  chunk_id: string;
  doc_id: string;
  title: string;
  section: string;
  text: string;
  source_type: string;
  rank: number;
  score: number;
  scores: { bm25: number | null; dense: number | null };
  mode: string;
};

export type BackendScheduledTask = {
  task_id: string;
  name: string;
  power_kw: number;
  duration_hours: number;
  earliest_start: number;
  latest_end: number;
  source_id: string;
  start: number;
  end: number;
  cost_eur: number;
  grid_stress: number;
};

export type BackendValidation = {
  valid: boolean;
  within_windows: boolean;
  below_capacity: boolean;
  avoid_hours_respected: boolean;
  peak_load_kw: number;
  hourly_load_kw: number[];
  max_load_kw: number;
};

export type BackendPlan = {
  objective: string;
  schedule: BackendScheduledTask[];
  validation: BackendValidation;
  total_cost_eur: number;
  average_grid_stress: number;
  peak_load_kw: number;
  baseline?: BackendPlan | null;
  baseline_note?: string;
  relaxation_note?: string;
  snapshot_mode?: string;
  tariff?: number[];
  stress?: number[];
};

export type TraceRecord = {
  step: number;
  tool: string;
  args: Record<string, unknown>;
  ok: boolean;
  duration_ms: number;
  summary: string;
  transport: string;
  decided_by: "llm" | "guardrail";
  thought: string;
};

export type AgentRunResponse = {
  plan: BackendPlan;
  spec: {
    tasks: { task_id: string; power_kw: number; duration_hours: number; earliest_start: number; latest_end: number }[];
    objective: string;
    max_load_kw: number;
    avoid_hours: number[];
  };
  evidence: BackendEvidence[];
  explanation: { summary: string; rationale: string[]; citation_ids: string[]; limitation: string };
  trace: TraceRecord[];
  modes: {
    llm: string | null;
    llm_live: boolean;
    intent: string | null;
    intent_adjustments: string[];
    explanation: string;
    retrieval: string;
    retrieval_backend: string | null;
    snapshot: string | null;
    transport: string;
    decision_notes: string[];
  };
};

const DEFAULT_API = "http://localhost:8000";

export function apiBase(): string {
  if (typeof window !== "undefined") {
    const fromQuery = new URLSearchParams(window.location.search).get("api");
    if (fromQuery) return fromQuery.replace(/\/$/, "");
  }
  return DEFAULT_API;
}

async function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return await Promise.race([
    promise,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error("timeout")), ms),
    ),
  ]);
}

export async function fetchHealth(timeoutMs = 2500): Promise<BackendHealth | null> {
  try {
    const response = await withTimeout(fetch(`${apiBase()}/health`), timeoutMs);
    if (!response.ok) return null;
    return (await response.json()) as BackendHealth;
  } catch {
    return null;
  }
}

export type RetrievalModeResult = {
  queries: number;
  hit_at_1: number;
  recall_at_4: number;
  mrr: number;
};

export type IntentExtractorResult = {
  missions: number;
  exact_match: number;
  per_field: Record<string, number>;
};

export type EvaluationResults = {
  environment: {
    generated_at: string;
    llm_model: string | null;
    embeddings_backend: string | null;
    embeddings_model?: string | null;
    corpus_chunks: number;
  };
  retrieval: {
    bm25?: RetrievalModeResult;
    dense?: RetrievalModeResult;
    hybrid?: RetrievalModeResult;
  };
  intent: Record<string, IntentExtractorResult>;
  llm_only_baseline: {
    skipped?: string;
    model?: string;
    attempts?: number;
    constraint_valid_rate?: number | null;
    violation_or_failure_rate?: number | null;
    schema_failures?: number;
    avg_cost_gap_eur_when_valid?: number | null;
  };
  greedy_ablation: {
    cases: {
      case: string;
      joint_cost_eur: number | null;
      greedy_cost_eur: number | null;
      greedy_valid: boolean;
    }[];
    greedy_failures: number;
    joint_failures: number;
  };
  agent_properties: {
    citation_precision: number;
    explanations_rejected_by_guard: number;
    deterministic_plan_replay: boolean;
  };
};

export async function fetchEvaluation(timeoutMs = 4000): Promise<EvaluationResults | null> {
  try {
    const response = await withTimeout(fetch(`${apiBase()}/api/evaluation`), timeoutMs);
    if (!response.ok) return null;
    return (await response.json()) as EvaluationResults;
  } catch {
    return null;
  }
}

export class MissionRejectedError extends Error {}

export async function runAgentPlan(
  prompt: string,
  objective?: string,
  timeoutMs = 180_000,
): Promise<AgentRunResponse> {
  const body: Record<string, unknown> = { prompt };
  if (objective) body.objective = objective;
  const response = await withTimeout(
    fetch(`${apiBase()}/api/agent/plan`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
    timeoutMs,
  );
  if (response.status === 422) {
    const detail = await response
      .json()
      .then((payload) => String(payload.detail ?? "Mission rejected"))
      .catch(() => "Mission rejected");
    throw new MissionRejectedError(detail);
  }
  if (!response.ok) throw new Error(`Backend error ${response.status}`);
  return (await response.json()) as AgentRunResponse;
}
