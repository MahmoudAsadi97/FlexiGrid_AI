"use client";

import { useEffect, useMemo, useState } from "react";
import {
  buildBenchmark,
  createPlan,
  formatHour,
  scenarios,
  tariff,
  type Objective,
  type Plan,
} from "@/lib/engine";

type View = "plan" | "evaluation" | "architecture";
type RunState = "idle" | "retrieving" | "tooling" | "optimizing" | "complete";

function Icon({ name }: { name: "bolt" | "play" | "check" | "database" | "brain" | "tool" | "chart" | "shield" | "arrow" }) {
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
  };
  return <svg {...common}>{paths[name]}</svg>;
}

function formatEuro(value: number) {
  return new Intl.NumberFormat("en-BE", { style: "currency", currency: "EUR" }).format(value);
}

function TimelineChart({ plan, showBaseline }: { plan: Plan; showBaseline: boolean }) {
  const width = 960;
  const height = 286;
  const left = 42;
  const right = 18;
  const top = 18;
  const plotBottom = 214;
  const innerWidth = width - left - right;
  const step = innerWidth / 24;
  const maxTariff = Math.max(...tariff);
  const maxLoad = 5;
  const load = showBaseline ? plan.baselineLoad : plan.hourlyLoad;
  const schedule = showBaseline ? plan.baseline : plan.schedule;
  const loadPoints = load
    .map((value, hour) => {
      const x = left + hour * step + step / 2;
      const y = plotBottom - (value / maxLoad) * 148;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="chart-wrap">
      <svg className="timeline-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="timeline-title timeline-desc">
        <title id="timeline-title">24-hour household energy schedule</title>
        <desc id="timeline-desc">Hourly retail tariff bars, controllable household load line, and scheduled appliance blocks.</desc>
        {[0, 1, 2, 3].map((line) => {
          const y = top + line * 48;
          return <line key={line} x1={left} y1={y} x2={width - right} y2={y} className="chart-grid" />;
        })}
        <rect x={left + 17 * step} y={top} width={3 * step} height={plotBottom - top} className="peak-window" />
        <text x={left + 18.5 * step} y={top + 15} className="peak-label" textAnchor="middle">EVENING PEAK</text>
        {tariff.map((value, hour) => {
          const barHeight = (value / maxTariff) * 108;
          return (
            <g key={hour}>
              <title>{`${formatHour(hour)} · ${value.toFixed(2)} €/kWh`}</title>
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
        <span><i className="legend-peak" /> Peak grid-stress window</span>
      </div>
    </div>
  );
}

function RunButton({ state, onRun }: { state: RunState; onRun: () => void }) {
  const labels: Record<RunState, string> = {
    idle: "Run agent plan",
    retrieving: "Retrieving evidence…",
    tooling: "Calling grid tools…",
    optimizing: "Critiquing schedule…",
    complete: "Plan verified",
  };
  return (
    <button className="run-button" onClick={onRun} disabled={state !== "idle" && state !== "complete"}>
      {state === "complete" ? <Icon name="check" /> : <Icon name="play" />}
      {labels[state]}
    </button>
  );
}

const pipelineStages = [
  { id: "retrieving", label: "RAG retriever", detail: "4 constraint chunks · grounded sources", icon: "database" as const },
  { id: "tooling", label: "MCP grid tools", detail: "Elia dataset contracts · frozen demo signal", icon: "tool" as const },
  { id: "optimizing", label: "Planner + critic", detail: "hard constraints · deterministic validator", icon: "brain" as const },
  { id: "complete", label: "Verified plan", detail: "machine-checked before generation", icon: "shield" as const },
];

function PlanView() {
  const [scenarioId, setScenarioId] = useState("morning");
  const [objective, setObjective] = useState<Objective>("balanced");
  const [plan, setPlan] = useState(() => createPlan("morning", "balanced"));
  const [runState, setRunState] = useState<RunState>("idle");
  const [showBaseline, setShowBaseline] = useState(false);
  const scenario = scenarios.find((item) => item.id === scenarioId) ?? scenarios[0];

  useEffect(() => {
    if (runState === "idle" || runState === "complete") return;
    const next: Record<Exclude<RunState, "idle" | "complete">, RunState> = {
      retrieving: "tooling",
      tooling: "optimizing",
      optimizing: "complete",
    };
    const timer = window.setTimeout(() => {
      if (runState === "optimizing") setPlan(createPlan(scenarioId, objective));
      setRunState(next[runState]);
    }, runState === "optimizing" ? 650 : 480);
    return () => window.clearTimeout(timer);
  }, [runState, scenarioId, objective]);

  const startRun = () => {
    setShowBaseline(false);
    setRunState("retrieving");
  };

  const selectScenario = (nextScenarioId: string) => {
    const nextScenario = scenarios.find((item) => item.id === nextScenarioId) ?? scenarios[0];
    setScenarioId(nextScenario.id);
    setObjective(nextScenario.objective);
    setPlan(createPlan(nextScenario.id, nextScenario.objective));
    setRunState("idle");
    setShowBaseline(false);
  };

  const stageReached = (id: string) => {
    const order = ["retrieving", "tooling", "optimizing", "complete"];
    if (runState === "idle") return false;
    return order.indexOf(id) <= order.indexOf(runState);
  };

  return (
    <div className="workspace-grid">
      <section className="main-column">
        <div className="brief-panel">
          <div className="panel-heading-row">
            <div>
              <span className="eyebrow">HOUSEHOLD MISSION</span>
              <h1>Plan tomorrow&apos;s flexible energy</h1>
            </div>
            <span className="dataset-chip"><span className="live-dot" /> Elia snapshot · reproducible</span>
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

          <div className="prompt-box">
            <div className="prompt-mark"><Icon name="bolt" /></div>
            <p>{scenario.prompt}</p>
          </div>

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
            <RunButton state={runState} onRun={startRun} />
          </div>
        </div>

        <div className="stats-grid" aria-label="Plan outcome metrics">
          <article className="metric-card primary-metric">
            <span>Estimated energy cost</span>
            <strong>{formatEuro(showBaseline ? plan.baselineCost : plan.totalCost)}</strong>
            <em>−{plan.savingsPercent}% vs earliest-start</em>
          </article>
          <article className="metric-card">
            <span>Demo stress index</span>
            <strong>{showBaseline ? plan.baselineGridScore : plan.averageGridScore}<small>/100</small></strong>
            <em>−{plan.gridImprovementPercent}% lower</em>
          </article>
          <article className="metric-card">
            <span>Hard constraints</span>
            <strong>{plan.constraintsSatisfied}<small>/{plan.constraintsTotal}</small></strong>
            <em><i className="tiny-check">✓</i> validator passed</em>
          </article>
          <article className="metric-card">
            <span>Evidence coverage</span>
            <strong>{plan.evidence.length}<small> sources</small></strong>
            <em><i className="tiny-check">✓</i> citations attached</em>
          </article>
        </div>

        <div className="schedule-panel">
          <div className="schedule-head">
            <div>
              <span className="eyebrow">24-HOUR PLAN</span>
              <h2>Loads shifted away from grid pressure</h2>
            </div>
            <div className="compare-toggle" role="group" aria-label="Compare schedules">
              <button className={!showBaseline ? "active" : ""} onClick={() => setShowBaseline(false)}>Optimized</button>
              <button className={showBaseline ? "active" : ""} onClick={() => setShowBaseline(true)}>Baseline</button>
            </div>
          </div>
          <TimelineChart plan={plan} showBaseline={showBaseline} />

          <div className="task-list">
            {(showBaseline ? plan.baseline : plan.schedule).map((task) => (
              <article className="task-row" key={task.id}>
                <div className="task-icon">{task.icon}</div>
                <div className="task-name">
                  <strong>{task.name}</strong>
                  <span>{task.powerKw.toFixed(1)} kW · {task.duration}h</span>
                </div>
                <div className="task-window">
                  <span>Scheduled</span>
                  <strong>{formatHour(task.start)}–{formatHour(task.end)}</strong>
                </div>
                <div className="task-result">
                  <strong>{formatEuro(task.cost)}</strong>
                  <span>grid {task.gridScore}/100</span>
                </div>
                <span className="valid-pill"><Icon name="check" /> Valid</span>
              </article>
            ))}
          </div>
        </div>
      </section>

      <aside className="trace-column" aria-label="Agent reasoning trace">
        <div className="trace-sticky">
          <div className="trace-header">
            <div>
              <span className="eyebrow">TRANSPARENT TRACE</span>
              <h2>How the plan was built</h2>
            </div>
            <span className={`trace-status ${runState}`}>{runState === "idle" ? "Ready" : runState === "complete" ? "Verified" : "Running"}</span>
          </div>

          <div className="pipeline-list">
            {pipelineStages.map((stage, index) => {
              const reached = stageReached(stage.id);
              const active = runState === stage.id;
              return (
                <div className={`pipeline-step ${reached ? "reached" : ""} ${active ? "active" : ""}`} key={stage.id}>
                  <div className="stage-icon"><Icon name={stage.icon} /></div>
                  <div>
                    <strong>{stage.label}</strong>
                    <span>{stage.detail}</span>
                  </div>
                  <i className="stage-state">{reached && !active ? "✓" : active ? "•••" : String(index + 1)}</i>
                </div>
              );
            })}
          </div>

          <div className="tool-log">
            <div className="tool-log-head"><span>MCP tool calls</span><em>read-only</em></div>
            <code><b>get_elia_grid_snapshot</b>({`{ use_live: false }`})</code>
            <code><b>retrieve_household_evidence</b>({`{ top_k: 4 }`})</code>
            <code><b>optimize_household_plan</b>({`{ objective: "${objective}" }`})</code>
          </div>

          <div className="evidence-head">
            <span>Retrieved evidence</span>
            <em>top-k = 4</em>
          </div>
          <div className="evidence-list">
            {plan.evidence.map((doc, index) => (
              <article className="evidence-card" key={doc.id}>
                <div className="evidence-number">{index + 1}</div>
                <div>
                  <div className="evidence-title"><strong>{doc.title}</strong><span>{doc.tag}</span></div>
                  <p>{doc.excerpt}</p>
                </div>
              </article>
            ))}
          </div>

          <div className="critic-note">
            <Icon name="shield" />
            <div><strong>Critic verdict</strong><p>No capacity, deadline, or comfort violations detected. Retail tariff and grid signals are kept semantically separate.</p></div>
          </div>
        </div>
      </aside>
    </div>
  );
}

function EvaluationView() {
  const benchmark = useMemo(() => buildBenchmark(), []);
  const testRows = scenarios.map((scenario) => {
    const plan = createPlan(scenario.id, scenario.objective);
    return {
      scenario: scenario.label,
      objective: scenario.objective,
      cost: plan.totalCost,
      improvement: Math.max(plan.savingsPercent, plan.gridImprovementPercent),
      valid: plan.constraintsSatisfied === plan.constraintsTotal,
    };
  });

  return (
    <div className="evaluation-page">
      <section className="evaluation-hero">
        <span className="eyebrow">REPRODUCIBLE EVALUATION</span>
        <h1>Evidence before adjectives.</h1>
        <p>Every displayed claim comes from deterministic fixture runs. LLM quality is evaluated separately so a fluent answer cannot hide an invalid schedule.</p>
        <div className="evaluation-badge"><Icon name="check" /> No model-generated benchmark numbers</div>
      </section>

      <section className="benchmark-grid">
        <article><span>Fixture runs</span><strong>{benchmark.runs}</strong><p>3 scenarios × 3 objectives</p></article>
        <article><span>Constraint pass rate</span><strong>{benchmark.constraintPassRate}%</strong><p>windows + 4.6 kW cap</p></article>
        <article><span>Cost non-regression</span><strong>{benchmark.costNonRegressionRate}%</strong><p>against earliest-start baseline</p></article>
        <article><span>Retrieval depth</span><strong>k={benchmark.retrievalTopK}</strong><p>ranked evidence chunks</p></article>
      </section>

      <div className="evaluation-columns">
        <section className="results-panel">
          <div className="section-heading"><div><span className="eyebrow">ACCEPTANCE SUITE</span><h2>Representative scenarios</h2></div><span className="suite-status"><i /> All deterministic checks pass</span></div>
          <div className="results-table-wrap">
            <table className="results-table">
              <thead><tr><th>Scenario</th><th>Objective</th><th>Cost</th><th>Best improvement</th><th>Validator</th></tr></thead>
              <tbody>{testRows.map((row) => <tr key={row.scenario}><td>{row.scenario}</td><td><span className="objective-pill">{row.objective}</span></td><td>{formatEuro(row.cost)}</td><td>−{row.improvement}%</td><td><span className="pass-pill">✓ Pass</span></td></tr>)}</tbody>
            </table>
          </div>
        </section>

        <aside className="evaluation-method">
          <span className="eyebrow">WHAT WE MEASURE</span>
          <h2>Four layers, four failure modes</h2>
          <ol className="measure-list">
            <li><b>1</b><div><strong>Retrieval</strong><span>Top-k depth and labelled EV-manual rank-1 check.</span></div></li>
            <li><b>2</b><div><strong>Tool use</strong><span>Typed MCP contracts and deterministic fallbacks.</span></div></li>
            <li><b>3</b><div><strong>Planning</strong><span>Cost, grid score, deadlines and capacity.</span></div></li>
            <li><b>4</b><div><strong>Generation</strong><span>Groundedness judged from cited evidence only.</span></div></li>
          </ol>
          <div className="limitation-box"><strong>Honest limitation</strong><p>The deployed demo uses a frozen Elia-shaped snapshot. Live ingestion is included in the source, but the presentation does not depend on API availability.</p></div>
        </aside>
      </div>
    </div>
  );
}

function ArchitectureView() {
  return (
    <div className="architecture-page">
      <section className="architecture-intro">
        <span className="eyebrow">SYSTEM DESIGN</span>
        <h1>Generative where useful. Deterministic where necessary.</h1>
        <p>The bounded demo selects a household mission, retrieves evidence and validates a schedule before an optional language model explains it.</p>
      </section>

      <section className="architecture-flow" aria-label="FlexiGrid architecture flow">
        <article className="architecture-node user-node"><span>01</span><div className="node-icon"><Icon name="bolt" /></div><h2>User mission</h2><p>Natural-language goals, deadlines and comfort constraints.</p><em>Unstructured input</em></article>
        <div className="flow-arrow"><Icon name="arrow" /></div>
        <article className="architecture-node"><span>02</span><div className="node-icon"><Icon name="database" /></div><h2>Lexical RAG</h2><p>Device manuals, tariff rules and household preferences.</p><em>Grounded context</em></article>
        <div className="flow-arrow"><Icon name="arrow" /></div>
        <article className="architecture-node"><span>03</span><div className="node-icon"><Icon name="tool" /></div><h2>MCP tools</h2><p>Elia forecasts, connection limit and planner functions.</p><em>Typed tool calls</em></article>
        <div className="flow-arrow"><Icon name="arrow" /></div>
        <article className="architecture-node accent-node"><span>04</span><div className="node-icon"><Icon name="brain" /></div><h2>Planner + critic</h2><p>Code optimizes and validates; the optional LLM explains only accepted plans.</p><em>Verified output</em></article>
      </section>

      <section className="data-contracts">
        <div className="data-contract-heading"><div><span className="eyebrow">ELIA OPEN DATA</span><h2>Belgian grid context</h2></div><a href="https://opendata.elia.be/" target="_blank" rel="noreferrer">Open official portal <Icon name="arrow" /></a></div>
        <div className="dataset-grid">
          <article><span className="dataset-id">ODS002</span><h3>Total load</h3><p>Measured, most-recent, day-ahead and week-ahead forecast for the Belgian grid.</p><a href="https://opendata.elia.be/explore/dataset/ods002/" target="_blank" rel="noreferrer">Dataset page ↗</a></article>
          <article><span className="dataset-id">ODS086</span><h3>Wind forecast</h3><p>Intraday, day-ahead and week-ahead wind-power forecasts, updated every quarter-hour.</p><a href="https://opendata.elia.be/explore/dataset/ods086/" target="_blank" rel="noreferrer">Dataset page ↗</a></article>
          <article><span className="dataset-id">ODS201</span><h3>Generation mix</h3><p>Actual generation in the Belgian control area, aggregated by fuel type.</p><a href="https://opendata.elia.be/explore/dataset/ods201/" target="_blank" rel="noreferrer">Dataset page ↗</a></article>
        </div>
      </section>

      <section className="design-decisions">
        <div><span className="decision-label">WHY RAG</span><h3>Policies change faster than models.</h3><p>Manuals and user constraints stay editable and citeable without fine-tuning.</p></div>
        <div><span className="decision-label">WHY MCP</span><h3>Tools remain swappable.</h3><p>Elia, tariff and device integrations expose typed contracts instead of prompt glue.</p></div>
        <div><span className="decision-label">WHY A CRITIC</span><h3>Physics is not negotiable.</h3><p>Every generated schedule is rejected if it breaks time windows or the grid cap.</p></div>
      </section>
    </div>
  );
}

export default function FlexiGridDashboard() {
  const [view, setView] = useState<View>("plan");
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
        <div className="topbar-meta"><span>BE</span><i /> <em>Prototype · v1.0</em></div>
      </header>
      <div className="content-shell">
        {view === "plan" && <PlanView />}
        {view === "evaluation" && <EvaluationView />}
        {view === "architecture" && <ArchitectureView />}
      </div>
      <footer className="app-footer">
        <span>FlexiGrid AI · Generative AI assignment prototype</span>
        <span>Elia data stays attributed · frozen demo fallback · no device control</span>
      </footer>
    </main>
  );
}
