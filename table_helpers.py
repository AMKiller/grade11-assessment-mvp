import docx
from docx.shared import Inches, Pt, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from mathml_omml import insert_inline_math

TWIPS_PER_INCH = 1440

QUESTION_COL_WIDTHS_IN = [0.5, 0.65, 4.45, 0.5]
MG_COL_WIDTHS_IN = [0.49, 4.58, 1.04]


def set_font(run, size=12, bold=False, italic=False, name='Times New Roman'):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.append(rFonts)
    for attr in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rFonts.set(qn(attr), name)


def set_table_fixed_layout_and_grid(table, col_widths_in):
    tbl = table._tbl
    tblPr = tbl.tblPr
    layout = tblPr.find(qn('w:tblLayout'))
    if layout is None:
        layout = OxmlElement('w:tblLayout')
        tblPr.append(layout)
    layout.set(qn('w:type'), 'fixed')
    # remove existing grid
    grid = tbl.find(qn('w:tblGrid'))
    if grid is not None:
        tbl.remove(grid)
    grid = OxmlElement('w:tblGrid')
    for w in col_widths_in:
        gridCol = OxmlElement('w:gridCol')
        gridCol.set(qn('w:w'), str(int(w * TWIPS_PER_INCH)))
        grid.append(gridCol)
    tbl.insert(list(tbl).index(tblPr) + 1, grid)
    # also set each cell's width explicitly
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            if idx < len(col_widths_in):
                cell.width = Inches(col_widths_in[idx])
                tcPr = cell._tc.get_or_add_tcPr()
                tcW = tcPr.find(qn('w:tcW'))
                if tcW is None:
                    tcW = OxmlElement('w:tcW')
                    tcPr.append(tcW)
                tcW.set(qn('w:w'), str(int(col_widths_in[idx] * TWIPS_PER_INCH)))
                tcW.set(qn('w:type'), 'dxa')


def hide_table_borders(table):
    tbl = table._tbl
    tblPr = tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{edge}')
        el.set(qn('w:val'), 'nil')
        borders.append(el)
    tblPr.append(borders)


def show_table_borders(table, size='4', color='000000'):
    tbl = table._tbl
    tblPr = tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{edge}')
        el.set(qn('w:val'), 'single')
        el.set(qn('w:sz'), size)
        el.set(qn('w:color'), color)
        borders.append(el)
    tblPr.append(borders)


def set_cell_vertical_alignment(cell, align='top'):
    tcPr = cell._tc.get_or_add_tcPr()
    vAlign = OxmlElement('w:vAlign')
    vAlign.set(qn('w:val'), align)
    tcPr.append(vAlign)


def set_cell_margins(cell, top=40, bottom=40, left=80, right=80):
    tcPr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement('w:tcMar')
    for side, val in (('top', top), ('bottom', bottom), ('left', left), ('right', right)):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:w'), str(val))
        el.set(qn('w:type'), 'dxa')
        mar.append(el)
    tcPr.append(mar)


def merge_cells_in_row(row, start_idx, end_idx):
    a = row.cells[start_idx]
    b = row.cells[end_idx]
    return a.merge(b)


def add_cell_content(cell, parts, size=12, bold=False, align=None, italic=False):
    """parts: list of str (plain text) or ('math', latex) tuples. Writes into
    the cell's first paragraph (clearing any default empty run)."""
    p = cell.paragraphs[0]
    if align is not None:
        p.alignment = align
    for part in parts:
        if isinstance(part, tuple) and part[0] == 'math':
            latex = part[1]
            # LibreOffice's math renderer shows a red error glyph for a math
            # zone that opens with a bare relational operator (no operand
            # before it), e.g. "=\frac{...}". Peel a leading "=" off into a
            # plain text run so the math zone always starts with a real term.
            if latex.startswith('='):
                r = p.add_run('= ')
                set_font(r, size=size, bold=bold, italic=italic)
                latex = latex[1:]
            insert_inline_math(p, latex)
        else:
            r = p.add_run(part)
            set_font(r, size=size, bold=bold, italic=italic)
    return p


def add_blank_row(table, ncols):
    row = table.add_row()
    for c in row.cells:
        set_font(c.paragraphs[0].add_run(''), size=6)
    return row


def insert_element_after(new_elem, ref_elem):
    ref_elem.addnext(new_elem)


# ============================================================
# Question-layout and marking-guide table builders
# ============================================================

def add_question_heading(doc, text, size=12):
    p = doc.add_paragraph()
    r = p.add_run(text)
    set_font(r, size=size, bold=True)
    return p


def _new_row_cells(table):
    row = table.add_row()
    return row


