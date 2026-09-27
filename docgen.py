import io
from pathlib import Path
from docx import Document
from docx.shared import Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from table_helpers import (
    set_font, add_question_heading, add_question_table, add_question_total_row,
    add_grand_total_paragraph, add_marking_guide_question_table,
    set_document_page_setup, set_document_default_font,
    add_information_sheet_image, set_table_fixed_layout_and_grid,
    show_table_borders
)
DEFAULT_COGNITIVE_TARGETS = {
    'knowledge': 20,
    'routine': 35,
    'complex': 30,
    'problem_solving': 15
}

COGNITIVE_LEVELS = ['knowledge', 'routine', 'complex', 'problem_solving']
COGNITIVE_LEVEL_NAMES = {
    'knowledge': 'Knowledge', 'routine': 'Routine',
    'complex': 'Complex', 'problem_solving': 'Problem Solving'
}
DIFFICULTY_TIERS = ['easy', 'medium', 'difficult']
DIFFICULTY_TIER_LABELS = {'easy': 'E', 'medium': 'M', 'difficult': 'D'}

# 2026-09-27: rebuilt to match the approved Task 8 reference format
# (reference/task8_baseline/build.py) -- one row per sub-question (never
# aggregated per top-level QUESTION), 4 cognitive levels x 3 difficulty
# tiers (E/M/D) = 12 mark-columns, each leaf's mark value in exactly one
# cell. Topic(0.75) + Q(0.45) + Sub-topic(1.35) + 12x0.28 tier cells(3.36)
# + Total(0.45) = 6.36in, comfortably under the ~6.69in usable A4 width
# (21cm page - 2x2cm margins) -- the reference's own 6.76in (build.py's
# W=[0.8,0.42,1.6]+[0.29]*12+[0.46]) came from a different template/page
# geometry than this app's no-template generic path.
COGNITIVE_GRID_COL_WIDTHS_IN = [0.75, 0.45, 1.35] + [0.28] * 12 + [0.45]


def _collect_grid_leaves(topics_data: list) -> list:
    """
    Flatten topics_data into one row per LEAF (never per top-level question
    or per stem) -- topic name, sub-question number, grid_label, marks,
    cognitive_level, difficulty_tier. This is the single source of truth
    the grid renderer, and its own column/row-total reconciliation, are
    both built from -- reuses _flatten_topic_hierarchy() so the grid can
    never disagree with the question paper/marking guide about what a
    sub-question's number or marks actually are.
    """
    rows = []
    for qnum, (topic, questions) in enumerate(topics_data, 1):
        flat = _flatten_topic_hierarchy(qnum, questions)
        for r in flat:
            if r.get("is_stem"):
                continue
            leaf = r["leaf"]
            rows.append({
                "topic": topic,
                "num": r["num"],
                "label": leaf.get("grid_label") or "",
                "marks": leaf.get("marks"),
                "level": leaf.get("cognitive_level"),
                "tier": leaf.get("difficulty_tier"),
            })
    return rows


def _flatten_topic_hierarchy(qnum: int, hierarchical_questions: list) -> list:
    """
    Flatten a topic's ordered list of hierarchical question dicts (one per
    archetype slot, as returned by generate_question()/generate_paper())
    into a single numbered row list, assigning composite qnum.i / qnum.i.j
    numbers -- e.g. "1.1", "1.5" (stem), "1.5.1", "1.5.2", "1.6".

    generation.py's own Python-generated numbering inside each dict only
    knows that dict's position within its own archetype call, not its
    position within the whole topic, so it's discarded here in favor of a
    topic-wide sequential index (matches format_SKILL.md's "primary
    sub-question number (1.1, 1.2, 2.1...)" scheme).

    Returns a list of dicts, each either:
      {"num": "1.5", "parts": [...], "marks": None, "is_stem": True}
      {"num": "1.1", "parts": [...], "marks": 3, "leaf": {...}}
      {"num": "1.5.1", "parts": [...], "marks": 2, "leaf": {...}}
    """
    flat = []
    i = 0
    for qdict in hierarchical_questions:
        for row in qdict.get("question_structure", []):
            i += 1
            if row.get("is_stem"):
                flat.append({
                    "num": f"{qnum}.{i}",
                    "parts": row.get("parts", []),
                    "marks": None,
                    "is_stem": True
                })
                for j, child in enumerate(row.get("children", []), 1):
                    flat.append({
                        "num": f"{qnum}.{i}.{j}",
                        "parts": child.get("parts", []),
                        "marks": child.get("marks"),
                        "leaf": child
                    })
            else:
                flat.append({
                    "num": f"{qnum}.{i}",
                    "parts": row.get("parts", []),
                    "marks": row.get("marks"),
                    "leaf": row
                })
    return flat


