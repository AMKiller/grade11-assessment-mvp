# Grade 11 Assessment Generator — Development Notes

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
