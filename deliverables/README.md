# Submission deliverables

| File | Purpose | Regenerate with |
| --- | --- | --- |
| `FlexiGrid_AI_Technical_Report.pdf` | Final technical report | `python docs/build_report.py` + export to PDF |
| `FlexiGrid_AI_Technical_Report.docx` | Editable report source | `python docs/build_report.py` |
| `FlexiGrid_AI_Defense_Deck.pptx` | Nine-slide, 10-minute defense deck with speaker notes | `python docs/build_deck.py` |

Both generators read the measured numbers from `backend/evaluation/results.json`, so the canonical order is: run `python -m flexigrid.evaluate` on the demo machine (with the local model up), then rebuild the report and deck — every table then carries that machine's provenance.

The live-demo script, examiner Q&A and upload checklist live in `docs/` so they are reviewed and updated alongside the source.

Before formal submission, replace the `project partner` placeholder on the report cover and deck title slide with the second student's full name (or attach the instructor's solo approval).
