from __future__ import annotations

import json
import os

from .core import Objective, create_demo_plan
from .models import Explanation
from .retrieval import retrieve

SYSTEM_PROMPT = """You explain already-validated household energy plans.
Never change task times or invent measurements. Use only the supplied plan and evidence.
Every factual reason must be supported by a citation_id. State that the grid signal is
derived from Elia forecasts and that the retail tariff is a separate frozen demo input."""


def _fallback_explanation(plan: dict, evidence: list[dict]) -> Explanation:
    citation_ids = [item["chunk_id"] for item in evidence]
    return Explanation(
        summary="The schedule moves flexible loads into lower-cost, lower-stress hours while preserving every deadline and the 4.6 kW connection limit.",
        rationale=[
            "The deterministic validator confirms the schedule stays inside all task windows.",
            "The connection limit is checked hour by hour before the explanation is produced.",
            "Elia load and wind forecasts provide grid context; the retail tariff remains a separate input.",
        ],
        citation_ids=citation_ids[:4],
        limitation="This fallback explanation uses a frozen demonstration snapshot and does not control real devices.",
    )


def generate_plan(prompt: str, objective: Objective = "balanced", use_llm: bool = False) -> dict:
    evidence = retrieve(prompt, top_k=4)
    plan = create_demo_plan(objective)
    explanation = _fallback_explanation(plan, evidence)
    mode = "deterministic-demo"

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    if use_llm and api_key and model:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps({"user_prompt": prompt, "verified_plan": plan, "evidence": evidence}),
                },
            ],
            text_format=Explanation,
        )
        candidate = response.output_parsed
        if candidate is not None:
            allowed = {item["chunk_id"] for item in evidence}
            if set(candidate.citation_ids).issubset(allowed):
                explanation = candidate
                mode = "llm-explanation"

    return {"plan": plan, "evidence": evidence, "explanation": explanation, "mode": mode}
