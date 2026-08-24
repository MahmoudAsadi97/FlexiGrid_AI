# FlexiGrid evaluation results

Generated 2026-08-24T12:18:23+00:00 · LLM: **none (deterministic fallback)** · embeddings: **tfidf (tfidf-svd-128)** · corpus 51 chunks.

Numbers below are produced by `python -m flexigrid.evaluate` on the machine named above; re-run it after changing models to refresh every table.

## 1. Retrieval (40 labelled queries, doc-level relevance)

| Mode | hit@1 | recall@4 | MRR |
| --- | ---: | ---: | ---: |
| bm25 | 0.950 | 0.988 | 0.969 |
| dense | 0.950 | 0.988 | 0.967 |
| hybrid | 0.950 | 0.988 | 0.971 |

## 2. Intent extraction (15 labelled missions)

| Extractor | exact match | devices | deadline | objective | cap | avoid |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| rules | 0.733 | 0.933 | 0.933 | 0.867 | 1.000 | 1.000 |

_The LLM extractor row is added when the harness runs with the local model available._

## 3. Baseline B — LLM-only scheduling (no optimizer)

_Skipped: requires the local model — run this harness on the demo machine with Ollama serving; results are stamped with that machine's model._

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
- Explanation modes: deterministic, deterministic, deterministic
