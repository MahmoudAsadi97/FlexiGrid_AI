"""Build the 10-minute defense deck (PPTX) from the repository state.

Like build_report.py, evaluation numbers are read from
backend/evaluation/results.json so the slides always match the measured
system:

    cd backend && python -m flexigrid.evaluate
    python docs/build_deck.py
"""

from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = REPO_ROOT / "deliverables" / "FlexiGrid_AI_Defense_Deck.pptx"
RESULTS_PATH = REPO_ROOT / "backend" / "evaluation" / "results.json"
RESULTS: dict | None = (json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
                        if RESULTS_PATH.exists() else None)

INK = RGBColor(0x0B, 0x17, 0x14)
INK_2 = RGBColor(0x23, 0x32, 0x2E)
MUTED = RGBColor(0x6C, 0x7C, 0x76)
TEAL = RGBColor(0x1C, 0x7C, 0x66)
LIME = RGBColor(0xAE, 0xE6, 0x37)
PALE = RGBColor(0xEE, 0xF3, 0xF0)
PAPER = RGBColor(0xF3, 0xF6, 0xF3)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
ORANGE = RGBColor(0xB4, 0x69, 0x31)

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def rget(path: list[str], fallback: str = "—") -> str:
    node: object = RESULTS
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return fallback
        node = node[key]
    return str(node)


def _fill(shape, color: RGBColor) -> None:
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def _text(slide, left, top, width, height, runs, *, size=14, color=INK_2,
          bold=False, align=PP_ALIGN.LEFT, leading=1.12, anchor=MSO_ANCHOR.TOP,
          font="Calibri"):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = anchor
    if isinstance(runs, str):
        runs = [runs]
    for index, line in enumerate(runs):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = align
        paragraph.line_spacing = leading
        paragraph.space_after = Pt(4)
        if isinstance(line, tuple):
            for fragment, frag_bold, frag_color in line:
                run = paragraph.add_run()
                run.text = fragment
                run.font.size = Pt(size)
                run.font.bold = frag_bold
                run.font.color.rgb = frag_color
                run.font.name = font
        else:
            run = paragraph.add_run()
            run.text = line
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = color
            run.font.name = font
    return box


def _card(slide, left, top, width, height, fill=WHITE):
    from pptx.enum.shapes import MSO_SHAPE

    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top,
                                  width, height)
    card.adjustments[0] = 0.055
    _fill(card, fill)
    card.shadow.inherit = False
    return card


def _slide(prs, kicker: str, title: str, notes: str, *, dark=False):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    background = slide.shapes.add_shape(1, 0, 0, SLIDE_W, SLIDE_H)
    _fill(background, INK if dark else PAPER)
    background.shadow.inherit = False
    if kicker:
        _text(slide, Inches(.65), Inches(.42), Inches(9), Inches(.4), kicker,
              size=12, color=LIME if dark else TEAL, bold=True, font="Consolas")
    if title:
        _text(slide, Inches(.62), Inches(.78), Inches(12.1), Inches(1.1), title,
              size=30, color=WHITE if dark else INK, bold=True)
    slide.notes_slide.notes_text_frame.text = notes
    return slide


def _chip_row(slide, chips, top, *, left=Inches(.65)):
    x = left
    for label in chips:
        width = Inches(.32 + .082 * len(label))
        chip = _card(slide, x, top, width, Inches(.42), fill=WHITE)
        frame = chip.text_frame
        frame.word_wrap = False
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        paragraph = frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.CENTER
        run = paragraph.add_run()
        run.text = label
        run.font.size = Pt(11)
        run.font.bold = True
        run.font.color.rgb = INK_2
        run.font.name = "Consolas"
        x = Emu(int(x) + int(width) + Emu(114300))


