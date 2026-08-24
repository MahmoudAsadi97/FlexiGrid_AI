# FlexiGrid AI — submission checklist

## Files to upload

- `FlexiGrid_AI_Technical_Report.pdf` — primary report.
- `FlexiGrid_AI_Technical_Report.docx` — editable report source.
- `FlexiGrid_AI_Defense_Deck.pptx` — eight-slide, 10-minute defense deck with speaker notes.
- `FlexiGrid_AI_Submission_Package.zip` — reproducible source, frozen fixture and tests.
- `FlexiGrid_AI_Demo_and_Defense.md` — live-demo script and examiner Q&A.

## Before uploading

1. Replace every `project partner` placeholder in the report and presentation with the second student's real name.
2. Confirm both students' names, class and academic year on the title page.
3. Open the hosted app and run **Morning → Balanced → Run agent plan**.
4. Confirm the status is **Verified**, all four constraints pass and the evidence/tool traces open.
5. Keep the report PDF open locally as the offline demo backup.

## Reproduce the prototype

```bash
npm ci
npm test
npm run lint

cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Run the optional Python API with `uvicorn flexigrid.api:app --reload`. The model key is optional; without one, the validated deterministic explanation fallback remains functional.

## Claims safe to defend

- The bounded demo uses lexical RAG, typed MCP-style tools, joint constrained search, a critic and optional schema-constrained generation.
- The frozen stress signal is representative demo data shaped around Elia dataset contracts, not a live Elia measurement.
- The reported figures are deterministic acceptance-test results for the labelled fixture, not a general LLM benchmark.
- Live normalization, 30+ held-out prompts and a production-scale MILP or CP-SAT optimizer are future validation work.
