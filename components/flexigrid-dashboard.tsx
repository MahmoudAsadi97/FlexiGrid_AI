"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createPlan,
  formatHour,
  gridStress as fixtureStress,
  scenarios,
  tariff as fixtureTariff,
  type Objective,
} from "@/lib/engine";
import {
  fetchEvaluation,
  fetchHealth,
  runAgentPlan,
  MissionRejectedError,
  type AgentRunResponse,
  type BackendHealth,
  type EvaluationResults,
  type TraceRecord,
} from "@/lib/api";

type View = "plan" | "evaluation" | "architecture";
type RunPhase = "idle" | "running" | "complete" | "error";

const TASK_ICONS: Record<string, string> = {
  ev: "EV",
  dishwasher: "DW",
  laundry: "WM",
  heat: "HP",
};

const RUN_STAGES: {
  icon: "brain" | "database" | "tool" | "chart" | "shield";
  label: string;
  detail: string;
}[] = [
  { icon: "brain", label: "Extract constraints", detail: "mission text → typed, schema-validated spec" },
  { icon: "database", label: "Grid snapshot", detail: "hourly tariff + Elia-derived stress" },
  { icon: "tool", label: "Retrieve evidence", detail: "hybrid RAG over the device & policy corpus" },
  { icon: "chart", label: "Optimize schedule", detail: "joint constrained search under the cap" },
  { icon: "shield", label: "Validate", detail: "independent critic re-checks every hour" },
];

function Icon({ name }: { name: "bolt" | "play" | "check" | "database" | "brain" | "tool" | "chart" | "shield" | "arrow" | "cpu" | "warn" }) {
  const common = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };
  const paths = {
    bolt: <path d="M13 2 4.8 13.1h6.4L10.6 22 19.2 10.9h-6.4L13 2Z" />,
    play: <><path d="M8 5v14l11-7L8 5Z" /><path d="M4 5v14" /></>,
    check: <path d="m5 12 4.2 4.2L19 6.5" />,
    database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>,
    brain: <><path d="M9.5 4.5A3.5 3.5 0 0 0 6 8v.2A3.8 3.8 0 0 0 4 15a3.5 3.5 0 0 0 5.5 3" /><path d="M14.5 4.5A3.5 3.5 0 0 1 18 8v.2A3.8 3.8 0 0 1 20 15a3.5 3.5 0 0 1-5.5 3M12 3v18M8 11h4M12 15h4" /></>,
    tool: <><path d="M14.7 6.3a4.4 4.4 0 0 0-5.6 5.6L4 17l3 3 5.1-5.1a4.4 4.4 0 0 0 5.6-5.6l-2.5 2.5-3-3 2.5-2.5Z" /></>,
    chart: <><path d="M4 19V9M10 19V5M16 19v-7M22 19H2" /></>,
    shield: <><path d="M12 3 5 6v5c0 4.6 2.8 7.8 7 10 4.2-2.2 7-5.4 7-10V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></>,
    arrow: <><path d="M5 12h14M14 7l5 5-5 5" /></>,
    cpu: <><rect x="6" y="6" width="12" height="12" rx="2" /><rect x="10" y="10" width="4" height="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M6 2v2M18 2v2M6 20v2M18 20v2" transform="translate(0 0)" /></>,
    warn: <><path d="M12 3 2.5 20h19L12 3Z" /><path d="M12 10v4M12 17.5v.5" /></>,
  };
  return <svg {...common}>{paths[name]}</svg>;
}

function formatEuro(value: number) {
  return new Intl.NumberFormat("en-BE", { style: "currency", currency: "EUR" }).format(value);
}

function signedPercent(value: number) {
  if (value === 0) return "±0%";
  return `${value >= 0 ? "−" : "+"}${Math.abs(value)}%`;
}