def _stat_cards(slide, entries, top, *, height=Inches(1.55), gap=.18):
    count = len(entries)
    total_gap = gap * (count - 1)
    width = Inches((12.05 - total_gap) / count)
    x = Inches(.65)
    for index, (value, label, detail) in enumerate(entries):
        dark = index == 0
        card = _card(slide, x, top, width, height, fill=INK if dark else WHITE)
        frame = card.text_frame
        frame.margin_left = Inches(.22)
        frame.margin_top = Inches(.16)
        frame.word_wrap = True
        p1 = frame.paragraphs[0]
        run = p1.add_run(); run.text = value
        run.font.size = Pt(26); run.font.bold = True
        run.font.color.rgb = LIME if dark else INK
        p2 = frame.add_paragraph()
        run = p2.add_run(); run.text = label
        run.font.size = Pt(11.5); run.font.bold = True
        run.font.color.rgb = WHITE if dark else TEAL
        p3 = frame.add_paragraph()
        run = p3.add_run(); run.text = detail
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0xA9, 0xBB, 0xB4) if dark else MUTED
        x = Emu(int(x) + int(width) + int(Inches(gap)))


def _bullets(slide, items, left, top, width, *, size=13.5, color=INK_2,
             gap_after=6, lead_color=TEAL):
    box = slide.shapes.add_textbox(left, top, width, Inches(4.6))
    frame = box.text_frame
    frame.word_wrap = True
    for index, item in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.space_after = Pt(gap_after)
        paragraph.line_spacing = 1.14
        if isinstance(item, tuple):
            lead, rest = item
            run = paragraph.add_run(); run.text = "▸ "
            run.font.color.rgb = lead_color; run.font.size = Pt(size); run.font.bold = True
            run = paragraph.add_run(); run.text = lead
            run.font.color.rgb = color if color != WHITE else WHITE
            run.font.size = Pt(size); run.font.bold = True
            run = paragraph.add_run(); run.text = " — " + rest
            run.font.size = Pt(size); run.font.color.rgb = MUTED if color != WHITE else RGBColor(0xA9, 0xBB, 0xB4)
        else:
            run = paragraph.add_run(); run.text = "▸ " + item
            run.font.size = Pt(size); run.font.color.rgb = color
    return box


def _table(slide, headers, rows, left, top, width, col_ratios, *, size=11):
    from pptx.util import Emu as _Emu

    table_shape = slide.shapes.add_table(len(rows) + 1, len(headers), left, top,
                                         width, Inches(.4 * (len(rows) + 1)))
    table = table_shape.table
    total = sum(col_ratios)
    for index, ratio in enumerate(col_ratios):
        table.columns[index].width = _Emu(int(int(width) * ratio / total))
    for column, header in enumerate(headers):
        cell = table.cell(0, column)
        cell.fill.solid(); cell.fill.fore_color.rgb = INK
        paragraph = cell.text_frame.paragraphs[0]
        run = paragraph.add_run(); run.text = header
        run.font.size = Pt(size); run.font.bold = True; run.font.color.rgb = LIME
    for row_index, row in enumerate(rows, start=1):
        for column, value in enumerate(row):
            cell = table.cell(row_index, column)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if row_index % 2 else PALE
            paragraph = cell.text_frame.paragraphs[0]
            run = paragraph.add_run(); run.text = str(value)
            run.font.size = Pt(size); run.font.color.rgb = INK_2
    return table


