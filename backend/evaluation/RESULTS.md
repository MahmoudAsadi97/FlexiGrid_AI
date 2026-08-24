# FlexiGrid evaluation results

Generated 2026-08-24T12:07:24+00:00 · LLM: **mock-planner-1** · embeddings: **ollama (mock-embed)** · corpus 51 chunks.

Numbers below are produced by `python -m flexigrid.evaluate` on the machine named above; re-run it after changing models to refresh every table.

## 1. Retrieval (40 labelled queries, doc-level relevance)

| Mode | hit@1 | recall@4 | MRR |
| --- | ---: | ---: | ---: |
| bm25 | 0.950 | 0.988 | 0.969 |
| dense | 0.650 | 0.900 | 0.762 |
| hybrid | 0.875 | 0.988 | 0.938 |

## 2. Intent extraction (15 labelled missions)

| Extractor | exact match | devices | deadline | objective | cap | avoid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| rules | 0.733 | 0.933 | 0.933 | 0.867 | 1.000 | 1.000 |
| llm | 0.733 | 0.933 | 0.933 | 0.867 | 1.000 | 1.000 |

## 3. Baseline B — LLM-only scheduling (no optimizer)

Model: mock-planner-1, 9 attempts.

- Constraint-valid rate: **0.333**
- Violation/failure rate: **0.667**
- Schema failures: 0
- Avg cost gap vs optimizer when valid: -0.21 €

## 4. Ablation — greedy vs joint constrained search

| Case | joint cost € | greedy cost € | greedy valid |
| --- | ---: | ---: | :-: |
| morning | 1.79 | — | ✗ infeasible |
| grid-friendly | 1.37 | 1.37 | ✓ |
| peak-avoidance | 1.84 | 1.84 | ✓ |
| tight-window (cost) | 1.87 | — | ✗ infeasible |
| tight-window (balanced) | 1.87 | — | ✗ infeasible |

Greedy failed outright on 3 case(s); joint search failed on 0.

## 5. Agent properties

- Citation precision vs retrieved allow-list: **1.000**
- Explanations rejected by the citation guard: 0
- Deterministic replay (identical plans): **yes**
- All 3 end-to-end plans valid: **yes**
- Explanation modes: llm, llm, llm
