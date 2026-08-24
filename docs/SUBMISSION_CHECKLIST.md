# FlexiGrid AI — submission checklist

## Files to upload

- `FlexiGrid_AI_Technical_Report.pdf` — primary report (regenerated from `docs/build_report.py`).
- `FlexiGrid_AI_Technical_Report.docx` — editable source of the same report.
- `FlexiGrid_AI_Defense_Deck.pptx` — 9-slide deck with speaker notes (regenerated from `docs/build_deck.py`).
- `FlexiGrid_AI_Submission_Package.zip` — full source, corpus, fixtures, tests, evaluation harness.
- `docs/DEMO_AND_DEFENSE.md` — live-demo script and examiner Q&A.

## Before uploading

1. Replace every `project partner` placeholder (report cover + deck title slide) with the second student's real name — or attach the instructor's solo approval.
2. On the demo machine: `ollama pull qwen2.5:3b-instruct && ollama pull nomic-embed-text`.
3. Run `cd backend && python -m flexigrid.doctor` — every check must PASS with the real model.
4. Regenerate the measured numbers **on the demo machine** so provenance names your hardware and model:

   ```bash
   cd backend && python -m flexigrid.evaluate
   python ../docs/build_report.py
   python ../docs/build_deck.py
   ```

5. Run both test suites: `python -m unittest discover -s tests -v` (85) and `npm test` (8).
6. Start everything and rehearse the five-step demo script once end-to-end, including the impossible-mission rejection and the MCP terminal run.
7. Export the report DOCX to PDF (or `soffice --headless --convert-to pdf`) if you edited it by hand.

## Claims safe to defend

- The mission text is load-bearing: a local LLM extracts typed constraints, and a sanitizer clamps them (adjustments visible in the trace).
- A genuine agent loop chooses real MCP tools; guardrail interventions are labelled, counted and tested.
- Retrieval is hybrid (BM25 + dense + RRF) over a 51-chunk labelled corpus, with a 40-query measured benchmark.
- The critic's necessity is quantified: LLM-only scheduling (Baseline B) violates constraints; the deterministic planner does not.
- The greedy ablation fails outright on the standard morning mission; joint search never fails.
- The stress signal is derived from Elia ods002+ods086 by tested code; the exam fixture is labelled, not passed off as live.
- All 93 tests and the full evaluation run offline; every number records which model and embedding backend produced it.

## Claims to avoid

- Any general LLM benchmark claim beyond the named local model.
- "Live Elia data" during the demo unless `ELIA_USE_LIVE=true` is actually set.
- Any suggestion that the system controls physical devices.