function percent(value: number | null | undefined, digits = 0) {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

// ---------------------------------------------------------------------------
// A unified view model so the chart and task list render identically whether
// the plan came from the live backend or the offline fallback engine.
// ---------------------------------------------------------------------------

type UiTask = {
  id: string;
  name: string;
  icon: string;
  powerKw: number;
  start: number;
  end: number;
  cost: number;
  gridScore: number;
};

type ViewPlan = {
  source: "live" | "offline";
  objective: string;
  schedule: UiTask[];
  baseline: UiTask[];
  hourlyLoad: number[];
  baselineLoad: number[];
  totalCost: number;
  baselineCost: number;
  averageGridScore: number;
  savingsPercent: number;
  gridImprovementPercent: number;
  checks: { label: string; ok: boolean }[];
  peakLoadKw: number;
  capKw: number;
  tariff: number[];
  stress: number[];
  hasBaseline: boolean;
  baselineGridScore: number | null;
  baselinePeakKw: number | null;
  baselineNote?: string;
  relaxationNote?: string;
};

function fromOffline(scenarioId: string, objective: Objective): ViewPlan {
  const plan = createPlan(scenarioId, objective);
  const map = (tasks: typeof plan.schedule): UiTask[] =>
    tasks.map((task) => ({
      id: task.id, name: task.name, icon: task.icon, powerKw: task.powerKw,
      start: task.start, end: task.end, cost: task.cost, gridScore: task.gridScore,
    }));
  return {
    source: "offline",
    objective,
    schedule: map(plan.schedule),
    baseline: map(plan.baseline),
    hourlyLoad: plan.hourlyLoad,
    baselineLoad: plan.baselineLoad,
    totalCost: plan.totalCost,
    baselineCost: plan.baselineCost,
    averageGridScore: plan.averageGridScore,
    savingsPercent: plan.savingsPercent,
    gridImprovementPercent: plan.gridImprovementPercent,
    checks: [
      { label: "Task windows", ok: plan.constraintsSatisfied >= 1 },
      { label: `Load ≤ ${plan.scenario.maxGridLoadKw} kW`, ok: plan.constraintsSatisfied === plan.constraintsTotal },
    ],
    peakLoadKw: Math.max(...plan.hourlyLoad),
    capKw: plan.scenario.maxGridLoadKw,
    tariff: fixtureTariff,
    stress: fixtureStress,
    hasBaseline: true,
    baselineGridScore: plan.baselineGridScore,
    baselinePeakKw: Math.max(...plan.baselineLoad),
  };
}

function fromLive(run: AgentRunResponse): ViewPlan {
  const plan = run.plan;
  const validation = plan.validation;
  const map = (tasks: typeof plan.schedule): UiTask[] =>
    tasks.map((task) => ({
      id: task.task_id,
      name: task.name,
      icon: TASK_ICONS[task.task_id] ?? task.task_id.slice(0, 2).toUpperCase(),
      powerKw: task.power_kw,
      start: task.start,
      end: task.end,
      cost: task.cost_eur,
      gridScore: task.grid_stress,
    }));
  const retrieved = new Set(run.evidence.map((chunk) => chunk.chunk_id));
  const citationsGrounded = run.explanation.citation_ids.every((id) => retrieved.has(id));
  const baseline = plan.baseline;
  const baselineCost = baseline?.total_cost_eur ?? plan.total_cost_eur;
  const baselineStress = baseline?.average_grid_stress ?? plan.average_grid_stress;
  const checks = [
    { label: "Task windows", ok: validation.within_windows },
    { label: `Load ≤ ${validation.max_load_kw} kW`, ok: validation.below_capacity },
    { label: "Avoid-hours", ok: validation.avoid_hours_respected },
    { label: "Citations grounded", ok: citationsGrounded },
  ];
  return {
    source: "live",
    objective: plan.objective,
    schedule: map(plan.schedule),
    baseline: baseline ? map(baseline.schedule) : [],
    hourlyLoad: validation.hourly_load_kw,
    baselineLoad: baseline?.validation.hourly_load_kw ?? [],
    totalCost: plan.total_cost_eur,
    baselineCost,
    averageGridScore: plan.average_grid_stress,
    savingsPercent: baselineCost ? Math.round((1 - plan.total_cost_eur / baselineCost) * 100) : 0,
    gridImprovementPercent: baselineStress ? Math.round((1 - plan.average_grid_stress / baselineStress) * 100) : 0,
    checks,
    peakLoadKw: validation.peak_load_kw,
    capKw: validation.max_load_kw,
    tariff: plan.tariff ?? fixtureTariff,
    stress: plan.stress ?? fixtureStress,
    hasBaseline: Boolean(baseline),
    baselineGridScore: baseline?.average_grid_stress ?? null,
    baselinePeakKw: baseline?.validation.peak_load_kw ?? null,
    baselineNote: plan.baseline_note,
    relaxationNote: plan.relaxation_note,
  };
}

// Consecutive identical tool calls (same tool, args, decider) collapse into
// one row with a ×N chip, so a model that loops reads as one step, not noise.
type CollapsedRecord = TraceRecord & { repeats: number };

function collapseTrace(trace: TraceRecord[]): CollapsedRecord[] {
  const collapsed: CollapsedRecord[] = [];
  for (const record of trace) {
    const previous = collapsed[collapsed.length - 1];
    if (
      previous &&
      previous.tool === record.tool &&
      previous.decided_by === record.decided_by &&
      JSON.stringify(previous.args) === JSON.stringify(record.args)
    ) {
      previous.repeats += 1;
      previous.duration_ms += record.duration_ms;
    } else {
      collapsed.push({ ...record, repeats: 1 });
    }
  }
  return collapsed;
}

// ---------------------------------------------------------------------------
// Chart
// ---------------------------------------------------------------------------

function stressBands(stress: number[], threshold = 75): { start: number; end: number }[] {
  const bands: { start: number; end: number }[] = [];
  let open: number | null = null;
  for (let hour = 0; hour <= 24; hour += 1) {
    const high = hour < 24 && stress[hour] >= threshold;
    if (high && open === null) open = hour;
    if (!high && open !== null) {
      bands.push({ start: open, end: hour });
      open = null;
    }
  }
  return bands;
}

function TimelineChart({ plan, showBaseline }: { plan: ViewPlan; showBaseline: boolean }) {
  const width = 960;
  const height = 286;
  const left = 42;
  const right = 18;
  const top = 18;
  const plotBottom = 214;
  const innerWidth = width - left - right;
  const step = innerWidth / 24;
  const maxTariff = Math.max(...plan.tariff);
  const maxLoad = Math.max(5, plan.capKw + 0.6);
  const load = showBaseline && plan.baselineLoad.length ? plan.baselineLoad : plan.hourlyLoad;
  const schedule = showBaseline && plan.baseline.length ? plan.baseline : plan.schedule;
  const loadPoints = load
    .map((value, hour) => {
      const x = left + hour * step + step / 2;
      const y = plotBottom - (value / maxLoad) * 148;
      return `${x},${y}`;
    })
    .join(" ");
  const capY = plotBottom - (plan.capKw / maxLoad) * 148;

  return (
    <div className="chart-wrap">
      <svg className="timeline-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="timeline-title timeline-desc">
        <title id="timeline-title">24-hour household energy schedule</title>
        <desc id="timeline-desc">Hourly retail tariff bars, controllable household load line, capacity cap, and scheduled appliance blocks.</desc>
        {[0, 1, 2, 3].map((line) => {
          const y = top + line * 48;
          return <line key={line} x1={left} y1={y} x2={width - right} y2={y} className="chart-grid" />;
        })}
        {stressBands(plan.stress).map((band) => (
          <g key={band.start}>
            <rect x={left + band.start * step} y={top} width={(band.end - band.start) * step} height={plotBottom - top} className="peak-window" />
            <text x={left + ((band.start + band.end) / 2) * step} y={top + 15} className="peak-label" textAnchor="middle">HIGH STRESS</text>
          </g>
        ))}
        {plan.tariff.map((value, hour) => {
          const barHeight = (value / maxTariff) * 108;
          return (
            <g key={hour}>
              <title>{`${formatHour(hour)} · ${value.toFixed(2)} €/kWh · stress ${plan.stress[hour]}/100`}</title>
              <rect
                x={left + hour * step + step * 0.18}
                y={plotBottom - barHeight}
                width={step * 0.64}
                height={barHeight}
                rx="3"
                className="price-bar"
              />
            </g>
          );
        })}
        <line x1={left} y1={capY} x2={width - right} y2={capY} className="cap-line" />
        <text x={width - right - 4} y={capY - 5} className="cap-label" textAnchor="end">{plan.capKw.toFixed(1)} kW cap</text>
        <polyline points={loadPoints} className="load-line-halo" />
        <polyline points={loadPoints} className="load-line" />
        {load.map((value, hour) => value > 0 ? (
          <g key={hour}>
            <title>{`${formatHour(hour)} · ${value.toFixed(1)} kW`}</title>
            <circle cx={left + hour * step + step / 2} cy={plotBottom - (value / maxLoad) * 148} r="4" className="load-point" />
          </g>
        ) : null)}
        {schedule.map((task, index) => (
          <g key={task.id}>
            <rect
              x={left + task.start * step + 2}
              y={226 + (index % 2) * 24}
              width={(task.end - task.start) * step - 4}
              height="19"
              rx="5"
              className={`task-block task-${index + 1}`}
            />
            <text
              x={left + (task.start + (task.end - task.start) / 2) * step}
              y={240 + (index % 2) * 24}
              textAnchor="middle"
              className="task-block-label"
            >{task.icon}</text>
          </g>
        ))}
        {[0, 3, 6, 9, 12, 15, 18, 21, 24].map((hour) => (
          <text key={hour} x={left + hour * step} y={282} className="axis-label" textAnchor={hour === 0 ? "start" : hour === 24 ? "end" : "middle"}>{String(hour).padStart(2, "0")}</text>
        ))}
        <text x="4" y="31" className="axis-unit">€/kWh</text>
        <text x="4" y="205" className="axis-unit">kW</text>
      </svg>
      <div className="chart-legend" aria-hidden="true">
        <span><i className="legend-bar" /> Retail tariff</span>
        <span><i className="legend-line" /> Controllable load</span>
        <span><i className="legend-peak" /> High grid-stress hours</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plan view
// ---------------------------------------------------------------------------

function BackendChip({ health, checking }: { health: BackendHealth | null; checking: boolean }) {
  if (checking) return <div className="backend-chip checking"><i /> Probing backend…</div>;
  if (!health) return <div className="backend-chip offline"><i /> Offline simulation — start the backend for the live pipeline</div>;
  const model = health.llm.live ? health.llm.model : "deterministic fallback";
  return (
    <div className="backend-chip live">
      <i /> Live pipeline · {model} · {health.embeddings.backend} embeddings · {health.corpus.chunks} chunks
    </div>
  );
}

function PlanView({ health }: { health: BackendHealth | null }) {
  const [scenarioId, setScenarioId] = useState("morning");
  const [objective, setObjective] = useState<Objective>("balanced");
  const [mission, setMission] = useState(scenarios[0].prompt);
  const [phase, setPhase] = useState<RunPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<AgentRunResponse | null>(null);
  // No plan is shown before a run: the agent (or the labelled offline
  // simulation) has to build everything the page displays.
  const [offlinePlan, setOfflinePlan] = useState<ViewPlan | null>(null);
  const [showBaseline, setShowBaseline] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const timerRef = useRef<number | null>(null);

  const live = Boolean(health);
  const plan: ViewPlan | null = run ? fromLive(run) : offlinePlan;
  const flagged = plan ? !plan.checks.every((check) => check.ok) : false;
  const showingBaseline = Boolean(showBaseline && plan?.hasBaseline);

  const selectScenario = (nextId: string) => {
    const scenario = scenarios.find((item) => item.id === nextId) ?? scenarios[0];
    setScenarioId(scenario.id);
    setObjective(scenario.objective);
    setMission(scenario.prompt);
    setRun(null);
    setError(null);
    setPhase("idle");
    setShowBaseline(false);
    setOfflinePlan(null);
  };

  const startRun = useCallback(async () => {
    setPhase("running");
    setError(null);
    setShowBaseline(false);
    setElapsedMs(0);
    const startedAt = performance.now();
    timerRef.current = window.setInterval(
      () => setElapsedMs(performance.now() - startedAt), 120);
    try {
      if (live) {
        const response = await runAgentPlan(mission, objective);
        setRun(response);
      } else {
        await new Promise((resolve) => setTimeout(resolve, 900));
        setRun(null);
        setOfflinePlan(fromOffline(scenarioId, objective));
      }
      setPhase("complete");
    } catch (caught) {
      setRun(null);
      setPhase("error");
      setError(caught instanceof MissionRejectedError
        ? `Critic rejected the mission: ${caught.message}`
        : `Backend error: ${caught instanceof Error ? caught.message : String(caught)}`);
    } finally {
      if (timerRef.current) window.clearInterval(timerRef.current);
    }
  }, [live, mission, objective, scenarioId]);

  useEffect(() => () => { if (timerRef.current) window.clearInterval(timerRef.current); }, []);

  return (
    <div className="workspace-grid">
      <section className="main-column">
        <div className="brief-panel">
          <div className="panel-heading-row">
            <div>
              <span className="eyebrow">HOUSEHOLD MISSION</span>
              <h1>Plan tomorrow&apos;s flexible energy</h1>
            </div>
            <span className="dataset-chip"><span className="live-dot" /> Elia snapshot · {run?.modes.snapshot === "live-derived" ? "live-derived" : "reproducible"}</span>
          </div>

          <div className="scenario-tabs" role="tablist" aria-label="Demo scenarios">
            {scenarios.map((item) => (
              <button
                key={item.id}
                role="tab"
                aria-selected={scenarioId === item.id}
                className={scenarioId === item.id ? "active" : ""}
                onClick={() => selectScenario(item.id)}
              >{item.shortLabel}</button>
            ))}
          </div>

          <label className="mission-editor">
            <span className="mission-label">Mission (free text — the local model turns this into typed constraints)</span>
            <textarea
              value={mission}
              rows={3}
              onChange={(event) => { setMission(event.target.value); setPhase("idle"); }}
              spellCheck={false}
            />
          </label>

          <div className="brief-actions">
            <fieldset className="objective-control">
              <legend>Optimization objective</legend>
              <div className="segmented-control">
                {(["balanced", "cost", "grid"] as Objective[]).map((item) => (
                  <button
                    key={item}
                    type="button"
                    aria-pressed={objective === item}
                    onClick={() => setObjective(item)}
                  >{item === "grid" ? "Grid support" : item[0].toUpperCase() + item.slice(1)}</button>
                ))}
              </div>
            </fieldset>
            <button className="run-button" onClick={startRun} disabled={phase === "running" || !mission.trim()}>
              {phase === "running" ? <span className="spinner" /> : phase === "complete" ? <Icon name="check" /> : <Icon name="play" />}
              {phase === "running"
                ? `${live ? "Agent running" : "Simulating"}… ${(elapsedMs / 1000).toFixed(1)} s`
                : phase === "complete"
                  ? flagged ? "Plan flagged — run again" : "Plan verified — run again"
                  : live ? "Run agent plan" : "Run offline simulation"}
            </button>
          </div>
        </div>

        {error && (
          <div className="error-card" role="alert">
            <Icon name="warn" />
            <div>
              <strong>No plan displayed</strong>
              <p>{error}</p>
            </div>
          </div>
        )}

        <div className="stats-grid" aria-label="Plan outcome metrics">
          <article className="metric-card primary-metric">
            <span>Estimated energy cost</span>
            <strong>{plan ? formatEuro(showingBaseline ? plan.baselineCost : plan.totalCost) : "—"}</strong>
            <em>{!plan
              ? "run a mission to compute"
              : showingBaseline
                ? "naive earliest-start baseline"
                : !plan.hasBaseline
                  ? "naive baseline infeasible"
                  : `${signedPercent(plan.savingsPercent)} vs earliest-start`}</em>
          </article>
          <article className="metric-card">
            <span>Grid-stress index</span>
            <strong>{plan
              ? <>{showingBaseline ? plan.baselineGridScore ?? plan.averageGridScore : plan.averageGridScore}<small>/100</small></>
              : "—"}</strong>
            <em>{!plan
              ? "run a mission to compute"
              : showingBaseline
                ? "earliest-start baseline"
                : !plan.hasBaseline
                  ? "baseline infeasible"
                  : `${signedPercent(plan.gridImprovementPercent)} vs baseline`}</em>
          </article>
          <article className="metric-card">
            <span>Hard constraints</span>
            <strong>{plan
              ? <>{plan.checks.filter((check) => check.ok).length}<small>/{plan.checks.length}</small></>
              : "—"}</strong>
            <em>{!plan
              ? "validated after every run"
              : showingBaseline
                ? "checks refer to the optimized plan"
                : plan.checks.every((check) => check.ok)
                  ? <><i className="tiny-check">✓</i> validator passed</>
                  : <>validator flagged {plan.checks.filter((check) => !check.ok).length}</>}</em>
          </article>
          <article className="metric-card">
            <span>Peak controllable load</span>
            <strong>{plan
              ? <>{(showingBaseline && plan.baselinePeakKw != null ? plan.baselinePeakKw : plan.peakLoadKw).toFixed(1)}<small> kW</small></>
              : "—"}</strong>
            <em>{plan ? `cap ${plan.capKw.toFixed(1)} kW` : "run a mission to compute"}</em>
          </article>
        </div>

        <div className="schedule-panel">
          <div className="schedule-head">
            <div>
              <span className="eyebrow">24-HOUR PLAN</span>
              <h2>{plan ? "Loads shifted away from grid pressure" : "Your 24-hour schedule appears here"}</h2>
            </div>
            {plan && (
              <div className="compare-toggle" role="group" aria-label="Compare schedules">
                <button className={!showingBaseline ? "active" : ""} onClick={() => setShowBaseline(false)}>Optimized</button>
                {plan.hasBaseline ? (
                  <button className={showingBaseline ? "active" : ""} onClick={() => setShowBaseline(true)}>Baseline</button>
                ) : (
                  <span className="infeasible-tag" title={plan.baselineNote}>baseline infeasible ✕</span>
                )}
              </div>
            )}
          </div>

          {plan && !plan.hasBaseline && plan.baselineNote && (
            <div className="baseline-banner" role="note">
              <Icon name="warn" />
              <p>{plan.baselineNote}</p>
            </div>
          )}

          {plan ? (
            <>
              <TimelineChart plan={plan} showBaseline={showingBaseline} />

              <div className="task-list">
                {(showingBaseline && plan.baseline.length ? plan.baseline : plan.schedule).map((task) => (
                  <article className="task-row" key={task.id}>
                    <div className="task-icon">{task.icon}</div>
                    <div className="task-name">
                      <strong>{task.name}</strong>
                      <span>{task.powerKw.toFixed(1)} kW · {task.end - task.start}h</span>
                    </div>
                    <div className="task-window">
                      <span>Scheduled</span>
                      <strong>{formatHour(task.start)}–{formatHour(task.end)}</strong>
                    </div>
                    <div className="task-result">
                      <strong>{formatEuro(task.cost)}</strong>
                      <span>grid {task.gridScore}/100</span>
                    </div>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <div className="chart-empty">
              <Icon name="chart" />
              <p>
                {live
                  ? "Press Run agent plan — the local model extracts your constraints, calls the MCP tools, and the verified schedule lands here."
                  : "Press Run offline simulation to replay the deterministic browser engine on the frozen fixture. Start the backend for the real pipeline."}
              </p>
            </div>
          )}
        </div>
      </section>

      <aside className="trace-column" aria-label="Agent reasoning trace">
        <div className="trace-sticky">
          <div className="trace-header">
            <div>
              <span className="eyebrow">TRANSPARENT TRACE</span>
              <h2>How the plan was built</h2>
            </div>
            <span className={`trace-status ${phase}${flagged ? " flagged" : ""}`}>
              {phase === "running"
                ? "Running"
                : phase === "error"
                  ? "Rejected"
                  : run
                    ? flagged ? "Flagged · live" : "Verified · live"
                    : plan
                      ? flagged ? "Flagged · sim" : "Offline sim"
                      : live ? "Ready · live" : "Offline sim"}
            </span>
          </div>

          {run ? (
            <>
              <div className="mode-strip">
                <span className={`mode-badge ${run.modes.llm_live ? "llm" : "det"}`}>
                  <Icon name="cpu" /> {run.modes.llm_live ? `local LLM · ${run.modes.llm}` : "deterministic fallback (no LLM)"}
                </span>
                <span className="mode-badge sub">intent: {run.modes.intent}</span>
                <span className="mode-badge sub">retrieval: {run.modes.retrieval} / {run.modes.retrieval_backend}</span>
                {run.modes.transport !== "direct" && (
                  <span className="mode-badge sub">transport: MCP stdio</span>
                )}
              </div>

              <div className="intent-panel">
                <div className="intent-head"><span>Extracted constraints</span><em>schema-validated</em></div>
                <div className="intent-chips">
                  {run.spec.tasks.map((task) => (
                    <span className="intent-chip" key={task.task_id}>
                      {TASK_ICONS[task.task_id] ?? task.task_id} · {task.power_kw} kW · {task.duration_hours}h · [{formatHour(task.earliest_start)}–{formatHour(task.latest_end)}]
                    </span>
                  ))}
                  <span className="intent-chip cap">cap {run.spec.max_load_kw} kW</span>
                  {run.spec.avoid_hours.length > 0 && (
                    <span className="intent-chip avoid">avoid {run.spec.avoid_hours.map(formatHour).join(", ")}</span>
                  )}
                </div>
                {run.modes.intent_adjustments.length > 0 && (
                  <div className="adjustment-note" role="note">
                    <strong>Sanitizer stepped in</strong>
                    <p>{run.modes.intent_adjustments.join("; ")}</p>
                  </div>
                )}
              </div>

              <div className="tool-log">
                <div className="tool-log-head"><span>Agent tool calls</span><em>{run.trace.length} steps</em></div>
                {collapseTrace(run.trace).map((record) => (
                  <div className={`tool-row ${record.ok ? "" : "failed"}`} key={record.step}>
                    <code><b>{record.tool}</b>{record.repeats > 1 ? <i className="repeat-chip">×{record.repeats}</i> : null}</code>
                    <span className="tool-meta">
                      <em className={`decided ${record.decided_by}`}>{record.decided_by}</em>
                      <em>{record.duration_ms} ms</em>
                    </span>
                    <p>{record.thought || record.summary}</p>
                  </div>
                ))}
              </div>

              <div className="evidence-head">
                <span>Retrieved evidence</span>
                <em>{run.modes.retrieval} · top-{run.evidence.length}</em>
              </div>
              <div className="evidence-list">
                {run.evidence.map((chunk) => (
                  <article className="evidence-card" key={chunk.chunk_id}>
                    <div className="evidence-number">{chunk.rank}</div>
                    <div>
                      <div className="evidence-title">
                        <strong>{chunk.title} — {chunk.section}</strong>
                        <span>{chunk.chunk_id}</span>
                      </div>
                      <p>{chunk.text.length > 180 ? `${chunk.text.slice(0, 177)}…` : chunk.text}</p>
                    </div>
                  </article>
                ))}
              </div>

              <div className="explanation-card">
                <div className="explanation-head">
                  <span>Cited explanation</span>
                  <em>{run.modes.explanation === "llm" ? `generated by ${run.modes.llm}` : "deterministic fallback"}</em>
                </div>
                <p className="explanation-summary">{run.explanation.summary}</p>
                <ul>
                  {run.explanation.rationale.map((line) => <li key={line}>{line}</li>)}
                </ul>
                <p className="explanation-citations">Citations: {run.explanation.citation_ids.join(", ")}</p>
                <p className="explanation-limitation">{run.explanation.limitation}</p>
              </div>

              <div className={`critic-note${flagged ? " flagged" : ""}`}>
                <Icon name={flagged ? "warn" : "shield"} />
                <div>
                  <strong>Critic verdict</strong>
                  <p>{plan && plan.checks.every((check) => check.ok)
                    ? `All ${plan.checks.length} checks passed: ${plan.checks.map((check) => check.label).join(", ")}.`
                    : plan
                      ? `Flagged: ${plan.checks.filter((check) => !check.ok).map((check) => check.label).join(", ")} — ${plan.checks.filter((check) => check.ok).length}/${plan.checks.length} other checks passed.`
                      : ""}
                    {plan?.relaxationNote ? ` ${plan.relaxationNote}` : ""}
                    {plan?.baselineNote ? ` ${plan.baselineNote}` : ""}</p>
                </div>
              </div>
            </>
          ) : phase === "running" && live ? (
            <>
              <div className="mode-strip">
                <span className="mode-badge llm"><Icon name="cpu" /> agent running · {(elapsedMs / 1000).toFixed(1)} s</span>
              </div>
              <ol className="pipeline-list running" aria-label="Pipeline stages in progress">
                {RUN_STAGES.map((stage, index) => (
                  <li className="pipeline-step reached" style={{ animationDelay: `${index * 0.45}s` }} key={stage.label}>
                    <span className="stage-icon"><Icon name={stage.icon} /></span>
                    <div>
                      <strong>{stage.label}</strong>
                      <span>{stage.detail}</span>
                    </div>
                  </li>
                ))}
              </ol>
              <p className="offline-note ready-note">
                The local model is choosing tools step by step. The real trace —
                every call, thought, and timing — replaces this list the moment
                the run completes.
              </p>
            </>
          ) : phase === "error" && live ? (
            <>
              <div className="mode-strip">
                <span className="mode-badge det"><Icon name="shield" /> live backend — mission rejected</span>
              </div>
              <p className="offline-note">
                The critic refused to display an invalid schedule — see the
                message on the left. Widen a time window, raise the capacity
                cap, or remove a device, then run again.
              </p>
            </>
          ) : plan ? (
            <>
              <div className="mode-strip">
                <span className="mode-badge det"><Icon name="cpu" /> offline simulation — browser engine</span>
              </div>
              <p className="offline-note">
                The backend is not connected, so this run replayed the
                deterministic browser-side engine on the frozen fixture. Start
                the API and the local model (<code>uvicorn flexigrid.api:app</code> +
                Ollama) and reload to see the real agent trace, retrieval, and
                the model-generated explanation here.
              </p>
              <div className="evidence-head"><span>Fixture evidence (simulated retrieval)</span><em>top-4</em></div>
              <div className="evidence-list">
                {createPlan(scenarioId, objective).evidence.map((doc, index) => (
                  <article className="evidence-card" key={doc.id}>
                    <div className="evidence-number">{index + 1}</div>
                    <div>
                      <div className="evidence-title"><strong>{doc.title}</strong><span>{doc.id}</span></div>
                      <p>{doc.excerpt}</p>
                    </div>
                  </article>
                ))}
              </div>
              <div className="critic-note">
                <Icon name="shield" />
                <div>
                  <strong>Critic verdict (offline)</strong>
                  <p>{plan.checks.every((check) => check.ok)
                    ? `Both computed checks passed: ${plan.checks.map((check) => check.label).join(", ")}.`
                    : "The offline validator flagged this schedule."}</p>
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="mode-strip">
                <span className={`mode-badge ${live ? "llm" : "det"}`}>
                  <Icon name="cpu" /> {live ? "backend connected — ready" : "backend offline — browser engine on standby"}
                </span>
              </div>
              {live ? (
                <p className="offline-note ready-note">
                  The live pipeline is up. Run a mission and this panel fills
                  with the real thing: the constraints the model extracted,
                  every tool call with its thought and timing, the retrieved
                  evidence, the cited explanation, and the critic&apos;s verdict.
                </p>
              ) : (
                <p className="offline-note">
                  The backend is not connected. Run offline simulation replays a
                  clearly-labelled deterministic browser engine; start the API
                  and the local model (<code>uvicorn flexigrid.api:app</code> +
                  Ollama) and reload for the real agent trace.
                </p>
              )}
              <ol className="pipeline-list" aria-label="Pipeline stages">
                {RUN_STAGES.map((stage) => (
                  <li className="pipeline-step" key={stage.label}>
                    <span className="stage-icon"><Icon name={stage.icon} /></span>
                    <div>
                      <strong>{stage.label}</strong>
                      <span>{stage.detail}</span>
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Evaluation view
// ---------------------------------------------------------------------------

const FALLBACK_EVAL: EvaluationResults = {
  environment: {
    generated_at: "2026-08-24T12:18:23+00:00",
    llm_model: null,
    embeddings_backend: "tfidf",
    embeddings_model: "tfidf-svd-128",
    corpus_chunks: 51,
  },
  retrieval: {
    bm25: { queries: 40, hit_at_1: 0.95, recall_at_4: 0.988, mrr: 0.969 },
    dense: { queries: 40, hit_at_1: 0.95, recall_at_4: 0.988, mrr: 0.967 },
    hybrid: { queries: 40, hit_at_1: 0.95, recall_at_4: 0.988, mrr: 0.971 },
  },
  intent: {
    rules: {
      missions: 15,
      exact_match: 0.733,
      per_field: { devices: 0.933, deadline: 0.933, objective: 0.867, max_load_kw: 1, avoid_hours: 1 },
    },
  },
  llm_only_baseline: { skipped: "requires the local model" },
  greedy_ablation: {
    cases: [
      { case: "morning", joint_cost_eur: 1.79, greedy_cost_eur: null, greedy_valid: false },
      { case: "grid-friendly", joint_cost_eur: 1.37, greedy_cost_eur: 1.37, greedy_valid: true },
      { case: "peak-avoidance", joint_cost_eur: 1.84, greedy_cost_eur: 1.84, greedy_valid: true },
      { case: "tight-window (cost)", joint_cost_eur: 1.87, greedy_cost_eur: null, greedy_valid: false },
      { case: "tight-window (balanced)", joint_cost_eur: 1.87, greedy_cost_eur: null, greedy_valid: false },
    ],
    greedy_failures: 3,
    joint_failures: 0,
  },
  agent_properties: {
    citation_precision: 1,
    explanations_rejected_by_guard: 0,
    deterministic_plan_replay: true,
  },
};

function EvaluationView() {
  const [measured, setMeasured] = useState<EvaluationResults | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchEvaluation().then((result) => {
      if (!cancelled && result) setMeasured(result);
    });
    return () => { cancelled = true; };
  }, []);

  const data = measured ?? FALLBACK_EVAL;
  const hybrid = data.retrieval.hybrid;
  const extractorName = data.intent["llm"] ? "llm" : "rules";
  const extractor = data.intent[extractorName];
  const baseline = data.llm_only_baseline;
  const ablation = data.greedy_ablation;
  const agentProps = data.agent_properties;
  const modelLabel = data.environment.llm_model ?? "no-LLM fallback";

  return (
    <div className="evaluation-page">
      <section className="evaluation-hero">
        <span className="eyebrow">SPLIT EVALUATION</span>
        <h1>Every subsystem measured separately.</h1>
        <p>
          Retrieval, intent extraction, planning, and generation are evaluated
          independently by <code>python -m flexigrid.evaluate</code>, which
          writes <code>backend/evaluation/results.json</code> and records which
          local model and embedding backend produced every number. A fluent
          answer can never hide an invalid schedule.
        </p>
        <div className="evaluation-badge"><Icon name="check" /> No model-generated benchmark numbers</div>
      </section>

      <section className="benchmark-grid">
        <article>
          <span>Retrieval · hybrid</span>
          <strong>{percent(hybrid?.hit_at_1)}</strong>
          <p>hit@1 on {hybrid?.queries ?? 40} labelled queries · recall@4 {percent(hybrid?.recall_at_4, 1)} · MRR {hybrid?.mrr ?? "—"}</p>
        </article>
        <article>
          <span>Intent · {extractorName}</span>
          <strong>{percent(extractor?.exact_match)}</strong>
          <p>exact-match on {extractor?.missions ?? 15} labelled missions · devices {percent(extractor?.per_field?.devices)} · cap {percent(extractor?.per_field?.max_load_kw)}</p>
        </article>
        <article>
          <span>LLM-only scheduling</span>
          <strong>{baseline.skipped ? "—" : percent(baseline.violation_or_failure_rate)}</strong>
          <p>{baseline.skipped
            ? "violation rate of direct-model scheduling — measure it on the demo machine with Ollama live; the critic holds displayed violations at zero"
            : `of ${baseline.attempts} direct-model schedules violate constraints (${baseline.model}) — the critic blocks every one from display`}</p>
        </article>
        <article>
          <span>Greedy vs joint search</span>
          <strong>{ablation.greedy_failures}/{ablation.cases.length}</strong>
          <p>cases where greedy placement fails outright · joint constrained search: {ablation.joint_failures} failures</p>
        </article>
      </section>

      <div className="evaluation-columns">
        <section className="results-panel">
          <div className="section-heading">
            <div><span className="eyebrow">MEASURED RESULTS</span><h2>results.json, rendered live</h2></div>
            <span className="suite-status"><i /> {measured ? "read from the running backend" : "packaged snapshot"} · {modelLabel}</span>
          </div>
          <div className="results-table-wrap">
            <table className="results-table">
              <thead><tr><th>Retrieval mode</th><th>hit@1</th><th>recall@4</th><th>MRR</th></tr></thead>
              <tbody>
                {(["bm25", "dense", "hybrid"] as const).map((mode) => {
                  const row = data.retrieval[mode];
                  if (!row) return null;
                  return (
                    <tr key={mode}>
                      <td><span className="objective-pill">{mode}</span></td>
                      <td>{percent(row.hit_at_1, 1)}</td>
                      <td>{percent(row.recall_at_4, 1)}</td>
                      <td>{row.mrr}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="results-table-wrap">
            <table className="results-table">
              <thead><tr><th>Ablation case</th><th>Joint search</th><th>Greedy placement</th></tr></thead>
              <tbody>
                {ablation.cases.map((row) => (
                  <tr key={row.case}>
                    <td>{row.case}</td>
                    <td>{row.joint_cost_eur != null ? formatEuro(row.joint_cost_eur) : "—"}</td>
                    <td>{row.greedy_valid && row.greedy_cost_eur != null
                      ? formatEuro(row.greedy_cost_eur)
                      : <span className="fail-pill">✗ infeasible</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="property-chips">
            <span className="property-chip"><Icon name="check" /> citation precision {percent(agentProps.citation_precision)}</span>
            <span className="property-chip"><Icon name="check" /> deterministic replay {agentProps.deterministic_plan_replay ? "yes" : "no"}</span>
            <span className="property-chip"><Icon name="shield" /> {agentProps.explanations_rejected_by_guard} explanations rejected by the citation guard</span>
          </div>
          <p className="table-footnote">
            Generated {data.environment.generated_at.slice(0, 10)} · {modelLabel} ·{" "}
            {data.environment.embeddings_backend} embeddings · corpus{" "}
            {data.environment.corpus_chunks} chunks. Re-run{" "}
            <code>python -m flexigrid.evaluate</code> after switching models —
            this page reads the refreshed numbers straight from the backend.
          </p>
        </section>

        <aside className="evaluation-method">
          <span className="eyebrow">WHAT WE MEASURE</span>
          <h2>Four layers, four failure modes</h2>
          <ol className="measure-list">
            <li><b>1</b><div><strong>Retrieval</strong><span>hit@1, recall@4, MRR on 40 labelled queries — BM25 vs dense vs hybrid.</span></div></li>
            <li><b>2</b><div><strong>Intent</strong><span>device/deadline/objective/cap accuracy on 15 missions — LLM vs rules.</span></div></li>
            <li><b>3</b><div><strong>Planning</strong><span>constraint validity, cost vs baselines, greedy-search ablation.</span></div></li>
            <li><b>4</b><div><strong>Generation</strong><span>citation precision against the retrieved allow-list; guard rejections.</span></div></li>
          </ol>
          <div className="limitation-box"><strong>Honest limitation</strong><p>Local-model numbers depend on the machine&apos;s model (default qwen2.5:3b-instruct). Re-run the harness after switching models; results.json records the provenance of every figure.</p></div>
        </aside>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Architecture view
// ---------------------------------------------------------------------------

function ArchitectureView() {
  return (
    <div className="architecture-page">
      <section className="architecture-intro">
        <span className="eyebrow">SYSTEM DESIGN</span>
        <h1>Generative where useful. Deterministic where necessary.</h1>
        <p>A local language model interprets missions, drives the tool loop and explains results; deterministic code owns feasibility. Every stage is inspectable through typed MCP tools.</p>
      </section>

      <section className="architecture-flow" aria-label="FlexiGrid architecture flow">
        <article className="architecture-node user-node"><span>01</span><div className="node-icon"><Icon name="bolt" /></div><h2>Mission</h2><p>Free-text goals, deadlines, comfort and capacity constraints.</p><em>Natural language</em></article>
        <div className="flow-arrow"><Icon name="arrow" /></div>
        <article className="architecture-node"><span>02</span><div className="node-icon"><Icon name="cpu" /></div><h2>Local LLM agent</h2><p>Extracts typed constraints, chooses tools step by step; a sanitizer clamps every value.</p><em>qwen2.5:3b via Ollama</em></article>
        <div className="flow-arrow"><Icon name="arrow" /></div>
        <article className="architecture-node"><span>03</span><div className="node-icon"><Icon name="tool" /></div><h2>MCP tools</h2><p>Hybrid RAG over 51 chunks, Elia snapshot with derived stress, optimizer, validator.</p><em>Typed contracts</em></article>
        <div className="flow-arrow"><Icon name="arrow" /></div>
        <article className="architecture-node accent-node"><span>04</span><div className="node-icon"><Icon name="brain" /></div><h2>Optimizer + critic</h2><p>Joint constrained search; independent re-validation gates every displayed plan.</p><em>Deterministic</em></article>
        <div className="flow-arrow"><Icon name="arrow" /></div>
        <article className="architecture-node"><span>05</span><div className="node-icon"><Icon name="shield" /></div><h2>Cited explanation</h2><p>Schema-constrained generation; citations restricted to the retrieved allow-list.</p><em>Grounded output</em></article>
      </section>

      <section className="data-contracts">
        <div className="data-contract-heading"><div><span className="eyebrow">ELIA OPEN DATA</span><h2>Belgian grid context</h2></div><a href="https://opendata.elia.be/" target="_blank" rel="noreferrer">Open official portal <Icon name="arrow" /></a></div>
        <div className="dataset-grid">
          <article><span className="dataset-id">ODS002</span><h3>Total load</h3><p>Day-ahead load forecast — the demand half of the derived stress signal.</p><a href="https://opendata.elia.be/explore/dataset/ods002/" target="_blank" rel="noreferrer">Dataset page ↗</a></article>
          <article><span className="dataset-id">ODS086</span><h3>Wind forecast</h3><p>Day-ahead wind forecast — the supply half of the derived stress signal.</p><a href="https://opendata.elia.be/explore/dataset/ods086/" target="_blank" rel="noreferrer">Dataset page ↗</a></article>
          <article><span className="dataset-id">ODS201</span><h3>Generation mix</h3><p>Actual generation by fuel type — context and a future carbon-aware objective.</p><a href="https://opendata.elia.be/explore/dataset/ods201/" target="_blank" rel="noreferrer">Dataset page ↗</a></article>
        </div>
        <p className="derivation-note">
          stress(h) = minmax(load forecast) − 0.5 · minmax(wind forecast), rescaled to 0–100.
          Implemented and unit-tested in <code>backend/flexigrid/derive.py</code>; the exam demo
          uses the labelled frozen snapshot, live derivation runs with <code>ELIA_USE_LIVE=true</code>.
        </p>
      </section>

      <section className="design-decisions">
        <div><span className="decision-label">WHY A LOCAL LLM</span><h3>Private, free, reproducible.</h3><p>Household data never leaves the machine, the demo needs no cloud key, and the same OpenAI-compatible client works with any endpoint.</p></div>
        <div><span className="decision-label">WHY HYBRID RAG</span><h3>Lexical precision + semantic recall.</h3><p>BM25 and dense embeddings are fused by reciprocal rank; the evaluation reports each mode separately.</p></div>
        <div><span className="decision-label">WHY MCP</span><h3>Tools remain swappable and inspectable.</h3><p>The same registry serves the in-process agent, the stdio MCP server, and any external MCP host.</p></div>
        <div><span className="decision-label">WHY A CRITIC</span><h3>Feasibility is not negotiable.</h3><p>Every schedule is re-validated hour by hour before display; the model can propose, never approve.</p></div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------

export default function FlexiGridDashboard() {
  const [view, setView] = useState<View>("plan");
  const [health, setHealth] = useState<BackendHealth | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchHealth().then((result) => {
      if (!cancelled) {
        setHealth(result);
        setChecking(false);
      }
    });
    return () => { cancelled = true; };
  }, []);

  return (
    <main className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={() => setView("plan")} aria-label="FlexiGrid AI home">
          <span className="brand-mark"><Icon name="bolt" /></span>
          <span><strong>FlexiGrid</strong><em>AI</em></span>
        </button>
        <nav aria-label="Primary navigation">
          <button className={view === "plan" ? "active" : ""} onClick={() => setView("plan")}>Plan</button>
          <button className={view === "evaluation" ? "active" : ""} onClick={() => setView("evaluation")}>Evaluation</button>
          <button className={view === "architecture" ? "active" : ""} onClick={() => setView("architecture")}>Architecture</button>
        </nav>
        <div className="topbar-meta"><BackendChip health={health} checking={checking} /></div>
      </header>
      {/* All views stay mounted so a live run survives tab switches — during
          the Q&A round, Plan → Architecture → Plan must not wipe the trace. */}
      <div className="content-shell">
        <div hidden={view !== "plan"}><PlanView health={health} /></div>
        <div hidden={view !== "evaluation"}><EvaluationView /></div>
        <div hidden={view !== "architecture"}><ArchitectureView /></div>
      </div>
      <footer className="app-footer">
        <span>FlexiGrid AI · Generative AI assignment prototype</span>
        <span>Local model · Elia data attributed · advisory only, no device control</span>
      </footer>
    </main>
  );
}