def _compute_actual_marks(question_groups: list) -> int:
    """
    Sum of leaf marks actually present in the rendered rows -- the single
    source of truth for every printed total (cover page, both grand TOTAL
    paragraphs, cognitive grid). Never trust a caller-supplied total_marks
    figure for display: if a paper generation run silently drops a failed
    slot (see generate_paper()'s generation_errors), a caller-supplied total
    would print a mark value the document doesn't actually contain -- a real
    bug found in the first live run (2026-09-24, see STATUS.md).
    """
    total = 0
    for qnum, questions in question_groups:
        flat = _flatten_topic_hierarchy(qnum, questions)
        total += sum(r['marks'] for r in flat if r['marks'] is not None)
    return total


def parts_to_cell_content(parts: list) -> list:
    """
    Convert generation.py's {"type": "text"|"math", "value": str} parts into
    the format add_cell_content() expects: a list of plain strings and/or
    ('math', latex) tuples. This is what actually routes math content through
    insert_inline_math() into real native Word equation objects, instead of
    every equation being flattened to plain text.
    """
    content = []
    for part in parts:
        if part.get("type") == "math":
            content.append(("math", part.get("value", "")))
        else:
            content.append(part.get("value", ""))
    return content


class DocumentGenerator:
    def __init__(self, template_path: str = None):
        """
        Args:
            template_path: Path to a .docx template with {{PLACEHOLDER}} tokens.
                          If None, create a generic cover page (per PROJECT_BRIEF.md:
                          plain, no branding, no border image -- this wins over
                          task_SKILL.md's richer branded front matter for the MVP).
        """
        self.template_path = template_path
        self.info_sheet_path = Path(__file__).parent / "information_sheet_gr11_gr12.png"

    def _prepare(self, topics_data: list, total_marks: int):
        """
        Shared setup for all three deliverables: computes the sub-numbered
        question_groups and the real (never caller-trusted) actual_total_marks.
        Single source of truth so the QP, MG, and grid can never disagree
        about totals even though they're now three separate files/methods.
        See _compute_actual_marks()'s docstring for why total_marks itself
        is never trusted for anything printed.
        """
        question_groups = [(i + 1, questions) for i, (_, questions) in enumerate(topics_data)]

        actual_total_marks = _compute_actual_marks(question_groups)
        if total_marks is not None and actual_total_marks != total_marks:
            print(
                f"  [docgen] WARNING: requested total_marks={total_marks} but the leaves actually "
                f"present in topics_data sum to {actual_total_marks} -- printing {actual_total_marks} "
                f"(the real figure), not the requested one. This usually means one or more question "
                f"slots failed to generate; check generate_paper()'s generation_errors."
            )
        return question_groups, actual_total_marks

    def _new_document_with_frontmatter(self, topics_data: list, task: str, term: str,
                                       time_minutes: int, actual_total_marks: int,
                                       examiner: str, moderator: str, grade: str):
        """Cover page (or template) + header/footer, shared by the question
        paper. The marking guide and grid don't get a full cover page."""
        topic_display = " & ".join(name for name, _ in topics_data)
        if self.template_path:
            doc = self._load_and_replace_template(
                topic_display, task, term, time_minutes, actual_total_marks, examiner,
                moderator, grade
            )
            # Per format_SKILL.md: a real template supplies its own header/footer/
            # border via its own section properties -- don't override them.
        else:
            doc = Document()
            set_document_page_setup(doc)
            set_document_default_font(doc)
            self._add_generic_cover_page(doc, topic_display, task, term, time_minutes,
                                         actual_total_marks, examiner, moderator, grade)
            # Per today's ruling: header text + page-number footer apply even
            # in the no-template path (task_SKILL.md's frame elements, applied
            # regardless of PROJECT_BRIEF.md's plain-cover-page simplification).
            left_header = f"Mathematics {task}".strip() if task else f"Grade {grade} Mathematics"
            right_header = term or ""
            self._set_header_footer(doc, left_header, right_header)
        return doc

    def generate_question_paper(self, topics_data: list,
                                total_marks: int, task: str = None,
                                term: str = None, time_minutes: int = None,
                                examiner: str = None, moderator: str = None,
                                grade: str = "11",
                                include_information_sheet: bool = True) -> bytes:
        """
        Generate the question paper as its own .docx: cover page, the QUESTION
        N tables (no marking guide, no cognitive grid), followed by the
        information sheet (Grade 11/12). See _prepare()'s docstring re:
        total_marks never being trusted for anything printed.

        Args:
            topics_data: List of (topic_name: str, questions: list[dict]) tuples --
                       see the (former) generate_full_assessment docstring for the
                       full shape.
            total_marks: Advisory only, see _prepare().
            task, term, time_minutes, examiner, moderator: Metadata for cover page/header
            grade: Grade (default "11")
            include_information_sheet: Append the DBE info sheet as the last page
                                        (Grade 11/12 only; per task_SKILL.md)

        Returns:
            .docx file as bytes
        """
        question_groups, actual_total_marks = self._prepare(topics_data, total_marks)
        doc = self._new_document_with_frontmatter(
            topics_data, task, term, time_minutes, actual_total_marks, examiner, moderator, grade
        )

        self._add_question_paper_body(doc, question_groups, actual_total_marks)

        if include_information_sheet and grade in ("11", "12"):
            doc.add_page_break()
            add_information_sheet_image(doc, str(self.info_sheet_path))

        return self._save_to_bytes(doc)

    def generate_marking_guide(self, topics_data: list,
                               total_marks: int, task: str = None,
                               term: str = None, grade: str = "11") -> bytes:
        """
        Generate the marking guide as its own .docx (no question paper, no
        cognitive grid). Keeps the same header/footer treatment as the
        question paper but skips the full metadata cover page -- the
        "MARKING GUIDELINE" heading (added by _add_marking_guide_body) plus
        the header text is enough to identify the document on its own.
        """
        question_groups, actual_total_marks = self._prepare(topics_data, total_marks)

        doc = Document()
        set_document_page_setup(doc)
        set_document_default_font(doc)
        left_header = f"Mathematics {task}".strip() if task else f"Grade {grade} Mathematics"
        right_header = term or ""
        self._set_header_footer(doc, left_header, right_header)

        self._add_marking_guide_body(doc, question_groups, actual_total_marks)

        return self._save_to_bytes(doc)

    def generate_cognitive_grid_xlsx(self, topics_data: list, target_distribution: dict = None) -> bytes:
        """
        Generate the cognitive level analysis grid as a genuine .xlsx
        workbook -- same 16-column structure, one row per sub-question, top
        Prescribed/Actual % and bottom Total/% summary rows, topic labelled
        once per block -- as the docx version, just delivered as a real
        spreadsheet (openpyxl) instead of a Word table so it can be opened,
        sorted, or adapted directly in Excel.
        """
        target_distribution = target_distribution or DEFAULT_COGNITIVE_TARGETS
        return self._build_cognitive_grid_xlsx(topics_data, target_distribution)

    def _load_and_replace_template(self, topic: str, task: str, term: str,
                                   time_minutes: int, total_marks: int,
                                   examiner: str, moderator: str, grade: str):
        """Load a template and replace {{PLACEHOLDER}} tokens."""
        doc = Document(self.template_path)

        replacements = {
            "{{GRADE}}": grade,
            "{{TASK}}": task or "",
            "{{TERM}}": term or "",
            "{{TOTAL}}": str(total_marks),
            "{{TIME}}": f"{time_minutes} minutes" if time_minutes else "",
            "{{EXAMINER}}": examiner or "",
            "{{MODERATOR}}": moderator or "",
            "{{TOPIC}}": topic
        }

        for paragraph in doc.paragraphs:
            for key, value in replacements.items():
                if key in paragraph.text:
                    for run in paragraph.runs:
                        if key in run.text:
                            run.text = run.text.replace(key, value)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for key, value in replacements.items():
                            if key in paragraph.text:
                                for run in paragraph.runs:
                                    if key in run.text:
                                        run.text = run.text.replace(key, value)

        return doc

    def _add_generic_cover_page(self, doc, topic: str, task: str, term: str,
                                time_minutes: int, total_marks: int,
                                examiner: str, moderator: str, grade: str):
        """Plain generic cover page -- no branding, no border image, no logo,
        per PROJECT_BRIEF.md's explicit MVP instruction (wins over task_SKILL.md's
        richer branded two-page front matter for this no-template path)."""
        title = doc.add_paragraph()
        r = title.add_run(f"Grade {grade} Mathematics")
        set_font(r, size=16, bold=True)

        subtitle = doc.add_paragraph()
        r = subtitle.add_run(topic)
        set_font(r, size=14, bold=True)

        info_items = []
        if task:
            info_items.append(f"Task: {task}")
        if term:
            info_items.append(f"Term: {term}")
        if time_minutes:
            info_items.append(f"Time: {time_minutes} minutes")
        info_items.append(f"Total Marks: {total_marks}")
        if examiner:
            info_items.append(f"Examiner: {examiner}")
        if moderator:
            info_items.append(f"Moderator: {moderator}")

        for item in info_items:
            p = doc.add_paragraph()
            r = p.add_run(item)
            set_font(r, size=12)

        doc.add_page_break()

    def _set_header_footer(self, doc, left_text: str, right_text: str):
        """Left/right header text + right-aligned page-number footer field.
        Applied to the no-template generic-cover path per today's ruling."""
        section = doc.sections[0]

        header = section.header
        header.is_linked_to_previous = False
        p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
        for run in list(p.runs):
            run.text = ''
        usable_width = section.page_width - section.left_margin - section.right_margin
        p.paragraph_format.tab_stops.add_tab_stop(usable_width, WD_TAB_ALIGNMENT.RIGHT)
        r_left = p.add_run(left_text)
        set_font(r_left, size=10)
        p.add_run('\t')
        r_right = p.add_run(right_text)
        set_font(r_right, size=10)

        footer = section.footer
        footer.is_linked_to_previous = False
        fp = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        for run in list(fp.runs):
            run.text = ''
        fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        self._add_page_number_field(fp)

    def _add_page_number_field(self, paragraph):
        """Insert a real Word PAGE field (updates automatically), not hand-typed text."""
        run = paragraph.add_run()
        set_font(run, size=10)
        fld_begin = OxmlElement('w:fldChar')
        fld_begin.set(qn('w:fldCharType'), 'begin')
        instr = OxmlElement('w:instrText')
        instr.set(qn('xml:space'), 'preserve')
        instr.text = 'PAGE'
        fld_end = OxmlElement('w:fldChar')
        fld_end.set(qn('w:fldCharType'), 'end')
        run._r.append(fld_begin)
        run._r.append(instr)
        run._r.append(fld_end)

    def _add_question_paper_body(self, doc, question_groups: list, grand_total: int):
        """One QUESTION N heading + one 4-column hidden-border table per group,
        sub-questions numbered N.1, N.2..., a per-question [N] total row inside
        the table, then the standalone bold centred grand TOTAL [N] paragraph."""
        for qnum, questions in question_groups:
            add_question_heading(doc, f"QUESTION {qnum}")
            flat = _flatten_topic_hierarchy(qnum, questions)
            rows = [
                {'num': r['num'], 'parts': parts_to_cell_content(r['parts']), 'marks': r['marks']}
                for r in flat
            ]
            table = add_question_table(doc, rows)
            question_total = sum(r['marks'] for r in flat if r['marks'] is not None)
            add_question_total_row(table, question_total)
            doc.add_paragraph()

        add_grand_total_paragraph(doc, grand_total)

    def _add_marking_guide_body(self, doc, question_groups: list, grand_total: int):
        """3-column visible-border marking guide table, same N.1/N.2 numbering
        as the question paper, one calculation step per row, ending with the
        same standalone grand TOTAL [N] paragraph."""
        heading = doc.add_paragraph()
        r = heading.add_run("MARKING GUIDELINE")
        set_font(r, size=14, bold=True)
        doc.add_paragraph()

        for qnum, questions in question_groups:
            flat = _flatten_topic_hierarchy(qnum, questions)
            step_groups = []
            for r in flat:
                if r.get("is_stem"):
                    continue  # stems carry no marks/marking steps of their own
                leaf = r["leaf"]
                steps = leaf.get("marking_steps") or [
                    {"parts": leaf.get("answer", []), "tick_label": "answer", "tick_count": 1}
                ]
                step_tuples = []
                for step in steps:
                    count = step.get("tick_count", 0)
                    label = step.get("tick_label")
                    tick_display = f"{'✓' * count} {label}" if count > 0 and label else None
                    step_tuples.append((parts_to_cell_content(step.get("parts", [])), tick_display))
                step_groups.append({
                    'num': r['num'],
                    'steps': step_tuples,
                    'marks': r['marks']
                })
            add_marking_guide_question_table(doc, qnum, step_groups)
            doc.add_paragraph()

        add_grand_total_paragraph(doc, grand_total)

    def _add_cognitive_grid(self, doc, topics_data: list, targets: dict):
        """
        Bordered COGNITIVE LEVEL ANALYSIS GRID matching the approved Task 8
        reference format (reference/task8_baseline/build.py / _CognitiveGrid.
        docx): one row per sub-question -- never aggregated per top-level
        QUESTION -- with 4 cognitive levels x 3 difficulty tiers (E/M/D) =
        12 mark-columns, a leaf's full mark value in exactly one of them,
        plus top Weighting/Actual% and bottom TOTAL/% summary rows.
        """
        doc.add_paragraph()
        heading = doc.add_paragraph()
        r = heading.add_run("COGNITIVE LEVEL ANALYSIS GRID")
        set_font(r, size=14, bold=True)

        leaves = _collect_grid_leaves(topics_data)
        total_marks = sum(leaf["marks"] for leaf in leaves if leaf["marks"])

        # 12 mark-column totals, keyed (level, tier). A leaf with a missing/
        # invalid level or tier can't happen in practice -- both are
        # required by generation.py's validator (check_leaf_flags) before a
        # leaf is ever accepted -- but if one ever slipped through, it
        # contributes to neither the column totals nor a data-row cell
        # below, so a pipeline regression shows up as a totals mismatch the
        # caller can see, not a silent miscount or a crash.
        col_totals = {(lvl, tier): 0 for lvl in COGNITIVE_LEVELS for tier in DIFFICULTY_TIERS}
        for leaf in leaves:
            key = (leaf["level"], leaf["tier"])
            if key in col_totals and leaf["marks"]:
                col_totals[key] += leaf["marks"]
        level_totals = {lvl: sum(col_totals[(lvl, t)] for t in DIFFICULTY_TIERS) for lvl in COGNITIVE_LEVELS}

        def pct(x):
            return round(100 * x / total_marks) if total_marks else 0

        table = doc.add_table(rows=0, cols=16)
        show_table_borders(table)

        def cell_text(c, text, bold=False, center=True, shade=None):
            p = c.paragraphs[0]
            run = p.add_run(str(text))
            set_font(run, size=8, bold=bold)
            if center:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if shade:
                tcPr = c._tc.get_or_add_tcPr()
                sh = OxmlElement('w:shd')
                sh.set(qn('w:val'), 'clear')
                sh.set(qn('w:fill'), shade)
                tcPr.append(sh)

        def summary_row(label, values, shade=None):
            row = table.add_row().cells
            merged_label = row[0].merge(row[1]).merge(row[2])
            cell_text(merged_label, label, bold=True, center=False, shade=shade)
            for i, level in enumerate(COGNITIVE_LEVELS):
                merged = row[3 + 3 * i].merge(row[4 + 3 * i]).merge(row[5 + 3 * i])
                cell_text(merged, values[level], bold=True, shade=shade)
            cell_text(row[15], values["total"], bold=True, shade=shade)

        # --- Top summary rows ---
        summary_row(
            "Weighting (Prescribed)",
            {**{lvl: f"{targets.get(lvl, 0)}%" for lvl in COGNITIVE_LEVELS}, "total": "100%"},
            shade="D9D9D9"
        )
        summary_row(
            "Actual %",
            {**{lvl: f"{pct(level_totals[lvl])}%" for lvl in COGNITIVE_LEVELS}, "total": f"{pct(total_marks)}%"},
            shade="D9D9D9"
        )

        # --- Column headers (2 rows: level names, then E/M/D per level) ---
        header_row = table.add_row().cells
        for i, h in enumerate(["Topic", "Q", "Sub-topic"]):
            cell_text(header_row[i], h, bold=True)
        for i, level in enumerate(COGNITIVE_LEVELS):
            merged = header_row[3 + 3 * i].merge(header_row[4 + 3 * i]).merge(header_row[5 + 3 * i])
            cell_text(merged, COGNITIVE_LEVEL_NAMES[level], bold=True)
        cell_text(header_row[15], "Total", bold=True)

        tier_row = table.add_row().cells
        for i in range(12):
            cell_text(tier_row[3 + i], DIFFICULTY_TIER_LABELS[DIFFICULTY_TIERS[i % 3]], bold=True)
        # Topic/Q/Sub-topic/Total only need to appear once -- vertically
        # merge them across both header rows (mirrors the reference's own
        # two-row header).
        prev_row = table.rows[-2].cells
        for i in (0, 1, 2, 15):
            tier_row[i].merge(prev_row[i])

        # --- Data rows: one per sub-question, never aggregated ---
        last_topic = None
        for leaf in leaves:
            row = table.add_row().cells
            cell_text(row[0], leaf["topic"] if leaf["topic"] != last_topic else "", bold=True, center=False)
            last_topic = leaf["topic"]
            cell_text(row[1], leaf["num"])
            cell_text(row[2], leaf["label"], center=False)
            if leaf["level"] in COGNITIVE_LEVELS and leaf["tier"] in DIFFICULTY_TIERS:
                col_index = 3 + COGNITIVE_LEVELS.index(leaf["level"]) * 3 + DIFFICULTY_TIERS.index(leaf["tier"])
                cell_text(row[col_index], leaf["marks"])
            cell_text(row[15], leaf["marks"], bold=True)

        # --- Bottom summary rows ---
        total_row = table.add_row().cells
        merged_label = total_row[0].merge(total_row[1]).merge(total_row[2])
        cell_text(merged_label, "TOTAL", bold=True, center=False, shade="D9D9D9")
        for i in range(12):
            lvl = COGNITIVE_LEVELS[i // 3]
            tier = DIFFICULTY_TIERS[i % 3]
            cell_text(total_row[3 + i], col_totals[(lvl, tier)], bold=True, shade="D9D9D9")
        cell_text(total_row[15], total_marks, bold=True, shade="D9D9D9")

        summary_row(
            "%",
            {**{lvl: f"{pct(level_totals[lvl])}%" for lvl in COGNITIVE_LEVELS}, "total": "100%"},
            shade="D9D9D9"
        )

        set_table_fixed_layout_and_grid(table, COGNITIVE_GRID_COL_WIDTHS_IN)

        note = doc.add_paragraph()
        r = note.add_run("E = Easy, M = Medium, D = Difficult.")
        set_font(r, size=9)

    def _build_cognitive_grid_xlsx(self, topics_data: list, targets: dict) -> bytes:
        """
        Same data/layout logic as _add_cognitive_grid (leaf collection, column
        totals, percentages) reproduced as an openpyxl worksheet: 2 header
        rows (level names + E/M/D tier labels, vertically merged for
        Topic/Q/Sub-topic/Total), one data row per sub-question (topic
        labelled once per block), and TOTAL/% summary rows -- bracketed by
        the same Prescribed/Actual % rows at the top as the docx grid.
        """
        leaves = _collect_grid_leaves(topics_data)
        total_marks = sum(leaf["marks"] for leaf in leaves if leaf["marks"])

        col_totals = {(lvl, tier): 0 for lvl in COGNITIVE_LEVELS for tier in DIFFICULTY_TIERS}
        for leaf in leaves:
            key = (leaf["level"], leaf["tier"])
            if key in col_totals and leaf["marks"]:
                col_totals[key] += leaf["marks"]
        level_totals = {lvl: sum(col_totals[(lvl, t)] for t in DIFFICULTY_TIERS) for lvl in COGNITIVE_LEVELS}

        def frac(x):
            return round(x / total_marks, 4) if total_marks else 0

        wb = Workbook()
        ws = wb.active
        ws.title = "Cognitive Level Analysis Grid"

        header_font = Font(name='Calibri', bold=True, size=10)
        cell_font = Font(name='Calibri', size=10)
        center = Alignment(horizontal='center', vertical='center', wrap_text=True)
        left = Alignment(horizontal='left', vertical='center', wrap_text=True)
        summary_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
        PCT_FMT = '0%'

        def set_cell(row, col, value, bold=False, align=center, shade=False, num_fmt=None):
            c = ws.cell(row=row, column=col, value=value)
            c.font = header_font if bold else cell_font
            c.alignment = align
            if shade:
                c.fill = summary_fill
            if num_fmt:
                c.number_format = num_fmt
            return c

        def summary_row(row, label, values, total_value, shade=True):
            set_cell(row, 1, label, bold=True, align=left, shade=shade)
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
            for i in range(2, 4):
                set_cell(row, i, None, bold=True, shade=shade)
            for i, level in enumerate(COGNITIVE_LEVELS):
                start_col = 4 + 3 * i
                set_cell(row, start_col, values[level], bold=True, shade=shade, num_fmt=PCT_FMT)
                ws.merge_cells(start_row=row, start_column=start_col, end_row=row, end_column=start_col + 2)
                for c in range(start_col + 1, start_col + 3):
                    set_cell(row, c, None, bold=True, shade=shade)
            set_cell(row, 16, total_value, bold=True, shade=shade, num_fmt=PCT_FMT)

        row = 1
        summary_row(row, "Weighting (Prescribed)",
                    {lvl: targets.get(lvl, 0) / 100 for lvl in COGNITIVE_LEVELS}, 1.0)
        row += 1
        summary_row(row, "Actual %",
                    {lvl: frac(level_totals[lvl]) for lvl in COGNITIVE_LEVELS}, frac(total_marks))
        row += 1

        header_row1 = row
        header_row2 = row + 1
        for col, h in ((1, "Topic"), (2, "Q"), (3, "Sub-topic")):
            set_cell(header_row1, col, h, bold=True)
            ws.merge_cells(start_row=header_row1, start_column=col, end_row=header_row2, end_column=col)
        for i, level in enumerate(COGNITIVE_LEVELS):
            start_col = 4 + 3 * i
            set_cell(header_row1, start_col, COGNITIVE_LEVEL_NAMES[level], bold=True)
            ws.merge_cells(start_row=header_row1, start_column=start_col, end_row=header_row1, end_column=start_col + 2)
            for c in range(start_col + 1, start_col + 3):
                set_cell(header_row1, c, None, bold=True)
            for j, tier in enumerate(DIFFICULTY_TIERS):
                set_cell(header_row2, start_col + j, DIFFICULTY_TIER_LABELS[tier], bold=True)
        set_cell(header_row1, 16, "Total", bold=True)
        ws.merge_cells(start_row=header_row1, start_column=16, end_row=header_row2, end_column=16)
        row = header_row2 + 1

        data_start_row = row
        last_topic = None
        for leaf in leaves:
            set_cell(row, 1, leaf["topic"] if leaf["topic"] != last_topic else "", bold=True, align=left)
            last_topic = leaf["topic"]
            set_cell(row, 2, leaf["num"])
            set_cell(row, 3, leaf["label"], align=left)
            for c in range(4, 16):
                set_cell(row, c, None)
            if leaf["level"] in COGNITIVE_LEVELS and leaf["tier"] in DIFFICULTY_TIERS:
                col_index = 4 + COGNITIVE_LEVELS.index(leaf["level"]) * 3 + DIFFICULTY_TIERS.index(leaf["tier"])
                set_cell(row, col_index, leaf["marks"])
            set_cell(row, 16, leaf["marks"], bold=True)
            row += 1
        data_end_row = row - 1

        set_cell(row, 1, "TOTAL", bold=True, align=left, shade=True)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
        for c in range(2, 4):
            set_cell(row, c, None, bold=True, shade=True)
        for i in range(12):
            lvl = COGNITIVE_LEVELS[i // 3]
            tier = DIFFICULTY_TIERS[i % 3]
            set_cell(row, 4 + i, col_totals[(lvl, tier)], bold=True, shade=True)
        set_cell(row, 16, total_marks, bold=True, shade=True)
        row += 1

        summary_row(row, "%", {lvl: frac(level_totals[lvl]) for lvl in COGNITIVE_LEVELS}, 1.0)

        # Column widths, scaled from the docx grid's inch widths (see
        # COGNITIVE_GRID_COL_WIDTHS_IN's own derivation note) to Excel's
        # character-based column width units.
        EXCEL_WIDTH_PER_INCH = 7.0
        for i, width_in in enumerate(COGNITIVE_GRID_COL_WIDTHS_IN, start=1):
            ws.column_dimensions[get_column_letter(i)].width = round(width_in * EXCEL_WIDTH_PER_INCH, 1)

        for r in range(1, row + 1):
            ws.row_dimensions[r].height = 24 if r > header_row2 else 30

        ws.freeze_panes = ws.cell(row=data_start_row, column=1)

        note_row = row + 2
        ws.cell(row=note_row, column=1, value="E = Easy, M = Medium, D = Difficult.").font = Font(name='Calibri', size=9, italic=True)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    def _save_to_bytes(self, doc) -> bytes:
        """Save document to bytes buffer."""
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()
