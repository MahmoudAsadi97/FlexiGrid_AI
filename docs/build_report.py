from __future__ import annotations

import math
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/flexigrid-matplotlib")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

OUTPUT_DIR = Path("/workspace/deliverables/flexigrid-ai")
ASSET_DIR = OUTPUT_DIR / "assets"
DOCX_PATH = OUTPUT_DIR / "FlexiGrid_AI_Technical_Report.docx"

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

TARIFF = [
    0.22, 0.18, 0.16, 0.15, 0.14, 0.15, 0.19, 0.27, 0.31, 0.29, 0.25, 0.23,
    0.21, 0.20, 0.22, 0.28, 0.37, 0.46, 0.42, 0.34, 0.28, 0.24, 0.21, 0.19,
]
GRID_STRESS = [48, 42, 38, 34, 31, 33, 45, 59, 71, 76, 68, 55, 42, 35, 29, 32, 51, 78, 91, 86, 70, 58, 52, 47]
OPTIMIZED_LOAD = [0, 0, 3.6, 3.6, 2.7, 1.9] + [0] * 18
BASELINE_LOAD = [4.1, 4.1, 0.8, 1.4, 1.4] + [0] * 19


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
        (2, "1", "Bounded mission", "Natural language"),
        (27, "2", "Lexical RAG", "Cited constraints"),
        (52, "3", "MCP tools", "Elia + devices"),
        (77, "4", "Planner + critic", "Validated output"),
    ]
    for index, (x, number, title, subtitle) in enumerate(stages):
        fill = "#0B1714" if index == 3 else "#EEF3F0"
        title_color = "white" if index == 3 else "#0B1714"
        box = FancyBboxPatch((x, 6), 20, 13, boxstyle="round,pad=.7,rounding_size=1.4", facecolor=fill, edgecolor="#DDE6E1", linewidth=1)
        ax.add_patch(box)
        ax.text(x + 2, 16.5, number, fontsize=8, color="#1C7C66" if index != 3 else "#AEE637", fontweight="bold")
        ax.text(x + 2, 12.7, title, fontsize=10, color=title_color, fontweight="bold")
        ax.text(x + 2, 9.4, subtitle, fontsize=7.5, color="#6C7C76" if index != 3 else "#A6B5AF")
        if index < 3:
            ax.add_patch(FancyArrowPatch((x + 20.6, 12.5), (x + 25.2, 12.5), arrowstyle="-|>", mutation_scale=10, linewidth=1.2, color="#87968F"))
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
    run = subtitle.add_run("Evidence-grounded household energy planning with RAG, agents, MCP tools and Elia Open Data")
    set_run_font(run, size=15, color=INK_2)

    add_callout(
        doc,
        "Project thesis",
        "Use retrieval and structured generation to explain bounded household missions, while keeping energy scheduling and safety constraints deterministic, testable and reproducible.",
        fill="E9F2ED",
    )

    metrics = doc.add_table(rows=1, cols=3)
    set_table_geometry(metrics, [3120, 3120, 3120])
    entries = [
        ("3 + 1", "advanced techniques", "RAG, agents, MCP, transformer"),
        ("9/9", "fixture configurations", "hard constraints passed"),
        ("18%", "fixture improvement", "cost and grid exposure vs baseline"),
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
    r = meta.add_run("AUTHORS")
    set_run_font(r, size=8, color=MUTED, bold=True)
    add_body(doc, "Nima Asadi and project partner", after=2)
    add_body(doc, "Team of two  •  August 2026  •  Howest", after=0)

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
    props.subject = "Generative AI assignment"
    props.author = "Nima Asadi and project partner"
    props.keywords = "RAG, MCP, agents, Elia, energy flexibility, generative AI"

    add_cover(doc)

    doc.add_heading("Executive summary", level=1)
    add_body(doc, "FlexiGrid AI is a household energy flexibility copilot for Belgium. A user states a goal such as charging an electric vehicle, pre-heating a home and completing appliances before a deadline. The system retrieves the relevant device and household constraints, calls typed grid-data tools, computes a feasible 24-hour schedule and generates a cited explanation. The prototype intentionally separates language generation from physical feasibility: a deterministic validator, not the language model, decides whether a plan is safe to display.")
    add_callout(doc, "Recommendation", "Submit FlexiGrid AI as the project. It demonstrates several advanced generative AI techniques in one coherent workflow, uses a credible Belgian data source, has measurable failure criteria and fits a 10-minute demonstration.")

    doc.add_heading("Problem definition", level=1)
    add_body(doc, "Households with an EV, heat pump and flexible appliances face competing objectives: finish tasks before deadlines, maintain comfort, avoid a connection-capacity peak and shift consumption away from grid-stress periods. Existing energy dashboards expose curves but still require the resident to translate those curves into a schedule. A generic chatbot is not sufficient because fluent text can violate power limits or confuse market prices with consumer tariffs.")
    doc.add_heading("Target user and success definition", level=2)
    add_body(doc, "The target user is a Belgian household or energy-coaching professional who needs an understandable next-day plan. Success is not defined as 'helpful text'. A successful response must satisfy every time window, stay at or below the configured 4.6 kW controllable-load cap, cite the evidence used, keep retail pricing separate from Elia imbalance-market concepts, and produce the same result when the frozen fixture and parameters are unchanged.")

    doc.add_heading("Project objectives", level=2)
    for item in (
        "Represent three natural-language household missions as typed, reproducible planning requests.",
        "Ground all device, comfort and data-source claims in retrieved chunks.",
        "Expose Elia, household and optimizer functions through MCP-style tools.",
        "Generate explanations only after the schedule passes deterministic validation.",
        "Evaluate retrieval, tool use, planning correctness and generation separately.",
    ):
        add_bullet(doc, item)

    doc.add_page_break()
    doc.add_heading("1. Data selection and pipeline", level=1)
    add_body(doc, "Elia, Belgium's transmission system operator, publishes open datasets through an Opendatasoft API. Three datasets define the grid-data contract for FlexiGrid AI. The live adapter preserves raw records and retrieval timestamps. The submitted planner uses a clearly labelled representative 0-100 stress fixture; deriving that signal from changing live schemas remains future pipeline work. This keeps the demo reproducible and prevents synthetic values from being presented as observations.")
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
    add_number(doc, "Fetch up to 100 recent records per supported dataset from Elia's v2.1 records endpoint.", num_id=data_list_id)
    add_number(doc, "Preserve dataset identifier, raw records and an ISO retrieval timestamp for reproducibility.", num_id=data_list_id)
    add_number(doc, "Return raw live records when explicitly enabled; otherwise use the frozen fixture.", num_id=data_list_id)
    add_number(doc, "Keep the representative 0-100 stress fixture labelled as demo data until a schema-tested live normalization stage is implemented.", num_id=data_list_id)
    add_callout(doc, "Important semantic guardrail", "Elia imbalance prices are settlement signals for balance responsible parties, not a household retail tariff. FlexiGrid therefore uses a separate labelled retail-tariff fixture for cost optimization.", fill="FFF4E8", accent="B46931")

    doc.add_heading("Privacy and EU constraints", level=2)
    add_body(doc, "The submitted prototype uses no personal smart-meter records and stores no user identity. A production pilot would require explicit household consent, data minimization, retention limits, device authentication, audit logs and a controller/processor assessment under GDPR. The prototype remains advisory: it does not send commands to physical devices.")

    doc.add_page_break()
    doc.add_heading("2. Technical architecture", level=1)
    architecture_picture = doc.add_picture(str(architecture_path), width=Inches(6.5))
    architecture_picture._inline.docPr.set("title", "FlexiGrid AI control flow")
    architecture_picture._inline.docPr.set("descr", "Four-stage flow: bounded mission, lexical RAG, MCP tools, then deterministic planner and critic.")
    caption = doc.add_paragraph("Figure 1. The language model is bounded by retrieved evidence, typed tools and a deterministic validator.")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.runs[0].italic = True
    caption.runs[0].font.size = Pt(8.5)
    caption.runs[0].font.color.rgb = rgb(MUTED)

    doc.add_heading("Retrieval-Augmented Generation", level=2)
    add_body(doc, "The retriever indexes short chunks from device manuals, a household comfort policy, the connection-capacity rule, tariff semantics and Elia dataset descriptions. The current baseline uses transparent lexical overlap and returns top-k = 4 chunks. This is deliberately small and reproducible; the next scaling step is a hybrid BM25 plus embedding retriever with a reranker. Retrieved chunk IDs become the only citation IDs the generator is allowed to return.")

    doc.add_heading("Agent workflow", level=2)
    add_body(doc, "The workflow separates planning and criticism. The planner receives the typed tasks and objective. The critic independently checks the output against time windows and hourly power. Only a valid plan is passed to the explanation model. If validation fails, the plan is rejected rather than repaired through persuasive prompting.")

    doc.add_heading("Model Context Protocol", level=2)
    add_table(
        doc,
        ["MCP tool", "Input", "Output / responsibility"],
        [
            ["get_elia_grid_snapshot", "use_live: bool", "Live records or frozen fixture with provenance"],
            ["retrieve_household_evidence", "query, top_k", "Ranked chunks with stable citation IDs"],
            ["get_demo_device_constraints", "none", "Typed power, duration and time windows"],
            ["optimize_household_plan", "objective", "Schedule, metrics and validator result"],
        ],
        [2850, 2100, 4410],
        small=True,
    )

    doc.add_page_break()
    doc.add_heading("Transformer model and structured output", level=2)
    add_body(doc, "When an API key and model are configured, the backend calls the OpenAI Responses API with a Pydantic Explanation schema. The response contains a concise summary, two to four rationale statements, citation IDs and a limitation. The backend rejects any citation ID that is not present in the retrieved evidence. Without a key, the same endpoint returns a deterministic cited explanation, keeping the prototype fully demonstrable offline.")

    doc.add_heading("3. Planning algorithm and design choices", level=1)
    add_body(doc, "Tasks are modelled as power, duration, earliest start, latest end and source ID. For each task, the optimizer enumerates feasible start hours and scores them using a weighted combination of normalized retail tariff and grid stress. A depth-first exhaustive search explores joint assignments and prunes branches whose partial score already exceeds the best complete solution.")
    equation = doc.add_paragraph()
    equation.alignment = WD_ALIGN_PARAGRAPH.CENTER
    equation.paragraph_format.space_before = Pt(10)
    equation.paragraph_format.space_after = Pt(12)
    run = equation.add_run("score(h) = w · normalized tariff(h) + (1 - w) · grid stress(h)")
    set_run_font(run, name="Cambria Math", size=12, color=INK, italic=True)

    add_callout(doc, "Validation finding", "The first greedy implementation could place the EV in a locally attractive slot and leave no feasible heat-pump window. Automated tests exposed this defect. The algorithm was replaced with joint constrained search; all nine scenario-objective combinations now pass.")

    doc.add_heading("Why not let the LLM schedule directly?", level=2)
    add_body(doc, "The current model layer explains an already validated bounded mission; it does not claim arbitrary intent extraction. Exact power and deadline constraints are represented as code. This hybrid design improves reliability, makes failures reproducible and gives the exam team a clear baseline. It also reduces model cost because the optimizer does not consume tokens.")

    doc.add_heading("Why not fine-tune?", level=2)
    add_body(doc, "Fine-tuning is not justified for this deadline or data volume. The changing knowledge consists mainly of manuals, household preferences and public grid feeds, which are better handled through retrieval and tools. Fine-tuning would be considered only after collecting a sizeable labelled set of intent-to-constraint examples and showing that prompting plus retrieval remains the bottleneck.")

    doc.add_heading("Complexity and scalability", level=2)
    add_body(doc, "Exhaustive search is appropriate for the four-device prototype but grows combinatorially. A production version should replace it with a mixed-integer linear program or constraint-programming solver, preserve the same tool contract and compare solution quality and latency against the exhaustive oracle on small fixtures.")

    doc.add_page_break()
    doc.add_heading("4. Prototype implementation", level=1)
    add_body(doc, "The submission contains a polished responsive interface and a separate Python technical backend. The interface demonstrates the complete user flow without external secrets; the backend shows the real RAG, Elia, MCP, optimizer and optional model integration that would power a production API.")
    add_table(
        doc,
        ["Layer", "Technology", "Purpose"],
        [
            ["Interface", "React 19, TypeScript, Vinext", "Scenario selection, schedule visualization, evidence and tool trace"],
            ["API", "FastAPI, Pydantic", "Typed plan and grid-snapshot endpoints"],
            ["GenAI", "OpenAI Responses API", "Schema-constrained cited explanation"],
            ["MCP", "Python MCP SDK / FastMCP", "Interoperable typed energy tools"],
            ["Data", "Elia v2.1 API + JSON fixture", "Belgian load, wind and generation context"],
            ["Tests", "Node test + unittest", "Rendered UI, optimizer, retrieval and reproducibility"],
        ],
        [1600, 2900, 4860],
        small=True,
    )

    doc.add_heading("Primary demonstration flow", level=2)
    demo_list_id = new_numbering_id(doc)
    add_number(doc, "Choose Morning, Grid friendly or Peak shield, then select Balanced, Cost or Grid support.", num_id=demo_list_id)
    add_number(doc, "Run the agent plan and watch retrieval, MCP tool calls, optimization and criticism progress.", num_id=demo_list_id)
    add_number(doc, "Compare optimized and earliest-start schedules on the 24-hour chart.", num_id=demo_list_id)
    add_number(doc, "Inspect cost, grid-stress, hard-constraint and evidence metrics.", num_id=demo_list_id)
    add_number(doc, "Open Evaluation to defend the measured results, then Architecture to explain design choices.", num_id=demo_list_id)

    doc.add_heading("Reproducibility", level=2)
    add_body(doc, "The public interface requires no API key. The repository README gives exact commands for the UI, FastAPI service, MCP server, live snapshot script and both test suites. Dependency ranges are constrained, the fixture is versioned and every displayed benchmark number is calculated from deterministic runs rather than copied from a model response.")

    doc.add_page_break()
    doc.add_heading("5. Evaluation", level=1)
    add_body(doc, "Evaluation is split by subsystem. This prevents a strong-looking natural-language answer from hiding retrieval, tool or optimization failures. The current automated suite covers nine combinations in the browser-side engine and three objective modes in the Python engine.")
    evaluation_picture = doc.add_picture(str(chart_path), width=Inches(6.5))
    evaluation_picture._inline.docPr.set("title", "Fixture schedule evaluation")
    evaluation_picture._inline.docPr.set("descr", "Two aligned charts compare the representative grid-stress index and retail tariff, then earliest-start and optimized household loads under a 4.6 kilowatt cap.")
    caption = doc.add_paragraph("Figure 2. Reproducible fixture: retail tariff and representative grid-stress index above; baseline and optimized controllable load below.")
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.runs[0].italic = True
    caption.runs[0].font.size = Pt(8.5)
    caption.runs[0].font.color.rgb = rgb(MUTED)

    doc.add_heading("Automated results", level=2)
    add_table(
        doc,
        ["Metric", "Result", "Basis", "Acceptance criterion"],
        [
            ["Constraint pass rate", "100% (9/9)", "3 scenarios × 3 objectives", "100%"],
            ["Cost non-regression", "100% (9/9)", "Compared with earliest-start baseline", "≥ 90%"],
            ["Morning fixture peak", "3.6 kW", "Hour-by-hour validator", "≤ 4.6 kW"],
            ["Morning fixture cost", "€1.79", "Frozen retail tariff", "Lower than €2.17 baseline"],
            ["Determinism", "Pass", "Repeated plan deep equality", "Identical output"],
            ["EV retrieval", "Rank 1", "Labelled lexical query", "EV manual first"],
        ],
        [2500, 1450, 3260, 2150],
        small=True,
    )
    add_body(doc, "These numbers validate the deterministic prototype, not generalize an LLM benchmark. Before claiming model quality, the team should label at least 30 unseen prompts and report retrieval recall@4, citation precision, tool-selection accuracy, groundedness and task success with bootstrap confidence intervals.")

    doc.add_heading("Baselines and ablations", level=2)
    for item in (
        "Baseline A: earliest feasible start, which satisfies constraints but ignores signals.",
        "Baseline B: LLM-only scheduling, evaluated for constraint violations and invented citations.",
        "Ablation 1: remove RAG to measure evidence-groundedness loss.",
        "Ablation 2: remove the critic to measure invalid-plan display rate.",
        "Ablation 3: replace exhaustive search with greedy placement to reproduce the discovered failure.",
    ):
        add_bullet(doc, item)

    doc.add_heading("6. Limitations, risk and responsible use", level=1)
    add_table(
        doc,
        ["Risk", "Current control", "Production requirement"],
        [
            ["Hallucinated rationale", "Citation allow-list and structured output", "Groundedness grader + human review"],
            ["Unsafe schedule", "Deterministic hard-constraint validator", "Device-specific safety envelope and fail-safe"],
            ["Stale or synthetic grid signal", "Timestamped raw adapter + explicit fixture label", "Schema-tested live derivation, freshness SLO and monitoring"],
            ["Tariff confusion", "Retail and imbalance concepts separated", "Supplier-specific billing contract tests"],
            ["Privacy leakage", "No personal meter data in prototype", "Consent, minimization, encryption and retention policy"],
            ["Search scalability", "Exhaustive search on four tasks", "MILP/CP-SAT optimizer with time budget"],
        ],
        [2200, 3350, 3810],
        small=True,
    )

    doc.add_heading("Team collaboration", level=2)
    add_body(doc, "The work should be divided without creating knowledge silos. Both students must review the complete code path and rehearse the same demo. A practical division is shown below; names can be assigned in the repository issue board while responsibilities remain shared.")
    add_table(
        doc,
        ["Workstream", "Team member A", "Team member B", "Shared verification"],
        [
            ["Data and backend", "Elia adapter, optimizer, MCP tools", "API integration and RAG corpus", "Pair review + backend test run"],
            ["Interface and evaluation", "Dashboard and chart", "Fixture labels and evaluation harness", "UI walkthrough + benchmark review"],
            ["Documentation and defense", "Methods and implementation", "Results, limitations and demo script", "Cross-question rehearsal"],
        ],
        [2050, 2500, 2500, 2310],
        small=True,
    )

    doc.add_heading("Conclusion", level=2)
    add_body(doc, "FlexiGrid AI is technically appropriate for the assignment because the advanced techniques are connected to a concrete workflow. RAG supplies changeable evidence, MCP separates tool contracts, structured generation explains only validated results and deterministic optimization guarantees feasibility. The bounded mission scope and labelled fixture keep current claims honest. The Belgian Elia integration makes the project locally relevant, while the automated acceptance suite makes it reproducible under exam conditions.")

    doc.add_heading("References", level=1)
    references = [
        ("Elia Open Data - measured and forecast total load (ods002)", "https://opendata.elia.be/explore/dataset/ods002/"),
        ("Elia Open Data - wind power forecast (ods086)", "https://opendata.elia.be/explore/dataset/ods086/"),
        ("Elia Open Data - total generation by fuel type (ods201)", "https://opendata.elia.be/explore/dataset/ods201/"),
        ("OpenAI API - Structured model outputs", "https://developers.openai.com/api/docs/guides/structured-outputs"),
        ("Model Context Protocol - specification", "https://modelcontextprotocol.io/specification"),
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
