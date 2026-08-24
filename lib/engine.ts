export type Objective = "balanced" | "cost" | "grid";

export type Task = {
  id: string;
  name: string;
  icon: string;
  powerKw: number;
  duration: number;
  earliestStart: number;
  latestEnd: number;
  sourceId: string;
};

export type ScheduledTask = Task & {
  start: number;
  end: number;
  cost: number;
  gridScore: number;
};

export type Evidence = {
  id: string;
  title: string;
  excerpt: string;
  tag: string;
  tokens: string[];
};

export type Scenario = {
  id: string;
  label: string;
  shortLabel: string;
  prompt: string;
  objective: Objective;
  maxGridLoadKw: number;
  tasks: Task[];
};

export type Plan = {
  scenario: Scenario;
  objective: Objective;
  schedule: ScheduledTask[];
  baseline: ScheduledTask[];
  evidence: Evidence[];
  totalCost: number;
  baselineCost: number;
  averageGridScore: number;
  baselineGridScore: number;
  savingsPercent: number;
  gridImprovementPercent: number;
  constraintsSatisfied: number;
  constraintsTotal: number;
  hourlyLoad: number[];
  baselineLoad: number[];
};

// OFFLINE FALLBACK ENGINE. When the Python backend is reachable the dashboard
// runs the real pipeline (local LLM, hybrid RAG, MCP tools) and renders its
// trace; this module only powers the clearly-labelled offline simulation and
// the static build. Fixture values mirror backend/data/elia_demo_snapshot.json.
export const tariff = [
  0.22, 0.18, 0.16, 0.15, 0.14, 0.15, 0.19, 0.27, 0.31, 0.29, 0.25, 0.23,
  0.21, 0.2, 0.22, 0.28, 0.37, 0.46, 0.42, 0.34, 0.28, 0.24, 0.21, 0.19,
];

export const gridStress = [
  48, 42, 38, 34, 31, 33, 45, 59, 71, 76, 68, 55, 42, 35, 29, 32, 51, 78,
  91, 86, 70, 58, 52, 47,
];

// Chunk IDs mirror the backend corpus (backend/flexigrid/corpus/*) so that
// offline citations remain meaningful references into the same documents.
export const evidenceCorpus: Evidence[] = [
  {
    id: "manual-ev#1",
    title: "Wallbox EVL-7 EV charger manual — Scheduled charging",
    excerpt: "The charger supports scheduled charging in one-hour blocks; in eco mode a two-hour block delivers ≈7.2 kWh at 3.6 kW.",
    tag: "Device manual",
    tokens: ["ev", "charger", "schedule", "eco", "3.6", "charge", "vehicle"],
  },
  {
    id: "manual-dishwasher#1",
    title: "EcoWash D600 dishwasher manual — Delayed start",
    excerpt: "Eco 50 °C uses ≈1.0 kWh over two hours. A delayed start of 1–24 h moves the cycle into cheaper night hours.",
    tag: "Device manual",
    tokens: ["dishwasher", "eco", "delay", "two", "hours", "1.0", "kwh"],
  },
  {
    id: "policy-comfort#1",
    title: "Household comfort policy — Wake-up and departure",
    excerpt: "Maintain 19–21 °C while occupied. Pre-heating may finish up to 30 minutes before the 06:30 wake-up.",
    tag: "User constraint",
    tokens: ["heat", "home", "comfort", "temperature", "occupied", "wake", "preheat"],
  },
  {
    id: "tariff-dynamic#2",
    title: "Dynamic contracts in Belgium — Imbalance prices are not consumer prices",
    excerpt: "Elia imbalance prices are market-settlement signals, not household prices; only the retail tariff sets the cost.",
    tag: "Tariff rule",
    tokens: ["dynamic", "tariff", "hourly", "price", "cost", "retail", "consumer"],
  },
  {
    id: "elia-ods002#0",
    title: "Elia Open Data ods002 — What the dataset contains",
    excerpt: "Measured and forecast total load of the Belgian control area per quarter-hour, including day-ahead forecasts.",
    tag: "Elia dataset",
    tokens: ["grid", "load", "forecast", "elia", "belgian", "peak", "day", "ahead"],
  },
  {
    id: "elia-ods086#0",
    title: "Elia Open Data ods086 — What the dataset contains",
    excerpt: "Intraday, day-ahead and week-ahead wind power forecasts, updated every quarter-hour.",
    tag: "Elia dataset",
    tokens: ["wind", "renewable", "forecast", "elia", "hourly", "grid", "clean"],
  },
  {
    id: "policy-capacity#1",
    title: "Capacity tariff — The FlexiGrid connection limit",
    excerpt: "Controllable household load is capped at 4.6 kW; a single violating hour can raise the capacity bill for twelve months.",
    tag: "Grid constraint",
    tokens: ["grid", "capacity", "load", "4.6", "kw", "peak", "limit"],
  },
];

