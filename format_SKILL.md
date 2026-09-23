---
name: format
description: Universal CAPS/DBE Mathematics document formatting for Anne-Marie's Grade 8-12 materials. Use this for ANY docx document (worksheets, tests, tasks, conversations) to ensure consistent worked-example layout, grade-band voice, Python-verified numbers, image-based diagrams, and — critically — the question-table layout, fonts, borders, page numbering and marking-guide structure that /worksheet, /test and /task all share. Always combine with /worksheet, /test, or /task for type-specific rules (cover pages, page frame, timing).
---

# Universal Document Formatting

**Status: mandatory ruleset, applied to every document, every time — not optional or conditionally triggered.** Every rule below has been broken at least once by a plausible-looking implementation that skipped or half-applied it; the fix each time came from comparing a rendered page directly against a real approved example, never from re-reading the prose alone. Treat "verified against a real example" as the standard for any new rule added here, and treat any generation pipeline built from this document as needing the same discipline: render and structurally check every output against these rules before it reaches Anne-Marie, rather than trusting that an instruction was followed because it's written down.

Core formatting rules that apply to **every** Grade 8–12 Maths document — worksheets, informal tests, formal tasks, and conversations. Type-specific deltas (cover pages, page border, information sheet, timing/total-marks header) live in `/worksheet`, `/test`, `/task`.

**Reusable code: `table_helpers.py` and `mathml_omml.py` — PRESENT as of the Task 7 (Grade 11 Equations/Inequalities + Exponents/Surds) build session.** `table_helpers.py` implements everything below (fixed-layout `tblGrid` in twips, hidden/visible border toggles, cell vertical alignment, the marking-guide table builder, `set_document_page_setup`, `set_document_default_font`, `add_information_sheet_image`) plus the question-paper/marking-guide table builders (`add_question_table`, `add_question_total_row`, `add_grand_total_paragraph`, `add_marking_guide_question_table`). `mathml_omml.py` (paired with `assets/MML2OMML.XSL`) handles native Word Math objects — see "Mathematical expressions as native Word Math objects" below. Still always verify these actually import and render correctly in a fresh session before trusting them blind — copy both `.py` files and the `assets/` folder into your working directory together, since `table_helpers.py` imports from `mathml_omml.py` by relative module name. If either file is ever missing again, rebuild from the specs in this document rather than assuming the import will work.

## Mathematical expressions as native Word Math objects (OMML)

**When Anne-Marie asks for equations as proper Word Math objects (not plain text, not images), use `mathml_omml.py`'s `insert_inline_math(paragraph, latex)`** — or `add_cell_content(cell, parts)` from `table_helpers.py`, which accepts a mix of plain strings and `('math', latex_string)` tuples and inserts each math tuple as a real, natively-editable Word equation inline with the surrounding text.

**The DSL is a small LaTeX-like subset**, not full LaTeX: `^{...}` / `^x` superscript, `_{...}` / `_x` subscript, `\frac{a}{b}`, `\sqrt{x}`, `\sqrt[n]{x}`, `{...}` grouping, and literal text/digits/operators — type unicode symbols directly (`± ≤ ≥ ≠ · ÷ Δ`) rather than via commands. Examples: `"3x^{2}+4x-2=0"`, `"\\frac{x^{-2}y^{3}}{x^{4}y^{-1}}"`, `"\\sqrt{x+3}=x-3"`.

**How it works (why this is reliable, not a hand-rolled guess):** the DSL is parsed into real MathML, then converted to OMML by running it through `assets/MML2OMML.XSL` — the actual stylesheet Microsoft ships with Office for this exact conversion (fetched from a public GitHub mirror; genuinely the same transform Word itself would apply). Hand-writing OMML XML directly was tried first and failed silently (LibreOffice rendered a totally blank page, no error) — going through real MathML + the real Microsoft XSLT is what actually produces valid, Word-native equation objects.

