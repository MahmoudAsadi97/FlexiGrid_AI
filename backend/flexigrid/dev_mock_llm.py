"""Deterministic OpenAI-compatible mock server for offline development and CI.

The exam demo runs against a real local model (Ollama). This mock exists so
that the *code paths* — protocol handling, JSON extraction, schema
validation, the repair round-trip, agent guardrails, and embedding calls —
can be integration-tested end to end on a machine with no model weights, and
so `npm run dev` has something to talk to during UI work.

It emulates three behaviours by inspecting the system prompt:

- agent-step decisions → a scripted planner that reads the state digest and
  picks the next canonical tool;
- intent extraction     → the rule-based mission parser, serialized as JSON;
- plan explanation      → a grounded explanation citing only allowed IDs.

Failure injection (to test the repair path):

- ``MOCK_LLM_MALFORMED_EVERY=N``  every Nth structured reply is truncated;
- ``MOCK_LLM_ROGUE=1``            agent decisions try to finish prematurely.

Run:  python -m flexigrid.dev_mock_llm  (serves on 127.0.0.1:11435)
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import re

from fastapi import FastAPI

from .intent import rule_based_spec

app = FastAPI(title="FlexiGrid mock LLM")

MODEL_ID = "mock-planner-1"
_counter = itertools.count(1)


def _malformed_due() -> bool:
    every = int(os.getenv("MOCK_LLM_MALFORMED_EVERY", "0") or 0)
    return every > 0 and next(_counter) % every == 0


@app.get("/v1/models")
def models() -> dict:
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}


def _wrap(content: str) -> dict:
    return {
        "id": "mock-completion",
        "object": "chat.completion",
        "model": MODEL_ID,
        "choices": [{"index": 0, "message": {"role": "assistant",
                                             "content": content},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _mission_from(text: str) -> str:
    match = re.search(r"mission:\s*(.+)", text, re.IGNORECASE)
    return match.group(1).strip() if match else text[:200]


def _agent_decision(user: str) -> dict:
    rogue = os.getenv("MOCK_LLM_ROGUE") == "1"
    if rogue and "plan: computed" not in user:
        return {"thought": "rogue mode: finishing early on purpose",
                "tool": "finish", "args": {}}
    if "constraints extracted: no" in user:
        return {"thought": "First turn the mission into typed constraints.",
                "tool": "extract_constraints", "args": {}}
    if "grid snapshot loaded: no" in user:
        return {"thought": "Fetch tariff and stress context for the day.",
                "tool": "get_grid_snapshot", "args": {}}
    if "evidence chunks: 0" in user:
        mission = _mission_from(user)
        return {"thought": "Ground the plan in device manuals and grid rules.",
                "tool": "retrieve_evidence",
                "args": {"query": mission, "top_k": 4}}
    if "plan: computed" not in user:
        return {"thought": "All context gathered; run the constrained search.",
                "tool": "optimize_schedule", "args": {}}
    if "validated: yes, valid" not in user:
        return {"thought": "Ask the independent critic to re-check the plan.",
                "tool": "validate_schedule", "args": {}}
    return {"thought": "A validated plan exists; nothing left to do.",
            "tool": "finish", "args": {}}


def _intent_payload(user: str) -> dict:
    mission = _mission_from(user)
    return rule_based_spec(mission).model_dump()


def _explanation_payload(user: str) -> dict:
    from .llm import extract_json

    allowed: list[str] = []
    cost = peak = None
    payload = extract_json(user)
    if payload:
        allowed = list(payload.get("allowed_citation_ids", []))
        plan = payload.get("verified_plan", {})
        cost = plan.get("total_cost_eur")
        peak = plan.get("peak_load_kw")
    citations = allowed[:3] or ["pipeline-stress#0"]
    return {
        "summary": f"Every task finishes inside its window for €{cost} with a "
                   f"peak of {peak} kW, under the connection cap.",
        "rationale": [
            "The validator re-checked task windows and hourly load before "
            "this text was generated.",
            "Flexible loads sit in hours with lower derived grid stress from "
            "Elia load and wind forecasts.",
            "Retail tariff data is a separate input; Elia signals never set "
            "the household price.",
        ],
        "citation_ids": citations,
        "limitation": "Mock-model output for offline development; the "
                      "examination demo uses a real local model.",
    }


def _naive_schedule(user: str) -> dict:
    """LLM-only baseline behaviour: stack everything into the cheapest hour.

    This mirrors the classic failure mode of letting a language model schedule
    directly — locally plausible, globally capacity-blind.
    """
    tasks = re.findall(r"-\s*(\w+):\s*([\d.]+)\s*kW for (\d+) h, window \[(\d+), (\d+)\)",
                       user)
    tariff_match = re.search(r"\[([\d.,\s]+)\]", user)
    tariff = [float(value) for value in
              tariff_match.group(1).split(",")] if tariff_match else [0.2] * 24
    assignments = []
    for task_id, _power, duration, earliest, latest in tasks:
        window = range(int(earliest), max(int(earliest) + 1,
                                          int(latest) - int(duration) + 1))
        best = min(window, key=lambda start: sum(
            tariff[hour] for hour in range(start, start + int(duration))
            if hour < 24))
        assignments.append({"task_id": task_id, "start": best})
    return {"assignments": assignments}


@app.post("/v1/chat/completions")
def chat(payload: dict) -> dict:
    messages = payload.get("messages", [])
    system = next((m.get("content", "") for m in messages
                   if m.get("role") == "system"), "")
    user = "\n".join(m.get("content", "") for m in messages
                     if m.get("role") == "user")

    if "planning agent" in system:
        body = _agent_decision(user)
    elif "machine-readable constraints" in system:
        body = _intent_payload(user)
    elif "already-validated" in system:
        body = _explanation_payload(user)
    elif "schedule household appliances directly" in system:
        body = _naive_schedule(user)
    else:
        return _wrap("The mock model answers planning, intent, and "
                     "explanation prompts only.")

    text = json.dumps(body)
    if _malformed_due() and "corrected JSON" not in user:
        return _wrap(text[: max(10, len(text) // 2)])  # truncated → repair path
    return _wrap(text)


@app.post("/v1/embeddings")
def embeddings(payload: dict) -> dict:
    """Deterministic hashed bag-of-words embeddings (cosine-meaningful)."""
    inputs = payload.get("input", [])
    if isinstance(inputs, str):
        inputs = [inputs]
    dimensions = 256
    data = []
    for index, text in enumerate(inputs):
        vector = [0.0] * dimensions
        for token in re.findall(r"[a-z0-9]+", str(text).lower()):
            digest = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vector[digest % dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        data.append({"object": "embedding", "index": index,
                     "embedding": [value / norm for value in vector]})
    return {"object": "list", "data": data,
            "model": payload.get("model", "mock-embed")}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=11435, log_level="warning")