const baseTasks: Task[] = [
  {
    id: "heat",
    name: "Heat-pump preheat",
    icon: "HP",
    powerKw: 1.4,
    duration: 2,
    earliestStart: 3,
    latestEnd: 7,
    sourceId: "manual-heatpump#0",
  },
  {
    id: "dishwasher",
    name: "Dishwasher · Eco",
    icon: "DW",
    powerKw: 0.5,
    duration: 2,
    earliestStart: 0,
    latestEnd: 7,
    sourceId: "manual-dishwasher#1",
  },
  {
    id: "ev",
    name: "EV charge · 7.2 kWh",
    icon: "EV",
    powerKw: 3.6,
    duration: 2,
    earliestStart: 0,
    latestEnd: 7,
    sourceId: "manual-ev#1",
  },
  {
    id: "laundry",
    name: "Laundry",
    icon: "WM",
    powerKw: 0.8,
    duration: 1,
    earliestStart: 0,
    latestEnd: 7,
    sourceId: "policy-capacity#1",
  },
];

export const scenarios: Scenario[] = [
  {
    id: "morning",
    label: "Ready by morning",
    shortLabel: "Morning",
    prompt:
      "Charge the EV, run laundry and dishwasher before 07:00. Preheat the home to 20.5 °C by 06:30. Keep controllable load below 4.6 kW.",
    objective: "balanced",
    maxGridLoadKw: 4.6,
    tasks: baseTasks,
  },
  {
    id: "grid-friendly",
    label: "Support the grid",
    shortLabel: "Grid friendly",
    prompt:
      "Finish flexible loads before 16:00. Prefer low-load, high-wind periods from the Elia forecast while respecting the 4.6 kW limit and comfort policy.",
    objective: "grid",
    maxGridLoadKw: 4.6,
    tasks: baseTasks.map((task) => ({
      ...task,
      earliestStart: task.id === "heat" ? 11 : 8,
      latestEnd: 16,
    })),
  },
  {
    id: "peak-avoidance",
    label: "Avoid evening peak",
    shortLabel: "Peak shield",
    prompt:
      "Charge the EV and run flexible loads by 23:00, but avoid the 17:00–20:00 Belgian grid peak. Never exceed 4.6 kW.",
    objective: "cost",
    maxGridLoadKw: 4.6,
    tasks: baseTasks.map((task) => ({
      ...task,
      earliestStart: 14,
      latestEnd: 23,
    })),
  },
];

function round(value: number, digits = 2) {
  return Number(value.toFixed(digits));
}

function tokenize(text: string) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9.]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter((token) => token.length > 2);
}

export function retrieveEvidence(query: string, k = 4): Evidence[] {
  const queryTokens = new Set(tokenize(query));
  return evidenceCorpus
    .map((doc) => ({
      doc,
      score: doc.tokens.reduce((sum, token) => sum + (queryTokens.has(token) ? 1 : 0), 0),
    }))
    .sort((a, b) => b.score - a.score || a.doc.id.localeCompare(b.doc.id))
    .slice(0, k)
    .map(({ doc }) => doc);
}

function optionScore(hour: number, task: Task, objective: Objective) {
  let total = 0;
  for (let offset = 0; offset < task.duration; offset += 1) {
    const h = hour + offset;
    const normalizedPrice = tariff[h] / Math.max(...tariff);
    const normalizedGrid = gridStress[h] / 100;
    const costWeight = objective === "cost" ? 0.84 : objective === "grid" ? 0.18 : 0.56;
    total += costWeight * normalizedPrice + (1 - costWeight) * normalizedGrid;
  }
  return total;
}

function taskMetrics(task: Task, start: number) {
  let cost = 0;
  let stress = 0;
  for (let offset = 0; offset < task.duration; offset += 1) {
    const h = start + offset;
    cost += task.powerKw * tariff[h];
    stress += gridStress[h];
  }
  return { cost: round(cost), gridScore: Math.round(stress / task.duration) };
}

function scheduleAtEarliest(scenario: Scenario): ScheduledTask[] {
  const load = Array(24).fill(0) as number[];
  return scenario.tasks.map((task) => {
    let chosen: number | null = null;
    for (let start = task.earliestStart; start <= task.latestEnd - task.duration; start += 1) {
      const fits = Array.from({ length: task.duration }, (_, offset) => start + offset).every(
        (hour) => load[hour] + task.powerKw <= scenario.maxGridLoadKw + 1e-9,
      );
      if (fits) {
        chosen = start;
        break;
      }
    }
    if (chosen === null) throw new Error("No feasible schedule for the supplied constraints");
    for (let offset = 0; offset < task.duration; offset += 1) load[chosen + offset] += task.powerKw;
    return { ...task, start: chosen, end: chosen + task.duration, ...taskMetrics(task, chosen) };
  });
}

