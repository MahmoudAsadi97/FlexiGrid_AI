# FlexiGrid AI — 10-minute demo and defense guide

## Presentation timing

| Time | Slide / action | Key message |
|---|---|---|
| 0:00–0:45 | Title | Generative AI interprets and explains; deterministic code guarantees feasibility. |
| 0:45–1:40 | Problem | A household request contains deadlines, comfort, power and evidence constraints that fluent text alone cannot guarantee. |
| 1:40–2:35 | Elia data | ods002, ods086 and ods201 provide Belgian load, wind and generation context. Retail tariff remains a separate labelled fixture. |
| 2:35–3:40 | Architecture | RAG retrieves allowed evidence, MCP exposes typed tools, the optimizer builds the schedule and the critic gates generation. |
| 3:40–4:30 | Algorithm | Explain the greedy failure and why exhaustive joint constrained search fixed it. |
| 4:30–7:10 | Live demo | Select Morning + Balanced, run the agent plan, inspect the schedule, evidence, tool trace, Evaluation and Architecture views. |
| 7:10–8:20 | Evaluation | Defend 9/9 constraint passes, 100% cost non-regression, 18% fixture improvement, deterministic output and EV retrieval rank 1. |
| 8:20–9:10 | Limitations | The fixture validates the prototype, not general LLM quality. Live data freshness, a held-out prompt set and production optimization remain future work. |
| 9:10–10:00 | Close | Restate the hybrid-design thesis and invite technical questions. |

## Live demo checklist

1. Open the deployed site before presenting and keep the Plan view selected.
2. Choose **Morning** and **Balanced**.
3. Select **Run agent plan** and narrate retrieval, MCP calls, optimization and criticism.
4. Point to the 24-hour chart, 4.6 kW cap, cost and grid-stress metrics.
5. Open the evidence list and MCP trace; identify a retrieved source ID and its corresponding citation.
6. Open **Evaluation** and explain the acceptance criteria.
7. Open **Architecture** and connect each stage to its implementation file.
8. Keep the report PDF available as a backup if connectivity fails.

## Likely examiner questions

### Why is this generative AI and not only an optimizer?

The current prototype is deliberately bounded: predefined natural-language missions drive evidence retrieval, and an optional transformer produces a schema-constrained cited explanation after validation. The optimizer is deterministic because exact power and time constraints are better represented and tested as code. Arbitrary free-text intent-to-constraint extraction is future work, not a result claimed by this demo.

### Why use RAG instead of fine-tuning?

Manuals, household policies and dataset descriptions change and require source-level traceability. RAG updates without retraining and exposes citation IDs. Fine-tuning would be justified only after collecting enough labelled intent-to-constraint examples and proving prompting plus retrieval remains the bottleneck.

### What does MCP add?

MCP separates model reasoning from typed data and action contracts. The same Elia, device, retrieval and optimization functions can be inspected, tested and reused by another compatible host without hiding their inputs and outputs inside a prompt.

### How do you prevent hallucinated citations?

The retriever returns stable chunk IDs. The structured explanation schema may reference only those IDs; the backend rejects every citation outside that allow-list.

### Why not let an LLM choose the exact schedule?

Language models can violate numeric constraints while sounding confident. The deterministic validator checks every task window and every hourly power sum. Generation happens only after validation passes.

### Why exhaustive search?

The fixture has four flexible tasks and a small discrete 24-hour horizon, so exhaustive joint search is fast, reproducible and acts as an oracle. A larger production system should use MILP or CP-SAT while preserving the same tool and validator contracts.

### What exactly comes from Elia?

The adapter supports raw records for total Belgian load (ods002), wind forecasts (ods086) and actual generation by fuel type (ods201). The offline demo uses a labelled representative grid-stress fixture shaped around those data contracts; it is not presented as a live Elia observation. A separate retail-tariff fixture is used for cost.

### Are the results scientifically generalizable?

No. The current numbers are acceptance-test results for a deterministic labelled fixture. The next evaluation should use at least 30 held-out user prompts and report retrieval recall@4, citation precision, tool-selection accuracy, groundedness and end-to-end task success with confidence intervals.

### How is privacy handled?

The submitted prototype uses no personal smart-meter records and stores no user identity. A production pilot would require consent, data minimization, retention limits, encryption, authentication, audit logs and a GDPR controller/processor assessment.

### How did both team members collaborate?

One member can lead Elia ingestion, optimization and MCP; the other can lead the interface, RAG corpus and evaluation harness. Both must review the full code path, run both test suites and rehearse the complete demo so either can answer every question.

## Recovery plan

- If the live Elia API is unavailable, use the clearly labelled frozen snapshot.
- If the model API is unavailable, use the deterministic cited explanation fallback.
- If the hosted interface is unavailable, run `npm run dev` locally or present the report’s architecture and evaluation figures.
- Do not claim a live booking, device command or real household tariff; the prototype is advisory and simulated.
