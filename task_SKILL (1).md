---
name: task
description: Formal assessment task formatting for Anne-Marie's Grade 8-12 CAPS Mathematics. Creates official "tasks" (formal SBA assessment documents) with Rising Stars branding, a native page border, DBE instructions, cognitive-level grid, and multi-topic weighting. Always pair with /format, which owns the table layout, fonts, borders, spacing, page numbering, diagram/gridline standards, and marking-guide structure — this skill only covers what a formal task has that a /test or /worksheet doesn't: the page frame, the two front-matter pages, the information sheet, and header text. Use for formal SBA assessments ONLY.
---

# Formal Assessment Task Builder

**Read `/format` first — it owns almost everything.** Question-layout tables (hidden borders, bottom-aligned marks, 0.5"/4.6"/1.0" columns), data tables (visible borders), Times New Roman 12pt, right-aligned page-number footer, diagram standards (including **BLACK gridlines only**), and the **3-column visible-border marking guide** are **all identical to `/test` and `/worksheet`** — use `table_helpers.py` from `/format`, don't rebuild any of it. (Check first that `table_helpers.py` actually exists in the `/format` skill folder before assuming it's importable — see the note at the top of `/format`'s SKILL.md.) This skill covers only what makes a formal task different: the page frame, the two front-matter pages, the information sheet at the back, and header text.

## Critical: Gridlines in all graphs — BLACK ONLY

**Every graph provided to learners or plotted by learners must use BLACK gridlines, never light gray.** This applies to:
- Graphs provided as reference material or in questions
- Any axis system shown for reading or plotting values
- All matplotlib-generated diagrams in the task

See `/format`'s "CRITICAL: Gridlines in all graphs — BLACK ONLY" section for implementation and verification steps. Light gray gridlines are invisible on printed pages and in classroom projection. **Blank grids provided for learners to draw their own graph also need minor gridlines** (not just the labelled major ones) so non-multiple-of-5 values can be plotted precisely — see `/format`'s diagram section.

## What a formal task has that /test and /worksheet don't

| | /worksheet | /test | **/task** |
|---|---|---|---|
| Everything in `/format` (tables, fonts, borders, page-number footer, memo, diagrams with BLACK gridlines) | ✓ | ✓ | ✓ |
| "Total: N marks / Time" header + grand total | ✗ | ✓ | ✓ |
| **Page border** | ✗ | ✗ | ✓ |
| **Two front-matter pages** (cover + instructions) | ✗ | ✗ | ✓ |
| **Information sheet** (last page) | ✗ | ✗ | ✓ |
| **Header text** (task/term info, left + right) | ✗ | ✗ | ✓ |
| Cognitive-level analysis grid | ✗ | optional | ✓ always |
| Multi-topic DBE mark weighting | ✗ | ✗ | ✓ |

The footer carries **only** the page number (right-aligned `PAGE` field, exactly as in `/format` — not centred, nothing else added). All the extra formal apparatus lives in the **header**, not the footer.

**The paper's grand total is a separate element from the header's "Total: N marks" line.** After the last question's table, add a standalone bold, centred paragraph reading `TOTAL [N]` — not inside any table, not bold-and-labelled per-question totals (those stay as plain `[N]`, unbolded, no "Total:" text — see `/format`'s question-layout table section). Confirmed correction from the Task 6 build: an earlier draft bolded and labelled every per-question total ("Total: [10]") and had no separate paper-level grand total at all — both were wrong.

