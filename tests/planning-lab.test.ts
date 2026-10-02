import assert from "node:assert/strict";
import test from "node:test";
import { apiErrorText, elapsedLabel, sampleProblem } from "../lib/planning-lab.ts";

test("sample inputs are aligned 15-minute vectors", () => {
  const p = sampleProblem();
  assert.equal(p.slot_minutes, 15);
  for (const values of [p.tariff_eur_per_kwh, p.stress, p.background_kw, p.reserve_kw]) assert.equal(values?.length, 96);
  assert.equal(new Set(p.jobs.map(j => j.task_id)).size, p.jobs.length);
  assert(p.jobs.every(j => j.latest_end - j.earliest_start >= j.power_kw.length));
});
test("capacity reserve and objective controls affect the actual request", () => {
  const p = sampleProblem(6, 1, 0.8, "grid");
  assert.equal(p.max_load_kw, 6); assert.equal(p.background_kw?.[0], 1);
  assert.equal(p.reserve_kw?.[0], 0.8); assert.equal(p.objective, "grid");
});
test("power profiles preserve quarter-hour energy units", () => {
  const ev = sampleProblem().jobs[0];
  assert(Math.abs(ev.power_kw.reduce((a,b) => a + b, 0) * 0.25 - 7.2) < 1e-9);
});
test("time formatting is elapsed time and supports longer horizons", () => {
  assert.equal(elapsedLabel(27, 15), "06:45");
  assert.equal(elapsedLabel(100, 15), "25:00");
});
test("typed API validation failures remain readable", () => {
  assert.equal(apiErrorText({ detail: "infeasible" }), "infeasible");
  assert.match(apiErrorText({ detail: [{ loc: ["body", "jobs"], msg: "invalid" }] }), /body.jobs: invalid/);
});
