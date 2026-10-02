"""The FlexiGrid planning agent.

A genuine tool-using loop: at every step the local LLM sees the mission, the
tool catalog, and a compact digest of what has been gathered so far, and
returns a schema-validated :class:`AgentDecision` choosing the next tool (or
``finish``). Tool execution is delegated to an executor — in-process by
default, or a live MCP client session (``mcp_host.py``) so the same agent can
run over the Model Context Protocol.

Guardrails, because a 3B model occasionally goes off-script and physics is
not negotiable:

- Malformed or unavailable decisions fall back to the canonical pipeline
  order; such steps are labelled ``decided_by: guardrail`` in the trace, so
  the demo never hides them.
- The loop is bounded (``MAX_STEPS``); repeated tool calls are redirected.
- Whatever the model decides, the plan is (re)optimized and (re)validated
  deterministically before anything is displayed, and the explanation may
  cite only retrieved chunk IDs.
"""

from __future__ import annotations

import json
import time

from .intent import spec_to_tasks
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from .llm import LocalLLM, get_llm
from .models import (AgentDecision, Explanation, MissionSpec, Objective,
                     ToolCallRecord)
from . import tools as toolbox

MAX_STEPS = 8

_CANONICAL_ORDER = ["extract_constraints", "get_grid_snapshot",
                    "retrieve_evidence", "optimize_schedule",
                    "validate_schedule", "finish"]

_AGENT_SYSTEM = (
    "You are the planning agent of FlexiGrid, a Belgian household energy "
    "assistant. You work in steps. At each step choose exactly one tool from "
    "the catalog (or 'finish' once a validated schedule exists). Typical "
    "order: extract_constraints first, then get_grid_snapshot, then "
    "retrieve_evidence with a query about the mission's devices and rules, "
    "then optimize_schedule, then validate_schedule, then finish. Do not "
    "repeat a tool that already succeeded. Keep 'thought' to one sentence."
)

_EXPLAIN_SYSTEM = (
    "You explain an already-validated household energy schedule. Never change "
    "task times and never invent numbers. Every factual claim must be "
    "supported by one of the allowed citation ids. Mention that the grid "
    "signal derives from Elia forecasts and that the retail tariff is a "
    "separate input. If 'validator_flags' is non-empty, state those flags "
    "plainly in the summary — never describe a flagged plan as fully clean. "
    "Write for a non-expert resident."
)


class ToolExecutor(Protocol):
    transport: str

    async def call(self, tool: str, args: dict[str, Any]) -> Any: ...


class DirectExecutor:
    """Runs registry functions in-process."""

    transport = "direct"

    async def call(self, tool: str, args: dict[str, Any]) -> Any:
        function = toolbox.TOOL_FUNCTIONS[tool]
        return function(**args)


@dataclass
class AgentState:
    mission: str
    objective: Objective | None = None
    retrieval_mode: str = "hybrid"
    spec: dict[str, Any] | None = None
    intent_mode: str | None = None
    intent_adjustments: list[str] = field(default_factory=list)
    snapshot_mode: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    plan: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    done: set[str] = field(default_factory=set)
    retrieve_calls: int = 0

    def digest(self) -> str:
        """Compact state summary shown to the model each step."""
        lines = [f"mission: {self.mission}"]
        if self.objective:
            lines.append(f"requested objective: {self.objective}")
        lines.append(f"constraints extracted: {'yes' if self.spec else 'no'}")
        if self.spec:
            lines.append("  tasks: " + ", ".join(
                f"{t['task_id']}({t['power_kw']}kW {t['duration_hours']}h "
                f"[{t['earliest_start']},{t['latest_end']}))"
                for t in self.spec["tasks"]))
        lines.append(f"grid snapshot loaded: {'yes (' + str(self.snapshot_mode) + ')' if self.snapshot_mode else 'no'}")
        lines.append(f"evidence chunks: {len(self.evidence)}")
        if self.plan:
            lines.append(
                f"plan: computed, cost €{self.plan.get('total_cost_eur')}, "
                f"peak {self.plan.get('peak_load_kw')} kW")
        lines.append(f"validated: {'yes, valid' if self.validation and self.validation.get('valid') else ('yes, INVALID' if self.validation else 'no')}")
        return "\n".join(lines)


