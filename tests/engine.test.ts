import assert from "node:assert/strict";
import test from "node:test";

import {
  buildBenchmark,
  createPlan,
  optimizeScenario,
  retrieveEvidence,
  scenarios,
  validateSchedule,
  type Objective,
  type Scenario,
} from "../lib/engine.ts";

test("all scenario-objective combinations satisfy hard constraints", () => {
  const objectives: Objective[] = ["balanced", "cost", "grid"];
  for (const scenario of scenarios) {
    for (const objective of objectives) {
      const plan = createPlan(scenario.id, objective);
      assert.equal(validateSchedule(plan.schedule, scenario).valid, true);
    }
  }
});

test("benchmark contains nine reproducible fixture runs", () => {
  const benchmark = buildBenchmark();
  assert.deepEqual(benchmark, {
    runs: 9,
    constraintPassRate: 100,
    costNonRegressionRate: 100,
    retrievalTopK: 4,
  });
});

test("EV request retrieves the EV manual first", () => {
  assert.equal(retrieveEvidence("charge the EV in eco mode")[0].id, "manual-ev#1");
});

test("constraint metrics only count computed checks", () => {
  const plan = createPlan("morning", "balanced");
  assert.equal(plan.constraintsTotal, 2); // windows + capacity — nothing padded
  assert.equal(plan.constraintsSatisfied, 2);
});

test("savings are signed, never clamped", () => {
  for (const scenario of scenarios) {
    for (const objective of ["balanced", "cost", "grid"] as Objective[]) {
      const plan = createPlan(scenario.id, objective);
      const expected = Math.round((1 - plan.totalCost / plan.baselineCost) * 100);
      assert.equal(plan.savingsPercent, expected);
    }
  }
});

test("planning is deterministic", () => {
  assert.deepEqual(createPlan("morning", "balanced"), createPlan("morning", "balanced"));
});

test("an infeasible mission is rejected instead of displayed", () => {
  const infeasible: Scenario = {
    id: "infeasible",
    label: "Infeasible",
    shortLabel: "Infeasible",
    prompt: "Run two 3.6 kW loads in the same one-hour window.",
    objective: "balanced",
    maxGridLoadKw: 4.6,
    tasks: [
      { id: "a", name: "Load A", icon: "A", powerKw: 3.6, duration: 1, earliestStart: 5, latestEnd: 6, sourceId: "grid-capacity" },
      { id: "b", name: "Load B", icon: "B", powerKw: 3.6, duration: 1, earliestStart: 5, latestEnd: 6, sourceId: "grid-capacity" },
    ],
  };
  assert.throws(() => optimizeScenario(infeasible), /No feasible schedule/);
});
