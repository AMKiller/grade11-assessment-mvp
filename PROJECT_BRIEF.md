# Grade 11 Assessment Generator — MVP Project Brief

Context for whoever/whatever picks this up next (written for a Claude Code session
starting from an empty repo). This captures everything decided in planning before
the build started.

## What this is

A Streamlit web app that generates Grade 11 CAPS Mathematics test papers
(question paper + marking guideline + cognitive level analysis grid) as a
downloadable .docx, with genuine native Word Math objects (not images, not
plain text) for every equation.

## Scope (MVP — deliberately narrow)

- **Grade 11 only.**
- **Two topics only:** Equations and Inequalities, Exponents and Surds.
- **"Balanced" cognitive-mode only** (prescribed FET target ratios: Knowledge
  20% / Routine 35% / Complex 30% / Problem-Solving 15%). Scaffold and
  Challenge modes are post-MVP.
- No auth, no payment, no rate limiting for the beta (2-3 known testers).

## Architecture decision (Sept 23, 2026) — stripped-down MVP, extensible seams, not extensible scaffolding

**A prior attempt at this same product exists** (`assessment-intelligence-platform`,
found on Anne-Marie's machine, origin/completeness unclear) with a full layered
backend already scaffolded: separate `api/`, `core/`, `database/`, `models/`,
`schemas/`, `services/`, `utils/` folders, an active venv. **Deliberately not
building on it.** A `database/` and `models/` layer with no actual database,
and a `services/` layer with no actual multi-user need yet, is exactly the
shape of a project that stalls on architecture before it ships one working
paper. Starting clean.

**The actual design principle for "add a database/login/more features later
without a rewrite"** is not to pre-build empty layers for them. It's to keep
the generation logic in plain functions with explicit inputs and outputs —
e.g. `generate_paper(topic, marks_split, cognitive_targets) -> Paper` — that
don't reach into a session, a request object, or global state. That function
is exactly as easy to wrap in a FastAPI endpoint or gate behind a login six
months from now as it is to call from a Streamlit script today. The
seam is in the function boundary, not in a folder structure built ahead of need.

**Concretely, MVP file shape should be flat and small:**
- `app.py` — Streamlit UI only (inputs, generate button, download button)
- `generation.py` — Claude API call + the sympy verification step; plain
  functions, no classes needed unless something genuinely calls for one
- `docgen.py` — wraps `table_helpers.py`/`mathml_omml.py` into
  "structured questions in → .docx bytes out"
- `knowledge_base.py` — loads/queries the two KB JSONs
- No `models/`, no `database/`, no `services/` layer, no user accounts.
  Every generated paper is a file the teacher downloads — nothing persisted
  server-side, so there's no data to migrate when accounts eventually exist.

## Proven building blocks (already built and working, carry these over)

All four files below were built and verified end-to-end in a prior chat session
(a real Grade 11 Task 7 paper was generated, rendered, and visually checked
page-by-page). They should be dropped into the new repo, not rebuilt from
scratch:

- `table_helpers.py` — python-docx table builders: hidden-border question-layout
  tables, visible-border 3-column marking-guide tables, cognitive-grid table,
  document/font setup, generic information-sheet image inserter.
- `mathml_omml.py` — mini-LaTeX-like DSL → real MathML → OMML (Word Math
  objects), via a real Microsoft stylesheet (see next file). Handles `^{}`,
  `_{}`, `\frac{}{}`, `\sqrt{}`, `\sqrt[n]{}`, unicode operators.
- `MML2OMML.XSL` — Microsoft's actual MathML-to-OMML conversion stylesheet
  (the same one Word itself uses). `mathml_omml.py` shells out to this via
  lxml's XSLT support. **Must sit in the same directory as `mathml_omml.py`.**
- `information_sheet_gr11_gr12.png` — cleaned, cropped genuine DBE information
  sheet image (Grade 11/12 standard formula sheet), no watermark, no title bar.

**Known gotchas from that build session, worth re-reading before debugging
from scratch:**
1. Rendering math for local verification requires LibreOffice's Math
   component specifically — `apt-get install -y libreoffice-math`. Without
   it, `<m:oMath>` elements are silently dropped on PDF conversion with no
   error at all (looks like a data bug, isn't one). **This is a dev-time
   verification dependency only — the deployed Streamlit app never renders
   a PDF, it only ever writes the .docx, so this is not a production
   dependency.**
2. A math object that opens with a bare relational operator (e.g. a
   continuation line `"=x^{-6}y^{4}"`) renders as a red error glyph in
   LibreOffice. `add_cell_content()` in `table_helpers.py` already works
   around this (peels a leading `=` into plain text first) — don't
   reintroduce the bug by calling `insert_inline_math()` directly on a
   string that starts with `=`.
3. Hand-writing OMML XML directly (skipping the MathML+XSLT step) fails
   silently — produces well-formed but unrenderable XML. Don't try to
   "simplify" by cutting out the XSLT step.

## Question bank

Two existing knowledge-base JSONs (already in this Claude project's files,
built via the past-paper-analyzer skill from real DBE past papers):
- Grade 11 Equations and Inequalities: 8 archetypes, 106 sub-questions
  extracted, `core`/`supplementary` evidence tiers.
- Grade 11 Exponents and Surds: 27 archetypes, 70 sub-questions extracted,
  `core`/`supplementary`/`rare_enrichment_only` evidence tiers (the
  rare-enrichment ones carry an explicit frequency cap — respect it).

**Generation policy (decided):** KB archetypes are the primary source of
*technique* — Claude should vary the specific numbers/context freely within
a chosen archetype, not be limited to the exact past-paper wording. Do not
invent question types with no archetype backing.

**Required safety net — do not skip this:** every generated question's
answer must be independently re-solved in Python (sympy) before being
accepted into a paper. This is what the human build session did by hand for
every single question (see the Task 7 session — every answer was
sympy-verified before drafting, and it still caught wrong tick-counts on
manual review). Trusting Claude's stated answer without independent
re-derivation is how a wrong mark scheme ships. Retry generation (or flag
for manual review) if the independent solve disagrees.

## Front matter (cover page) handling

- Teacher can **upload a one-page .docx template** containing literal
  placeholder tokens: `{{GRADE}}`, `{{TASK}}`, `{{TERM}}`, `{{TOTAL}}`,
  `{{TIME}}`, `{{EXAMINER}}`, `{{MODERATOR}}`, `{{TOPIC}}`. App does a
  straightforward find-and-replace on those tokens, then appends the
  generated content into the template's final section (same technique
  proven in the Task 7 build: locate the paragraph holding the section-break
  `sectPr`, insert after it).
- Missing tokens are just skipped, not a hard failure.
- **If no template uploaded:** generate a plain generic cover page in code
  (title block, no branding, no border image) — this needs building, it
  doesn't exist yet.

## Deployment

- **Streamlit Community Cloud**, public link, free tier.
- Repo: teacher (Anne-Marie) has a GitHub account but is starting this repo
  from scratch.
- No system-level (`packages.txt`) dependencies needed — `requirements.txt`
  only: `streamlit`, `python-docx`, `lxml`, `anthropic`.
- No auth/rate-limiting for the 2-3 person beta — explicitly deferred, not
  forgotten.

## Suggested build order (originally sketched against a ~9-day window,
Thu–Wed, one day lost to marking)