export function optimizeScenario(scenario: Scenario, objective = scenario.objective): ScheduledTask[] {
  const load = Array(24).fill(0) as number[];
  const tasks = [...scenario.tasks].sort(
    (a, b) =>
      a.latestEnd - a.earliestStart - a.duration - (b.latestEnd - b.earliestStart - b.duration) ||
      b.powerKw - a.powerKw ||
      a.id.localeCompare(b.id),
  );
  let bestScore = Number.POSITIVE_INFINITY;
  let bestStarts: Record<string, number> | null = null;

  const search = (index: number, score: number, starts: Record<string, number>) => {
    if (score >= bestScore) return;
    if (index === tasks.length) {
      bestScore = score;
      bestStarts = { ...starts };
      return;
    }
    const task = tasks[index];
    const options = Array.from(
      { length: task.latestEnd - task.duration - task.earliestStart + 1 },
      (_, offset) => task.earliestStart + offset,
    ).sort((a, b) => optionScore(a, task, objective) - optionScore(b, task, objective) || a - b);

    for (const start of options) {
      const hours = Array.from({ length: task.duration }, (_, offset) => start + offset);
      if (!hours.every((hour) => load[hour] + task.powerKw <= scenario.maxGridLoadKw + 1e-9)) continue;
      hours.forEach((hour) => { load[hour] += task.powerKw; });
      starts[task.id] = start;
      search(index + 1, score + optionScore(start, task, objective), starts);
      delete starts[task.id];
      hours.forEach((hour) => { load[hour] -= task.powerKw; });
    }
  };

  search(0, 0, {});
  if (!bestStarts) throw new Error("No feasible schedule for the supplied constraints");
  const selectedStarts = bestStarts as Record<string, number>;
  return tasks.map((task) => {
    const start = selectedStarts[task.id];
    return { ...task, start, end: start + task.duration, ...taskMetrics(task, start) };
  });
}

function toHourlyLoad(schedule: ScheduledTask[]) {
  const load = Array(24).fill(0) as number[];
  for (const task of schedule) {
    for (let hour = task.start; hour < task.end; hour += 1) load[hour] += task.powerKw;
  }
  return load.map((value) => round(value, 1));
}

export function validateSchedule(schedule: ScheduledTask[], scenario: Scenario) {
  const hourlyLoad = toHourlyLoad(schedule);
  const withinWindows = schedule.every(
    (task) => task.start >= task.earliestStart && task.end <= task.latestEnd,
  );
  const belowCapacity = hourlyLoad.every((value) => value <= scenario.maxGridLoadKw + 1e-9);
  return { withinWindows, belowCapacity, valid: withinWindows && belowCapacity };
}

export function createPlan(scenarioId = "morning", objective?: Objective): Plan {
  const scenario = scenarios.find((item) => item.id === scenarioId) ?? scenarios[0];
  const selectedObjective = objective ?? scenario.objective;
  const schedule = optimizeScenario(scenario, selectedObjective);
  const baseline = scheduleAtEarliest(scenario);
  const totalCost = round(schedule.reduce((sum, task) => sum + task.cost, 0));
  const baselineCost = round(baseline.reduce((sum, task) => sum + task.cost, 0));
  const averageGridScore = Math.round(schedule.reduce((sum, task) => sum + task.gridScore, 0) / schedule.length);
  const baselineGridScore = Math.round(baseline.reduce((sum, task) => sum + task.gridScore, 0) / baseline.length);
  const checks = validateSchedule(schedule, scenario);

  return {
    scenario,
    objective: selectedObjective,
    schedule,
    baseline,
    evidence: retrieveEvidence(scenario.prompt, 4),
    totalCost,
    baselineCost,
    averageGridScore,
    baselineGridScore,
    // Signed on purpose: a regression must be visible, not clamped away.
    savingsPercent: Math.round((1 - totalCost / baselineCost) * 100),
    gridImprovementPercent: Math.round((1 - averageGridScore / baselineGridScore) * 100),
    // Only checks that are actually computed count. The offline engine
    // verifies task windows and the hourly capacity cap — nothing else.
    constraintsSatisfied: Number(checks.withinWindows) + Number(checks.belowCapacity),
    constraintsTotal: 2,
    hourlyLoad: toHourlyLoad(schedule),
    baselineLoad: toHourlyLoad(baseline),
  };
}

export function formatHour(hour: number) {
  return `${String(hour).padStart(2, "0")}:00`;
}

export function buildBenchmark() {
  const runs = scenarios.flatMap((scenario) =>
    (["balanced", "cost", "grid"] as Objective[]).map((objective) => createPlan(scenario.id, objective)),
  );
  const valid = runs.filter((plan) => validateSchedule(plan.schedule, plan.scenario).valid).length;
  const lowerCost = runs.filter((plan) => plan.totalCost <= plan.baselineCost).length;
  return {
    runs: runs.length,
    constraintPassRate: Math.round((valid / runs.length) * 100),
    costNonRegressionRate: Math.round((lowerCost / runs.length) * 100),
    retrievalTopK: 4,
  };
}
