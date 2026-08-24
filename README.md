# FlexiGrid AI

Evidence-grounded household energy planning with RAG, MCP-style tools, constrained search and schema-validated generation.

[Live demo](https://flexigrid-ai.nima-asadi-3167.chatgpt.site) · [Technical report](deliverables/FlexiGrid_AI_Technical_Report.pdf) · [Defense deck](deliverables/FlexiGrid_AI_Defense_Deck.pptx) · [Demo guide](docs/DEMO_AND_DEFENSE.md)

![FlexiGrid AI planning dashboard](docs/figures/flexigrid-dashboard.jpg)

## What it does

FlexiGrid AI turns a selected, bounded household mission into a validated 24-hour flexibility schedule. It retrieves device and policy evidence, obtains grid context through typed tools, searches feasible task assignments jointly, rejects invalid plans and only then generates a cited explanation.

The prototype demonstrates a deliberate hybrid design:

- **Generative AI** retrieves evidence and optionally produces a structured explanation.
- **Deterministic code** enforces deadlines, device windows and the 4.6 kW controllable-load limit.
- **Transparent traces** expose evidence IDs, MCP tool calls, metrics and the critic verdict.
- **Offline fallbacks** keep the demonstration reproducible when Elia or a model API is unavailable.

## Architecture

```mermaid
flowchart LR
    A[Bounded mission] --> B[Lexical RAG]
    B --> C[MCP-style tools]
    C --> D[Planner + critic]
    D --> E[Cited explanation]
```

| Layer | Responsibility | Main implementation |
| --- | --- | --- |
| Interface | Mission selection, timeline, evidence and tool trace | `components/flexigrid-dashboard.tsx` |
| Planning engine | Joint constrained search and deterministic metrics | `lib/engine.ts` |
| Retrieval | Top-k lexical retrieval with stable evidence IDs | `backend/flexigrid/retrieval.py` |
| Tools | Typed Elia, retrieval and optimization contracts | `backend/flexigrid/mcp_server.py` |
| Agent | Plan validation and optional structured explanation | `backend/flexigrid/agent.py` |
| Data adapter | Live Elia API contracts plus frozen fallback | `backend/flexigrid/elia_client.py` |

## Elia data contract

The live adapter targets three official Belgian grid datasets:

| Dataset | Prototype use |
| --- | --- |
| `ods002` | Measured and forecast total load |
| `ods086` | Wind generation forecast |
| `ods201` | Generation mix by fuel type |

The public exam demo intentionally uses a labelled, frozen grid-stress fixture. It is representative demo data, **not a live Elia observation**. Household cost uses a separate consumer-tariff fixture; Elia imbalance prices are not treated as retail tariffs.

## Verified fixture results

| Check | Result |
| --- | ---: |
| Scenario-objective constraint passes | 9 / 9 |
| Morning cost: earliest start | €2.17 |
| Morning cost: optimized | €1.79 |
| Morning peak controllable load | 3.6 kW |
| Connection limit | 4.6 kW |
| Labelled EV retrieval query | EV manual ranked first |

These are deterministic acceptance-test results for the included fixture, not a general LLM benchmark.

## Repository structure

```text
app/                      Application shell
components/               Interactive planning dashboard
lib/engine.ts             Browser-side deterministic optimizer
backend/flexigrid/        Python agent, RAG, tools and Elia adapter
backend/data/             Reproducible frozen fixture
backend/tests/            Backend acceptance tests
tests/                    Frontend engine and rendered-output tests
docs/                     Report source, demo guide and defense material
deliverables/             Submission-ready report and slide deck
scripts/                  Reproducible build helpers
```

## Quick start

### Interface

Requirements: Node.js 22.13 or newer.

```bash
npm ci
npm run dev
```

### Python backend

Requirements: Python 3.11 or newer.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # Windows: copy .env.example .env
uvicorn flexigrid.api:app --reload
```

`OPENAI_API_KEY` and `OPENAI_MODEL` are optional. Without them, the complete validated pipeline uses its deterministic cited-explanation fallback. With them and `use_llm=true`, structured model output is checked against the retrieved citation allow-list.

Run the MCP server:

```bash
cd backend
python -m flexigrid.mcp_server
```

Fetch a fresh Elia snapshot:

```bash
cd backend
python scripts/fetch_elia_snapshot.py
```

## Tests

```bash
npm test
npm run lint

cd backend
python -m unittest discover -s tests -v
```

The automated checks cover all scenario-objective combinations, deadline and capacity constraints, deterministic replay, infeasible-plan rejection, retrieval depth, EV rank-1 retrieval and citation allow-list enforcement.

## Scope and limitations

- Missions are bounded, typed demo scenarios; arbitrary free-text intent-to-constraint extraction is future work.
- Exhaustive joint search is appropriate for four discrete demo tasks. Production scale should use MILP or CP-SAT.
- The interface is advisory and does not control real household devices.
- A real pilot requires tariff-specific billing, consent, authentication, audit logging and GDPR retention controls.
- Broader evaluation should add at least 30 held-out prompts and report retrieval recall@4, citation precision, groundedness and end-to-end task success.

## Academic deliverables

- [Technical report — PDF](deliverables/FlexiGrid_AI_Technical_Report.pdf)
- [Technical report — editable DOCX](deliverables/FlexiGrid_AI_Technical_Report.docx)
- [10-minute defense deck](deliverables/FlexiGrid_AI_Defense_Deck.pptx)
- [Demo and examiner Q&A guide](docs/DEMO_AND_DEFENSE.md)
- [Submission checklist](docs/SUBMISSION_CHECKLIST.md)

Before submitting, replace the remaining `project partner` placeholder in the report and presentation with the second student's name.
