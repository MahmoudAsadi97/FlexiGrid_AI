from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    title: str
    text: str
    tags: tuple[str, ...]


CORPUS = [
    Chunk("manual-ev-04", "EV charger manual §4.2", "The charger supports scheduled one-hour blocks and draws at most 3.6 kW in eco mode.", ("ev", "charger", "schedule", "eco", "3.6")),
    Chunk("manual-dw-11", "Dishwasher manual p.11", "Eco 50 C uses approximately 1.0 kWh over two hours. Delayed start is supported.", ("dishwasher", "eco", "delay", "hours")),
    Chunk("comfort-home", "Household comfort policy", "Maintain 19 to 21 C while occupied. Pre-heating may finish 30 minutes before wake-up.", ("heat", "comfort", "temperature", "wake", "preheat")),
    Chunk("grid-capacity", "Connection capacity profile", "Controllable household load is capped at 4.6 kW to avoid a capacity peak.", ("grid", "capacity", "load", "4.6", "peak")),
    Chunk("elia-ods002", "Elia ods002", "Measured and forecast total load on the Belgian grid, including day-ahead and week-ahead forecasts.", ("elia", "grid", "load", "forecast", "belgian")),
    Chunk("elia-ods086", "Elia ods086", "Intraday, day-ahead and week-ahead wind power forecasts, updated every quarter-hour.", ("elia", "wind", "forecast", "renewable", "grid")),
    Chunk("tariff-contract", "Demo retail tariff", "A frozen hourly retail tariff is used for cost. Elia imbalance prices are not consumer prices.", ("retail", "tariff", "hourly", "cost", "consumer")),
]


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9.]+", text.lower()) if len(token) > 2}


def retrieve(query: str, top_k: int = 4) -> list[dict[str, object]]:
    """Small lexical baseline: deterministic, inspectable and fast for the demo corpus."""
    query_tokens = _tokens(query)
    scored: list[tuple[float, Chunk]] = []
    for chunk in CORPUS:
        chunk_tokens = _tokens(chunk.text) | set(chunk.tags) | _tokens(chunk.title)
        overlap = query_tokens & chunk_tokens
        score = len(overlap) / max(1, len(query_tokens | chunk_tokens))
        scored.append((score, chunk))
    ranked = sorted(scored, key=lambda item: (-item[0], item[1].chunk_id))[:top_k]
    return [
        {"chunk_id": chunk.chunk_id, "title": chunk.title, "text": chunk.text, "score": round(score, 4)}
        for score, chunk in ranked
    ]
