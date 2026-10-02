"""FlexiGrid evaluation harness.

Measures each subsystem separately, so a fluent model answer can never hide a
retrieval or planning failure:

1. Retrieval  — 40 labelled queries; hit@1, recall@4, MRR for BM25, dense,
                and hybrid modes (retrieval ablation).
2. Intent     — 15 labelled missions; device/deadline/objective/cap accuracy
                for the LLM extractor and the rule-based ablation.
3. Baseline B — LLM-only scheduling (no optimizer): constraint-violation
                rate, the number that justifies the hybrid architecture.
4. Ablation   — greedy vs joint constrained search, including the tight-
                window case class where greedy fails outright.
5. Citations  — explanation citation ID validity against the retrieved
                allow-list, plus how often the guard had to reject.
6. Determinism— identical inputs must give identical plans.

Results go to ``evaluation/results.json`` (machine-readable; the report
builder consumes this) and ``evaluation/RESULTS.md`` (human-readable). Every
result records which LLM and embedding backend produced it, so numbers are
never quoted out of context.

Run:  cd backend && python -m flexigrid.evaluate [--skip-llm] [--runs 3]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from . import core
from .agent import run_agent
from .elia_client import EliaClient
from .intent import extract_intent, rule_based_spec, sanitize, spec_to_tasks
from .llm import LocalLLM, get_llm
from .models import MissionSpec
from .retrieval import get_index

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUT_DIR = Path(__file__).resolve().parent.parent / "evaluation"


# --------------------------------------------------------------------------
# 1. Retrieval
# --------------------------------------------------------------------------

def evaluate_retrieval() -> dict:
    queries = [json.loads(line) for line in
               (DATA_DIR / "eval_queries.jsonl").read_text().splitlines() if line]
    index = get_index()
    results: dict[str, dict] = {}
    for mode in ("bm25", "dense", "hybrid"):
        hits_at_1 = 0
        recalls: list[float] = []
        reciprocal_ranks: list[float] = []
        for item in queries:
            relevant = set(item["relevant_docs"])
            retrieved = index.retrieve(item["query"], top_k=4, mode=mode)
            docs = [chunk["doc_id"] for chunk in retrieved]
            if docs and docs[0] in relevant:
                hits_at_1 += 1
            found = relevant & set(docs)
            recalls.append(len(found) / len(relevant))
            rank = next((position + 1 for position, doc in enumerate(docs)
                         if doc in relevant), None)
            reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        results[mode] = {
            "queries": len(queries),
            "hit_at_1": round(hits_at_1 / len(queries), 3),
            "recall_at_4": round(statistics.mean(recalls), 3),
            "mrr": round(statistics.mean(reciprocal_ranks), 3),
        }
    results["backend"] = {"name": index.backend.name, "model": index.backend.model}
    return results


# --------------------------------------------------------------------------
# 2. Intent extraction
# --------------------------------------------------------------------------

def _score_spec(spec: MissionSpec, gold: dict) -> dict[str, bool]:
    devices = sorted(task.task_id for task in spec.tasks)
    deadline = max(task.latest_end for task in spec.tasks)
    return {
        "devices": devices == sorted(gold["devices"]),
        "deadline": deadline == gold["deadline"],
        "objective": spec.objective == gold["objective"],
        "max_load_kw": abs(spec.max_load_kw - gold["max_load_kw"]) < 1e-6,
        "avoid_hours": sorted(spec.avoid_hours) == sorted(gold["avoid_hours"]),
    }


def evaluate_intent(llm: LocalLLM | None, use_llm: bool) -> dict:
    missions = [json.loads(line) for line in
                (DATA_DIR / "eval_missions.jsonl").read_text().splitlines() if line]
    modes: dict[str, dict] = {}

    def run(mode_name: str, extractor) -> None:
        field_scores: dict[str, int] = {}
        exact = 0
        failures: list[str] = []
        for gold in missions:
            try:
                spec = extractor(gold["mission"])
            except Exception as error:  # noqa: BLE001
                failures.append(f"{gold['mission'][:40]}…: {error}")
                continue
            scores = _score_spec(spec, gold)
            for key, value in scores.items():
                field_scores[key] = field_scores.get(key, 0) + int(value)
            exact += int(all(scores.values()))
        n = len(missions)
        modes[mode_name] = {
            "missions": n,
            "exact_match": round(exact / n, 3),
            "per_field": {key: round(value / n, 3)
                          for key, value in field_scores.items()},
            "failures": failures,
        }

    run("rules", lambda mission: sanitize(rule_based_spec(mission))[0])
    if use_llm and llm is not None and llm.available():
        def llm_extractor(mission: str) -> MissionSpec:
            result = extract_intent(mission, llm=llm, use_llm=True)
            if result.mode != "llm":
                raise RuntimeError("LLM extraction fell back to rules")
            return result.spec
        run("llm", llm_extractor)
    return modes


# --------------------------------------------------------------------------
# 3. Baseline B — LLM-only scheduling (no optimizer, no critic)
# --------------------------------------------------------------------------

class _Assignment(BaseModel):
    task_id: str
    start: int = Field(ge=0, le=23)


class _ScheduleProposal(BaseModel):
    assignments: list[_Assignment] = Field(min_length=1, max_length=6)


_BASELINE_SYSTEM = (
    "You schedule household appliances directly. Given tasks with power, "
    "duration, and allowed windows, plus a 24-hour tariff, choose a start "
    "hour for every task. Respect each task's window and keep the combined "
    "load of overlapping tasks at or below the capacity limit."
)


def evaluate_llm_only_baseline(llm: LocalLLM | None, use_llm: bool,
                               runs_per_scenario: int = 3) -> dict:
    if not (use_llm and llm is not None and llm.available()):
        return {"skipped": "requires the local model — run this harness on the "
                           "demo machine with Ollama serving; results are "
                           "stamped with that machine's model"}
    tariff, stress, _ = EliaClient().series(use_live=False)
    scenarios = {
        "morning": "Charge the EV, run laundry and dishwasher before 07:00. "
                   "Preheat the home by 06:30.",
        "grid-friendly": "Finish the EV charge, laundry and dishwasher "
                         "between 08:00 and 16:00.",
        "peak-avoidance": "Charge the EV and run the dishwasher after 14:00 "
                          "but before 23:00, avoid 17:00 to 20:00.",
    }
    total = 0
    valid_count = 0
    schema_failures = 0
    cost_gaps: list[float] = []
    for name, mission in scenarios.items():
        spec, _ = sanitize(rule_based_spec(mission))
        tasks = spec_to_tasks(spec)
        optimal = core.optimize(tasks, spec.objective, spec.max_load_kw,
                                tariff=tariff, stress=stress,
                                avoid_hours=spec.avoid_hours)
        optimal_cost = sum(task.cost_eur for task in optimal)
        task_block = "\n".join(
            f"- {task.task_id}: {task.power_kw} kW for {task.duration_hours} h, "
            f"window [{task.earliest_start}, {task.latest_end})"
            for task in tasks)
        user = (f"Tasks:\n{task_block}\n\nHourly tariff (EUR/kWh, hour 0-23): "
                f"{tariff}\nCapacity limit: {spec.max_load_kw} kW combined.\n"
                f"Assign a start hour to every task.")
        for _ in range(runs_per_scenario):
            total += 1
            proposal, _notes = llm.structured(_ScheduleProposal,
                                              _BASELINE_SYSTEM, user,
                                              max_tokens=300)
            if proposal is None:
                schema_failures += 1
                continue
            starts = {item.task_id: item.start for item in proposal.assignments}
            if (len(proposal.assignments) != len(tasks)
                    or set(starts) != {task.task_id for task in tasks}):
                schema_failures += 1
                continue
            scheduled = []
            for task in tasks:
                start = starts[task.task_id]
                end = start + task.duration_hours
                if end > 24:
                    break
                cost = sum(task.power_kw * tariff[hour]
                           for hour in range(start, end))
                scheduled.append(core.ScheduledTask(
                    **{**task.__dict__}, start=start, end=end,
                    cost_eur=round(cost, 2), grid_stress=0))
            else:
                verdict = core.validate(scheduled, spec.max_load_kw,
                                        spec.avoid_hours, expected_tasks=tasks)
                if verdict["valid"]:
                    valid_count += 1
                    llm_cost = sum(task.cost_eur for task in scheduled)
                    cost_gaps.append(llm_cost - optimal_cost)
                continue
            schema_failures += 1
    return {
        "model": llm.config.model,
        "attempts": total,
        "constraint_valid_rate": round(valid_count / total, 3) if total else None,
        "violation_or_failure_rate": round(1 - valid_count / total, 3) if total else None,
        "schema_failures": schema_failures,
        "avg_cost_gap_eur_when_valid":
            round(statistics.mean(cost_gaps), 2) if cost_gaps else None,
    }


# --------------------------------------------------------------------------
# 4. Ablation — greedy vs joint search
# --------------------------------------------------------------------------

def evaluate_greedy_ablation() -> dict:
    tariff, stress, _ = EliaClient().series(use_live=False)
    cases = []
    for mission, label in [
        ("Charge the EV, run laundry and dishwasher before 07:00. Preheat the "
         "home by 06:30.", "morning"),
        ("Finish the EV charge, laundry and dishwasher between 08:00 and "
         "16:00, support the grid.", "grid-friendly"),
        ("Charge the EV and run the dishwasher after 14:00 but before 23:00, "
         "avoid 17:00 to 20:00, cheapest.", "peak-avoidance"),
    ]:
        spec, _ = sanitize(rule_based_spec(mission))
        cases.append((label, spec_to_tasks(spec), spec))
    # The failure-class case: two high-power tasks squeezed into overlapping
    # tight windows. Greedy places the EV at its locally best hour and strands
    # the heat pump; joint search finds the only global arrangement.
    tight = [
        core.Task("ev", "EV charge · eco mode", 3.6, 2, 0, 4, "manual-ev#1"),
        core.Task("heat", "Heat-pump preheat", 1.4, 2, 2, 4, "manual-heatpump#0"),
    ]
    rows = []
    greedy_failures = 0
    for label, tasks, spec in cases:
        joint = core.optimize(tasks, spec.objective, spec.max_load_kw,
                              tariff=tariff, stress=stress,
                              avoid_hours=spec.avoid_hours)
        joint_cost = round(sum(task.cost_eur for task in joint), 2)
        try:
            greedy = core.greedy_optimize(tasks, spec.objective,
                                          spec.max_load_kw, tariff=tariff,
                                          stress=stress)
            greedy_cost = round(sum(task.cost_eur for task in greedy), 2)
            greedy_valid = core.validate(greedy, spec.max_load_kw)["valid"]
        except core.InfeasibleMission:
            greedy_cost, greedy_valid = None, False
            greedy_failures += 1
        rows.append({"case": label, "joint_cost_eur": joint_cost,
                     "greedy_cost_eur": greedy_cost,
                     "greedy_valid": greedy_valid})
    for objective in ("cost", "balanced"):
        joint = core.optimize(tight, objective, 4.6, tariff=tariff, stress=stress)
        joint_cost = round(sum(task.cost_eur for task in joint), 2)
        try:
            greedy = core.greedy_optimize(tight, objective, 4.6,
                                          tariff=tariff, stress=stress)
            greedy_cost = round(sum(task.cost_eur for task in greedy), 2)
            greedy_valid = True
        except core.InfeasibleMission:
            greedy_cost, greedy_valid = None, False
            greedy_failures += 1
        rows.append({"case": f"tight-window ({objective})",
                     "joint_cost_eur": joint_cost,
                     "greedy_cost_eur": greedy_cost,
                     "greedy_valid": greedy_valid})
    return {"cases": rows, "greedy_failures": greedy_failures,
            "joint_failures": 0}


# --------------------------------------------------------------------------
# 5 + 6. Citations and determinism (via the full agent)
# --------------------------------------------------------------------------

async def evaluate_agent_properties(use_llm: bool) -> dict:
    missions = [
        "Charge the EV, run laundry and dishwasher before 07:00. Preheat the "
        "home by 06:30. Keep controllable load below 4.6 kW.",
        "Finish the EV charge, laundry and dishwasher between 08:00 and "
        "16:00 and support the grid.",
        "Charge the EV and run the dishwasher after 14:00 but before 23:00, "
        "avoid the 17:00 to 20:00 peak.",
    ]
    citation_precisions: list[float] = []
    rejections = 0
    runs = []
    for mission in missions:
        result = await run_agent(mission, use_llm=use_llm)
        allowed = {chunk["chunk_id"] for chunk in result["evidence"]}
        cited = result["explanation"]["citation_ids"]
        inside = sum(1 for citation in cited if citation in allowed)
        citation_precisions.append(inside / len(cited) if cited else 0.0)
        rejections += sum("rejected" in note
                          for note in result["modes"]["decision_notes"])
        runs.append(result)
    first = await run_agent(missions[0], use_llm=False)
    second = await run_agent(missions[0], use_llm=False)
    deterministic = first["plan"] == second["plan"]
    return {
        "citation_precision": round(statistics.mean(citation_precisions), 3),
        "citation_id_validity": round(statistics.mean(citation_precisions), 3),
        "citation_metric_note": "ID allow-list membership only; semantic support is not measured",
        "explanations_rejected_by_guard": rejections,
        "deterministic_plan_replay": deterministic,
        "agent_runs": len(runs),
        "all_plans_valid": all(run["plan"]["validation"]["valid"] for run in runs),
        "explanation_modes": [run["modes"]["explanation"] for run in runs],
    }


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def render_markdown(results: dict) -> str:
    environment = results["environment"]
    lines = [
        "# FlexiGrid evaluation results",
        "",
        f"Generated {environment['generated_at']} · "
        f"LLM: **{environment['llm_model'] or 'none (deterministic fallback)'}** · "
        f"embeddings: **{environment['embeddings_backend']}"
        f" ({environment['embeddings_model']})** · corpus "
        f"{environment['corpus_chunks']} chunks.",
        "",
        "Numbers below are produced by `python -m flexigrid.evaluate` on the "
        "machine named above; re-run it after changing models to refresh "
        "every table.",
        "",
        f"## 1. Retrieval ({results['retrieval']['bm25']['queries']} labelled "
        f"queries, doc-level relevance)",
        "",
        "| Mode | hit@1 | recall@4 | MRR |",
        "| --- | ---: | ---: | ---: |",
    ]
    retrieval = results["retrieval"]
    for mode in ("bm25", "dense", "hybrid"):
        row = retrieval[mode]
        lines.append(f"| {mode} | {row['hit_at_1']:.3f} | "
                     f"{row['recall_at_4']:.3f} | {row['mrr']:.3f} |")
    lines += ["", "## 2. Intent extraction (15 labelled missions)", "",
              "| Extractor | exact match | devices | deadline | objective | cap | avoid |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for mode, row in results["intent"].items():
        fields = row["per_field"]
        lines.append(
            f"| {mode} | {row['exact_match']:.3f} | {fields.get('devices', 0):.3f} | "
            f"{fields.get('deadline', 0):.3f} | {fields.get('objective', 0):.3f} | "
            f"{fields.get('max_load_kw', 0):.3f} | {fields.get('avoid_hours', 0):.3f} |")
    if "llm" not in results["intent"]:
        lines.append("")
        lines.append("_The LLM extractor row is added when the harness runs "
                     "with the local model available._")
    baseline = results["llm_only_baseline"]
    lines += ["", "## 3. Baseline B — LLM-only scheduling (no optimizer)", ""]
    if "skipped" in baseline:
        lines.append(f"_Skipped: {baseline['skipped']}._")
    else:
        lines += [
            f"Model: {baseline['model']}, {baseline['attempts']} attempts.",
            "",
            f"- Constraint-valid rate: **{baseline['constraint_valid_rate']}**",
            f"- Violation/failure rate: **{baseline['violation_or_failure_rate']}**",
            f"- Schema failures: {baseline['schema_failures']}",
            f"- Avg cost gap vs optimizer when valid: "
            f"{baseline['avg_cost_gap_eur_when_valid']} €",
        ]
    lines += ["", "## 4. Ablation — greedy vs joint constrained search", "",
              "| Case | joint cost € | greedy cost € | greedy valid |",
              "| --- | ---: | ---: | :-: |"]
    for row in results["greedy_ablation"]["cases"]:
        greedy_cost = row["greedy_cost_eur"]
        lines.append(f"| {row['case']} | {row['joint_cost_eur']} | "
                     f"{greedy_cost if greedy_cost is not None else '—'} | "
                     f"{'✓' if row['greedy_valid'] else '✗ infeasible'} |")
    lines.append(f"\nGreedy failed outright on "
                 f"{results['greedy_ablation']['greedy_failures']} case(s); "
                 f"joint search failed on 0.")
    agent = results["agent_properties"]
    lines += ["", "## 5. Agent properties", "",
              f"- Citation ID validity vs retrieved allow-list: "
              f"**{agent['citation_precision']:.3f}**",
              f"- Explanations rejected by the citation guard: "
              f"{agent['explanations_rejected_by_guard']}",
              f"- Deterministic replay (identical plans): "
              f"**{'yes' if agent['deterministic_plan_replay'] else 'NO'}**",
              f"- All {agent['agent_runs']} end-to-end plans valid: "
              f"**{'yes' if agent['all_plans_valid'] else 'NO'}**",
              f"- Explanation modes: {', '.join(agent['explanation_modes'])}",
              ""]
    return "\n".join(lines)


async def main_async(skip_llm: bool, runs: int) -> dict:
    llm = get_llm()
    use_llm = not skip_llm
    llm_live = use_llm and llm.available()
    index = get_index()
    results = {
        "environment": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "llm_model": llm.config.model if llm_live else None,
            "llm_base_url": llm.config.base_url if llm_live else None,
            "embeddings_backend": index.backend.name,
            "embeddings_model": index.backend.model,
            "corpus_chunks": len(index.chunks),
            "corpus_fingerprint": index.fingerprint,
        },
        "retrieval": evaluate_retrieval(),
        "intent": evaluate_intent(llm, llm_live),
        "llm_only_baseline": evaluate_llm_only_baseline(llm, llm_live, runs),
        "greedy_ablation": evaluate_greedy_ablation(),
        "agent_properties": await evaluate_agent_properties(use_llm),
    }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-llm", action="store_true",
                        help="only run deterministic evaluations")
    parser.add_argument("--runs", type=int, default=3,
                        help="LLM-only baseline attempts per scenario")
    parser.add_argument("--out", default=str(OUT_DIR))
    arguments = parser.parse_args()

    results = asyncio.run(main_async(arguments.skip_llm, arguments.runs))
    out_dir = Path(arguments.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2),
                                          encoding="utf-8")
    (out_dir / "RESULTS.md").write_text(render_markdown(results),
                                        encoding="utf-8")
    print(f"Wrote {out_dir / 'results.json'} and {out_dir / 'RESULTS.md'}")
    print(render_markdown(results))


if __name__ == "__main__":
    main()
