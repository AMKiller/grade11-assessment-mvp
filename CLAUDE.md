# Grade 11 Assessment Generator — Development Notes

## Formatting specification — read before touching generation.py or docgen.py

**`format_SKILL.md` and `task_SKILL (1).md` (in this repo root) are the authoritative formatting specification for the output document** — question numbering, table structure, marking-guide layout, cognitive grid, front matter, fonts, borders, spacing. They are not optional background reading; the question-numbering scheme, marking-guide structure, and cognitive grid described there are **not yet implemented** in `generation.py`/`docgen.py` as of Sept 23, 2026 (see the audit in that day's conversation history / git log around commit adding this note). Read both files in full at the start of any session that edits `generation.py` or `docgen.py`, before writing or changing a single line.

**Precedence rule when the skills conflict with `PROJECT_BRIEF.md`:** on front-matter (cover page, page border, branding, template tokens), `PROJECT_BRIEF.md` wins — the MVP's generic no-template fallback stays plain/unbranded/no-border, per PROJECT_BRIEF's explicit "no branding, no border image" instruction. On everything in the body of the paper (question numbering, tables, marking guide, cognitive grid), `format_SKILL.md` wins. **No `SECTION A`/`SECTION B` header wrapping around `QUESTION N` blocks even for multi-topic papers** — confirmed explicitly out of scope, despite appearing in the real reference document below.

**`Gr11_Task7_Equations_Exponents_QP_MG.docx` (in this repo root) is a real, human-approved reference document** — the actual proven output from the prior manual build session. When in doubt about a formatting/content detail the skill files don't fully pin down, check this file directly with python-docx rather than guessing from prose. This is how a real gotcha was caught: an earlier pass bound marking-guide tick labels to the KB's `marking_pattern.typical_breakdown` field verbatim (DBE-internal marker shorthand like `"A1 (CA): substitution..."`), but the real document's actual marking guide displays short plain-English labels instead — `"✓ substitution"`, `"✓ factors"`, `"✓✓ both answers"` — never the `A1`/`M1`/`CA` code itself. The KB field is documentation of the internal marking convention, not the display convention. If you're touching `marking_steps` generation, don't reintroduce this — `tick_label` must be a plain description, `typical_breakdown` guides structure (step count/order) not notation.

**Known, deliberately deferred gap:** the reference document shows genuine 3-level nesting (`1.5` as a shared stem, with `1.5.1`/`1.5.2` as separate scaffolded children, each with its own marks) — e.g. one simultaneous-equations question split into "show that it reduces to..." then "hence solve." The current generator only produces flat depth-0 numbering (`1.1`, `1.2`, `1.3`...) — every generated question is a single, complete, non-nested archetype instance. Supporting real nesting would mean teaching the generator a new output shape (stem + several numbered sub-parts) and deciding which archetypes naturally scaffold this way vs. staying atomic (most stay atomic). Scoped as a future enhancement, not a bug — discussed and explicitly deferred on Sept 23, 2026.

## Architecture Decisions (Sept 23, 2026)

**Flat-file, no pre-scaffolded layers.** Every generated paper is a file downloaded by the teacher — nothing persisted server-side. This keeps the system simple and makes it trivial to add auth/persistence later (the seam is in the function boundary, not a folder structure).

### File Structure

- **app.py** — Streamlit UI only (inputs, generate, download)
- **generation.py** — Claude API + sympy verification (plain functions, no classes except GeneratedQuestion)
- **knowledge_base.py** — Load/query two KB JSONs
- **docgen.py** — Assemble questions → .docx bytes
- **table_helpers.py, mathml_omml.py, MML2OMML.XSL** — Proven from prior build; do not rewrite
- **information_sheet_gr11_gr12.png** — DBE formula sheet image

### Key Design Constraints

1. **SymPy verification is non-negotiable.** Every answer must be independently re-solved before acceptance. The human build session (Task 7) did this by hand; we do it in code.

   **Gotcha (found + fixed Sept 23, 2026):** an early implementation of `_verify_answer()` was a stub that looked convincing but did nothing real — it parsed Claude's own `answer_expression` string and checked if *that* had solutions, which is circular (verifies the answer is self-consistent, not that it's correct). If you're touching verification logic, the actual design is: Claude emits a separate machine-parseable `sympy_problem` (the equation/inequality/system, distinct from the human-readable question) plus a `claimed_solution`, tagged by `problem_type`. We solve `sympy_problem` from scratch with SymPy and numerically compare against `claimed_solution`. `problem_type: "unverifiable"` (proofs, "verify that" identities, word problems with no clean symbolic form) is explicitly flagged `manual_review_required=True`, never silently passed. See `test_verification.py` for the contract this must keep satisfying — it includes a deliberately-wrong-answer case that must fail, and a legitimate-root-rejection case (e.g. discarding a negative length) that must still pass.

