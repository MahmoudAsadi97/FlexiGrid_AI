/** Explicit inputs and checked outputs for the experimental scheduling workbench. */
export type PlanningJob = {
  task_id: string;
  power_kw: number[];
  earliest_start: number;
  latest_end: number;
};
export type PlanningProblem = {
  jobs: PlanningJob[];
  slot_minutes: 15 | 30 | 60;
  tariff_eur_per_kwh: number[];
  stress: number[];
  max_load_kw: number;
  background_kw?: number[];
  reserve_kw?: number[];
  avoid_slots?: number[];
  fixed_starts?: Record<string, number>;
  objective: "cost" | "grid" | "balanced";
  cost_weight?: number;
  price_scale_eur_per_kwh?: number;
};
export type PlanningResult = {
  starts: Record<string, number>;
  solver: { backend: string; status: string; mip_gap: number | null; dual_bound: number | null };
  problem_sha256: string;
  slot_minutes: number;
  advisory_only: boolean;
  assumptions: string[];
  validation: {
    valid: boolean;
    errors: string[];
    flexible_load_kw: number[];
    forecast_total_load_kw: number[];
    reserved_total_load_kw: number[];
    peak_load_kw: number;
    flexible_energy_kwh: number;
    flexible_cost_eur: number;
    forecast_total_cost_eur: number;
    objective_value: number;
    capacity_scope: string;
  };
};

/** Synthetic 24-hour inputs, deliberately not labelled as a real tariff or forecast. */
export function sampleProblem(cap = 4.6, background = 0.45, reserve = 0.3,
  objective: PlanningProblem["objective"] = "cost"): PlanningProblem {
  const hours = Array.from({ length: 96 }, (_, i) => i / 4);
  return {
    jobs: [
      { task_id: "ev", power_kw: Array(8).fill(3.6), earliest_start: 0, latest_end: 28 },
      { task_id: "dishwasher", power_kw: [1.8, 0.2, 0.15, 1.2, 0.1, 0.1, 0.05, 0.05], earliest_start: 0, latest_end: 28 },
      { task_id: "laundry", power_kw: [1.6, 0.3, 0.3, 0.15], earliest_start: 0, latest_end: 28 },
      { task_id: "heat", power_kw: Array(8).fill(1.4), earliest_start: 12, latest_end: 28 },
    ],
    slot_minutes: 15,
    tariff_eur_per_kwh: hours.map(h => Number((0.14 + 0.2 * Math.exp(-((h - 18) ** 2) / 10) + 0.08 * Math.exp(-((h - 7) ** 2) / 3)).toFixed(4))),
    stress: hours.map(h => Math.round(30 + 55 * Math.exp(-((h - 18) ** 2) / 9))),
    max_load_kw: cap,
    background_kw: hours.map(h => Number((background + (h >= 5 && h < 7 ? 0.15 : 0)).toFixed(3))),
    reserve_kw: Array(96).fill(reserve),
    avoid_slots: [],
    fixed_starts: {},
    objective,
    cost_weight: 0.56,
    price_scale_eur_per_kwh: 0.3,
  };
}

/** Elapsed time, not a timezone conversion. Supports horizons longer than a day. */
export function elapsedLabel(slot: number, minutes: number): string {
  const total = slot * minutes;
  return `${Math.floor(total / 60).toString().padStart(2, "0")}:${(total % 60).toString().padStart(2, "0")}`;
}
export function apiErrorText(payload: unknown): string {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return "The backend rejected this request.";
  const detail = (payload as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(item => {
    const row = item as { loc?: unknown[]; msg?: string };
    return `${row.loc?.join(".") ?? "request"}: ${row.msg ?? "invalid value"}`;
  }).join("; ");
  return "The backend rejected this request.";
}