def _summarize(tool: str, result: Any) -> str:
    if tool == "get_grid_snapshot":
        return f"mode={result.get('mode', 'unknown')}"
    if tool == "retrieve_evidence":
        ids = [item["chunk_id"] for item in result][:4]
        return f"{len(result)} chunks: {', '.join(ids)}"
    if tool == "extract_constraints":
        tasks = result.get("spec", {}).get("tasks", [])
        return (f"{len(tasks)} tasks via {result.get('mode')} "
                f"({len(result.get('adjustments', []))} adjustments)")
    if tool == "optimize_schedule":
        return (f"cost €{result.get('total_cost_eur')}, "
                f"peak {result.get('peak_load_kw')} kW, "
                f"valid={result.get('validation', {}).get('valid')}")
    if tool == "validate_schedule":
        return (f"valid={result.get('valid')} "
                f"(windows={result.get('within_windows')}, "
                f"capacity={result.get('below_capacity')})")
    return "ok"


def _default_args(tool: str, state: AgentState) -> dict[str, Any]:
    if tool == "extract_constraints":
        return {"mission": state.mission}
    if tool == "retrieve_evidence":
        return {"query": state.mission, "top_k": 4, "mode": state.retrieval_mode}
    if tool == "optimize_schedule":
        return {"spec": state.spec,
                "objective": state.objective or (state.spec or {}).get("objective", "balanced")}
    if tool == "validate_schedule":
        plan = state.plan or {}
        spec = state.spec or {}
        return {"schedule": plan.get("schedule", []),
                "max_load_kw": spec.get("max_load_kw", 4.6),
                "avoid_hours": spec.get("avoid_hours", [])}
    return {}


def _safe_args(decision: AgentDecision, state: AgentState, use_llm: bool) -> dict[str, Any]:
    """The model may refine retrieval, but cannot grant itself authority."""
    args = _default_args(decision.tool, state)
    if decision.tool == "extract_constraints":
        args["use_llm"] = use_llm
    if decision.tool == "retrieve_evidence":
        query = decision.args.get("query")
        if isinstance(query, str) and query.strip():
            args["query"] = query[:2000]
        top_k = decision.args.get("top_k")
        if type(top_k) is int:
            args["top_k"] = min(max(top_k, 1), 8)
    return args


def _apply_result(tool: str, result: Any, state: AgentState) -> None:
    if tool == "extract_constraints":
        state.spec = result.get("spec")
        state.intent_mode = result.get("mode")
        state.intent_adjustments = list(result.get("adjustments", []))
    elif tool == "get_grid_snapshot":
        state.snapshot_mode = result.get("mode", "unknown")
    elif tool == "retrieve_evidence":
        state.evidence = list(result)
        state.retrieve_calls += 1
    elif tool == "optimize_schedule":
        state.plan = result
        state.validation = result.get("validation")
    elif tool == "validate_schedule":
        state.validation = result
    state.done.add(tool)


def _next_canonical(state: AgentState) -> str:
    for tool in _CANONICAL_ORDER:
        if tool == "finish":
            return "finish"
        if tool not in state.done:
            return tool
    return "finish"


def _catalog_text() -> str:
    return "\n".join(f"- {name}: {description}"
                     for name, description in toolbox.TOOL_DESCRIPTIONS.items())


async def _decide(llm: LocalLLM | None, state: AgentState,
                  llm_live: bool) -> tuple[AgentDecision, str, list[str]]:
    """Returns (decision, decided_by, notes)."""
    if llm_live and llm is not None:
        user = (f"Tool catalog:\n{_catalog_text()}\n\n"
                f"Current state:\n{state.digest()}\n\n"
                f"Choose the next tool. Set tool='finish' only when a plan "
                f"exists and validation says valid.")
        decision, notes = llm.structured(AgentDecision, _AGENT_SYSTEM, user,
                                         max_tokens=300)
        if decision is not None:
            # retrieve_evidence may legitimately run twice (different queries);
            # beyond that the model is looping and the pipeline moves on.
            repeated = (decision.tool != "finish" and decision.tool in state.done
                        and (decision.tool != "retrieve_evidence"
                             or state.retrieve_calls >= 2))
            premature = decision.tool == "finish" and not (
                state.plan and state.validation and state.validation.get("valid"))
            index = _CANONICAL_ORDER.index(decision.tool)
            missing = [name for name in _CANONICAL_ORDER[:index] if name not in state.done]
            if not repeated and not premature and not missing:
                return decision, "llm", notes
            if missing:
                notes.append("decision overruled: prerequisites missing: " + ", ".join(missing))
            reason = ("retrieval already ran twice"
                      if decision.tool == "retrieve_evidence"
                      else "repeated a completed tool") if repeated \
                else "finished before a valid plan"
            notes.append(f"decision overruled: {reason}")
        fallback = _next_canonical(state)
        return (AgentDecision(thought=f"guardrail queued the next stage: {fallback}",
                              tool=fallback), "guardrail", notes)
    fallback = _next_canonical(state)
    return (AgentDecision(thought="deterministic pipeline (no LLM reachable)",
                          tool=fallback), "guardrail", [])