2. **Claude varies numbers/context freely within archetypes.** KB archetypes are technique sources, not exact question templates. Do not invent question types without archetype backing.

3. **CAPS balanced cognitive mode only** (MVP). K20/R35/C30/PS15 targets. Scaffold/Challenge are post-MVP.

4. **No database, no user accounts.** Every paper is a download. Rate limiting is deferred (not forgotten).

## Critical Gotchas (from prior build session)

**LibreOffice Math requirement (dev-time only):**
- Local rendering verification needs `apt-get install -y libreoffice-math`
- Without it, `<m:oMath>` elements are silently dropped on PDF conversion (looks like a data bug, isn't)
- **Not a production dependency** — the Streamlit app never renders a PDF, only writes .docx

**Math object rendering edge cases:**
- A math object opening with a bare relational operator (e.g. "=x^{-6}") renders as red error in LibreOffice
- `add_cell_content()` in `table_helpers.py` already handles this (peels leading "=" into plain text)
- Don't bypass this by calling `insert_inline_math()` directly on strings starting with "="

**OMML/XSLT step is mandatory:**
- Hand-writing OMML XML directly (skipping MathML+XSLT) fails silently
- Always go through mathml_omml.py's XSLT conversion

## Usage Tiers in Knowledge Bases

Each archetype carries a `usage_guidance.tier`:
- **core** (3+ examples, independent papers) — draw on freely
- **supplementary** (1-2 examples) — use occasionally, shouldn't dominate
- **rare_enrichment_only** (single example, often Level 4) — cap deliberately (frequency_cap field)

The MVP app filters to "core" + "supplementary" by default; `rare_enrichment_only` is for optional challenge questions only.

## Testing

Run `python3 test_integration.py` to verify:
- KB loading and archetype sampling
- GeneratedQuestion serialization
- Document generation (produces valid .docx)
- Cognitive distribution analysis

This test **does not call Claude API**, so no ANTHROPIC_API_KEY needed.

## Deployment to Streamlit Community Cloud

1. Ensure `requirements.txt` is current
2. Create `streamlit_app = app.py` symlink or rename
3. Push main to GitHub
4. Connect repo at https://share.streamlit.io/
5. Set `ANTHROPIC_API_KEY` in Streamlit secrets (Settings → Secrets)
6. Smoke-test live link (generate one paper, download, spot-check)

## Next Steps (Post-MVP)

- Edge case handling: thin-archetype warnings, API timeout/retry logic, malformed JSON
- Manual marking-guide annotation UI (questions 1–5 have template, user fills in steps)
- Generic fallback cover page (currently minimal; could add school branding placeholder)
- Scaffold/Challenge cognitive modes
- Auth + paper history (requires persistence layer; refactor is minimal: generation.py functions remain unchanged)

## Known Product Limitations (Communicate to Beta Testers)

- Structural cognitive-grid compliance ≠ pedagogically appropriate difficulty for a specific cohort
- The tool removes tedium and enforces DBE-style structure; it cannot judge whether that structure suits a given class
- Balanced mode only (MVP); Scaffold/Challenge deferred
