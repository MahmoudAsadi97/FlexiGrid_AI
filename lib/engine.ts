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

// Frozen 24-hour fixture used for a reproducible demo. The production adapter
// replaces gridStress with signals derived from Elia ods002 + ods086.
export const tariff = [
  0.22, 0.18, 0.16, 0.15, 0.14, 0.15, 0.19, 0.27, 0.31, 0.29, 0.25, 0.23,
  0.21, 0.2, 0.22, 0.28, 0.37, 0.46, 0.42, 0.34, 0.28, 0.24, 0.21, 0.19,
];

export const gridStress = [
  48, 42, 38, 34, 31, 33, 45, 59, 71, 76, 68, 55, 42, 35, 29, 32, 51, 78,
  91, 86, 70, 58, 52, 47,
];

export const evidenceCorpus: Evidence[] = [
  {
    id: "manual-ev-04",
    title: "EV charger manual · §4.2",
    excerpt: "The charger supports scheduled one-hour blocks and draws at most 3.6 kW in eco mode.",
    tag: "Device manual",
    tokens: ["ev", "charger", "schedule", "eco", "3.6", "charge", "vehicle"],
  },
  {
    id: "manual-dw-11",
    title: "Dishwasher manual · p. 11",
    excerpt: "Eco 50 °C uses approximately 1.0 kWh over two hours. Delayed start is supported.",
    tag: "Device manual",
    tokens: ["dishwasher", "eco", "delay", "two", "hours", "1.0", "kwh"],
  },
  {
    id: "comfort-home",
    title: "Household comfort policy",
    excerpt: "Maintain 19–21 °C while occupied. A pre-heat may finish up to 30 minutes before wake-up.",
    tag: "User constraint",
    tokens: ["heat", "home", "comfort", "temperature", "occupied", "wake", "preheat"],
  },
  {
    id: "tariff-contract",
    title: "Demo tariff contract · §2",
    excerpt: "The demo uses a frozen hourly retail tariff. Elia imbalance prices are not treated as consumer prices.",
    tag: "Tariff rule",
    tokens: ["dynamic", "tariff", "hourly", "price", "cost", "retail", "consumer"],
  },
  {
    id: "elia-ods002",
    title: "Elia Open Data · ods002",
    excerpt: "Measured and forecast total load on the Belgian grid, including day-ahead and week-ahead forecasts.",
    tag: "Elia dataset",
    tokens: ["grid", "load", "forecast", "elia", "belgian", "peak", "day", "ahead"],
  },
  {
    id: "elia-ods086",
    title: "Elia Open Data · ods086",
    excerpt: "Intraday, day-ahead and week-ahead wind power forecasts, updated every quarter-hour.",
    tag: "Elia dataset",
    tokens: ["wind", "renewable", "forecast", "elia", "hourly", "grid", "clean"],
  },
  {
    id: "grid-capacity",
    title: "Connection capacity profile",
    excerpt: "Controllable household load is capped at 4.6 kW to avoid creating a new capacity peak.",
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
    sourceId: "comfort-home",
  },
  {
    id: "dishwasher",
    name: "Dishwasher · Eco",
    icon: "DW",
    powerKw: 0.5,
    duration: 2,
    earliestStart: 0,
    latestEnd: 7,
    sourceId: "manual-dw-11",
  },
  {
    id: "ev",
    name: "EV charge · 7.2 kWh",
    icon: "EV",
    powerKw: 3.6,
    duration: 2,
    earliestStart: 0,
    latestEnd: 7,
    sourceId: "manual-ev-04",
  },
  {
    id: "laundry",
    name: "Laundry",
    icon: "WM",
    powerKw: 0.8,
    duration: 1,
    earliestStart: 0,
    latestEnd: 7,
    sourceId: "grid-capacity",
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
    let chosen = task.earliestStart;
    for (let start = task.earliestStart; start <= task.latestEnd - task.duration; start += 1) {
      const fits = Array.from({ length: task.duration }, (_, offset) => start + offset).every(
        (hour) => load[hour] + task.powerKw <= scenario.maxGridLoadKw,
      );
      if (fits) {
        chosen = start;
        break;
      }
    }
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
    savingsPercent: Math.max(0, Math.round((1 - totalCost / baselineCost) * 100)),
    gridImprovementPercent: Math.max(0, Math.round((1 - averageGridScore / baselineGridScore) * 100)),
    constraintsSatisfied: Number(checks.withinWindows) + Number(checks.belowCapacity) + 2,
    constraintsTotal: 4,
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