1. Repo scaffold; drop in the four proven files; generalize
   `table_helpers.py` calls from the hardcoded Task-7 content into
   parametrized functions.
2. Generic fallback cover-page builder + `{{TOKEN}}` template ingestion
   (find/replace + locate insertion point in an arbitrary uploaded docx).
3. Claude API generation layer: takes topic(s) + mark split + cognitive
   targets + relevant KB JSON as context → structured JSON out (questions,
   marking steps, cognitive level, archetype citation). Add the sympy
   verification step here — do not defer it.
4. Wire generation JSON → document assembly (reuse the table builders) →
   full paper end-to-end.
5. Streamlit UI: topic/marks/time inputs, examiner/moderator/task/term
   fields, template uploader, generate + download.
6. Verification pass: generate several real papers, render locally with
   `libreoffice-math` installed, check every page by eye (same discipline
   as the Task 7 build — rendered proof, not just "the code looks right").
7. Edge cases: thin-archetype handling, API failures, malformed JSON,
   timeouts/loading states.
8. Deploy to Streamlit Community Cloud, smoke-test the live link.

## Known product-level limitation to keep surfacing to beta testers

Structural cognitive-grid compliance (hitting the K/R/C/P percentages) is
not the same as pedagogically appropriate difficulty for a given cohort.
The tool removes tedium and enforces DBE-style structure; it can't judge
whether that structure is right for a specific class. Say this plainly in
the beta pitch, don't let the grid-compliance framing imply more than it
delivers.