**Environment requirement — `libreoffice-math` must be installed to even verify this.** The base container's LibreOffice install does *not* include the Math component by default (only writer/calc/impress/draw/core). Without it, LibreOffice silently drops every `<m:oMath>` element on import — a math-containing document converts to PDF as if the equations were never there, with no error and no blank space reserved, which looks exactly like a data problem when it's actually a missing package. Run this once per fresh session before trusting any rendered check of math content:
```bash
apt-get update && apt-get install -y libreoffice-math
```
(Confirmed: `archive.ubuntu.com`/`security.ubuntu.com` are reachable from this environment's network allowlist, so this installs cleanly — just don't skip it and conclude the math pipeline is broken when it's just not installed yet.)

**Known gotcha — a math object that opens with a bare relational operator renders as a red error glyph in LibreOffice.** A continuation line like `"=x^{-6}y^{4}"` (common in marking-guide steps that continue the previous line) shows as a garbled `¿` character instead of `=`, because the math zone has no operand before the `=`. `add_cell_content` already works around this automatically — it peels a leading `=` off into a plain text run before handing the rest to `insert_inline_math` — so this is handled for you if you use `add_cell_content` rather than calling `insert_inline_math` directly on a string that starts with `=`.

**Always verify rendered math, every time, the same way as every other rule in this document:** render to PDF, view the actual page image, and confirm each equation shows proper stacked fractions/radicals/superscripts (not flat text, not a blank gap, not a red error glyph) before delivery.


## Document Setup — A4 Page, 2 cm Margins

**Every document must start with page setup.** Call `set_document_page_setup(doc)` immediately after creating a Document, before adding any content. This sets:
- **Paper size:** A4 (21.0 cm × 29.7 cm)
- **Margins:** 2 cm on all sides (left, right, top, bottom)

This is non-negotiable — all materials for Rising Stars must use this exact page geometry, whether worksheet, test, or formal task.

**Exception — building from a real Anne-Marie template (`QP_Template.docx` / `MG_Template.docx` or similar):** if the template already defines its own page size/margins/header/footer/page-border via its own section properties, **use the template's existing geometry as-is** rather than overriding it with the 2cm/A4 defaults above. Confirmed on Task 6: the real templates use ~0.75" margins with a header-embedded page-border image and a `PAGE` field footer, not the generic setup. Continue writing new content (page breaks + paragraphs/tables) inside the template's own final section so header/footer/border/page-numbering inherit automatically — don't create a fresh python-docx `Document()` and rebuild the frame from scratch when a template exists.

## Font

**Times New Roman, 12pt, body text throughout.** This is not just `run.font.size = Pt(12)` on the runs you write — Word will fall back to Calibri/11 on anything you didn't explicitly touch (default `Normal` style, table cells created via `table.add_row()`, etc.) unless you also set it at the style level. Use `set_document_default_font(doc)` (sets `Normal` style) **and** `set_font(run, ...)` on every run you create (sets `w:rFonts` on all four slots — ascii/hAnsi/eastAsia/cs — not just one, since Word can render inconsistently if only one slot is set). Headings/titles may be larger (14–18pt) but stay Times New Roman and bold.

## The four-column question-layout table

Every question in a worksheet, test, or task question paper goes in its own single table, laid out as:

| Column | Width | Content | Alignment |
|---|---|---|---|
| 1 | 0.5" | Primary sub-question number (1.1, 1.2, 2.1...) | left, top |
| 2 | 0.65" | Sub-sub-question number (1.1.1, 2.1.2...), blank for depth-0 rows | left, top |
| 3 | 4.45" | The question text / working | left, top |
| 4 | 0.5" | Marks: `(3)` per sub-question; `[6]` question total on the last row | right, **bottom** |

Narrowed from an earlier 1.0" marks column after a real-Word check showed it far wider than a bracketed one- or two-digit mark ever needs — the freed width goes to the content column (3.95" → 4.45"), which was the tighter constraint on wrapping. `QUESTION_COL_WIDTHS` in `table_helpers.py` reflects this.

**Column widths are not optional decoration — get this wrong and the whole page looks amateurish.** `cell.width = Inches(x)` alone does **nothing** in real Word; Word renders column widths from the table's `tblGrid` XML element, which python-docx does not maintain automatically. You must call `set_table_fixed_layout_and_grid(table, QUESTION_COL_WIDTHS)` (forces `tblLayout type="fixed"` and writes `tblGrid` directly) after building every table, every time. Verify by reading back `tblGrid` from the saved file, not just by trusting the widths you set.

**Marks are bottom-aligned in their cell**, so that when a question wraps to two lines, the `(3)` sits level with the *last* line of the question, not the first. Use `set_cell_vertical_alignment(cell, 'bottom')` on the marks cell only — leave the question-text cell at default top alignment.

**One question = one table, always — no exceptions, even for a data table or diagram.** Any reference material a Question needs goes right after the `QUESTION N` heading, before the first sub-question — never sandwiched between two sub-questions, which forces an unwanted second table object and produces visibly uneven spacing in real Word. Each question gets: a bold `QUESTION N` heading paragraph, any reference tables/diagrams it needs, then its own single table covering every sub-question, with a `[total]` row as the table's last row (right-aligned, not bold).

**Exception — a diagram or blank grid needed only partway through a question** (e.g. "draw the ogive" in sub-question 2.3, then later sub-questions read values off it): embed the image **inside the same table**, as its own row, in the content column (index 2 of the 4), with the number and marks columns blank on that row. Do not break the question into two separate tables to accommodate the image — confirmed against a real DBE-style precedent (`Gr12_Task5_Finance_Statistics_QP_post_moderation.docx`), where a provided ogive is embedded exactly this way, inside a blank row of the same question's table, positioned between the stem/sub-question that introduces it and the first sub-question that depends on it.

**Per-question total row: `[N]` only — no "Total:" label, not bold.** Right-aligned in the marks column, bottom-aligned, same as every other marks cell. This was mis-implemented as `Total: [N]` in bold during the Task 6 build and corrected — the bracket alone, unbolded, is correct and matches the pre-existing spec above.

**Grand paper total — separate from the per-question totals.** After the last question's table, add a standalone paragraph (not a table row): centred, bold, reading `TOTAL [N]` where N is the paper's full mark total. This is a document-level element, not part of any single question's table.

## Genuine data tables (frequency tables, given data sets shown as a table, etc.)

Any table that displays actual data the learner needs to read — a frequency table, cumulative frequency table, contingency table — is a **different kind of table** from the question-layout table above, and stays **visibly bordered**. Use `add_data_table(doc, headers, rows, col_widths)`, which calls `show_table_borders(table)` — this writes an explicit `tblBorders` with `val="single" sz="4"` directly, **not** by setting `table.style = 'Table Grid'` alone. Relying on the style name is a trap: LibreOffice fills in a visible border from its own fallback even when the style isn't fully defined in the document, so it looks correct when you render a check locally — but real Microsoft Word does not, and the table silently loses its border for the person who actually opens it in Word. Always write the border XML explicitly.

**Datasets are displayed, never described in prose.** If a question references "the frequency table below" or "the data set", that table must actually appear in the document. Don't write a question that presupposes data the reader can't see — check this by literally reading each question against the page it sits on, not just the code that generated it.

**Every given data set is shown as an actual table, even a bare list of discrete values.** Confirmed against a real DBE Nov 2025 P2 paper: a simple list like 8 players' points scores ("11 14 19 20 8 10 2 14") is shown as a bordered single-row table of cells, not as inline text with semicolons (e.g. never "11 ; 14 ; 19 ; 20 ; 8 ; 10 ; 2 ; 14" as a bold text line). Use `add_bare_data_table(doc, values, col_widths)` for this — a single row, no header/label row, borders visible — whenever the surrounding sentence already explains what the numbers are. Use the headered `add_data_table` when the data needs column labels (frequency tables, paired data like age-vs-price). **When two or more related datasets are given side by side (e.g. "Class A" and "Class B" marks for a compare-two-data-sets question), use `add_labelled_data_table(doc, rows_with_labels, col_widths)`** — one row per labelled dataset, a bold label in the first column, the values in the remaining columns, borders visible, no header row needed since the row labels carry that role. This was previously missed entirely on a first pass (two datasets were written as bold inline text lines, "Class A: 18 ; 20 ; 22...") and only caught by the same real-example comparison as the column-merge fix above — the general rule ("every dataset in a table") was already documented, but hadn't been extended to the two-datasets-side-by-side case until it actually came up.

**Sub-sub-questions are indented relative to their parent sub-question.** Confirmed against the same real paper: 2.1.1/2.1.2 sit visually indented relative to their parent 2.1 (which itself sits at the same indent level as any other x.y sub-question). `add_question_table` computes this automatically from the sub-question number's dot-count (`"2.1"` → depth 0, `"2.1.1"` → depth 1). A parent stem line like `2.1` introducing a data table before its own `2.1.1`/`2.1.2` children carries no mark of its own (`marks=None`) — same "stem" mechanism already used for one-level nesting, now confirmed to work for this two-level case too.

**Column-merge direction — verified against a real post-moderation QP (`Gr12_Task5_Finance_Statistics_QP_post_moderation.docx`), correcting an earlier wrong implementation.** The four columns are: Column 1 = primary number (0.5"), Column 2 = sub-sub-number (0.65"), Column 3 = content (4.45"), Column 4 = marks (0.5"). **Column 1 (the primary number, e.g. "1.1") is NEVER merged with anything — it always stays its own separate, narrow column.** Column 2 (the sub-sub-number) merges into Column 3 (content) only when Column 2 would otherwise sit blank — i.e. for every depth-0 row (`"1.1"`, one dot) and every stem row (`marks=None`, e.g. `"1.5"` introducing children). Depth-1 rows (`"1.1.1"`, two dots) keep Column 2 as the sub-sub-number and Column 3 as content, unmerged — the resulting narrower content width *is* the visual indent; **do not also add a manual paragraph indent** on top of this (tested and confirmed redundant/wrong — the real precedent has no `w:ind` element on these paragraphs at all).

An earlier version of this skill had the merge backwards — merging Column 1 with Column 2 to hold the primary number, leaving Column 3 alone for content. This is wrong: it pushes every question's content roughly 0.65" further right than it should sit, and was only caught by comparing a rendered page directly against a real approved QP, not by reading the code. If in doubt, verify against a real example file rather than trusting a prose description (including this one) — table-structure bugs like this render correctly-looking-enough to miss on a casual glance, and only show up as a clear discrepancy side-by-side with ground truth.

**Blank spacer row after every sub-question, without exception — this applies to the question-layout table itself, not just the marking guide.** Confirmed against the same real precedent: every leaf sub-question row (one that carries its own marks) is followed by a completely blank row (all four cells empty) before the next sub-question begins — including between two children of the same stem (e.g. between `1.5.1` and `1.5.2`), and including immediately before the question's own `[N]` total row. The **only** place a blank row is skipped is directly after a stem row (`marks=None`) — its first child follows immediately, with no blank between the stem and `x.y.1`. An embedded image row (see the diagram exception above) also gets a trailing blank spacer, for the same visual-breathing-room reason. Implement this as a single rule in the table-building loop: after finishing any row that is not a stem and not the `TOTAL` row itself, add one blank row before continuing — don't try to special-case it per call site, since that's exactly how it got missed the first time (documented as a rule in this file, but never actually wired into the table-building function until a real example forced the comparison).

## Marking guide table — 3-column visible-border format

**The marking guide is NOT built from the same 4-column hidden-border question-layout table as the question paper.** It is a distinct table style, confirmed against a real Anne-Marie post-moderation memo (`Gr12_Task5_Finance_Statistics_MEMO_post_moderation.docx`):

| Column | Width (twips / inches) | Content | 
|---|---|---|
| 1 | 700 twips ≈ 0.49" | Sub-question number — first row of that sub-question only, blank on continuation rows |
| 2 | 6600 twips ≈ 4.58" | Working — **one calculation step per table row**, not multiple lines packed into one cell |
| 3 | 1500 twips ≈ 1.04" | Tick annotation for that specific row (blank if the row is a pure intermediate algebra step with no mark of its own); the mark bracket `(N)` is appended as its own paragraph in the **last** row's tick cell |

**Borders are visible throughout** — `tblBorders` with `val="single" sz="4" color="000000"` on all edges (top/left/bottom/right/insideH/insideV), not hidden like the question-paper table.

**Header row:** merged across all 3 columns (`gridSpan=3` on the surviving cell after merging), left-aligned, plain text `QUESTION N` — not bold in the verified precedent.

**Blank spacer row between every sub-question** — an entirely empty row (all 3 cells blank), same spacer convention as the question-paper table, but here it's a real empty table row rather than paragraph spacing.

**Worked examples inside the marking guide still follow the formula-first, one-step-per-line convention** (see below) — the difference from the question paper is only the table's column/border structure, not the worked-example content rules.

Example row sequence for a 3-mark sub-question with two ticked steps:
```
| 1.2 | σ = √[Σ(x−x̄)²/n]        |                              |
|     | σ_A = 2,29                | ✓ method                    |
|     | σ_B = 7,94                | ✓✓ both standard deviations |
|     |                            | correct                     |
|     |                            | (3)                          |
|     |                            |                              |   <- blank spacer row
```

Use a dedicated helper (`add_marking_guide_table`) distinct from `add_question_table` for this — don't try to reuse the question-paper table builder with different border settings, since the column widths, header treatment, and per-row (rather than per-cell-with-embedded-newlines) structure all differ.

**Front matter (cover page) is shared with the question paper's template style** — grade/total/time/examiner/moderator block, Rising Stars title box — but the *body* always uses this 3-column visible format, not the question paper's 4-column hidden format, regardless of what a specific instruction elsewhere might suggest about "generic default" tables. If in doubt, ask for or check a real approved memo before building.

**The marking guide ends with the same standalone grand-total paragraph as the question paper.** After the last question's marking-guide table (and before the cognitive-level grid, if one follows), add a standalone paragraph — centred, bold, reading `TOTAL [N]`, exactly matching the question paper's grand-total paragraph in wording, position (its own paragraph, not a table row) and formatting (see `/task`'s grand-total rule). This was previously only specified for the question paper; the marking guide was missed and shipped without one until Anne-Marie caught it directly. Compute `N` from the same per-question mark values used everywhere else in the build — never hand-type it, and always confirm it matches the question paper's own `TOTAL [N]`.

## South African decimal notation

**All numbers use comma-decimal notation** (e.g. `3,25`, not `3.25`) — this is the standard South African convention and applies everywhere a decimal appears: worked examples, marking guides, question text, tables, diagrams. Thousands separators, where needed, use a space (`12 500`) not a comma, to avoid ambiguity with the decimal comma. This was previously only documented inside one downstream skill (`help-them-pass-functions`) rather than here — it's a universal formatting rule, not specific to that workflow, so it's stated once here and every document-producing skill inherits it.

**No interim rounding** — carry exact or symbolic values through the working and round only the final answer (to the precision the question specifies, or two decimal places by default).

## Worked examples — formula first, each step on its own line

All worked examples in documents and marking guides follow this pattern:

1. **Formula line.** Boxed or plain (depending on context — worked examples in the memo are plain; those in teaching documents may have a box). State the complete formula with all symbols, exactly as it appears on the Information Sheet or (for Gr 8–9) in the grade-band voice version.
   
2. **Each calculation step on a new line.** No "substitute and simplify" condensed into one line — break it into steps that match DBE marking guide conventions. Each step shows the operation being performed and the result. Example:
   ```
   A = P(1 + i)ⁿ
   A = 15 000(1 + 0,06)⁸
   A = 15 000(1,06)⁸
   A = 15 000(1,593848...)
   A = 23 907,72
   ```
   In the 3-column marking guide table specifically, each of these lines is its **own table row** in column 2 (see "Marking guide table" above), not stacked as multiple lines inside one cell.
   
3. **All operations and substitutions visible.** Don't skip steps that a learner could get wrong (e.g., showing only "A = 15 000(1,06)⁸ = 23 907,72" without the intermediate evaluation of (1,06)⁸). Marking guides tick each step that appears, so each line must correspond to a tickable operation.

4. **Final answer highlighted** — in the memo, via a green-coloured or otherwise visually distinct line; in student-facing marking guides, a bold/clear line. Never just "23 907,72" on its own at the end — the final answer must read as distinct from the working.

This applies to every worked example in any document: conversations, worksheets, tests, tasks, formal assessments, teaching slide decks, and marking guides.

## Diagrams — matplotlib PNG, transparent background, 150+ DPI

**Diagrams are always PNG images generated by matplotlib, never as shapes inside Word or PowerPoint.**

**Marking guides must show the actual completed diagram, never a text description of it.** Confirmed correction from the Task 6 build: an earlier pass wrote marking-guide entries like "✓ correct Venn diagram structure" or "✓ smooth curve through cumulative frequency points" as the entire answer for a drawing-based sub-question. This is wrong — generate the real matplotlib image showing the **correct, completed** diagram (the ogive with the curve actually drawn through the calculated points, plus interpolation drop-lines for any value read off it in a later sub-question; the Venn diagram with every region's final numeric value filled in; the tree diagram with every branch's probability labelled and each outcome's combined probability shown) and embed that image in the marking guide's content column, exactly as described in "Marking guide table" above. Tick annotations still accompany the image for mark allocation, but the image itself — not prose — is the answer.

### Axes conventions

- **Axes through the origin (y-axis spine at x=0, x-axis spine at y=0)**, not a boxed plot with axvline/axhline, for function-style graphs. **Exception: ogives and other statistics grids conventionally keep all four spines visible as a bordered box** (matches real DBE grid paper and the graph-paper look expected for cumulative-frequency work) — don't force the zero-crossing spine style onto these.
  ```python
  ax.spines['left'].set_position('zero')
  ax.spines['bottom'].set_position('zero')
  ax.spines['top'].set_visible(False)
  ax.spines['right'].set_visible(False)
  ```
- **Grid is present only when the learner needs to read values or plot points**, not for every diagram. When present, **grid lines must be black, not light gray** — ensures high contrast for printed pages and projection. Set:
  ```python
  ax.grid(True, color='black', linewidth=0.5, alpha=0.7)
  ```
- **Blank grids provided for learners to draw their own graph** (e.g. "draw the ogive to represent this data") need **both major and minor gridlines**: major gridlines at the labelled scale interval (e.g. every 5 units) so the axes are readable, **plus fine minor gridlines (typically every 1 unit)** so the learner can plot values that don't land on a multiple of the major interval (a cumulative frequency of 13, 27, 39, 47 — not multiples of 5 — must still be plottable precisely). Use `ax.xaxis.set_minor_locator`/`ax.yaxis.set_minor_locator` (`MultipleLocator(1)`) alongside the major locators, and grid both: major gridlines heavier/more opaque, minor gridlines thinner/lighter, both black.
- **Size blank drawing grids large** — roughly half a page (e.g. a 4.3" embed width scaled to produce ~5–5.5" height) so there's room to plot and draw accurately. Undersized grids that cram 50 units of cumulative frequency into 2 inches are unusable.
- **Tick marks visible on both axes** — learners read values from these.
- **Axis labels clear:** "$x$" or "$y$" in LaTeX, or spelled-out labels like "Time (seconds)" / "Distance (metres)".

### Reading values from graphs — axis calibration rule

**When a learner is asked to read a value off a graph (e.g. "Find the y-intercept" or "Write down the value of y when x = 2"), the target value MUST land exactly on a labelled gridline.** Never require the learner to estimate between marks. Drop-lines to axes are required; coordinate labels on points themselves are forbidden.

Example: a cubic graph with a zero at x = 2 should have the x-axis labelled with x = 2 as an explicit tick and gridline, not as a value between x = 1 and x = 3 that the learner must interpolate.

**This rule is why blank drawing grids need minor gridlines (see above):** the values the learner will need to read back off their own drawn curve (an interpolated median, Q1, Q3) are frequently not multiples of the major gridline spacing, so the *grid itself*, not just a provided finished graph, needs fine enough resolution to plot and later re-read those values accurately.

### Angle notation in diagrams

- **Angle labels**: use combining circumflex `U+0302` over the vertex letter, e.g. `B̂` for angle B, or the standard hat symbol. Never the `∠` symbol inside diagrams.
  ```python
  ax.text(x, y, r'$\hat{B} = 35°$', ...)  # or use Unicode combining circumflex
  ```
- **Multiple angles in a triangle**: write the full three-letter notation with hat over middle letter, e.g. `ÂBC` (angle at B in triangle ABC).

### Line naming in diagrams

**Lines are named with two capital letters from their endpoints (e.g. `AB`, `CD`, `EF`), never a single lowercase letter (`l`, `m`, `t`).** This applies to every line in a diagram — sides of a shape, parallel lines, and transversals alike. Label each line's two endpoints with capital letters in the diagram, and refer to the line in question text and marking guides as the two-letter name (e.g. "line AB ∥ line CD, cut by transversal EF"), not by a single-letter line name.

### Unlabelled/unknown angle naming in diagrams

**An angle whose size is to be determined (not yet named as part of a triangle/quadrilateral) is labelled with a single CAPITAL letter — P, Q, R, S, T, ... — never a lowercase letter (`p`, `q`, `r`).** This is distinct from the hat notation above, which applies once an angle is referred to by its vertex/arm letters (e.g. `B̂` or `ÂBC`); a bare unknown angle marked directly on a diagram (e.g. "determine the value of P") uses a plain capital letter with no hat.

### Marking parallel lines in diagrams

**Parallel lines are marked with matching arrow chevrons (`>` or `>>`) drawn across each line, not tick/hash marks.** Use a single `>` on each line of a parallel pair; if a second, unrelated parallel pair appears in the same diagram, mark that pair with `>>` (double chevron) to distinguish it from the first pair. Tick/hash marks (as used for equal side lengths in triangles/quadrilaterals) must never be reused for parallel-line marking — the two conventions are visually distinct and must not be conflated.

### Export settings

```python
plt.savefig('diagram.png', dpi=150, bbox_inches='tight', transparent=True)
```

- **DPI:** 150 minimum (readable at both screen and print resolution).
- **Transparent background:** `transparent=True` — embeds cleanly into documents without visible white boxes.
- **Tight bounding box:** `bbox_inches='tight'` — removes excess whitespace around the diagram.
- **No axis spines:** when appropriate for the question type (e.g. a Venn diagram or tree diagram has no axis frame).

### Sizing and placement in documents

- **Word documents (docx):** embed PNG at 3–4 inches wide, centered, for a diagram that's reference material or a supporting illustration. **Blank drawing grids and marking-guide answer diagrams may run wider — up to ~4.3" to fill a question-layout table's content column, or full-width for a half-page grid** — see the sizing note above. Use:
  ```python
  from docx.shared import Inches
  doc.add_picture('diagram.png', width=Inches(4))
  last_paragraph = doc.paragraphs[-1]
  last_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
  ```
  When embedding inside a table cell (question-layout or marking-guide table), add the picture to a run inside that cell's paragraph and center the paragraph, rather than adding it to the document body — this is what keeps the image inside the table structure (see "one question = one table" exception above).
- **PowerPoint (pptx):** embed at slide size (typically 5–6 inches wide), centered or positioned per slide layout.

### Verification before embedding

1. Open the PNG file and visually confirm: axis labels readable, gridlines visible (and BLACK if present), angle/label notation renders correctly, no text overlap, no invisible or washed-out elements.
2. After embedding in the document, render to PDF and check the image appears at correct size, is centered if intended, and has not degraded in quality.

## Angle notation (verbal and written, not in diagrams)

**South African angle notation:** hat symbol (combining circumflex U+0302) over the **middle/vertex letter** only.

### Correct forms:
- Single angle: `B̂` (angle at vertex B)
- Angle in a triangle: `B̂AC` (angle at B in triangle ABC) — **never** `ÂB` or `B̂C` for an angle that's actually at B
- Reason phrase: "∠s of Δ" is acceptable (the ∠ symbol is allowed in reason phrases only, not in the angle name itself)

### Python implementation for docx
```python
def hat(letter):
    return letter + '\u0302'  # hat(B) → B̂

# Usage:
f"Angle {hat('B')} = 45°"
f"In {hat('B')}{hat('A')}{hat('C')} = 90°"  # Angle BAC = 90°, hat only on middle letter
# But this is awkward — better:
f"In triangle ABC, {hat('A')} = 90°"
```

### JavaScript implementation for slide decks

In pptxgenjs or other JavaScript contexts:

```javascript
const H = c => c + '\u0302';          // H('A') → 'Â'
const ANG = (a,b,c) => a + H(b) + c; // ANG('A','B','C') → 'AB̂C'

// Usage:
`If ${H('A')} = 45°, find ${H('B')}.`
`Angle ${ANG('A','B','C')} = 35° (corresp. ∠s)`
```

### Consistency checks before delivery

- Search all text for `∠A`, `∠B`, `∠ABC` patterns (except inside "∠s of Δ" type phrases) — should find none
- Search for "angle A" or "angle B" written out in words followed by an equals sign — should use Â notation instead
- In diagrams (matplotlib), verify that angle labels don't use `∠` symbol or misspelled Unicode
- Diagram labels should read as clear hat notation (e.g. Â, B̂, AB̂C) in the final rendered image

## Font colour

- **All text:** dark gray (RGB 51,51,51 or darker) or black.
- **Never light gray** (RGB 192 or lighter) — unreadable printed, projected, or on classroom screens from a distance.
- Emphasis via bold/italic/navy/gold/green — not lighter shades of gray.

## Slide deck typography — Calibri, 18pt minimum, black only

Applies to every pptx deck (teach-deck, worksheet-deck, opener-deck) — a stricter rule than the docx "Font colour" rule above, which allows dark gray for print documents. Decks are viewed via projector only (printing is cost-prohibitive), so:

- **Font:** Calibri throughout, every text box on every slide.
- **Minimum size: 18pt for every piece of text on a slide, with no exceptions.** This includes elements previously treated as "small print" — footers, tag/pill labels, tick-count and mark-allocation lines, timer-badge subtext, mark-value badges. If an element was built at 9–13pt, it must be raised to at least 18pt, and the layout (card heights, spacing, footer placement) adjusted to fit.
- **Font colour: black (`000000`) only — no grey at any shade, including the `MUTED` grey used for footers and tick lines in the existing deck libraries.** Colour is reserved for semantic emphasis, never for de-emphasis: navy for headings/titles, gold for quick-check boxes, green for final answers, red/blue for tag pills. Muted/grey text is not permitted at any size.
- **Exception for dark (navy) slide backgrounds — cover slides, day/topic title slides:** black text is invisible on navy. On these slides use white for body/footer text instead of black (titles already use white; this now extends to footers and any other text on a navy background). This is not a grey allowance — white and black are the only two options, chosen for contrast against the background, never grey on either.
- Update the shared colour and font-size constants in each deck's `deck_lib.js` (or equivalent reference script) to match, rather than patching individual slides — this is a global constant change per deck skill.

**Before delivery of any deck:** render to PDF and visually check every page — confirm no text reads as grey and nothing is smaller than 18pt. This is a visual check; font-size and colour values in the generation code can't be trusted without seeing the rendered slide.

## Diagram annotation colours — NO YELLOW OR GOLD

**Never use yellow or gold (#B8862B, #FFD700, or similar) for annotation arrows, highlight lines, or text labels in matplotlib diagrams.** These colours are invisible on projected slides and wash out on printed pages.

Use instead:
- Royal blue `#2E6DA4` — primary annotation colour
- Red `#B03A2E` — secondary annotation / emphasis
- Dark green `#17452B` — tertiary / boundary markers

This applies to all matplotlib-generated diagrams regardless of destination (docx worksheets/tests, pptx teach/opener decks). Gold fill boxes (`#FBF3E3` with dark text) for slide deck quick-check cards are fine — this rule covers diagram annotation lines/arrows/labels only.

## CRITICAL: Gridlines in all graphs — BLACK ONLY

**Gridlines must ALWAYS be black, never light gray, in every graph given to learners or plotted by learners.**

This applies whenever:
- A graph is provided in a question and the learner must read values from it
- A graph is provided as reference material
- Learners are asked to plot or construct a graph
- Any axis system with gridlines is shown

**Why:** 
- Light gray gridlines are invisible on printed pages, in projection, and on classroom display screens
- Black gridlines provide the contrast needed for accurate value-reading and graph interpretation
- This matches DBE exam paper standards for all graph materials

**Implementation:**
- **matplotlib (Python):** `ax.grid(True, color='black', linewidth=0.5, alpha=0.7)` or specify as hex: `color='#000000'`
- **When exported to PNG:** verify the gridlines are visibly black in the final image before embedding
- **After embedding in docx/pptx:** render to PDF and visually confirm gridlines remain black and readable

**Verification step (mandatory before delivery):**
1. After generating any diagram with gridlines, view the PNG file at 100% zoom
2. After embedding in the document, render to PDF and check every page containing a graph
3. Print a sample page and visually confirm gridlines are dark and readable — not faint or washed out

## Verification workflow — mandatory before delivery, every single time

1. `soffice --headless --convert-to pdf` the document.
2. `pdftoppm -jpeg -r 100` every page to an image.
3. **Actually view each rendered page image** — column widths, borders, mark alignment, spacing, page numbers, and gridline colour (where applicable) are things you must see, not things you can confirm by reading python-docx property values. Every formatting bug fixed this session (invisible column widths, missing table borders in real Word, wrong-vertical-alignment marks, phantom blank paragraphs, missing page numbers, light-gray gridlines) was invisible in the code and only became obvious on the rendered page.
4. Cross-check: does every question that references a table actually have that table printed above/below it? Read the questions as a learner would, not just as generated content.
5. Recompute all displayed totals independently — never hand-type a `[6]` or `TOTAL: 50 MARKS` figure; sum it from the actual mark values in code and use that variable. This includes the grand paper total, which must match the sum of every question's own total independently.
6. **Context-containment check.** For every sub-question, ask: *does this use the data/diagram introduced in its own QUESTION heading, or does it depend on a different question's dataset?* If a sub-question references another question's data (e.g. "Using the dataset given in QUESTION 1.7" inside QUESTION 2), it belongs in the question that owns that data — move it there and renumber. The only exception is a deliberate "hence" chain within the same question. Flag any cross-question data dependency explicitly at the draft stage so it can be caught before moderation.
7. **Cross-question placement check (structural, not just within-question).** This is a separate failure mode from Step 6: a whole *question* can be misplaced, not just a sub-question. For every QUESTION, ask: *does any sub-question here depend on a dataset, diagram, or scenario that was introduced under a DIFFERENT question number?* If so, that sub-question is not a new question — it is the next sequential sub-question of the question that owns the data, and must be renumbered and moved there (e.g. a stray "2.1" that depends on Question 1's dataset becomes "1.8", not "2.1"). A new QUESTION number must always introduce its own self-contained scenario/dataset/diagram. Read the paper start-to-finish as a first-time learner would, question by question, and confirm each one is self-contained before delivery.
8. **Tick-count vs mark-allocation reconciliation.** For every sub-question in the marking guide: count the actual tick annotations shown, and compare that count to the bracketed mark value, e.g. `(3)`. They must match exactly — never deliver a sub-question showing 3 ticks against a stated 2 marks, or vice versa. Do this by counting programmatically from the same data structure that generates the ticks and the bracket value (never hand-typed independently), then re-verify by reading the rendered page. Also cross-check: sum of sub-question marks = question total; sum of question totals = paper total; memo total = paper total; cognitive-level grid total = paper total; grand paper total paragraph = paper total.
9. **Cognitive-level spot-check against a cited past paper.** At the draft-review sign-off gate (before content is locked, not at final delivery), for each question claimed as a given cognitive level (Knowledge/Routine/Complex/Problem-Solving), name a specific comparable question from an actual past paper in the project knowledge base at that same level, and confirm the drafted question matches its genuine difficulty — not just its surface structure. A question that looks like a Complex-level question but only requires one lookup step is a Routine question mislabelled, and must be redesigned, not relabelled. This check happens early because it requires rewriting the question, which is wasted effort if caught only at final delivery. If no comparable past-paper citation can be found for a claimed Complex or Problem-Solving item, flag this explicitly to Anne-Marie rather than delivering it uncited.

## Information sheet — real extracted image, not reconstructed text

For Grade 11/12 tasks, use `add_information_sheet_image(doc, image_path)`. The source is a genuine scanned DBE past paper page with no text layer — there was no editable/vector content available to extract even in principle, so an image is the correct approach here, not a shortcut. The asset lives at `/task`'s `assets/information_sheet_gr11_gr12.png`, already cropped to exclude the source paper's own header/footer and its own title bar (the title is added as native Word text separately, matching the rest of the document — don't duplicate it by leaving the title in the image too). Sized by height (`height_inches=7.3` default), centred, confirmed to fit one page after a real page's header/footer space.

**If Anne-Marie says she'll add the information sheet herself, skip this step entirely** — don't generate or append a placeholder. Confirmed on Task 6: she handled this manually, so the build proceeded without Section 2.