def _validator_flags(state: AgentState) -> list[str]:
    """Human-readable names of the checks the validator did not pass."""
    validation = state.validation or {}
    flags = []
    if validation.get("within_windows") is False:
        flags.append("task windows")
    if validation.get("below_capacity") is False:
        flags.append("capacity cap")
    if validation.get("avoid_hours_respected") is False:
        flags.append("avoid-hours preference")
    return flags


def _fallback_explanation(state: AgentState) -> Explanation:
    citations = [item["chunk_id"] for item in state.evidence][:4]
    plan = state.plan or {}
    flags = _validator_flags(state)
    summary = (f"The schedule finishes every task inside its window for "
               f"€{plan.get('total_cost_eur', '?')} with a peak of "
               f"{plan.get('peak_load_kw', '?')} kW, below the "
               f"{(state.spec or {}).get('max_load_kw', 4.6)} kW controllable-load cap.")
    if flags:
        summary += (f" The independent validator flagged: {', '.join(flags)} — "
                    f"honouring every stated constraint left no feasible "
                    f"schedule, so the conflict is reported here instead of "
                    f"being hidden.")
    if not citations:
        summary += " No evidence was retrieved; only computed schedule checks are available."
    return Explanation(
        summary=summary,
        rationale=[
            "A deterministic validator re-checked every task window and each "
            "hour's combined load before this explanation was produced.",
            "Loads are shifted towards hours with a lower derived grid-stress "
            "index, which is computed from Elia load and wind forecasts.",
            "The retail tariff used for cost is a separate labelled input; "
            "Elia grid data never sets the household price.",
        ] if citations else [
            "The numeric schedule passed local duration, window and capacity checks.",
            "No source-supported rationale is available because retrieval returned no evidence.",
        ],
        citation_ids=citations,
        limitation="Advisory demonstration on a labelled data snapshot; the "
                   "planner does not control real devices. Background household load "
                   "is not included in this hourly plan. Temperature targets are "
                   "not verified by a thermal model.",
    )


async def _explain(llm: LocalLLM | None, llm_live: bool,
                   state: AgentState) -> tuple[Explanation, str, list[str]]:
    allowed = [item["chunk_id"] for item in state.evidence]
    if llm_live and llm is not None and allowed:
        evidence_digest = [
            {"chunk_id": item["chunk_id"], "title": item["title"],
             "text": item["text"][:400]}
            for item in state.evidence
        ]
        user = json.dumps({
            "mission": state.mission,
            "verified_plan": {
                "schedule": (state.plan or {}).get("schedule", []),
                "total_cost_eur": (state.plan or {}).get("total_cost_eur"),
                "peak_load_kw": (state.plan or {}).get("peak_load_kw"),
                "objective": (state.plan or {}).get("objective"),
            },
            "validator_flags": _validator_flags(state),
            "allowed_citation_ids": allowed,
            "evidence": evidence_digest,
        })
        candidate, notes = llm.structured(Explanation, _EXPLAIN_SYSTEM, user,
                                          max_tokens=600)
        if candidate is not None:
            if candidate.citation_ids and set(candidate.citation_ids).issubset(set(allowed)):
                return candidate, "llm", notes
            notes.append("explanation rejected: cited IDs outside the retrieved "
                         "allow-list")
        return _fallback_explanation(state), "fallback-after-llm", notes
    return _fallback_explanation(state), "deterministic", []


