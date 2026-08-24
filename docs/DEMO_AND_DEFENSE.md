# FlexiGrid AI — 10-minute demo and defense guide

## Pre-demo setup

```bash
ollama serve                                   # local model runtime
cd backend && uvicorn flexigrid.api:app --port 8000
npm run dev                                    # interface on :3000
cd backend && python -m flexigrid.doctor       # every check must PASS
```

The top bar must read **Live pipeline · qwen2.5:3b-instruct**. Keep one terminal ready for `python -m flexigrid.mcp_host "..."` and the report PDF open as the offline backup.

## Presentation timing

| Time | Slide / action | Key message |
|---|---|---|
| 0:00–0:45 | Title | A local model interprets and explains; deterministic code owns feasibility; every claim is a measured number. |
| 0:45–1:45 | Problem | Deadlines, comfort, and the Flemish capacity tariff. Present the measured LLM-only scheduling result (Baseline B) as the motivation for the architecture. |
| 1:45–3:00 | Data | Elia ods002/ods086/ods201, the tested stress derivation, the labelled fixture, and the 51-chunk corpus with distractors. |
| 3:00–4:30 | Architecture + techniques | Five stages; guardrails visible in the trace; one tool registry over MCP; each course technique load-bearing, exclusions argued. |
| 4:30–5:15 | Algorithm | Joint constrained search; the greedy ablation fails the morning mission outright — measured, not anecdotal. |
| 5:15–7:45 | Live demo | The five-step script below. |
| 7:45–9:00 | Evaluation | Retrieval table, intent ablation, Baseline B, citation precision, provenance line. |
| 9:00–10:00 | Conclusion | Proven vs next; invite questions on any layer. |

## Live demo script (2.5 minutes)

1. Point at the top-bar chip: model name, embedding backend, corpus size — nothing simulated.
2. Run the Morning mission. Walk the right column top-down: extracted constraint chips (with any sanitizer adjustments), the five tool calls with milliseconds and the **llm/guardrail** attribution, retrieval scores, the cited explanation, the critic verdict.
3. Edit the mission text live — change "before 07:00" to "before 05:00", or add "avoid 17:00 to 20:00" — run again; the schedule follows the text.
4. Type an impossible mission: *"Charge the EV before 01:00, keep load below 2.0 kW."* The critic rejects it and the UI shows the rejection instead of a plan.
5. In the terminal: `python -m flexigrid.mcp_host "Charge the EV before 07:00"` — the same agent, every tool call now over a real MCP stdio session.

## Likely examiner questions

### Why is this generative AI and not just an optimizer?

The mission is free text and the model is load-bearing twice: it extracts the typed constraints that define the optimization problem, and it drives the tool loop. Delete the mission text's deadline and the plan changes; that is measurable in the intent evaluation. What the model does *not* own is feasibility — deliberately, and Baseline B is the measured justification.

### What does the LLM actually decide in the agent loop?

At each step it receives the tool catalog and a state digest and returns a schema-validated decision (tool + arguments + one-sentence thought). The trace shows every decision it made and every step a guardrail had to take instead. Rogue behaviour is part of the test suite: a mock model that tries to finish before planning is demonstrably overruled.

### Why a local model instead of GPT-4-class APIs?

Privacy (household data never leaves the machine), cost and reproducibility (no key, no rate limits, exam demo cannot be broken by a provider outage), and honesty of evaluation (the harness stamps exactly which model produced each number). The client is OpenAI-compatible, so a hosted model is a one-line config change — the architecture is model-agnostic.

### Why hybrid retrieval? Why does BM25 look strong?

The corpus is small and in-domain, so lexical overlap is a strong baseline — the evaluation says so openly. Dense embeddings contribute on paraphrased queries ("car" vs "EV"); reciprocal-rank fusion combines both without tuning score scales. All three modes are switchable per request and measured separately; that is the ablation.

### How do you prevent hallucinated citations?

The retriever returns stable chunk IDs; the explanation schema is validated; the backend rejects any citation outside the retrieved allow-list and falls back to a deterministic explanation. The guard's rejection count is itself reported in the evaluation.

### Why not let the LLM schedule directly?

Because it is a measured question, not a matter of taste. Baseline B gives the model the tasks, windows, tariff and capacity cap in the prompt — everything except the optimizer — and validates its direct schedules. The violation-or-failure rate for the defense machine's model is recorded in `evaluation/RESULTS.md` with full provenance; the deterministic search records zero violations under identical conditions. Direct model schedules are locally plausible but globally capacity-blind.

### Why exhaustive search? What about scale?

Four tasks over 24 hours is a small discrete problem; branch-and-bound joint search is optimal and acts as an oracle. The greedy ablation shows why "just pick good slots" fails. At production scale the same tool contract would front an MILP/CP-SAT solver, benchmarked against the exhaustive oracle on small fixtures.

### What exactly comes from Elia, and what is derived?

Raw quarter-hour records from ods002 (load) and ods086 (wind) via the official v2.1 API. The 0–100 stress signal is derived — normalized load minus half normalized wind — by a unit-tested module that records its method and provenance. The exam demo uses a labelled frozen fixture; `ELIA_USE_LIVE=true` derives from live records. Retail cost comes from a separate labelled tariff input, never from Elia imbalance prices.

### Where would fine-tuning fit? Why no diffusion/multimodal?

The intent evaluation shows the residual a LoRA fine-tune would target (per-task deadlines, unusual phrasing); fine-tuning is scheduled for when extraction is the measured bottleneck, not before. Diffusion and multimodal models are excluded with an explicit argument: the problem contains no image or audio modality and no generative-sampling need, so they would add scope without a role this problem can justify.

### Are the results scientifically generalizable?

The deterministic results (constraints, ablation, determinism, retrieval on the labelled set) are exact for this fixture and corpus. Local-model numbers are point measurements for the named model; the harness re-runs in one command and records provenance. Confidence intervals over a broader mission set are named future work in the report.

### How is privacy handled?

Everything runs locally — model included. No personal smart-meter data, no user identity, no cloud calls. A production pilot's requirements (consent, minimization, retention, fail-safe control, GDPR roles) are tabulated in the report's risk section.

### How did the team divide the work?

Per the report's collaboration table — data/backend vs interface/evaluation, documentation shared — with the explicit rule that both members run `doctor`, both test suites, and the full demo. Every layer has a file-level owner and a second reader.

## Recovery plan

- Ollama down → the pipeline runs in labelled deterministic mode; state the fallback explicitly and continue — graceful degradation is part of the design.
- Backend down → the interface shows "Offline simulation" and replays the browser engine; switch to the MCP terminal demo.
- Everything down → the report PDF and the deck's evaluation slide carry the measured numbers.
- Never claim: live Elia observation during the demo (unless `ELIA_USE_LIVE` is actually on), device control, or a general LLM benchmark.