def add_question_table(doc, rows):
    """rows: list of dicts {'num': '1.1', 'parts': [...], 'marks': int|None}
    parts is a list of str / ('math', latex) tuples for the content cell."""
    table = doc.add_table(rows=0, cols=4)
    hide_table_borders(table)

    def add_row(num_text, content_parts, marks_text, merge23, is_total=False, blank=False):
        row = table.add_row()
        c0, c1, c2, c3 = row.cells
        set_cell_vertical_alignment(c3, 'bottom')
        if blank:
            for c in (c0, c1, c2, c3):
                set_font(c.paragraphs[0].add_run(''), size=6)
            return
        if merge23:
            # depth-0 / stem row: primary number in col0, col1+col2 merge into content
            if num_text:
                r = c0.paragraphs[0].add_run(num_text)
                set_font(r, size=12)
            else:
                c0.paragraphs[0].add_run('')
            merged = c1.merge(c2)
            add_cell_content(merged, content_parts, size=12)
        else:
            # depth-1 row: col0 blank (primary already shown on stem row),
            # col1 holds the sub-sub-number, col2 holds content only
            c0.paragraphs[0].add_run('')
            if num_text:
                r = c1.paragraphs[0].add_run(num_text)
                set_font(r, size=12)
            else:
                c1.paragraphs[0].add_run('')
            add_cell_content(c2, content_parts, size=12)
        # marks column
        p3 = c3.paragraphs[0]
        p3.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if marks_text:
            r = p3.add_run(marks_text)
            set_font(r, size=12, bold=False)

    for item in rows:
        num = item['num']
        parts = item['parts']
        marks = item.get('marks')
        depth = num.count('.') - 1 if num else 0
        is_stem = marks is None
        merge23 = is_stem or depth == 0
        marks_text = f"({marks})" if (marks is not None) else None
        add_row(num, parts, marks_text, merge23)
        if not is_stem:
            add_row(None, [], None, True, blank=True)

    set_table_fixed_layout_and_grid(table, QUESTION_COL_WIDTHS_IN)
    return table


def add_question_total_row(table, total_marks):
    row = table.add_row()
    c0, c1, c2, c3 = row.cells
    set_cell_vertical_alignment(c3, 'bottom')
    for c in (c0, c1, c2):
        c.paragraphs[0].add_run('')
    p3 = c3.paragraphs[0]
    p3.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = p3.add_run(f"[{total_marks}]")
    set_font(r, size=12, bold=False)


def add_grand_total_paragraph(doc, total_marks):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"TOTAL [{total_marks}]")
    set_font(r, size=12, bold=True)
    return p


# ---------------- Marking guide (3-column visible-border) ----------------

def add_marking_guide_question_table(doc, question_num, step_groups):
    """step_groups: list of sub-question groups. Each group is a dict:
    {'num': '1.1', 'steps': [ (content_parts, tick_text_or_None), ... ]}
    The mark bracket '(N)' goes in the LAST step's tick cell as its own line
    (we append it as a second paragraph in that cell)."""
    table = doc.add_table(rows=0, cols=3)
    show_table_borders(table)

    # header row, merged across 3 cols
    header_row = table.add_row()
    hc = header_row.cells[0]
    merged = hc.merge(header_row.cells[1]).merge(header_row.cells[2])
    merged.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = merged.paragraphs[0].add_run(f"QUESTION {question_num}")
    set_font(r, size=12, bold=False)

    for gi, group in enumerate(step_groups):
        num = group['num']
        steps = group['steps']
        marks = group.get('marks')
        for si, (parts, tick) in enumerate(steps):
            row = table.add_row()
            c0, c1, c2 = row.cells
            if si == 0:
                r = c0.paragraphs[0].add_run(num)
                set_font(r, size=12)
            else:
                c0.paragraphs[0].add_run('')
            add_cell_content(c1, parts, size=12)
            p2 = c2.paragraphs[0]
            if tick:
                r = p2.add_run(tick)
                set_font(r, size=12)
            if si == len(steps) - 1 and marks is not None:
                p2b = c2.add_paragraph()
                r = p2b.add_run(f"({marks})")
                set_font(r, size=12)
        # blank spacer row between sub-questions
        brow = table.add_row()
        for c in brow.cells:
            set_font(c.paragraphs[0].add_run(''), size=6)

    set_table_fixed_layout_and_grid(table, MG_COL_WIDTHS_IN)
    return table


# ============================================================
# Document setup (only needed when NOT building from a real
# Anne-Marie template — a template supplies its own geometry)
# ============================================================

def set_document_page_setup(doc):
    """A4, 2cm margins on all sides. Skip this when building from a real
    template (QP_Template.docx etc.) — use the template's own geometry."""
    from docx.shared import Cm
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2)
    section.right_margin = Cm(2)
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)


def set_document_default_font(doc, name='Times New Roman', size=12):
    """Sets the Normal style so table.add_row() cells etc. don't fall back
    to Calibri. Still call set_font() on every run you create explicitly."""
    from docx.shared import Pt
    style = doc.styles['Normal']
    style.font.name = name
    style.font.size = Pt(size)
    rpr = style.element.get_or_add_rPr()
    rFonts = rpr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rpr.append(rFonts)
    for attr in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'):
        rFonts.set(qn(attr), name)


def add_information_sheet_image(doc, image_path, height_inches=7.3):
    """Grade 11/12 info sheet — a real extracted DBE page image (see this
    skill's assets/ folder), not reconstructed text. Title is added as
    native text separately (see /task) — don't put a title in the image."""
    from docx.shared import Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc.add_picture(image_path, height=Inches(height_inches))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