async def run_agent(mission: str,
                    objective: Objective | None = None,
                    retrieval_mode: str = "hybrid",
                    use_llm: bool = True,
                    llm: LocalLLM | None = None,
                    executor: ToolExecutor | None = None) -> dict[str, Any]:
    """Run the full mission → validated plan → cited explanation pipeline."""
    llm = llm or get_llm()
    executor = executor or DirectExecutor()
    llm_live = bool(use_llm and llm.available())
    state = AgentState(mission=mission, objective=objective,
                       retrieval_mode=retrieval_mode)
    trace: list[ToolCallRecord] = []
    decision_notes: list[str] = []

    for step in range(1, MAX_STEPS + 1):
        decision, decided_by, notes = await _decide(llm, state, llm_live)
        decision_notes.extend(notes)
        if decision.tool == "finish":
            trace.append(ToolCallRecord(
                step=step, tool="finish", args={}, ok=True, duration_ms=0,
                summary="agent finished", transport=executor.transport,
                decided_by=decided_by, thought=decision.thought))
            break

        args = _safe_args(decision, state, use_llm)

        started = time.perf_counter()
        try:
            result = await executor.call(decision.tool, args)
            ok = True
            summary = _summarize(decision.tool, result)
            _apply_result(decision.tool, result, state)
        except Exception as error:  # tool errors are data, not crashes
            ok = False
            summary = f"{type(error).__name__}: {error}"
        duration_ms = int((time.perf_counter() - started) * 1000)
        loggable_args = {key: value for key, value in args.items()
                        if key not in ("spec", "schedule")}
        trace.append(ToolCallRecord(
            step=step, tool=decision.tool, args=loggable_args, ok=ok,
            duration_ms=duration_ms, summary=summary,
            transport=executor.transport, decided_by=decided_by,
            thought=decision.thought))
        if state.plan and state.validation and state.validation.get("valid") \
                and state.evidence and step >= 4 and not llm_live:
            break  # deterministic path is done once everything exists

    # Completeness guardrail: whatever the model did, these must exist.
    for tool in ("extract_constraints", "get_grid_snapshot", "retrieve_evidence",
                 "optimize_schedule", "validate_schedule"):
        if tool not in state.done:
            args = _default_args(tool, state)
            if tool == "extract_constraints":
                args.setdefault("use_llm", use_llm)
            started = time.perf_counter()
            result = await executor.call(tool, args)
            _apply_result(tool, result, state)
            duration_ms = int((time.perf_counter() - started) * 1000)
            trace.append(ToolCallRecord(
                step=len(trace) + 1, tool=tool,
                args={key: value for key, value in args.items()
                      if key not in ("spec", "schedule")},
                ok=True, duration_ms=duration_ms,
                summary=_summarize(tool, result), transport=executor.transport,
                decided_by="guardrail",
                thought=f"guardrail completed the pipeline by running {tool}"))

    # Tool responses and model decisions are not the final trust boundary.
    # Reconstruct against the extracted mission in this process, even over MCP.
    try:
        spec = MissionSpec.model_validate(state.spec)
        schedule = [toolbox.core.ScheduledTask(**t) for t in (state.plan or {}).get("schedule", [])]
        checked = toolbox.core.validate(schedule, spec.max_load_kw, spec.avoid_hours,
                                        expected_tasks=spec_to_tasks(spec))
        expected_objective = state.objective or spec.objective
        if not checked["valid"] or (state.plan or {}).get("objective") != expected_objective:
            raise ValueError("schedule does not match the authorized mission")
    except (ValueError, TypeError, KeyError) as error:
        raise toolbox.core.InfeasibleMission(
            "Final mission-bound validation rejected the plan") from error
    state.validation = checked
    state.plan["validation"] = checked
    state.snapshot_mode = state.plan.get("snapshot_mode", state.snapshot_mode)

    explanation, explanation_mode, explain_notes = await _explain(
        llm, llm_live, state)

    return {
        "plan": state.plan,
        "spec": state.spec,
        "evidence": state.evidence,
        "explanation": explanation.model_dump(),
        "trace": [record.model_dump() for record in trace],
        "modes": {
            "llm": llm.config.model if llm_live else None,
            "llm_live": llm_live,
            "intent": state.intent_mode,
            "intent_adjustments": state.intent_adjustments,
            "explanation": explanation_mode,
            "retrieval": retrieval_mode,
            "retrieval_backend": None,  # filled by the API layer
            "snapshot": state.snapshot_mode,
            "transport": executor.transport,
            "decision_notes": decision_notes + explain_notes,
            "citation_check": "retrieved-ID allow-list only; not semantic entailment",
            "final_gate": "local-mission-bound-validator",
        },
    }
