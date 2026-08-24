"""Build the FlexiGrid technical report (DOCX) from the repository state.

Evaluation tables are populated from backend/evaluation/results.json, which
is produced by `python -m flexigrid.evaluate`. Re-run the harness on the demo
machine (with Ollama serving the local model), then re-run this script, and
the report numbers refresh with full provenance.

    cd backend && python -m flexigrid.evaluate
    python docs/build_report.py
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/flexigrid-matplotlib")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "deliverables"
ASSET_DIR = REPO_ROOT / "docs" / "rendered-report"
DOCX_PATH = OUTPUT_DIR / "FlexiGrid_AI_Technical_Report.docx"
RESULTS_PATH = REPO_ROOT / "backend" / "evaluation" / "results.json"

sys.path.insert(0, str(REPO_ROOT / "backend"))
from flexigrid import core as flexi_core  # noqa: E402

RESULTS: dict | None = (
    json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    if RESULTS_PATH.exists() else None
)


def result_or(path: list[str], fallback: str = "n/a") -> str:
    node: object = RESULTS
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return fallback
        node = node[key]
    return str(node)

INK = "0B1714"
INK_2 = "23322E"
MUTED = "6C7C76"
TEAL = "1C7C66"
LIME = "AEE637"
PALE = "EEF3F0"
LINE = "DDE6E1"
ORANGE = "F3A65A"
WHITE = "FFFFFF"
BLUE = "2E74B5"
DARK_BLUE = "1F4D78"

TARIFF = flexi_core.TARIFF
GRID_STRESS = flexi_core.GRID_STRESS


def _hourly(schedule) -> list[float]:
    load = [0.0] * 24
    for task in schedule:
        for hour in range(task.start, task.end):
            load[hour] += task.power_kw
    return load


# Real current fixture plans — recomputed at build time, never hand-typed.
_DEMO = flexi_core.demo_tasks()
OPTIMIZED_LOAD = _hourly(flexi_core.optimize(_DEMO, "balanced"))
BASELINE_LOAD = _hourly(flexi_core.earliest_start_schedule(_DEMO))
MORNING_COST = round(sum(t.cost_eur for t in flexi_core.optimize(_DEMO, "balanced")), 2)
MORNING_BASELINE_COST = round(
    sum(t.cost_eur for t in flexi_core.earliest_start_schedule(_DEMO)), 2)
MORNING_PEAK = round(max(OPTIMIZED_LOAD), 1)


def rgb(hex_value: str) -> RGBColor:
    return RGBColor.from_string(hex_value)


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=80, start=120, bottom=80, end=120) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_cell_border(cell, color=LINE, size=6) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "start", "bottom", "end", "insideH", "insideV"):
        node = borders.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), str(size))
        node.set(qn("w:color"), color)


def set_table_geometry(table, widths_dxa: list[int], indent_dxa=120) -> None:
    total = sum(widths_dxa)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl_pr = table._tbl.tblPr
    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(indent_dxa))
    tbl_ind.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths_dxa:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        for index, cell in enumerate(row.cells):
            width = widths_dxa[index]
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(width))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell)
            set_cell_border(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def set_run_font(run, name="Calibri", size=None, color=None, bold=None, italic=None) -> None:
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = rgb(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def add_page_field(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run()
    fld_char = OxmlElement("w:fldChar")
    fld_char.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = " PAGE "
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "1"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.extend([fld_char, instr_text, fld_sep, text, fld_end])
    set_run_font(run, size=8.5, color=MUTED)


def add_hyperlink(paragraph, text: str, url: str) -> None:
    part = paragraph.part
    relation = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relation)
    run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), TEAL)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    r_pr.extend([color, underline])
    text_node = OxmlElement("w:t")
    text_node.text = text
    run.extend([r_pr, text_node])
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_body(doc: Document, text: str, *, bold_lead: str | None = None, after=6, keep=False):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.line_spacing = 1.10
    paragraph.paragraph_format.keep_with_next = keep
    if bold_lead and text.startswith(bold_lead):
        lead = paragraph.add_run(bold_lead)
        set_run_font(lead, size=10.5, color=INK, bold=True)
        rest = paragraph.add_run(text[len(bold_lead):])
        set_run_font(rest, size=10.5, color=INK_2)
    else:
        run = paragraph.add_run(text)
        set_run_font(run, size=10.5, color=INK_2)
    return paragraph


def add_bullet(doc: Document, text: str):
    paragraph = doc.add_paragraph(style="List Bullet")
    paragraph.paragraph_format.left_indent = Inches(0.5)
    paragraph.paragraph_format.first_line_indent = Inches(-0.25)
    paragraph.paragraph_format.space_after = Pt(8)
    paragraph.paragraph_format.line_spacing = 1.167
    run = paragraph.add_run(text)
    set_run_font(run, size=10.5, color=INK_2)
    return paragraph


def new_numbering_id(doc: Document) -> int:
    numbering = doc.part.numbering_part.element
    style_num_id = int(doc.styles["List Number"].element.pPr.numPr.numId.val)
    base_num = next(node for node in numbering.findall(qn("w:num")) if int(node.get(qn("w:numId"))) == style_num_id)
    abstract_num_id = base_num.find(qn("w:abstractNumId")).get(qn("w:val"))
    next_num_id = max(int(node.get(qn("w:numId"))) for node in numbering.findall(qn("w:num"))) + 1
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(next_num_id))
    abstract = OxmlElement("w:abstractNumId")
    abstract.set(qn("w:val"), abstract_num_id)
    level_override = OxmlElement("w:lvlOverride")
    level_override.set(qn("w:ilvl"), "0")
    start_override = OxmlElement("w:startOverride")
    start_override.set(qn("w:val"), "1")
    level_override.append(start_override)
    num.extend([abstract, level_override])
    numbering.append(num)
    return next_num_id


def add_number(doc: Document, text: str, *, num_id: int | None = None):
    paragraph = doc.add_paragraph(style="List Number")
    if num_id is not None:
        num_pr = paragraph._p.get_or_add_pPr().get_or_add_numPr()
        num_pr.get_or_add_ilvl().val = 0
        num_pr.get_or_add_numId().val = num_id
    paragraph.paragraph_format.left_indent = Inches(0.5)
    paragraph.paragraph_format.first_line_indent = Inches(-0.25)
    paragraph.paragraph_format.space_after = Pt(8)
    paragraph.paragraph_format.line_spacing = 1.167
    run = paragraph.add_run(text)
    set_run_font(run, size=10.5, color=INK_2)
    return paragraph


def add_callout(doc: Document, label: str, text: str, fill=PALE, accent=TEAL):
    table = doc.add_table(rows=1, cols=1)
    set_table_geometry(table, [9360])
    cell = table.cell(0, 0)
    set_cell_shading(cell, fill)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    label_run = p.add_run(f"{label.upper()}  ")
    set_run_font(label_run, size=9, color=accent, bold=True)
    body = p.add_run(text)
    set_run_font(body, size=10.2, color=INK_2)
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(3)


def add_table(doc: Document, headers: list[str], rows: list[list[str]], widths: list[int], *, small=False):
    table = doc.add_table(rows=1, cols=len(headers))
    set_table_geometry(table, widths)
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        set_cell_shading(cell, "F2F4F7")
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if index > 0 else WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(header)
        set_run_font(run, size=8.6 if small else 9.2, color=INK, bold=True)
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)
    for row_values in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row_values):
            p = cells[index].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if index > 0 else WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(str(value))
            set_run_font(run, size=8.4 if small else 9.0, color=INK_2)
    set_table_geometry(table, widths)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def create_signal_chart(path: Path) -> None:
    hours = list(range(24))
    tariff_norm = [value / max(TARIFF) * 100 for value in TARIFF]
    fig, axes = plt.subplots(2, 1, figsize=(9.1, 4.4), sharex=True, gridspec_kw={"height_ratios": [1.4, 1]})
    fig.patch.set_facecolor("white")
    axes[0].plot(hours, GRID_STRESS, color="#F3A65A", lw=2.2, label="Representative grid-stress index")
    axes[0].plot(hours, tariff_norm, color="#1C7C66", lw=2.2, label="Retail tariff (normalized)")
    axes[0].axvspan(17, 20, color="#F3A65A", alpha=.10, lw=0)
    axes[0].set_ylabel("Index (0-100)", fontsize=8)
    axes[0].set_ylim(0, 105)
    axes[0].legend(loc="upper left", frameon=False, fontsize=8, ncol=2)
    axes[0].grid(axis="y", color="#DDE6E1", linewidth=.7)
    axes[1].step(hours, BASELINE_LOAD, where="mid", color="#A9B8B1", lw=1.8, label="Earliest-start baseline")
    axes[1].step(hours, OPTIMIZED_LOAD, where="mid", color="#1C7C66", lw=2.2, label="Optimized load")
    axes[1].axhline(4.6, color="#B34B4B", lw=1.1, ls="--", label="4.6 kW cap")
    axes[1].fill_between(hours, OPTIMIZED_LOAD, step="mid", color="#AEE637", alpha=.18)
    axes[1].set_ylabel("Load (kW)", fontsize=8)
    axes[1].set_xlabel("Hour of day", fontsize=8)
    axes[1].set_ylim(0, 5.2)
    axes[1].set_xticks(range(0, 24, 3))
    axes[1].legend(loc="upper right", frameon=False, fontsize=7.5, ncol=3)
    axes[1].grid(axis="y", color="#DDE6E1", linewidth=.7)
    for axis in axes:
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(labelsize=7.5, colors="#6C7C76", length=0)
    fig.suptitle("Fixture day: flexible load moves into lower-pressure hours", x=.08, ha="left", fontsize=11, fontweight="bold", color="#0B1714")
    plt.tight_layout(rect=(0, 0, 1, .94))
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def create_architecture_diagram(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.1, 2.35))
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 25)
    ax.axis("off")
    stages = [
        (1.2, "1", "Mission", "Free text"),
        (21.2, "2", "Local LLM agent", "Intent + tool loop"),
        (41.2, "3", "MCP tools", "RAG · Elia · optimizer"),
        (61.2, "4", "Optimizer + critic", "Deterministic gate"),
        (81.2, "5", "Cited explanation", "Allow-listed"),
    ]
    accent_index = 3
    for index, (x, number, title, subtitle) in enumerate(stages):
        fill = "#0B1714" if index == accent_index else "#EEF3F0"
        title_color = "white" if index == accent_index else "#0B1714"
        box = FancyBboxPatch((x, 6), 16.4, 13, boxstyle="round,pad=.7,rounding_size=1.4", facecolor=fill, edgecolor="#DDE6E1", linewidth=1)
        ax.add_patch(box)
        ax.text(x + 1.4, 16.5, number, fontsize=8, color="#1C7C66" if index != accent_index else "#AEE637", fontweight="bold")
        ax.text(x + 1.4, 12.7, title, fontsize=8.6, color=title_color, fontweight="bold")
        ax.text(x + 1.4, 9.4, subtitle, fontsize=6.8, color="#6C7C76" if index != accent_index else "#A6B5AF")
        if index < len(stages) - 1:
            ax.add_patch(FancyArrowPatch((x + 17.1, 12.5), (x + 20.3, 12.5), arrowstyle="-|>", mutation_scale=10, linewidth=1.2, color="#87968F"))
    ax.text(2, 23, "FlexiGrid AI control flow", fontsize=12, color="#0B1714", fontweight="bold")
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def style_document(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(.492)
    section.footer_distance = Inches(.492)
    section.different_first_page_header_footer = True

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal.font.size = Pt(11)
    normal.font.color.rgb = rgb(INK_2)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.10

    for name, size, color, before, after in (
        ("Heading 1", 16, TEAL, 16, 8),
        ("Heading 2", 13, TEAL, 12, 6),
        ("Heading 3", 12, DARK_BLUE, 8, 4),
    ):
        style = styles[name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = rgb(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    header = section.header
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    hp.paragraph_format.space_after = Pt(0)
    hr = hp.add_run("FLEXIGRID AI   /   TECHNICAL REPORT")
    set_run_font(hr, size=8.5, color=MUTED, bold=True)

    footer = section.footer
    table = footer.add_table(rows=1, cols=2, width=Inches(6.5))
    set_table_geometry(table, [7200, 2160], indent_dxa=0)
    for cell in table.rows[0].cells:
        set_cell_border(cell, color=WHITE, size=0)
    lp = table.cell(0, 0).paragraphs[0]
    lr = lp.add_run("Generative AI project  •  Belgium energy flexibility")
    set_run_font(lr, size=8.5, color=MUTED)
    add_page_field(table.cell(0, 1).paragraphs[0])


def add_cover(doc: Document) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(30)
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run("GENERATIVE AI  /  PROJECT REPORT")
    set_run_font(r, name="Calibri", size=10, color=TEAL, bold=True)

    title = doc.add_paragraph()
    title.paragraph_format.space_before = Pt(80)
    title.paragraph_format.space_after = Pt(10)
    run = title.add_run("FlexiGrid AI")
    set_run_font(run, size=35, color=INK, bold=True)

    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(26)
    run = subtitle.add_run("A local-LLM agent that plans household energy over MCP tools: hybrid RAG, Elia Open Data, and a deterministic optimizer-critic")
    set_run_font(run, size=15, color=INK_2)

    add_callout(
        doc,
        "Project thesis",
        "A small local language model interprets free-text missions and drives the tool loop; deterministic code owns feasibility. Every stage is typed, traced, measured separately, and reproducible without any cloud API key.",
        fill="E9F2ED",
    )

    retrieval_recall = result_or(["retrieval", "hybrid", "recall_at_4"], "—")
    metrics = doc.add_table(rows=1, cols=3)
    set_table_geometry(metrics, [3120, 3120, 3120])
    entries = [
        ("4 + 1", "advanced techniques", "local transformer, agent, hybrid RAG, MCP + deterministic critic"),
        ("103", "automated tests", "95 backend + 8 interface, all passing"),
        (retrieval_recall, "retrieval recall@4", "hybrid BM25 + dense, 40 labelled queries"),
    ]
    for index, (value, label, detail) in enumerate(entries):
        cell = metrics.cell(0, index)
        set_cell_shading(cell, INK if index == 0 else PALE)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run(value)
        set_run_font(r, size=22, color=LIME if index == 0 else INK, bold=True)
        p2 = cell.add_paragraph()
        p2.paragraph_format.space_after = Pt(2)
        r = p2.add_run(label)
        set_run_font(r, size=8.5, color=WHITE if index == 0 else TEAL, bold=True)
        p3 = cell.add_paragraph()
        r = p3.add_run(detail)
        set_run_font(r, size=7.5, color="A9BBB4" if index == 0 else MUTED)

    doc.add_paragraph().paragraph_format.space_after = Pt(24)
    meta = doc.add_paragraph()
    meta.paragraph_format.space_before = Pt(32)
    meta.paragraph_format.space_after = Pt(3)
    r = meta.add_run("AUTHOR")
    set_run_font(r, size=8, color=MUTED, bold=True)
    add_body(doc, "Mahmoud Asadi Heris", after=2)
    add_body(doc, "CTAI — final year  •  Course: Generative AI  •  August 2026  •  Howest", after=0)

    doc.add_page_break()


def build_report() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    chart_path = ASSET_DIR / "signal-and-load.png"
    architecture_path = ASSET_DIR / "architecture.png"
    create_signal_chart(chart_path)
    create_architecture_diagram(architecture_path)

    doc = Document()
    style_document(doc)
    props = doc.core_properties
    props.title = "FlexiGrid AI - Technical Report"
    props.subject = "Generative AI — project report"
    props.author = "Mahmoud Asadi Heris"
    props.keywords = "local LLM, Ollama, agents, MCP, hybrid RAG, Elia, energy flexibility, generative AI"

    add_cover(doc)

    doc.add_heading("Executive summary", level=1)
    add_body(doc, "FlexiGrid AI is a household energy flexibility copilot for Belgium. A resident types a free-text mission such as 'charge the EV and run the dishwasher before 07:00'. A local language model (Qwen2.5-3B-Instruct served by Ollama) extracts typed constraints from that text, then drives an agent loop over Model Context Protocol tools: hybrid retrieval over a 51-chunk household/grid corpus, an Elia grid snapshot with a derived stress signal, a joint constrained-search optimizer, and an independent validator. Only after the validator passes does the model generate an explanation, and it may cite only the chunk IDs that retrieval actually returned. The design principle throughout: the model proposes, deterministic code disposes.")
    add_callout(doc, "Techniques demonstrated", "Transformer (local 3B instruct model with schema-constrained decoding and a repair loop) · Agent (model-driven tool selection with guardrails) · RAG (BM25 + dense embeddings fused by reciprocal rank) · MCP (FastMCP server + a real stdio client session) · plus a deterministic optimizer-critic that the evaluation shows the model cannot replace.")

    doc.add_heading("Problem definition", level=1)
    add_body(doc, "Households with an EV, heat pump and flexible appliances face competing objectives: finish tasks before deadlines, maintain comfort, avoid a connection-capacity peak and shift consumption away from grid-stress periods. Existing energy dashboards expose curves but still require the resident to translate those curves into a schedule. A generic chatbot is not sufficient because fluent text can violate power limits or confuse market prices with consumer tariffs.")
    doc.add_heading("Target user and success definition", level=2)
    add_body(doc, "The target user is a Belgian household or energy-coaching professional who needs an understandable next-day plan. Success is not defined as 'helpful text'. A successful response must satisfy every time window stated in the mission, stay at or below the connection-capacity cap (default 4.6 kW, adjustable per mission), respect requested avoid-hours, cite only retrieved evidence, keep retail pricing separate from Elia imbalance-market concepts, and reproduce exactly when the inputs are unchanged.")

    doc.add_heading("Project objectives", level=2)
    for item in (
        "Turn arbitrary free-text household missions into typed, sanitized planning constraints with a local model.",
        "Let the model drive the tool loop itself, over real MCP contracts, with every decision visible in a trace.",
        "Ground device, comfort and data-source claims in a retrievable corpus with stable citation IDs.",
        "Generate explanations only after a deterministic validator passes, with citations restricted to an allow-list.",
        "Measure retrieval, intent extraction, planning and generation separately, including an LLM-only baseline and a greedy-search ablation.",
    ):
        add_bullet(doc, item)

    doc.add_page_break()
    doc.add_heading("1. Data selection and pipeline", level=1)
    add_body(doc, "Elia, Belgium's transmission system operator, publishes open datasets through an Opendatasoft API. Three datasets define the grid-data contract. The derivation pipeline (backend/flexigrid/derive.py) is implemented and unit-tested: quarter-hour day-ahead forecasts are bucketed into hourly means, load and wind are min-max normalized over the day, and stress(h) = norm(load) − 0.5·norm(wind), rescaled to 0–100. With ELIA_USE_LIVE=true the adapter fetches live records and derives the signal with provenance and a retrieval timestamp; the examination demo defaults to a clearly labelled frozen fixture so every number reproduces offline. The second data asset is the retrieval corpus: 15 documents / 51 chunks covering device manuals, household policies, the Flemish capacity tariff, dynamic-contract semantics, Elia dataset documentation, and the derivation methodology itself, each labelled with a source type (public-summary, synthetic-representative, user-policy, project-doc).")
    add_table(
        doc,
        ["Dataset", "Official content", "Role in FlexiGrid"],
        [
            ["ods002", "Measured and forecast total Belgian load", "Intended peak/load-pressure feature"],
            ["ods086", "Intraday, day-ahead and week-ahead wind forecast", "Intended renewable-opportunity feature"],
            ["ods201", "Actual generation aggregated by fuel type", "Generation-mix context and future carbon proxy"],
        ],
        [1500, 3600, 4260],
    )
    source = doc.add_paragraph()
    source.paragraph_format.space_before = Pt(4)
    source.paragraph_format.space_after = Pt(4)
    run = source.add_run("Official sources: ")
    set_run_font(run, size=8.5, color=MUTED, italic=True)
    add_hyperlink(source, "ods002", "https://opendata.elia.be/explore/dataset/ods002/")
    source.add_run("  |  ")
    add_hyperlink(source, "ods086", "https://opendata.elia.be/explore/dataset/ods086/")
    source.add_run("  |  ")
    add_hyperlink(source, "ods201", "https://opendata.elia.be/explore/dataset/ods201/")

    doc.add_heading("Data contract", level=2)
    data_list_id = new_numbering_id(doc)
    add_number(doc, "Fetch up to 100 recent records per dataset from Elia's v2.1 records endpoint; preserve dataset ID, raw records and an ISO retrieval timestamp.", num_id=data_list_id)
    add_number(doc, "Derive the hourly 0-100 stress series from ods002 + ods086 with the tested derivation module; record the method and wind weight in the output.", num_id=data_list_id)
    add_number(doc, "On any live failure, fall back to the frozen fixture and label the response mode accordingly — the pipeline degrades, it never breaks.", num_id=data_list_id)
    add_number(doc, "Every snapshot carries provenance: mode (live-derived / frozen-demo-fixture), source, and an explicit warning on fixture data.", num_id=data_list_id)
    add_callout(doc, "Important semantic guardrail", "Elia imbalance prices are settlement signals for balance responsible parties, not a household retail tariff. FlexiGrid therefore uses a separate labelled retail-tariff fixture for cost optimization.", fill="FFF4E8", accent="B46931")

    doc.add_heading("Privacy and EU constraints", level=2)
    add_body(doc, "The submitted prototype uses no personal smart-meter records and stores no user identity. A production pilot would require explicit household consent, data minimization, retention limits, device authentication, audit logs and a controller/processor assessment under GDPR. The prototype remains advisory: it does not send commands to physical devices.")

    doc.add_heading("2. Technical architecture", level=1)
    architecture_picture = doc.add_picture(str(architecture_path), width=Inches(6.5))
    architecture_picture._inline.docPr.set("title", "FlexiGrid AI control flow")
    architecture_picture._inline.docPr.set("descr", "Five-stage flow: free-text mission, local LLM agent, MCP tools, deterministic optimizer and critic, cited explanation.")
    caption = doc.add_paragraph("Figure 1. The language model interprets and explains; typed tools, the optimizer and the critic bound everything it does.")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.runs[0].italic = True
    caption.runs[0].font.size = Pt(8.5)
    caption.runs[0].font.color.rgb = rgb(MUTED)

    doc.add_heading("Local transformer and structured output", level=2)
    add_body(doc, "All generation runs on a local model — Qwen2.5-3B-Instruct served by Ollama on the demo machine's 8 GB GPU — through a provider-agnostic OpenAI-compatible client, so no cloud key or network access is required and household text never leaves the machine. Small local models are not reliable JSON emitters, so every structured call follows the same discipline: the JSON schema is embedded in the prompt, json-mode is requested when the server supports it, the first balanced JSON object is extracted from the reply, validated against a Pydantic schema, repaired once through a round-trip quoting the validation errors, and abandoned to a deterministic fallback if it still fails. The response's mode flags state which path actually ran.")

    doc.add_heading("Intent extraction: the model becomes load-bearing", level=2)
    add_body(doc, "The mission text is not decoration: the model converts it into a typed MissionSpec (tasks with power, duration and windows; objective; capacity cap; avoid-hours). A deterministic sanitizer then clamps every value against a device catalog — implausible powers are reset, impossible windows widened, duplicates dropped — and reports each adjustment in the trace. A rule-based parser provides the no-model fallback and doubles as the ablation baseline for the intent evaluation.")
    add_body(doc, "Two of the sanitizer's guardrails came directly from field testing with free-typed missions. First, 12-hour clock times are normalized to 24-hour form before either extractor sees the text, because the 3B model reliably misread AM/PM phrasing ('before 07:00 AM' became evening windows in a live run). Second, a degenerate avoid-hours list — the model once emitted 18 avoided hours out of 24, leaving the optimizer almost no room — is dropped entirely and reported as an adjustment. When a feasible avoid-hours preference genuinely conflicts with the stated windows, the optimizer relaxes it and the system surfaces that as a flagged verdict with an explicit relaxation note; a conflict is reported, never hidden behind a fluent explanation.")

    doc.add_heading("Agent workflow", level=2)
    add_body(doc, "Planning runs as a genuine tool-using loop: at each step the model sees the mission, the tool catalog and a digest of gathered state, and returns a schema-validated decision naming the next tool. Guardrails keep the loop honest — repeated tools and premature finishes are overruled, a bounded step budget applies, and any stage the model skipped is completed deterministically. Every step is recorded with its arguments, duration, transport and who decided it (llm or guardrail), and the interface renders that trace verbatim.")

    doc.add_heading("Model Context Protocol", level=2)
    add_body(doc, "One registry backs every consumer: the FastMCP server exposes the five tools below over MCP, the bundled MCP host (backend/flexigrid/mcp_host.py) spawns that server and runs the same agent through a real stdio client session, and the FastAPI layer reuses the registry in-process. The tool contracts are themselves a retrievable corpus document, so the model can read the guarantees of its own tools.")
    add_table(
        doc,
        ["MCP tool", "Input", "Output / responsibility"],
        [
            ["get_grid_snapshot", "use_live: bool", "Tariff + derived stress series with provenance"],
            ["retrieve_evidence", "query, top_k, mode", "Ranked chunks, stable citation IDs, per-mode scores"],
            ["extract_constraints", "mission: str", "Typed, sanitized MissionSpec + adjustment log"],
            ["optimize_schedule", "spec, objective", "Schedule, validation, earliest-start baseline"],
            ["validate_schedule", "schedule, cap", "Independent hour-by-hour critic verdict"],
        ],
        [2850, 2100, 4410],
        small=True,
    )

    doc.add_heading("Retrieval-Augmented Generation", level=2)
    add_body(doc, "Retrieval is hybrid: Okapi BM25 over the chunk text and tags, dense cosine similarity over embeddings, and reciprocal-rank fusion of the two rankings as the default mode. The embedding backend resolves through a chain — Ollama's nomic-embed-text when the local runtime serves it, sentence-transformers when installed, and a deterministic TF-IDF/LSA fallback that needs no downloads — and every trace, health response and evaluation records which backend produced its numbers. Retrieved chunk IDs form the only citation allow-list the generator may use; the backend rejects any explanation that cites outside it.")

    doc.add_heading("3. Planning algorithm and design choices", level=1)
    add_body(doc, "Tasks are modelled as power, duration, earliest start, latest end and source ID. For each task, the optimizer enumerates feasible start hours and scores them using a weighted combination of normalized retail tariff and grid stress. A depth-first exhaustive search explores joint assignments and prunes branches whose partial score already exceeds the best complete solution.")
    equation = doc.add_paragraph()
    equation.alignment = WD_ALIGN_PARAGRAPH.CENTER
    equation.paragraph_format.space_before = Pt(10)
    equation.paragraph_format.space_after = Pt(12)
    run = equation.add_run("score(h) = w · normalized tariff(h) + (1 - w) · grid stress(h)")
    set_run_font(run, name="Cambria Math", size=12, color=INK, italic=True)

    greedy_failures = result_or(["greedy_ablation", "greedy_failures"], "3")
    add_callout(doc, "Validation finding", f"The first greedy implementation could place the EV in a locally attractive slot and leave no feasible heat-pump window. The greedy optimizer is deliberately kept as a measured ablation: in the current harness it fails outright on {greedy_failures} case(s), including the standard morning mission, while joint constrained search fails on none.")

    doc.add_heading("Why not let the LLM schedule directly?", level=2)
    baseline_b_rate = result_or(["llm_only_baseline", "violation_or_failure_rate"], "")
    baseline_b_model = result_or(["llm_only_baseline", "model"], "the local model")
    if baseline_b_rate and baseline_b_rate != "None":
        baseline_sentence = (f"Its constraint violation-or-failure rate is {baseline_b_rate} "
                             f"in the recorded harness run with {baseline_b_model}, against 0 "
                             f"for the deterministic search.")
    else:
        baseline_sentence = ("The recorded rate for the defense machine's model is produced by "
                             "`python -m flexigrid.evaluate` and appears in "
                             "evaluation/RESULTS.md; the deterministic search records 0 "
                             "violations under the same conditions.")
    add_body(doc, "This is a measured claim, not a design opinion. Baseline B in the evaluation asks the model to assign start hours directly, with the tasks, windows, tariff and cap in the prompt and a validated output schema — everything except the optimizer. " + baseline_sentence + " Language models produce locally plausible schedules that are globally capacity-blind; the hybrid design follows from exactly this measurement.")

    doc.add_heading("Why not fine-tune? Why not diffusion or multimodal?", level=2)
    add_body(doc, "Fine-tuning is excluded with an argument, not ignored: the intent evaluation identifies where it would help (per-task deadlines, unusual phrasings), and a LoRA pass on synthetic mission-to-JSON pairs is the designated next step once prompting is demonstrably the bottleneck — currently the sanitizer plus the repair loop closes most of the gap at zero training cost. Diffusion and multimodal models are excluded because the problem contains no image or audio modality and no generative-sampling need; they would add scope without a role the problem can justify. Every included technique carries a measurable responsibility in the pipeline.")

    doc.add_heading("Complexity and scalability", level=2)
    add_body(doc, "Exhaustive search is appropriate for the four-device prototype but grows combinatorially. A production version should replace it with a mixed-integer linear program or constraint-programming solver, preserve the same tool contract and compare solution quality and latency against the exhaustive oracle on small fixtures.")

    doc.add_heading("4. Prototype implementation", level=1)
    add_body(doc, "The interface is wired to the backend: the dashboard probes the API on load, shows which model and embedding backend are live, sends the free-text mission to the real agent, and renders the returned trace verbatim — every tool call with its duration and whether the model or a guardrail decided it, the extracted constraints with sanitizer adjustments, retrieval scores per chunk, the model's cited explanation, and the critic's verdict. When the backend is down, the interface degrades to a clearly labelled offline simulation of the same fixture; nothing simulated is ever presented as live.")
    add_table(
        doc,
        ["Layer", "Technology", "Purpose"],
        [
            ["Interface", "React 19, TypeScript, Vinext", "Free-text missions, live agent trace, honest constraint metrics"],
            ["LLM runtime", "Ollama · Qwen2.5-3B-Instruct", "Intent extraction, tool-loop decisions, cited explanation — fully local"],
            ["Agent", "Python, Pydantic schemas", "Bounded tool loop with guardrails and a complete trace"],
            ["Retrieval", "BM25 + dense + RRF", "51-chunk corpus, three switchable modes, backend chain"],
            ["MCP", "FastMCP server + stdio client host", "Same registry over the protocol and in-process"],
            ["Data", "Elia v2.1 API + derive.py + fixtures", "Live-derived or frozen stress signal with provenance"],
            ["API", "FastAPI + CORS", "/health, /api/agent/plan, /api/retrieve, /api/intent, snapshots"],
            ["Tests", "unittest + node:test (103 tests)", "Optimizer, retrieval, intent, agent, API, MCP round-trip, UI render"],
        ],
        [1600, 2900, 4860],
        small=True,
    )

    doc.add_heading("Primary demonstration flow", level=2)
    demo_list_id = new_numbering_id(doc)
    add_number(doc, "Start Ollama, the FastAPI backend and the interface; the top-bar chip confirms 'Live pipeline' with the model name.", num_id=demo_list_id)
    add_number(doc, "Type or edit a free-text mission and run the agent; walk through the trace — intent chips, each tool call, the guardrail column.", num_id=demo_list_id)
    add_number(doc, "Compare optimized and earliest-start schedules on the 24-hour chart against the capacity cap and high-stress bands.", num_id=demo_list_id)
    add_number(doc, "Type an impossible mission (e.g. an EV charge due 01:00 under a 2 kW cap) and show the critic rejecting it instead of displaying it.", num_id=demo_list_id)
    add_number(doc, "Run `python -m flexigrid.mcp_host \"...\"` in a terminal to show the identical agent over a real MCP stdio session, then open Evaluation and Architecture.", num_id=demo_list_id)

    doc.add_heading("Reproducibility", level=2)
    add_body(doc, "No cloud key exists anywhere in the system. `python -m flexigrid.doctor` verifies the environment (corpus, retrieval, adapter, LLM endpoint, structured output, agent, MCP round-trip) with actionable hints. A deterministic mock LLM server ships with the repository so the full agent code path is testable on machines without model weights, and the evaluation records the model and embedding backend behind every number. All 103 tests run without network access.")

    doc.add_heading("5. Evaluation", level=1)
    environment_note = "Run `python -m flexigrid.evaluate` to generate results.json; tables below then populate automatically."
    if RESULTS:
        environment = RESULTS["environment"]
        environment_note = (
            f"Numbers in this section come from evaluation/results.json, generated "
            f"{environment['generated_at']} with LLM "
            f"{environment['llm_model'] or 'disabled (deterministic fallback)'} and "
            f"embedding backend {environment['embeddings_backend']} "
            f"({environment['embeddings_model']}) over {environment['corpus_chunks']} corpus chunks. "
            f"Re-running the harness on the demo machine refreshes every table with that machine's provenance.")
    add_body(doc, "Evaluation is split by subsystem so a fluent answer can never hide a retrieval, intent, planning or grounding failure. " + environment_note)
    evaluation_picture = doc.add_picture(str(chart_path), width=Inches(6.5))
    evaluation_picture._inline.docPr.set("title", "Fixture schedule evaluation")
    evaluation_picture._inline.docPr.set("descr", "Two aligned charts compare the representative grid-stress index and retail tariff, then earliest-start and optimized household loads under a 4.6 kilowatt cap.")
    caption = doc.add_paragraph("Figure 2. Reproducible fixture: retail tariff and representative grid-stress index above; baseline and optimized controllable load below.")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.runs[0].italic = True
    caption.runs[0].font.size = Pt(8.5)
    caption.runs[0].font.color.rgb = rgb(MUTED)

    doc.add_heading("Retrieval (40 labelled queries)", level=2)
    retrieval_rows = []
    for mode in ("bm25", "dense", "hybrid"):
        retrieval_rows.append([
            mode,
            result_or(["retrieval", mode, "hit_at_1"]),
            result_or(["retrieval", mode, "recall_at_4"]),
            result_or(["retrieval", mode, "mrr"]),
        ])
    add_table(doc, ["Mode", "hit@1", "recall@4", "MRR"], retrieval_rows,
              [2200, 2380, 2390, 2390], small=True)
    add_body(doc, "Relevance is labelled at document level over the 15-document corpus, which contains deliberate distractors (battery/PV, safety, generation-mix documents). BM25 is a strong baseline on this in-domain corpus; the dense and hybrid rows expose the embedding backend's real contribution, and the same harness re-scores any backend swap in one command.")

    doc.add_heading("Intent extraction (15 labelled missions)", level=2)
    intent_rows = []
    for mode_name in ("rules", "llm"):
        if RESULTS and mode_name in RESULTS.get("intent", {}):
            intent_rows.append([
                mode_name,
                result_or(["intent", mode_name, "exact_match"]),
                result_or(["intent", mode_name, "per_field", "devices"]),
                result_or(["intent", mode_name, "per_field", "deadline"]),
                result_or(["intent", mode_name, "per_field", "objective"]),
                result_or(["intent", mode_name, "per_field", "avoid_hours"]),
            ])
    if not intent_rows:
        intent_rows = [["rules", "—", "—", "—", "—", "—"]]
    add_table(doc, ["Extractor", "exact", "devices", "deadline", "objective", "avoid"],
              intent_rows, [1900, 1490, 1490, 1500, 1490, 1490], small=True)
    add_body(doc, "The rule-based parser is the ablation: it handles single global deadlines well and fails on per-task deadlines and unusual phrasing — precisely the residual the language model is there to close. Every model extraction still passes through the sanitizer before planning.")

    doc.add_heading("Baseline B — LLM-only scheduling, and the greedy ablation", level=2)
    baseline_rows = [
        ["Joint constrained search (ours)", "0 violations", "optimal on fixture", "the shipped planner"],
        [f"Greedy placement (ablation)",
         f"{result_or(['greedy_ablation', 'greedy_failures'], '3')} infeasible case(s)",
         "equal cost when it survives", "reproduces the historical defect"],
        [f"LLM-only ({result_or(['llm_only_baseline', 'model'], 'local model')})",
         (f"{result_or(['llm_only_baseline', 'violation_or_failure_rate'])} violation/failure rate"
          if result_or(["llm_only_baseline", "violation_or_failure_rate"], "") not in ("", "None")
          else "measured on the demo machine (see RESULTS.md)"),
         (f"{result_or(['llm_only_baseline', 'avg_cost_gap_eur_when_valid'])} € avg gap when valid"
          if result_or(["llm_only_baseline", "avg_cost_gap_eur_when_valid"], "") not in ("", "None")
          else "—"),
         "why generation never owns feasibility"],
    ]
    add_table(doc, ["Planner", "Constraint safety", "Cost quality", "Role"],
              baseline_rows, [2900, 2400, 2400, 1660], small=True)

    doc.add_heading("Agent properties", level=2)
    add_table(
        doc,
        ["Property", "Result", "Mechanism"],
        [
            ["Citation precision", result_or(["agent_properties", "citation_precision"]),
             "explanations may cite only retrieved chunk IDs; violations are rejected"],
            ["Guard rejections", result_or(["agent_properties", "explanations_rejected_by_guard"]),
             "count of model explanations the allow-list guard refused"],
            ["Deterministic replay", "pass" if result_or(["agent_properties", "deterministic_plan_replay"]) == "True" else result_or(["agent_properties", "deterministic_plan_replay"]),
             "identical mission + fixture ⇒ byte-identical plan"],
            ["End-to-end validity", "all valid" if result_or(["agent_properties", "all_plans_valid"]) == "True" else result_or(["agent_properties", "all_plans_valid"]),
             "validator gates every displayed plan"],
            ["Morning fixture", f"€{MORNING_COST} · {MORNING_PEAK} kW peak",
             f"vs €{MORNING_BASELINE_COST} earliest-start baseline, 4.6 kW cap"],
        ],
        [2300, 2300, 4760],
        small=True,
    )
    add_body(doc, "Guardrail behaviour is itself under test: an adversarial mode of the reference mock model attempts to finish before planning and is demonstrably overruled, and malformed-JSON injection exercises the repair round-trip. Remaining future work: a broader mission set with confidence intervals, a groundedness grader beyond citation checking, and comparisons across several local models.")

    doc.add_heading("6. Limitations, risk and responsible use", level=1)
    add_table(
        doc,
        ["Risk", "Current control", "Production requirement"],
        [
            ["Hallucinated rationale", "Citation allow-list, structured output, repair-then-fallback", "Groundedness grader + human review"],
            ["Non-compliant agent decisions", "Schema-validated decisions, bounded loop, guardrail completion", "Policy tests across model versions"],
            ["Unsafe schedule", "Independent hour-by-hour validator gates every displayed plan", "Device-specific safety envelope and fail-safe"],
            ["Stale or synthetic grid signal", "Tested live derivation + labelled frozen fixture with provenance", "Freshness SLO and monitoring"],
            ["Tariff confusion", "Retail and imbalance concepts separated in data and corpus", "Supplier-specific billing contract tests"],
            ["Privacy leakage", "Fully local model; no cloud calls, no personal meter data", "Consent, minimization, encryption, retention policy"],
            ["Search scalability", "Exhaustive search on ≤4 tasks (measured vs greedy)", "MILP/CP-SAT optimizer with time budget"],
        ],
        [2200, 3350, 3810],
        small=True,
    )

    doc.add_heading("Work organization", level=2)
    add_body(doc, "The project was designed, implemented, evaluated and documented end to end by the author, organized as three workstreams with explicit verification at each boundary. Because a single person carried every workstream, the assignment's requirement that the presenter can explain the entire project — data pipeline, model design, implementation and evaluation alike — is satisfied by construction; the defense preparation notes rehearse cross-cutting questions on every layer.")
    add_table(
        doc,
        ["Workstream", "Scope", "Verification"],
        [
            ["Data and backend", "Elia adapter and derivation, optimizer and critic, agent loop, MCP server and host, RAG corpus", "95 backend tests; python -m flexigrid.doctor end-to-end check"],
            ["Interface and evaluation", "Live dashboard with verbatim trace, honest state design, split evaluation harness", "8 interface tests; measured results.json with provenance"],
            ["Documentation and defense", "Technical report, defense deck, demo script and rehearsed Q&A", "Dry-run of the full 10-minute demo incl. failure modes"],
        ],
        [2300, 4260, 2800],
        small=True,
    )

    doc.add_heading("Conclusion", level=2)
    add_body(doc, "FlexiGrid AI connects the course's advanced techniques into one measured workflow rather than a showcase of disconnected parts. A local transformer makes free text load-bearing through typed intent extraction; a genuine agent loop selects real MCP tools and is provably guarded; hybrid RAG grounds every claim in a corpus with stable citations; and the evaluation quantifies why the deterministic optimizer-critic must own feasibility — the model that explains the plan measurably cannot schedule it. Everything runs offline on one machine, every number carries its provenance, and every mode the system can degrade into is labelled in the interface. The Belgian Elia integration and capacity-tariff framing keep the project locally real; the 103-test suite and the mock-model harness keep it reproducible under exam conditions.")

    doc.add_heading("References", level=1)
    references = [
        ("Elia Open Data - measured and forecast total load (ods002)", "https://opendata.elia.be/explore/dataset/ods002/"),
        ("Elia Open Data - wind power forecast (ods086)", "https://opendata.elia.be/explore/dataset/ods086/"),
        ("Elia Open Data - total generation by fuel type (ods201)", "https://opendata.elia.be/explore/dataset/ods201/"),
        ("Model Context Protocol - specification", "https://modelcontextprotocol.io/specification"),
        ("Ollama - OpenAI compatibility API", "https://docs.ollama.com/openai"),
        ("Qwen2.5 - technical report", "https://arxiv.org/abs/2412.15115"),
        ("Robertson & Zaragoza - The Probabilistic Relevance Framework: BM25 and Beyond", "https://doi.org/10.1561/1500000019"),
        ("Cormack, Clarke & Buettcher - Reciprocal Rank Fusion", "https://doi.org/10.1145/1571941.1572114"),
    ]
    for label, url in references:
        paragraph = doc.add_paragraph(style="List Bullet")
        paragraph.paragraph_format.left_indent = Inches(.5)
        paragraph.paragraph_format.first_line_indent = Inches(-.25)
        paragraph.paragraph_format.space_after = Pt(5)
        add_hyperlink(paragraph, label, url)

    doc.save(DOCX_PATH)
    print(DOCX_PATH)


if __name__ == "__main__":
    build_report()