**This grand-total paragraph is not unique to the question paper — the marking guide gets the identical standalone `TOTAL [N]` paragraph**, in the same place (after its last question's table) and the same style (centred, bold, bracket only). Confirmed missed on an earlier Task 6 build: the question paper had its `TOTAL [N]`, the marking guide did not, and it went unnoticed until pointed out directly. Both documents' totals must match each other and the sum of every question's own total — see `/format`'s marking-guide section and the verification workflow's reconciliation step.

## Before building anything

**Prompts to gather before starting:**

1. **Grade** (8, 9, 10, 11, or 12)
2. **Task number** (e.g., Task 5)
3. **Topics covered** (e.g., Finance and Statistics)
4. **Total marks** (e.g., 50)
5. **Time allocation** (e.g., 1 hour)
6. **Examiner name** (e.g., AE Killer)
7. **Moderator name** (e.g., M Visser)
8. **Left header text** (e.g., "Mathematics Task 5")
9. **Right header text** (e.g., "Term 3 2026")
10. **For Grades 8–10 only:** Which formulas/information should appear on the information sheet? (Standard sheet for Gr 11–12; selective for Gr 8–10)
11. **Real template check:** does Anne-Marie have an approved `QP_Template.docx` / `MG_Template.docx` (or similarly named front-matter templates) to build from? If so, **use them as the actual starting document** (open with python-docx, edit the cover-title text and header text in place, then append new content in the template's own final section) rather than reconstructing the front matter from this skill's generic description. Confirmed on Task 6: the real templates carry exact Rising Stars branding, page-border images, and pre-set header/footer references that are far safer to reuse than to rebuild.
12. **Information sheet handling:** confirm whether Anne-Marie wants it generated, or will add it herself. If she'll add it, skip Section 2 entirely for that build.

## Mandatory sign-off gates — stop and show your work, even on a single comprehensive prompt

A formal task is built in four gated stages. **This applies even when Anne-Marie's request already specifies everything in one prompt** (e.g. "create a 150 mark Grade 12 Paper 1 task, check the ATP, check the standard setting booklet, generate the paper, marking guide, and cognitive grid"). A comprehensive single-turn prompt describes the *destination*, not pre-approval to skip the checkpoints. Treat it as a request to begin at Gate 1, not a request to deliver a finished document in one pass.

1. **Gate 1 — ATP audit and day/topic plan.** Present the ATP-derived topic list, mark allocation per topic (from the Standard Setting Booklet), and total-marks check. Stop and wait for approval before drafting a single question.
2. **Gate 2 — Question drafts.** Present every question stem (paper) with claimed cognitive level and marks per sub-question — no marking guide yet, no full document. This is also where the Step 9 cognitive-level spot-check (see /format) happens: cite a comparable past-paper question at the same claimed level for each question. Stop and wait for approval. **If Anne-Marie's feedback changes the cognitive-level balance (e.g. "too much Routine, not enough Complex/Problem-Solving"), restructure and re-present the full draft with an updated cognitive-grid totals table before proceeding — don't patch silently and move on.**
3. **Gate 3 — Content build.** Only after Gate 2 approval, build the full paper, marking guide, and cognitive grid together. **Verify the exact marking-guide table format against a real approved example if one exists or can be requested** — don't assume a column count/border style; ask if unsure (confirmed necessary on Task 6, where the marking guide's actual format — 3 columns, visible borders, one working step per row — differed from an initial assumption of a 4-column hidden-border style matching the question paper).
4. **Gate 4 — Final assembled document.** Present the rendered, verified document (per /format's verification workflow, Steps 1–9, including gridline verification) for final sign-off.

Do not collapse gates because the original prompt was thorough or because Anne-Marie's instruction sounded final ("generate the paper and marking guide and cognitive grid"). That phrasing describes the eventual deliverable, not permission to skip Gates 1 and 2. If genuinely unsure whether a reply like "go ahead" or "continue" is approving one gate or all remaining gates, ask which — do not assume blanket approval silently.

## Document structure — three sections

**Section 0 — Front matter, page 1 (Cover page):**
- Rising Stars Academy logo and branding
- Subject: Mathematics; Grade, task number, topic(s)
- Student details table (Name, Surname, Date)
- Question mark grid (shows which questions worth how many marks)
- Task summary: Grade, Total marks, Time, Examiner, Moderator
- Examiner/Moderator signature lines
- Border: native page border applied to this section; **no header text, no page number on this page**

**Section 0 — Front matter, page 2 (Instructions):**
- Standard DBE-worded instructions box (see below)
- Border + header text begins here (or on page 1 of the question paper proper — confirm per template) alongside page numbering

**Section 1 (Question paper — uses /format's question-layout tables throughout):**
- Header: left-aligned text (e.g. "Mathematics Task 5") + right-aligned text (e.g. "Term 3 2026")
- Footer: right-aligned page number only, per `/format`
- Every question built exactly as `/format` specifies — one `QUESTION N` heading + one 3-column table per question, hidden borders, bottom-aligned marks, data tables visibly bordered
- **All graphs and diagrams use BLACK gridlines** (see `/format`'s gridline rule); **blank drawing grids also carry minor gridlines** (see `/format`)
- **A blank spacer row after EVERY sub-question row**, not just between questions — `/format`'s `add_question_table` does this automatically now (confirmed against Anne-Marie's real approved Task document, which spaces every single sub-question row, not just question-to-question).
- **Multi-part questions use a stem line**: a context-setting line with no mark (`marks=None` in `add_question_table`'s tuple), followed by nested sub-parts like `1.5.1`, `1.5.2` that do carry marks — e.g. `("1.5", "Sipho takes out a home loan...", None)` then `("1.5.1", "Determine the monthly instalment.", "3")`. Don't flatten a multi-part question into a single flat numbering scheme when the source material has a genuine shared stem.
- **After the last question's table:** a standalone bold, centred `TOTAL [N]` paragraph — the paper's grand total, separate from any per-question total (see above).

**Section 2 (Information sheet — last page, Grade 11 and Grade 12 only):**
- Formulas and reference information — the complete, unabridged sheet (see "Information sheet" section below for the exact content and sourcing rule)
- Header: same as Section 1 (left/right text); border continues automatically since it's a section-level property, not a per-page image
- Footer: same as Section 1 (right-aligned page number, continuing the sequence)
- **Grade 10 tasks/tests have no information sheet section at all** — formulas are stated inline at question level instead. Don't add one reflexively; check the grade first.
- **If Anne-Marie says she'll add this herself, skip it entirely for this build.**

## Verified against a real approved Task — corrections locked in

Several rounds of comparison against Anne-Marie's actual approved, moderated Task documents surfaced real corrections, now baked into `/format` and this skill:

- **No bold on answer lines** in the marking guide. An early pass proposed bolding final-answer lines based on a misread of a file that turned out to be mislabeled (see below) — don't reintroduce this.
- **The Cognitive Level Analysis Grid lives in the same document**, not a separate spreadsheet — see the Cognitive-level analysis grid section above.
- **Gridlines in all graphs must be BLACK** — light gray is invisible when printed or projected. This is verified at the PDF-render stage as part of the mandatory verification workflow.
- **Per-question totals are plain `[N]`, right-aligned, not bold, no "Total:" label.** The paper's grand total is a separate, standalone `TOTAL [N]` paragraph — bold and centred — after the last question. Confirmed on Task 6 after an initial build bolded and mislabelled the per-question totals and omitted the grand total entirely.
- **The marking guide uses a 3-column visible-border table, not the question paper's 4-column hidden-border table.** Confirmed against a real post-moderation memo on Task 6 — see `/format`'s "Marking guide table" section for the exact spec (column widths, header treatment, one-working-step-per-row structure, tick placement, spacer rows).
- **Marking-guide answers for drawing-based sub-questions (draw the ogive, draw a Venn diagram, draw a tree diagram) must show the actual completed diagram as a generated image**, not a text description of what a correct diagram would contain. Confirmed correction on Task 6 — see `/format`'s diagrams section.
- **`table_helpers.py` (and `mathml_omml.py`) are present in the `/format` skill folder as of the Task 7 build** — check they still import cleanly before assuming so (a future skill edit could remove them again), but don't assume they're absent by default the way Task 6 had to.
- **The question-layout table's primary-number column must never be merged away.** An earlier implementation merged the primary-number column together with the sub-sub-number column (backwards from the real precedent), pushing every question's content roughly 0.65" too far right. Confirmed and fixed against `Gr12_Task5_Finance_Statistics_QP_post_moderation.docx` — see `/format`'s corrected column-merge description.
- **Every sub-question in the question paper — not just the marking guide — gets a blank spacer row after it**, including before each question's own total. This was already documented as a marking-guide rule but had not been extended to the question-layout table itself until directly compared against a real precedent.
- **Every dataset is a table, including two datasets shown side by side** (e.g. two classes' marks for a compare-two-data-sets question) — use a labelled data table (bold row label + values), never a bold inline text line. See `/format`'s dataset section for the exact helper.

## Formatting — delegate to /format completely

There is no distinct OOXML building here. Every aspect of the question tables, data tables, fonts, spacing, borders, page numbering, marking guide structure, diagram standards (including gridline colour), and information sheet is delegated to `/format`'s `table_helpers.py` (or its from-scratch reconstruction, if the file is missing — see `/format`'s note). Focus this skill only on the parts that are genuinely task-specific: the page border logic, the two front-matter pages, and the header/footer frame.

## Cognitive-level analysis grid

A mandatory component of every task. It lives as a real visible table in the document itself, not in a separate spreadsheet. Two formats have been trialled:

1. **Long format (by question):** Rows = questions (QUESTION 1, QUESTION 2, etc.); columns = cognitive levels (Knowledge, Routine, Complex, Problem-Solving); cells = the marks from each question allocated to each level. Subtotals per column; grand total (confirms = paper total). This is the format Anne-Marie's approved Task 5 uses, and is easier to read at a glance.
2. **Short format (by topic):** Rows = topics; columns = cognitive levels + total marks. Similar structure, different row grouping.

Confirmed: use the **long format** (by question) — this matches Anne-Marie's actual approved task document.

### Grid structure

| QUESTION | Knowledge | Routine | Complex | Problem-Solving | **Total** |
|---|---|---|---|---|---|
| QUESTION 1 | 3 | 2 | 0 | 1 | **6** |
| QUESTION 2 | 1 | 4 | 2 | 0 | **7** |
| ... | | | | | |
| **TOTAL** | **12** | **18** | **12** | **8** | **50** |

- **Rows:** one per question, plus a header row and a totals row
- **Columns:** Question number | Knowledge | Routine | Complex | Problem-Solving | Total
- **Every cell is a number.** No formulas or per-cell mark reasoning — just the count of marks at each level. If a question has no marks at a given level, the cell is `0`, not blank.
- **Bold the total row and total column** for emphasis. The grand total (bottom-right cell) confirms the paper total.

### Mark allocation rules

- A sub-question at Knowledge level contributes its marks to that column; same for Routine, Complex, Problem-Solving.
- A single sub-question is **never split across multiple levels** — it is entirely one or entirely the other. A sub-question's mark value goes wholly into exactly one cognitive-level column.
- **Sum each level's column** and each question's row independently, then verify:
  - Sum of each row = that question's total marks ✓
  - Sum of each column = that level's total across all questions ✓
  - Sum of all cells = paper total ✓

### Placement in the document

The grid appears **after the marking guide, before the information sheet** (for Gr 11–12). It is a visible table with borders, matching the style of the marking guide and any data tables — not hidden or in a box outside the main flow. The heading is "COGNITIVE LEVEL ANALYSIS GRID" in bold, followed by the grid itself, left-aligned like other tables in the document. **If there is no information sheet section (Anne-Marie adding it herself, or Grade 10), the grid is simply the last content in the document.**

**Two extra rows always sit at the bottom of the grid, below the TOTAL row: "FET TARGET %" and "THIS TASK %".** Confirmed standing requirement (Task 6). FET TARGET % uses the fixed targets from the tiering framework (Knowledge 20% / Routine 35% / Complex 30% / Problem-Solving 15%, or the GET row — 25/45/20/10 — for Grade 8–9) with the Total column showing "—" (targets don't sum to a mark total). THIS TASK % is each column's total divided by the paper's grand total, rounded to a whole percent, with the Total column showing "100%". Both rows are bold, same visible-border style as the rest of the grid, computed from the same totals used everywhere else in the verification workflow (never hand-typed independently).

## Difficulty check — what actually makes a question Complex or Problem-Solving, not just labelled that way

A recurring failure: questions are *labelled* Complex or Problem-Solving in the cognitive grid without being *redesigned* to that difficulty — this is what made Task 6 Paper 1/2 feel too easy despite a grid that claimed otherwise. Use these concrete tests before accepting a question's claimed level:

- **Knowledge:** a single recall step or direct formula substitution with no decision-making — the learner is told exactly what to do.
- **Routine:** a standard multi-step procedure the learner has drilled before, applied to new numbers — no judgement calls about *which* method or *which* formula to use; that choice is obvious from the question's phrasing. **Note: pure construction/drawing steps (draw the graph, draw the tree diagram, draw the Venn diagram) are conventionally Routine, even when several such steps are needed — don't inflate them to Complex just because they carry several marks. This is also why Routine tends to run high in diagram-heavy topics; compensate by strengthening genuinely decision-based sub-questions elsewhere rather than mislabelling construction steps.**
- **Complex:** the learner must first **decide** which procedure applies (the question does not signal the method), or must **combine two or more previously-separate skills** in one sub-question (e.g. use a diagram to find a length, then use that length in a trig ratio — or, confirmed as a working Statistics/Probability analogue on Task 6: read a value off a graph via interpolation, then apply an un-cued formula — like the IQR outlier fences — to a value not shown on the graph; or solve for an unknown in a Venn diagram from a total-population constraint, then read a combined region using that unknown). If the required method is unambiguous from the wording alone, it is not Complex — it's Routine no matter how many steps it has.
- **Problem-Solving:** genuinely unfamiliar in structure — the learner must adapt a known technique to a scenario that doesn't map directly onto a drilled question type, often requiring an intermediate insight not explicitly cued by the question (a "hence" that isn't obvious, an unstated assumption they must identify, a non-routine combination of topics). **Confirmed-working Problem-Solving archetypes from Task 6: explaining why grouped-data means are only "estimates" (a genuine conceptual-limitation question, not a calculation); explaining why two sequential events without replacement are not independent (requires articulating the mechanism, not just computing a probability).** When no past-paper citation exists for a constructed Problem-Solving item like these, flag that explicitly to Anne-Marie at Gate 2 rather than presenting it as fully precedented.

**Concrete red flags that a "Complex" or "Problem-Solving" question is actually Routine in disguise:**
- The question names the formula or method to use ("use the compound interest formula to find...") — naming the method removes the decision-making that defines Complex.
- Numbers are unusually clean/round for the claimed level — Complex and Problem-Solving questions from real past papers rarely have suspiciously tidy numbers; that's a Routine-question signature.
- The question is a past-paper Routine question with only the surface numbers changed, re-labelled Complex without adding a genuine decision point or skill combination.
- Every sub-question in a multi-part question increases in mark value but not in actual decision-complexity (more steps ≠ higher cognitive level).
- **A pure drawing/construction instruction ("draw the ogive", "draw a tree diagram") labelled Complex or above just because it carries several marks.**

**Before finalising any question claimed as Complex or Problem-Solving:** state explicitly, in one sentence, what decision or skill-combination makes it that level (not just "it has multiple steps"). If that sentence can't be written honestly, redesign the question rather than deliver it at that label.

**When Anne-Marie flags the overall cognitive-level balance as off** (e.g. too much Routine, not enough Complex/Problem-Solving), the fix is usually **not** relabelling existing questions — it's redesigning specific sub-questions to genuinely combine skills or require an uncued decision (per the definitions above), then recomputing the whole grid honestly and presenting the new totals against the FET target for approval. Confirmed workable on Task 6: removing/replacing a couple of straightforward sub-questions with genuine "compare two data sets", "solve for an unknown region in a Venn diagram", and "explain why not independent" items shifted the paper from ~18%/54%/18%/10% (K/R/C/P) to ~20%/34%/30%/16% — very close to the FET target of 20/35/30/15 — without inventing artificial difficulty.

## Multi-topic mark weighting

**Always weight against** official DBE weighting per grade/paper. Example: Gr 10 Paper 2 November → Euclidean Geometry 20, Analytical Geometry 15, Trigonometry 50, Statistics 15. Don't invent proportional weighting; use the reference document's per-grade June/November tables. **Exception:** when Anne-Marie specifies her own custom topic split for a task that doesn't correspond to a full official paper (e.g. a Statistics/Probability/Finance task combining topics from different official papers), her specified split is the plan — verify it sums to the total and sanity-check it against ATP scope constraints (see below), but don't override it with an invented "official" weighting that doesn't apply to this particular topic combination.

**Always check the ATP for partial topic coverage before drafting.** Confirmed critical on Task 6: Anne-Marie's Finance topic had only 2 of 4 ATP sub-points taught (growth formulae and exchange-rate implications; decay/depreciation and effective/nominal rates were not yet covered). This meant most of the pre-catalogued Finance question-bank types for that grade were actually out of scope, because they're built on the untaught sub-points. Cross-check every candidate question type against the specific ATP sub-points confirmed as taught, not just against the topic name as a whole — a topic can be "in progress" with only some of its sub-points available.

## Information sheet (last page)

**Use the genuine official DBE Information Sheet content, not a curated subset of formulas relevant to just this task's topics.** Real DBE papers always print the full standard sheet regardless of which topics that specific paper covers — a Statistics/Probability task still gets the same sheet that includes the quadratic formula, financial mathematics, sequences and series, calculus, coordinate geometry, and trig identities, not just the mean/probability formulas actually needed. An early version of this skill built a short hand-picked list of only the directly relevant formulas — wrong; always transcribe the real sheet in full. A verified real transcription (from an actual DBE past paper, confirmed against Anne-Marie's project knowledge) is:

```
x = [−b ± √(b² − 4ac)] / 2a

A = P(1 + ni)      A = P(1 − ni)      A = P(1 − i)ⁿ      A = P(1 + i)ⁿ

Tₙ = a + (n − 1)d      Sₙ = n/2 [2a + (n − 1)d]

Tₙ = arⁿ⁻¹      Sₙ = a(rⁿ − 1) / (r − 1) ; r ≠ 1      S∞ = a / (1 − r) ; −1 < r < 1

F = x[(1 + i)ⁿ − 1] / i      P = x[1 − (1 + i)⁻ⁿ] / i

f'(x) = lim(h→0) [f(x + h) − f(x)] / h

d = √[(x₂ − x₁)² + (y₂ − y₁)²]      M = ( (x₁+x₂)/2 ; (y₁+y₂)/2 )

y = mx + c      y − y₁ = m(x − x₁)      m = (y₂ − y₁)/(x₂ − x₁)      m = tan θ

(x − a)² + (y − b)² = r²

In ΔABC:  a/sin A = b/sin B = c/sin C     a² = b² + c² − 2bc·cos A     Area = ½ab·sin C

sin(α ± β) = sin α cos β ± cos α sin β
cos(α ± β) = cos α cos β ∓ sin α sin β
cos 2α = cos²α − sin²α = 2cos²α − 1 = 1 − 2sin²α      sin 2α = 2 sin α cos α

x̄ = Σx / n      σ² = Σ(xᵢ − x̄)² / n

P(A) = n(A) / n(S)      P(A or B) = P(A) + P(B) − P(A and B)

ŷ = a + bx      b = Σ(x − x̄)(y − ȳ) / Σ(x − x̄)²
```

Note what's deliberately **not** on this sheet — e.g. the IQR outlier-fence formulas (`Q₁ − 1,5×IQR`, `Q₃ + 1,5×IQR`). Real DBE questions that need a formula not on the sheet state it inline in the question itself rather than assuming it's memorised; match that convention rather than padding the info sheet with extra formulas to cover every question. **This is also a genuine Complex-level lever** (see the difficulty check above): a sub-question that needs the IQR fence formula must either state it inline (Routine, method cued) or the learner must recall it from having used it before (Complex, if genuinely un-cued and combined with reading values off a graph).

**Grade 10: no information sheet at all.** Confirmed policy — formulas needed for a Gr 10 task/test are stated inline at question level instead (e.g. "Use the formula A = P(1 + i)ⁿ to determine..."). Do not generate or append any information sheet page for Grade 10 documents.

**Grade 11 and Grade 12: the complete information sheet, unabridged.** Same full sheet for both grades — do not trim it down to only the formulas relevant to that specific task's topics (this was already established above: real DBE papers print the full standard sheet regardless of which topics that paper actually covers). **Unless Anne-Marie says she'll add it herself — confirm this explicitly before building, and skip Section 2 entirely if so.**

**The information sheet is a real extracted image, not reconstructed plain text.** Confirmed necessary: the source PDF (a genuine Nov 2025 DBE past paper) has no text layer on this page at all — it's a scanned/image-based page, so there was no editable text or vector content to lift out even in principle. A hand-typed plain-text approximation was tried first and was visibly wrong in one specific way that matters: the real `cos 2α` entry uses a stacked brace grouping three alternative forms, which plain text with Unicode symbols cannot reproduce.

Use `add_information_sheet_image(doc, image_path)` from `/format`'s `table_helpers.py`. The extracted, cropped image is saved at `assets/information_sheet_gr11_gr12.png` in this skill folder — cropped to exclude the source paper's own header/footer branding ("Mathematics/P2", "DBE/November 2025", "Copyright reserved") **and** its own "INFORMATION SHEET" title bar, since the title is added separately as native Word text (matching the font/style of every other heading in the document) rather than being part of the image — don't add both, or the title appears twice.

## Verification (before delivery)

Everything in `/format`'s verification workflow (Steps 1–9, including gridline verification), plus task-specific checks:
- Render to PDF; check page images for border visibility, header text alignment, readability
- **Gridlines in all diagrams/graphs must be BLACK and clearly visible** in the PDF rendering (Step 3 of `/format` verification)
- **Also run the full file-integrity check** (zip test, XML well-formedness, content-types coverage) on any document containing hand-built OOXML before considering it done — see "Page border" above
- Confirm the cover page has **no** header text and **no** page number (border only)
- Confirm page numbering starts correctly from the instructions/questions section and continues through the information sheet (or through the last question if there's no information sheet section)
- Auto-count questions from document; verify matches the instructions page's `[AUTO-COUNT]`
- All displayed subtotals and totals independently recomputed (never hand-typed) — **including the standalone grand-total paragraph**, which must equal the sum of every question's own total
- Confirm cognitive-grid totals match the task's total marks
- Confirm mark weighting matches DBE targets per grade/paper, or Anne-Marie's specified custom split for a partial/combined-topic task
- Header/footer spacing consistent across all pages
- Page border visible on every page, using the native `w:pgBorders` approach — the border is a section property, so it doesn't need per-page embedding logic and can't desync from page boundaries the way an image-based approach could
- **Every drawing-based marking-guide answer (ogive, Venn diagram, tree diagram, etc.) shows an actual generated completed-answer image, not a text description**