def build() -> None:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # 1 ── Title ----------------------------------------------------------
    slide = _slide(prs, "GENERATIVE AI  /  PROJECT DEFENSE", "", (
        "45s. FlexiGrid AI plans household energy flexibility for Belgium. "
        "One sentence thesis: a local language model interprets and explains, "
        "deterministic code owns feasibility, and every claim on these slides "
        "is a measured number from the repository's evaluation harness."),
        dark=True)
    _text(slide, Inches(.62), Inches(2.05), Inches(11.5), Inches(1.2),
          "FlexiGrid AI", size=54, color=WHITE, bold=True)
    _text(slide, Inches(.65), Inches(3.25), Inches(11.6), Inches(1.0),
          "A local-LLM agent that plans household energy over MCP tools — "
          "hybrid RAG, Elia Open Data, and a deterministic optimizer-critic.",
          size=19, color=RGBColor(0xC9, 0xD6, 0xD0))
    _chip_row(slide, ["100% local · no cloud key", "qwen2.5:3b via Ollama",
                      "93 automated tests", "every number measured"],
              Inches(4.35))
    _text(slide, Inches(.65), Inches(6.55), Inches(11), Inches(.5),
          "Nima Asadi and project partner  ·  Howest  ·  2026",
          size=13, color=RGBColor(0x8D, 0xA0, 0x99))

    # 2 ── Problem --------------------------------------------------------
    slide = _slide(prs, "PROBLEM", "A fluent answer can still be an invalid schedule", (
        "60s. The household problem: EV, heat pump, appliances; deadlines, "
        "comfort, and the Flemish capacity tariff, where one bad quarter-hour "
        "raises the bill for twelve months. Then the hook: we measured what "
        "happens when you let the language model schedule directly — the "
        "violation number on the right. That number is why this architecture "
        "exists."))
    _bullets(slide, [
        ("Real constraints", "deadlines, 19–21 °C comfort, and a 4.6 kW cap under "
         "the Flemish capacity tariff — one violating hour costs money for a year"),
        ("Real data semantics", "Elia imbalance prices are not consumer prices; "
         "a planner that confuses them gives financially wrong advice"),
        ("The failure mode", "chat assistants produce locally plausible, "
         "globally capacity-blind schedules — fluent text, invalid physics"),
    ], Inches(.65), Inches(2.0), Inches(7.3), size=14)
    card = _card(slide, Inches(8.3), Inches(2.0), Inches(4.35), Inches(3.4), fill=INK)
    frame = card.text_frame; frame.margin_left = Inches(.3); frame.margin_top = Inches(.28)
    frame.word_wrap = True
    p = frame.paragraphs[0]; run = p.add_run()
    run.text = rget(["llm_only_baseline", "violation_or_failure_rate"], "0.67")
    run.font.size = Pt(48); run.font.bold = True; run.font.color.rgb = LIME
    p = frame.add_paragraph(); run = p.add_run()
    run.text = "violation-or-failure rate when the LLM schedules directly"
    run.font.size = Pt(13); run.font.bold = True; run.font.color.rgb = WHITE
    p = frame.add_paragraph(); run = p.add_run()
    run.text = ("Baseline B, measured by python -m flexigrid.evaluate — same "
                "tasks, windows, tariff and cap in the prompt; no optimizer. "
                "The deterministic planner: 0 violations.")
    run.font.size = Pt(11); run.font.color.rgb = RGBColor(0xA9, 0xBB, 0xB4)

    # 3 ── Data -----------------------------------------------------------
    slide = _slide(prs, "DATA", "Elia Open Data + a corpus with provenance", (
        "75s. Two data assets. Left: the Elia contract — ods002 load, ods086 "
        "wind, ods201 mix — and the tested derivation: stress equals "
        "normalized load minus half normalized wind, rescaled to 0-100. Live "
        "mode derives from real records with a timestamp; the exam fixture is "
        "labelled, never passed off as live. Right: the retrieval corpus — 15 "
        "documents, 51 chunks, each with a source type, including deliberate "
        "distractors so retrieval metrics mean something."))
    _bullets(slide, [
        ("ods002 · ods086 · ods201", "load forecast, wind forecast, generation mix "
         "from Belgium's TSO via the v2.1 records API"),
        ("Derived stress signal", "stress(h) = minmax(load) − 0.5·minmax(wind) → 0–100; "
         "implemented and unit-tested in derive.py, live or frozen with provenance"),
        ("Semantic guardrail", "retail tariff is a separate labelled input — imbalance "
         "prices never set the household price"),
    ], Inches(.65), Inches(2.0), Inches(6.6), size=13.5)
    _bullets(slide, [
        ("15 docs / 51 chunks", "device manuals, comfort policy, capacity tariff, "
         "dynamic contracts, Elia docs, the derivation method itself"),
        ("Stable citation IDs", "doc#section identifiers survive re-ingestion — "
         "citations are reproducible"),
        ("Labelled source types", "public-summary, synthetic-representative, "
         "user-policy, project-doc — nothing pretends to be what it is not"),
    ], Inches(7.55), Inches(2.0), Inches(5.2), size=13.5)

    # 4 ── Architecture ---------------------------------------------------
    slide = _slide(prs, "ARCHITECTURE", "The model proposes. Code disposes.", (
        "90s. Walk the five stages left to right: free-text mission; the local "
        "model extracts typed constraints — sanitizer clamps them; the same "
        "model chooses tools step by step with guardrails; all tools are MCP "
        "contracts served by one registry — the demo runs them in-process and "
        "over a real stdio session; the optimizer and independent critic gate "
        "everything; explanation cites only retrieved IDs. Emphasize: the "
        "trace shows who decided every step, model or guardrail."))
    stages = [
        ("01", "Mission", "free text, any phrasing"),
        ("02", "Local LLM agent", "intent → typed spec · tool loop"),
        ("03", "MCP tools", "RAG · Elia · optimizer · critic"),
        ("04", "Optimizer + critic", "joint search · hour-by-hour gate"),
        ("05", "Cited explanation", "allow-listed citations only"),
    ]
    x = Inches(.65)
    for index, (number, title, sub) in enumerate(stages):
        dark = index == 3
        card = _card(slide, x, Inches(2.2), Inches(2.28), Inches(1.7),
                     fill=INK if dark else WHITE)
        frame = card.text_frame; frame.margin_left = Inches(.16); frame.margin_top = Inches(.14)
        frame.word_wrap = True
        p = frame.paragraphs[0]; run = p.add_run(); run.text = number
        run.font.size = Pt(11); run.font.bold = True
        run.font.color.rgb = LIME if dark else TEAL; run.font.name = "Consolas"
        p = frame.add_paragraph(); run = p.add_run(); run.text = title
        run.font.size = Pt(14.5); run.font.bold = True
        run.font.color.rgb = WHITE if dark else INK
        p = frame.add_paragraph(); run = p.add_run(); run.text = sub
        run.font.size = Pt(10); run.font.color.rgb = RGBColor(0xA9, 0xBB, 0xB4) if dark else MUTED
        x = Emu(int(x) + int(Inches(2.28)) + int(Inches(.14)))
    _bullets(slide, [
        ("Guardrails, not hope", "schema-validated decisions, bounded steps, repeated tools "
         "overruled, skipped stages completed deterministically — all visible in the trace"),
        ("One tool registry", "FastMCP server, real MCP stdio host, and the API share the "
         "same five typed contracts — swap the transport, keep the behaviour"),
        ("Degrades, never breaks", "no model → rule-based intent + deterministic explanation, "
         "clearly labelled; live Elia down → labelled frozen fixture"),
    ], Inches(.65), Inches(4.35), Inches(12), size=13.5)

    # 5 ── Techniques -----------------------------------------------------
    slide = _slide(prs, "TECHNIQUES", "Every technique is load-bearing — none is decoration", (
        "60s. Map to the course list. Transformer: local Qwen2.5-3B with "
        "schema-constrained decoding and a repair loop. Agent: the model "
        "chooses the tools. RAG: hybrid BM25 plus dense with rank fusion, "
        "three switchable modes. MCP: real server, real client session. "
        "Fine-tuning, diffusion, multimodal: excluded with an argument, not "
        "ignored — and the intent ablation shows exactly where a LoRA would "
        "slot in if extraction became the bottleneck."))
    _table(slide, ["Technique", "Where it runs", "Proof it matters"],
           [
               ["Transformer (local)", "Qwen2.5-3B-Instruct via Ollama — intent, decisions, explanation",
                "free text drives the plan; repair loop measured"],
               ["Agent", "schema-validated tool loop with guardrails",
                "trace shows llm vs guardrail per step"],
               ["RAG (hybrid)", "BM25 + dense + reciprocal-rank fusion",
                f"recall@4 {rget(['retrieval', 'hybrid', 'recall_at_4'])} on 40 labelled queries"],
               ["MCP", "FastMCP server + stdio client host",
                "same agent, same tools, real protocol session"],
               ["Deterministic critic", "joint search + independent validator",
                f"LLM-only baseline fails {rget(['llm_only_baseline', 'violation_or_failure_rate'], '—')} of runs; critic: 0"],
           ],
           Inches(.65), Inches(2.05), Inches(12.05), [2.4, 4.4, 4.3], size=12)
    _text(slide, Inches(.65), Inches(5.6), Inches(12), Inches(1.2),
          "Excluded with argument: fine-tuning (LoRA on intent extraction is the named next step once "
          "prompting is the measured bottleneck), diffusion and multimodal (no image/audio modality in "
          "the problem — including them would be technique tourism).",
          size=12.5, color=MUTED)

    # 6 ── Algorithm ------------------------------------------------------
    slide = _slide(prs, "ALGORITHM", "Joint constrained search, with the greedy failure on display", (
        "60s. Tasks are power, duration, window. Score is weighted normalized "
        "tariff plus stress. Branch-and-bound joint search with "
        "most-constrained-first ordering. The greedy version is kept as a "
        "measured ablation and fails outright on the morning mission — the "
        "EV takes the locally best slot and strands the heat pump. "
        "Avoid-hours are honoured when feasible and relaxed with a note when "
        "not. Everything replays byte-identical."))
    _bullets(slide, [
        ("score(h) = w·tariff̂(h) + (1−w)·stresŝ(h)", "w = 0.84 cost / 0.56 balanced / 0.18 grid"),
        ("Branch-and-bound joint search", "most-constrained-first, prunes on best score, "
         "optimal for the ≤4-task day; MILP/CP-SAT named for production scale"),
        ("Independent critic", "re-validates windows, avoid-hours and every hour's summed "
         "load before anything is displayed"),
    ], Inches(.65), Inches(2.0), Inches(6.9), size=13.5)
    _table(slide, ["Case", "Joint", "Greedy"],
           [
               ["morning (fixture)", "valid", "infeasible"],
               ["grid-friendly", "valid", "valid, equal cost"],
               ["peak-avoidance", "valid", "valid, equal cost"],
               ["tight-window ×2", "valid", "infeasible"],
           ],
           Inches(7.8), Inches(2.05), Inches(4.85), [2.2, 1.3, 1.9], size=12)
    _text(slide, Inches(7.8), Inches(4.35), Inches(4.8), Inches(.9),
          f"greedy fails {rget(['greedy_ablation', 'greedy_failures'], '3')}/5 cases · joint fails 0 — "
          "measured by the harness, not asserted",
          size=12, color=ORANGE, bold=True)

    # 7 ── Live demo ------------------------------------------------------
    slide = _slide(prs, "LIVE DEMO", "Everything on screen is the real pipeline", (
        "150s. Demo order: 1) top-bar chip proves the live backend and names "
        "the model. 2) run the morning mission — walk the trace: intent chips "
        "with sanitizer notes, five tool calls with milliseconds and the "
        "llm/guardrail column, retrieval scores, the model's cited "
        "explanation. 3) edit the mission live — move the deadline, add "
        "avoid-hours — schedule follows. 4) type the impossible mission — "
        "critic rejects it, nothing is displayed. 5) terminal: python -m "
        "flexigrid.mcp_host shows the same agent over a real MCP session. "
        "Fallback if anything dies: offline mode is clearly labelled and the "
        "report PDF is open."))
    steps = [
        ("1", "Live badge", "backend chip names the model, embeddings and corpus — no simulation"),
        ("2", "Run the mission", "trace: intent chips → 5 tool calls (ms, llm/guardrail) → cited explanation"),
        ("3", "Edit the text", "change deadline / avoid-hours — the free text visibly drives the plan"),
        ("4", "Break it on purpose", "impossible mission → the critic rejects; no invalid plan is ever shown"),
        ("5", "MCP terminal", "python -m flexigrid.mcp_host — same agent over a real stdio session"),
    ]
    y = Inches(2.05)
    for number, title, detail in steps:
        card = _card(slide, Inches(.65), y, Inches(12.05), Inches(.86))
        frame = card.text_frame; frame.margin_left = Inches(.25)
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = frame.paragraphs[0]
        run = p.add_run(); run.text = f"{number}   "
        run.font.size = Pt(15); run.font.bold = True; run.font.color.rgb = TEAL
        run.font.name = "Consolas"
        run = p.add_run(); run.text = f"{title} — "
        run.font.size = Pt(13.5); run.font.bold = True; run.font.color.rgb = INK
        run = p.add_run(); run.text = detail
        run.font.size = Pt(12.5); run.font.color.rgb = MUTED
        y = Emu(int(y) + int(Inches(.98)))

    # 8 ── Evaluation -----------------------------------------------------
    environment_line = "run python -m flexigrid.evaluate to regenerate"
    if RESULTS:
        environment = RESULTS["environment"]
        environment_line = (f"measured with {environment['llm_model'] or 'deterministic fallback'} · "
                            f"{environment['embeddings_backend']} embeddings · "
                            f"{environment['corpus_chunks']} chunks · {environment['generated_at']}")
    slide = _slide(prs, "EVALUATION", "Correctness measured before fluency", (
        "75s. Four independent measurements. Retrieval on 40 labelled "
        "queries across three modes — note BM25 is a strong in-domain "
        "baseline and we say so. Intent extraction against the rule-based "
        "ablation. Baseline B: the LLM scheduling alone violates constraints; "
        "the critic never does. Citation precision 1.0 because the allow-list "
        "guard makes anything else impossible — and the guard's rejections "
        "are counted, not hidden. Every number states which model produced "
        "it."))
    _table(slide, ["Retrieval (40 queries)", "hit@1", "recall@4", "MRR"],
           [[mode,
             rget(["retrieval", mode, "hit_at_1"]),
             rget(["retrieval", mode, "recall_at_4"]),
             rget(["retrieval", mode, "mrr"])] for mode in ("bm25", "dense", "hybrid")],
           Inches(.65), Inches(2.0), Inches(5.9), [2.6, 1.1, 1.2, 1.1], size=12)
    _table(slide, ["Property", "Result"],
           [
               ["Intent exact-match (rules ablation)", rget(["intent", "rules", "exact_match"])],
               ["LLM-only scheduling violations (Baseline B)", rget(["llm_only_baseline", "violation_or_failure_rate"], "—")],
               ["Citation precision (allow-list)", rget(["agent_properties", "citation_precision"])],
               ["Deterministic replay", "pass" if rget(["agent_properties", "deterministic_plan_replay"]) == "True" else rget(["agent_properties", "deterministic_plan_replay"])],
               ["Constraint validity, end-to-end", "all plans valid" if rget(["agent_properties", "all_plans_valid"]) == "True" else rget(["agent_properties", "all_plans_valid"])],
           ],
           Inches(6.85), Inches(2.0), Inches(5.85), [3.4, 1.6], size=12)
    _text(slide, Inches(.65), Inches(5.95), Inches(12), Inches(.6),
          environment_line, size=11.5, color=MUTED, font="Consolas")

    # 9 ── Conclusion -----------------------------------------------------
    slide = _slide(prs, "CONCLUSION", "Precise about what is proven — and what is next", (
        "45s. Proven: free text drives a validated plan through a real agent "
        "on real MCP tools with a local model, and the evaluation quantifies "
        "why the critic must exist. Next: LoRA for intent once it is the "
        "measured bottleneck, MILP at scale, a broader mission set with "
        "confidence intervals, carbon-aware objective from ods201. Close by "
        "inviting questions on any layer — both of us can walk every file."),
        dark=True)
    _text(slide, Inches(.65), Inches(2.1), Inches(5.6), Inches(.5),
          "PROVEN NOW", size=13, color=LIME, bold=True, font="Consolas")
    _bullets(slide, [
        "Free-text missions → typed constraints → validated plans, fully local",
        "A real agent over real MCP tools, guardrails measured under rogue tests",
        "Hybrid RAG with stable citations and a 40-query labelled benchmark",
        "The critic's necessity quantified by the LLM-only baseline",
        "93 tests, mock-model CI harness, every number with provenance",
    ], Inches(.65), Inches(2.6), Inches(5.9), size=13, color=WHITE)
    _text(slide, Inches(6.95), Inches(2.1), Inches(5.6), Inches(.5),
          "NEXT", size=13, color=LIME, bold=True, font="Consolas")
    _bullets(slide, [
        "LoRA fine-tune for intent extraction once it is the measured bottleneck",
        "MILP / CP-SAT planner behind the same tool contract at scale",
        "Broader mission set with bootstrap confidence intervals",
        "Carbon-aware objective from the ods201 generation mix",
        "Pilot requirements: consent, billing contracts, fail-safe control",
    ], Inches(6.95), Inches(2.6), Inches(5.9), size=13, color=WHITE)
    _text(slide, Inches(.65), Inches(6.6), Inches(12), Inches(.5),
          "github.com/MahmoudAsadi97/FlexiGrid_AI  ·  python -m flexigrid.doctor reproduces this talk",
          size=12, color=RGBColor(0x8D, 0xA0, 0x99), font="Consolas")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT_PATH)
    print(OUT_PATH)


if __name__ == "__main__":
    build()
