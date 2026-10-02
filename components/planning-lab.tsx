"use client";

import { useState } from "react";
import { apiBase } from "@/lib/api";
import { apiErrorText, elapsedLabel, sampleProblem, type PlanningProblem, type PlanningResult } from "@/lib/planning-lab";

async function post<T>(route: string, payload: unknown): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20_000);
  try {
    const response = await fetch(`${apiBase()}${route}`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify(payload), signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(apiErrorText(result));
    return result as T;
  } finally { clearTimeout(timer); }
}
function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function LoadChart({ result, problem }: { result: PlanningResult; problem: PlanningProblem }) {
  const values = result.validation;
  const max = Math.max(problem.max_load_kw, values.peak_load_kw, 1) * 1.15;
  const n = values.flexible_load_kw.length;
  const points = (row: number[]) => row.map((v, i) => `${50 + i / Math.max(n - 1, 1) * 840},${240 - v / max * 205}`).join(" ");
  const capY = 240 - problem.max_load_kw / max * 205;
  return <div className="lab-chart">
    <svg viewBox="0 0 920 290" role="img" aria-label="Flexible load, forecast total and reserved total compared with the capacity cap in kilowatts">
      {[0, 0.25, 0.5, 0.75, 1].map(f => <g key={f}><line x1="50" x2="890" y1={240 - f * 205} y2={240 - f * 205} className="lab-grid" /><text x="42" y={244 - f * 205} textAnchor="end">{(f * max).toFixed(1)}</text></g>)}
      <text x="15" y="20">kW</text>
      <polyline points={points(values.flexible_load_kw)} className="lab-flex-line" />
      <polyline points={points(values.forecast_total_load_kw)} className="lab-total-line" />
      <polyline points={points(values.reserved_total_load_kw)} className="lab-reserve-line" />
      <line x1="50" x2="890" y1={capY} y2={capY} className="lab-cap-line" />
      {[0, 0.25, 0.5, 0.75, 1].map(f => <text key={f} x={50 + f * 840} y="263" textAnchor="middle">{elapsedLabel(Math.round(f * (n - 1)), problem.slot_minutes)}</text>)}
      <text x="465" y="286" textAnchor="middle">Elapsed time from horizon start</text>
    </svg>
    <div className="lab-legend"><span>Flexible load</span><span>Forecast total</span><span>Forecast + reserve</span><span>Capacity cap</span></div>
  </div>;
}
export default function PlanningLab() {
  const [cap, setCap] = useState(4.6);
  const [background, setBackground] = useState(0.45);
  const [reserve, setReserve] = useState(0.3);
  const [objective, setObjective] = useState<PlanningProblem["objective"]>("cost");
  const [input, setInput] = useState(() => JSON.stringify(sampleProblem(), null, 2));
  const [solved, setSolved] = useState<{ problem: PlanningProblem; result: PlanningResult } | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("Synthetic inputs. No real household or tariff data is preloaded.");
  const [busy, setBusy] = useState(false);

  function edit(text: string) { setInput(text); setSolved(null); setError(""); }
  async function run() {
    setBusy(true); setError(""); setSolved(null);
    try {
      const problem = JSON.parse(input) as PlanningProblem;
      const result = await post<PlanningResult>("/api/planning/solve", problem);
      setSolved({ problem, result });
    } catch (e) { setError(e instanceof Error ? e.message : "Planning failed. Start the Python backend and try again."); }
    finally { setBusy(false); }
  }
  async function load(file: File | undefined, calibration: boolean) {
    if (!file) return;
    setError("");
    if (file.size > 5_000_000) { setError("Use a JSON file smaller than 5 MB."); return; }
    setBusy(true);
    try {
      const payload = JSON.parse(await file.text());
      if (calibration) {
        const result = await post<{ reserve_kw: number[]; alpha: number; calibration_blocks: number; warning: string }>("/api/planning/calibrate", payload);
        const current = JSON.parse(input) as PlanningProblem;
        if (result.reserve_kw.length !== current.tariff_eur_per_kwh.length) throw new Error("Calibration horizon does not match the planning horizon.");
        edit(JSON.stringify({ ...current, reserve_kw: result.reserve_kw }, null, 2));
        setNotice(`Calibrated from ${result.calibration_blocks} blocks at alpha=${result.alpha}. ${result.warning}`);
      } else { edit(JSON.stringify(payload, null, 2)); setNotice("User-supplied inputs. Verify timestamps, units and provenance before solving."); }
    } catch (e) { setError(e instanceof Error ? e.message : "Invalid JSON input."); }
    finally { setBusy(false); }
  }
  return <div className="planning-lab">
    <section className="lab-hero">
      <span className="eyebrow">RESEARCH WORKBENCH</span>
      <h1>Plan with headroom. Inspect the checks.</h1>
      <p>15-minute mixed-integer scheduling with appliance power profiles, background consumption and an explicit reserve for forecast error. Every result is checked against the original input.</p>
      <div className="lab-badges"><span>Real backend solver</span><span>No simulated results</span><span>Advisory only</span></div>
    </section>
    <div className="lab-layout">
      <section className="lab-panel">
        <h2>1. Define the problem</h2>
        <p className="lab-muted">These sample controls replace the JSON when you select Load sample. Edit the JSON for custom jobs, hard avoid slots or fixed starts.</p>
        <fieldset disabled={busy} className="lab-controls">
          <label>Capacity cap (kW)<input type="number" min="0.1" max="1000" step="0.1" value={cap} onChange={e => setCap(Number(e.target.value))} /></label>
          <label>Background (kW)<input type="number" min="0" max="1000" step="0.05" value={background} onChange={e => setBackground(Number(e.target.value))} /></label>
          <label>Reserve (kW)<input type="number" min="0" max="1000" step="0.05" value={reserve} onChange={e => setReserve(Number(e.target.value))} /></label>
          <label>Objective<select value={objective} onChange={e => setObjective(e.target.value as PlanningProblem["objective"])}><option value="cost">Electricity cost</option><option value="grid">Grid-stress exposure</option><option value="balanced">Balanced</option></select></label>
          <button type="button" onClick={() => { edit(JSON.stringify(sampleProblem(cap, background, reserve, objective), null, 2)); setNotice("Synthetic sample loaded. Manual reserve is not statistically calibrated."); }}>Load sample</button>
          <label className="lab-upload">Import problem JSON<input type="file" accept=".json,application/json" onChange={e => void load(e.target.files?.[0], false)} /></label>
          <label className="lab-upload">Import calibration JSON<input type="file" accept=".json,application/json" onChange={e => void load(e.target.files?.[0], true)} /></label>
        </fieldset>
        <label className="lab-json-label" htmlFor="planning-json">Planning request</label>
        <textarea id="planning-json" spellCheck={false} disabled={busy} value={input} onChange={e => edit(e.target.value)} />
        <p className="lab-muted">Calibration JSON: forecasts_kw and actuals_kw are matching lists of held-out horizon blocks; alpha is the error level. Forecasts must not use the matching outcomes.</p>
        <button className="lab-primary" disabled={busy} onClick={() => void run()}>{busy ? "Computing…" : "Solve and validate"}</button>
      </section>
      <section className="lab-panel lab-results" aria-live="polite">
        <h2>2. Inspect the result</h2>
        <p className="lab-notice">{notice}</p>
        {error && <div className="lab-error" role="alert">{error}<p>No replacement schedule was generated. Check the input and backend connection.</p></div>}
        {!solved && !error && <div className="lab-empty"><h3>No computed result yet</h3><p>The request is sent to your Python backend. Ollama is not needed for this numerical workbench.</p><code>uvicorn flexigrid.api:app --port 8000</code></div>}
        {solved && <>
          <div className="lab-status"><strong>{solved.result.solver.status === "optimal" ? "Optimal within solver tolerances" : "Feasible incumbent, not proven optimal"}</strong><span>{solved.result.solver.backend}</span></div>
          <div className="lab-kpis">
            <div><span>Flexible cost</span><strong>€{solved.result.validation.flexible_cost_eur.toFixed(3)}</strong></div>
            <div><span>Reserved peak</span><strong>{solved.result.validation.peak_load_kw.toFixed(2)} kW</strong></div>
            <div><span>Flexible energy</span><strong>{solved.result.validation.flexible_energy_kwh.toFixed(2)} kWh</strong></div>
            <div><span>Relative solver gap</span><strong>{solved.result.solver.mip_gap == null ? "Unavailable" : `${(100 * solved.result.solver.mip_gap).toFixed(4)}%`}</strong></div>
          </div>
          <LoadChart problem={solved.problem} result={solved.result} />
          <div className="lab-table"><table><thead><tr><th>Task</th><th>Start</th><th>End</th><th>Energy (kWh)</th></tr></thead><tbody>{solved.problem.jobs.map(job => {
            const start = solved.result.starts[job.task_id];
            return <tr key={job.task_id}><td>{job.task_id}</td><td>{elapsedLabel(start, solved.problem.slot_minutes)}</td><td>{elapsedLabel(start + job.power_kw.length, solved.problem.slot_minutes)}</td><td>{(job.power_kw.reduce((a, b) => a + b, 0) * solved.problem.slot_minutes / 60).toFixed(2)}</td></tr>;
          })}</tbody></table></div>
          <p className="lab-muted">Input SHA-256 <code className="lab-hash">{solved.result.problem_sha256}</code></p>
          <button onClick={() => download("flexigrid-verified-plan.json", solved)}>Export request + result</button>
        </>}
        <div className="lab-limits"><h3>What the check does not prove</h3><p>Slot-average capacity is not an electrical safety guarantee. Heat-pump temperature, EV state of charge, carbon savings and real billing are not modelled. The reserve requires valid calibration assumptions. Inputs use elapsed-time slots; align dates and timezones before import.</p></div>
      </section>
    </div>
  </div>;
}
