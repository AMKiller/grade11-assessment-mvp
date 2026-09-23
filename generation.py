import ast
import json
import os
import random
import time
from types import SimpleNamespace
from typing import Optional
import anthropic
from anthropic import Anthropic
from sympy import (
    sympify, solve, solveset, solve_univariate_inequality, symbols, simplify,
    Eq, Interval, Union, FiniteSet, S, oo
)
from sympy.parsing.sympy_parser import parse_expr
from knowledge_base import KnowledgeBase
from mathml_omml import latex_to_omath


client = Anthropic()
kb = KnowledgeBase()

# Single config constant for the generation model -- lets us compare Opus 5.5
# vs Sonnet 5 on the same paper for cost and quality without editing code.
# Override via the GENERATION_MODEL env var (e.g. GENERATION_MODEL=claude-opus-5-5).
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "claude-sonnet-5")


# ============================================================
# API call retry policy -- fail-fast on non-retryable errors
# ============================================================

# Transient errors: worth retrying with backoff, since the same request is
# likely to succeed shortly after. RateLimitError=429, InternalServerError
# covers all 5xx, APIConnectionError covers network failures (its subclass
# APITimeoutError is caught too).
RETRYABLE_API_EXCEPTIONS = (
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.APIConnectionError,
)

MAX_API_RETRIES = 5
API_RETRY_BASE_DELAY = 1.0  # seconds; doubles each attempt


class NonRetryableAPIError(Exception):
    """
    Raised for any Anthropic API error that must NOT be retried -- 400
    (including "credit balance too low" and "prompt too long", which are
    real fatal problems that asking again won't fix), 401 (bad API key),
    403 (permission denied), or any other non-transient API error -- and
    also once MAX_API_RETRIES is exhausted on a genuinely transient error,
    since a rate limit or outage that hasn't cleared after several backoff
    attempts won't clear for the next question either.

    This is meant to propagate all the way up through generate_question()
    and generate_paper() and abort the ENTIRE paper immediately, unlike a
    verification failure or malformed-JSON retry (see generate_question()),
    which only affects the one question being generated. Wraps the
    original exception in .original so callers/UI can show its real detail.
    """
    def __init__(self, original: Exception):
        self.original = original
        super().__init__(str(original))


def _call_claude_with_retry(**kwargs):
    """
    Call the Anthropic API with fail-fast retry semantics. See
    RETRYABLE_API_EXCEPTIONS / NonRetryableAPIError for the policy.
    """
    last_exception = None
    for attempt in range(MAX_API_RETRIES):
        try:
            return client.messages.create(**kwargs)
        except RETRYABLE_API_EXCEPTIONS as e:
            last_exception = e
            if attempt < MAX_API_RETRIES - 1:
                delay = API_RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                print(
                    f"  [api retry] {type(e).__name__} (attempt {attempt + 1}/{MAX_API_RETRIES}), "
                    f"retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                continue
            raise NonRetryableAPIError(e) from e
        except anthropic.APIError as e:
            # Anything else (400/401/403/404/422/...) is not in the
            # retryable set above -- fail fast, no retry.
            raise NonRetryableAPIError(e) from e

    raise NonRetryableAPIError(last_exception) from last_exception

# ============================================================
# Hierarchical Structure Support
# ============================================================

def validate_hierarchical_structure(data: dict, target_marks: int) -> tuple[bool, list[str]]:
    """Validate hierarchical question structure before sending to docgen."""
    errors = []

    if not isinstance(data, dict) or "question_structure" not in data:
        return False, ["Missing 'question_structure' key"]

    structure = data.get("question_structure", [])
    if not isinstance(structure, list) or not structure:
        return False, ["'question_structure' must be a non-empty list"]

    total_leaf_marks = 0

    for i, row in enumerate(structure):
        if not isinstance(row, dict):
            errors.append(f"Row {i}: must be a dict")
            continue

        is_stem = row.get("is_stem", False)
        marks = row.get("marks")
        cognitive_level = row.get("cognitive_level")

        if is_stem:
            if marks is not None:
                errors.append(f"Row {i}: stem row must have marks=null, got {marks}")
            if cognitive_level is not None:
                errors.append(f"Row {i}: stem row must have cognitive_level=null")

            children = row.get("children", [])
            if not isinstance(children, list) or len(children) < 2:
                errors.append(f"Row {i}: stem must have ≥2 children, got {len(children)}")

            for j, child in enumerate(children):
                if not isinstance(child.get("marks"), int) or child.get("marks", 0) <= 0:
                    errors.append(f"Row {i}, child {j}: marks must be >0")
                else:
                    total_leaf_marks += child.get("marks")

                if child.get("cognitive_level") not in ["knowledge", "routine", "complex", "problem_solving"]:
                    errors.append(f"Row {i}, child {j}: invalid cognitive_level")

                tick_sum = sum(s.get("tick_count", 0) for s in child.get("marking_steps", []))
                if tick_sum != child.get("marks"):
                    errors.append(f"Row {i}, child {j}: tick_count {tick_sum} != marks {child.get('marks')}")
        else:
            if not isinstance(marks, int) or marks <= 0:
                errors.append(f"Row {i}: flat row marks must be >0")
            else:
                total_leaf_marks += marks

            if cognitive_level not in ["knowledge", "routine", "complex", "problem_solving"]:
                errors.append(f"Row {i}: invalid cognitive_level")

            tick_sum = sum(s.get("tick_count", 0) for s in row.get("marking_steps", []))
            if tick_sum != marks:
                errors.append(f"Row {i}: tick_count {tick_sum} != marks {marks}")

    if total_leaf_marks != target_marks:
        errors.append(f"Total leaf marks {total_leaf_marks} != target {target_marks}")

    return len(errors) == 0, errors


def _generate_numbering_for_hierarchy(hierarchy: dict) -> dict:
    """Add Python-generated numbering to hierarchical structure."""
    numbered = {"question_structure": [], "total_marks": hierarchy.get("total_marks", 0)}
    question_num = 1

    for row in hierarchy.get("question_structure", []):
        if row.get("is_stem"):
            row["num"] = str(question_num)
            numbered["question_structure"].append(row)

            for child_idx, child in enumerate(row.get("children", []), 1):
                child["num"] = f"{question_num}.{child_idx}"

            question_num += 1
        else:
            row["num"] = str(question_num)
            numbered["question_structure"].append(row)
            question_num += 1

    return numbered


def _normalize_parts(value) -> list:
    """
    Accept either a plain string (wrapped as a single text part, for
    backward compat / hand-constructed test questions) or a list of
    {"type": "text"|"math", "value": str} parts (the real generation
    output), and always return the parts-list form.
    """
    if isinstance(value, str):
        return [{"type": "text", "value": value}]
    if isinstance(value, list):
        return value
    return [{"type": "text", "value": str(value)}]


def parts_to_plain_text(parts: list) -> str:
    """Join parts into a plain-text approximation for previews/debugging.
    Math parts are shown as their raw DSL source -- not pretty, but the
    real rendering happens via OMML in the actual .docx, not here."""
    out = []
    for part in parts:
        out.append(part.get("value", ""))
    return "".join(out)


class GeneratedQuestion:
    def __init__(self, archetype_id: str, question_text, answer_text,
                 answer_expression: str, marks: int, cognitive_level: str,
                 problem_type: str = "unverifiable", sympy_problem: str = "",
                 claimed_solution: str = "", marking_steps: list = None):
        """
        question_text / answer_text: either a plain string, or a list of
        {"type": "text"|"math", "value": str} parts -- the latter is what
        real generation produces, so docgen.py can route "math" parts
        through insert_inline_math() for genuine Word Math objects instead
        of plain unicode text.
        """
        self.archetype_id = archetype_id
        self.question_parts = _normalize_parts(question_text)
        self.answer_parts = _normalize_parts(answer_text)
        self.answer_expression = answer_expression
        self.marks = marks
        self.cognitive_level = cognitive_level
        self.problem_type = problem_type
        self.sympy_problem = sympy_problem
        self.claimed_solution = claimed_solution
        self.marking_steps = marking_steps or []
        self.sympy_verified = False
        self.manual_review_required = False
        self.sympy_error = None
        self.marking_fidelity_warning = None

    @property
    def question_text(self) -> str:
        """Plain-text rendering of question_parts, for previews/logging."""
        return parts_to_plain_text(self.question_parts)

    @property
    def answer_text(self) -> str:
        """Plain-text rendering of answer_parts, for previews/logging."""
        return parts_to_plain_text(self.answer_parts)

    def to_dict(self):
        return {
            "archetype_id": self.archetype_id,
            "question": self.question_text,
            "answer": self.answer_text,
            "answer_expression": self.answer_expression,
            "marks": self.marks,
            "cognitive_level": self.cognitive_level,
            "problem_type": self.problem_type,
            "marking_steps": self.marking_steps,
            "sympy_verified": self.sympy_verified,
            "manual_review_required": self.manual_review_required,
            "sympy_error": self.sympy_error,
            "marking_fidelity_warning": self.marking_fidelity_warning
        }


def _log_api_call(message, purpose: str, attempt: int = 0) -> dict:
    """
    Extract usage stats from an Anthropic API response and print a one-line
    log entry. Returns a plain dict record for later summarization -- no
    new dependencies, just stdlib.
    """
    usage = getattr(message, 'usage', None)
    record = {
        "purpose": purpose,
        "attempt": attempt + 1,
        "model": getattr(message, 'model', 'unknown'),
        "input_tokens": getattr(usage, 'input_tokens', 0) or 0,
        "output_tokens": getattr(usage, 'output_tokens', 0) or 0,
        "cache_read_input_tokens": getattr(usage, 'cache_read_input_tokens', 0) or 0,
        "cache_creation_input_tokens": getattr(usage, 'cache_creation_input_tokens', 0) or 0,
    }
    print(
        f"  [usage] {purpose} (attempt {record['attempt']}): "
        f"in={record['input_tokens']} out={record['output_tokens']} "
        f"cache_read={record['cache_read_input_tokens']} "
        f"cache_write={record['cache_creation_input_tokens']}"
    )
    return record


def _summarize_usage(usage_log: list) -> dict:
    """Roll up a list of _log_api_call records into per-paper totals."""
    total_calls = len(usage_log)
    total_input = sum(r["input_tokens"] for r in usage_log)
    total_output = sum(r["output_tokens"] for r in usage_log)
    total_cache_read = sum(r["cache_read_input_tokens"] for r in usage_log)
    total_cache_write = sum(r["cache_creation_input_tokens"] for r in usage_log)
    retries = sum(1 for r in usage_log if r["attempt"] > 1)

    return {
        "total_calls": total_calls,
        "retries": retries,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cache_read_tokens": total_cache_read,
        "total_cache_creation_tokens": total_cache_write,
    }


def print_usage_summary(usage_log: list, label: str = "Paper"):
    s = _summarize_usage(usage_log)
    print(f"\n=== API Usage Summary: {label} ===")
    print(f"  Total calls: {s['total_calls']} ({s['retries']} were retries)")
    print(f"  Total input tokens:  {s['total_input_tokens']}")
    print(f"  Total output tokens: {s['total_output_tokens']}")
    print(f"  Cache read tokens:     {s['total_cache_read_tokens']}")
    print(f"  Cache creation tokens: {s['total_cache_creation_tokens']}")
    return s


class QuestionGenerator:
    def __init__(self, topic: str, api_key: str = None):
        self.topic = topic
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self.kb = kb
        self.selected_archetypes = []
        self.usage_log = []

    def select_archetypes(self, num_questions: int,
                         target_distribution: dict = None,
                         prefer_core: bool = True,
                         seed: int = None):
        """
        Select archetypes for a paper.

        Args:
            num_questions: How many archetypes to select
            target_distribution: Cognitive % targets (K/R/C/P)
            prefer_core: If True, filter to ["core", "supplementary"] only,
                        excluding rare_enrichment_only items
            seed: Random seed
        """
        tier_filter = ["core", "supplementary"] if prefer_core else None

        self.selected_archetypes = self.kb.sample_by_cognitive_distribution(
            self.topic,
            num_archetypes=num_questions,
            target_distribution=target_distribution,
            tier_filter=tier_filter,
            seed=seed
        )

    def generate_question(self, archetype_id: str, marks: int = None,
                         cognitive_targets: dict = None,
                         max_retries: int = 3) -> Optional[dict]:
        """
        Generate a single (possibly hierarchical) question from an
        archetype, with sympy verification of every leaf.

        Args:
            archetype_id: Which archetype to generate from
            marks: Marks for this question (if None, inferred from archetype pattern)
            cognitive_targets: {level: marks} dict fixing, BEFORE the call,
                how this slot's marks split across cognitive levels. This
                is the leaf plan's output for this slot -- see
                _build_leaf_plan / generate_paper. If None, defaults to
                all marks at "routine" (matches old flat-question behavior).
            max_retries: How many times to retry if any leaf fails verification

        Returns:
            The numbered hierarchical dict (question_structure + total_marks)
            if successful (or after retries are exhausted, with failing
            leaves flagged manual_review_required=True), None only if every
            attempt raised (malformed JSON, failed validation, unsupported
            math) rather than merely failing verification.
        """
        archetype = self.kb.get_archetype(self.topic, archetype_id)

        if marks is None:
            marks = archetype.marking_pattern.get("typical_total_marks", 3)
            if marks is None:
                marks = 3

        if cognitive_targets is None:
            cognitive_targets = {'knowledge': 0, 'routine': marks, 'complex': 0, 'problem_solving': 0}

        last_exception = None

        for attempt in range(max_retries):
            try:
                data = self._call_claude(archetype, marks, cognitive_targets, attempt=attempt)
            except NonRetryableAPIError:
                # Fail fast: a non-retryable API error (bad request, bad
                # credentials, insufficient credit, etc.) is not a
                # generation-quality problem this question's retry loop can
                # fix -- retrying would just repeat the same fatal error.
                # Propagate immediately so generate_paper() aborts the
                # whole paper instead of burning retries per question.
                raise
            except Exception as e:
                last_exception = e
                print(f"  Attempt {attempt + 1}/{max_retries}: {type(e).__name__}: {e}")
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"All {max_retries} attempts failed. Last error: {type(last_exception).__name__}: {last_exception}"
                    ) from last_exception
                continue

            data["archetype_id"] = archetype.archetype_id
            all_verified, failed_leaves = self._verify_all_leaves(data)

            if all_verified:
                return data
            elif attempt < max_retries - 1:
                print(f"  Attempt {attempt + 1}/{max_retries}: {len(failed_leaves)} leaf(s) failed verification "
                      f"({', '.join(failed_leaves)}), retrying...")
                continue
            else:
                print(f"  All {max_retries} attempts exhausted. "
                      f"{len(failed_leaves)} leaf(s) flagged for manual review.")
                return data

        return None

    def _verify_all_leaves(self, data: dict) -> tuple[bool, list]:
        """
        Independently verify every leaf (a flat row, or one of a stem's
        children) in a hierarchical question structure. Mutates each leaf
        dict in place with sympy_verified / manual_review_required /
        sympy_error -- the same contract flat GeneratedQuestion verification
        used, now applied per-leaf since a single Claude call can return
        several independently-markable leaves.

        Returns (all_verified, failed_leaf_labels).
        """
        all_ok = True
        failures = []

        def verify_leaf(leaf: dict, label: str):
            nonlocal all_ok
            if leaf.get("problem_type") == "unverifiable":
                leaf["manual_review_required"] = True
                leaf["sympy_verified"] = False
                leaf["sympy_error"] = (
                    "Not mechanically verifiable by SymPy (proof/identity/word problem archetype) "
                    "-- flagged for manual review, not independently confirmed."
                )
                return

            ns = SimpleNamespace(
                problem_type=leaf.get("problem_type"),
                sympy_problem=leaf.get("sympy_problem", ""),
                claimed_solution=leaf.get("claimed_solution", "")
            )
            verified, detail = self._verify_answer(ns)
            leaf["sympy_verified"] = verified
            if verified:
                leaf["manual_review_required"] = False
                leaf["sympy_error"] = None
            else:
                leaf["manual_review_required"] = True
                leaf["sympy_error"] = f"Independent SymPy solve disagreed with claimed answer: {detail}"
                all_ok = False
                failures.append(label)

        for i, row in enumerate(data.get("question_structure", [])):
            if row.get("is_stem"):
                for j, child in enumerate(row.get("children", [])):
                    verify_leaf(child, f"row[{i}].child[{j}]")
            else:
                verify_leaf(row, f"row[{i}]")

        return all_ok, failures

    def _call_claude(self, archetype, marks: int, cognitive_targets: dict = None, attempt: int = 0) -> dict:
        """Call Claude to generate a question structure from an archetype.

        Returns a dict with question_structure (list of rows) and total_marks.
        Rows may be flat or stems with children; numbering is added by Python."""
        system_prompt = f"""You are a Grade 11 Mathematics assessment generator for {self.topic}.

You will generate realistic exam-style questions based on established archetypes,
varying the numbers and context freely within the archetype's scope.

Respond ONLY with valid JSON, no other text. Generate ONE QUESTION block (hierarchical or flat).

JSON STRUCTURE:
{{
    "question_structure": [
        {{
            "type": "stem_row",
            "is_stem": true,
            "parts": [{{"type": "text", "value": "context text"}}],
            "marks": null,
            "cognitive_level": null,
            "children": [
                {{"parts": [...], "marks": 2, "cognitive_level": "routine", "answer": [...], "marking_steps": [...], "problem_type": "...", "sympy_problem": "...", "claimed_solution": "..."}},
                {{"parts": [...], "marks": 3, "cognitive_level": "complex", ...}}
            ]
        }},
        {{
            "type": "flat_row",
            "is_stem": false,
            "parts": [{{"type": "text", "value": "Solve: "}}],
            "marks": 2,
            "cognitive_level": "routine",
            "answer": [...],
            "marking_steps": [...],
            "problem_type": "equation",
            "sympy_problem": "...",
            "claimed_solution": "..."
        }}
    ],
    "total_marks": 6
}}

DO NOT generate numbering strings (no "1.1", "1.5.1"). Python assigns numbers.

CRITICAL: "sympy_problem" and "claimed_solution" exist so your answer can be independently
re-solved and checked by SymPy before this question is accepted into a real assessment.
Get these exactly right -- a wrong answer that passes this check ships to real students.

MATH NOTATION -- applies to "question", "answer", and every marking_steps[].parts (human-readable
content that ends up in the actual document, rendered as real native Word equation objects, not
plain text or an image). Every one of these fields is a JSON list of parts, each part one of:
    {{"type": "text", "value": "Solve for x: "}}
    {{"type": "math", "value": "2x^{{2}}+x-5=0"}}
Split at every boundary between prose and mathematical notation -- e.g. "Solve for x: " is a text
part, "2x^{{2}}+x-5=0" is a math part. A string with no math in it is still a list, just with one
text part, e.g. [{{"type": "text", "value": "Show that the answer is unique."}}].

Inside a "math" part's value, you may ONLY use this notation (this is a small DSL, not full
LaTeX -- anything outside this list will fail to render and the whole question will be rejected):
  - "^{{...}}" or "^x" for superscript/exponent, "_{{...}}" or "_x" for subscript
  - "\\frac{{a}}{{b}}" for a fraction, "\\sqrt{{x}}" for a square root, "\\sqrt[n]{{x}}" for an nth root
  - "{{...}}" for grouping
  - unicode symbols typed directly for everything else: ± ≤ ≥ ≠ · ÷ √ Δ ∈ ∞ π etc. -- do NOT use
    LaTeX commands for these (no \\leq, \\geq, \\neq, \\left(, \\right), \\text{{}}, \\dfrac, \\cdot
    is the one exception that IS supported, but prefer the unicode · directly)
  - plain digits/letters/operators as needed
Decimals use South African comma notation even inside math parts, e.g. {{"type": "math", "value":
"1,35"}} -- this parses correctly as a single number, same as "1.35" would.

This restriction does NOT apply to "sympy_problem" or "claimed_solution" -- those two fields stay
in standard Python/JSON numeric syntax with periods, are NOT split into parts, and are never
rendered as math objects (they're parsed by code, not displayed).

"marking_steps" is a JSON list of objects, one per line of working, in the order a marker would
tick them, e.g.:
[
    {{"parts": [{{"type": "math", "value": "2x^{{2}} - x - 6 = 0"}}], "tick_label": "standard form", "tick_count": 1}},
    {{"parts": [{{"type": "math", "value": "(2x + 3)(x - 2) = 0"}}], "tick_label": "factors", "tick_count": 1}},
    {{"parts": [{{"type": "math", "value": "x = -3/2"}}, {{"type": "text", "value": " or "}}, {{"type": "math", "value": "x = 2"}}], "tick_label": "both answers", "tick_count": 2}}
]
Each step's "parts" follows the exact same MATH NOTATION rules as "question"/"answer" above.
The archetype's own "typical_breakdown" (given below, under Marking pattern) is the PRIMARY
STRUCTURAL GUIDE for this list -- it comes from real DBE marking memos, not a suggestion. Follow
its step count and order as closely as the specific question you're generating allows. But its
notation (A1, M1, A1 (CA) etc.) is the internal shorthand this project's knowledge base was
documented in -- NOT what appears in the final marking guide. For "tick_label", write a short
plain-English description of what's being credited instead -- e.g. "substitution", "factors",
"critical value", "answer", "standard form", "expand", "completing the square", "conclusion",
"setup". Never output "A1", "M1", "CA", or any DBE-internal code as the tick_label itself.

"tick_count" is normally 1 (one tick). Use 2 only when a single line legitimately earns two
marks credited together as one combined tick (e.g. a compound answer like "x = 3 or x = -2"
where the archetype's typical_breakdown shows something like "A1+A1: both value(s)") -- in that
case set tick_label to something like "both answers"/"both values"/"both x-values" and
tick_count: 2; do not split that into two separate step objects. Use tick_count: 0 (and
tick_label: null) only for a rare pure intermediate line with no mark of its own -- most steps
in most archetypes carry a tick. The LAST step must be the final answer, exactly matching "answer".

You may deviate from typical_breakdown's exact step count/order ONLY when the archetype's own
"consensus" or "notes" field explicitly documents that this kind of variation is legitimate (e.g.
an accepted alternative method, or a special case needing an extra step) -- match that documented
variation, don't invent a new one. Do not compress multiple ticked steps into one object beyond
the tick_count:2 compound-answer case above -- one tick-worthy operation per step, matching real
DBE marking guide granularity.

COGNITIVE LEVEL -- use these concrete definitions, not just the label names, when setting
"cognitive_level" (self-labelling a question "complex" because it has many marks, without it
actually requiring a decision or skill-combination, is a common and serious mistake):
- "knowledge": a single recall step or direct formula substitution, no decision-making.
- "routine": a standard multi-step procedure the learner has drilled before, applied to new
  numbers -- the method to use is obvious from how the question is phrased.
- "complex": the learner must DECIDE which procedure applies (the question does not name the
  method), OR must combine two or more previously-separate skills in one sub-question. If the
  required method is unambiguous from the wording alone, it is NOT complex, no matter how many
  marks or steps it has.
- "problem_solving": genuinely unfamiliar in structure -- requires adapting a known technique to
  a scenario that doesn't map directly onto a drilled question type, often needing an insight not
  explicitly cued by the question.
Red flag that a question is mislabelled: if you named the method in the question text itself
("using the quadratic formula, solve..."), that removes the decision-making that would justify
"complex" or higher -- it's "routine" regardless of mark value.

Rules for "problem_type" and the two machine-readable fields:

1. problem_type = "equation" (single-variable equation solved for x):
   - sympy_problem: the equation rearranged to "<expr> = 0" form, giving ONLY the left side
     expression using Python/SymPy syntax (x**2 for powers, sqrt(x) for roots, no "=0" needed
     -- just the expression that equals zero). Example: for "2x+1=5/x" write "2*x**2 + x - 5"
     (after clearing the fraction: 2x^2+x-5=0). If a fraction can't be cleared to a polynomial
     (e.g. it has a sqrt of x), still provide a single expression equal to zero.
   - claimed_solution: a Python list of the numeric x-values you claim solve it, e.g. "[1.35, -1.85]".
     If the question asks for 2 decimal places, round to match. If a value must be REJECTED
     (e.g. makes a denominator zero, or is negative for a surd/geometric-length problem), DO NOT
     include the rejected value in claimed_solution -- only include values that are actually the
     final accepted answer.

2. problem_type = "inequality" (single-variable inequality solved for x):
   - sympy_problem: the inequality in Python/SymPy syntax, one side vs 0, e.g. "2*x**2 - 5*x - 12 <= 0"
   - claimed_solution: a SymPy Interval/Union expression as a string representing your claimed
     solution set, e.g. "Interval(-1.5, 4)" or "Union(Interval.open(-oo,-3), Interval.open(5,oo))"

3. problem_type = "system" (simultaneous equations in x and y):
   - sympy_problem: two equations separated by a semicolon, each in "<expr>=0" form using x and y,
     e.g. "y - 2*x + 1; x**2 + y**2 - 10"
   - claimed_solution: a Python list of (x, y) tuples you claim solve the system, e.g. "[(1, 1), (-2.2, -5.4)]"

4. problem_type = "unverifiable" (use ONLY when none of the above apply -- proofs, "verify that"
   identities, general parametric proofs, geometry/word problems requiring real-world interpretation
   that can't be reduced to a clean symbolic equation/inequality/system):
   - sympy_problem: leave as empty string ""
   - claimed_solution: leave as empty string ""
   - Prefer problem_type "equation"/"inequality"/"system" whenever the archetype allows it --
     only use "unverifiable" when there is genuinely no clean symbolic form.
"""

        archetype_context = f"""
Archetype: {archetype.name} ({archetype.archetype_id})
Description: {archetype.description}

Marking pattern: {json.dumps(archetype.marking_pattern, indent=2)}
Language notes: {archetype.language_notes}

Marks for this question: {marks}

Cognitive level targets (REQUIRED, not a hint): {json.dumps(cognitive_targets or {'knowledge': 0, 'routine': marks, 'complex': 0, 'problem_solving': 0})}
This was computed by the paper's mark-allocation plan BEFORE this archetype was chosen for this
slot -- your leaves' marks MUST sum to these targets, level by level. If this archetype's usual
examples sit at a different level than what's required here (e.g. the target calls for "complex"
but this archetype's typical instance is "knowledge"/"routine"), you MUST REDESIGN the question to
genuinely reach that level per the COGNITIVE LEVEL definitions above -- add a decision point the
question doesn't name outright, combine two of the archetype's skills into one sub-question,
remove a cue that tells the learner which method to use, etc. Do NOT simply keep the archetype's
usual routine question and relabel cognitive_level to something higher; that mislabels the paper's
actual difficulty and defeats the point of this target. If a target level genuinely cannot be
reached within this archetype's scope even after a real redesign attempt, generate the closest
legitimate level instead of a false label -- an honest mismatch is preferred over a fake one, and
will be visible in the paper's printed grid rather than silently hidden.

Generate ONE new question in this archetype's style.
Vary the numbers and specific context - do NOT use the exact past-paper examples.
Your output may use flat rows (independent sub-questions) or hierarchical (stem + children) --
a natural way to hit multiple cognitive levels in one slot is a stem with children at different
levels (e.g. a "routine" first part and a "complex" second part), matching the target's split.
"""

        message = _call_claude_with_retry(
            model=GENERATION_MODEL,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": archetype_context
                }
            ],
            system=system_prompt
        )

        self.usage_log.append(_log_api_call(
            message, purpose=f"generate_question:{archetype.archetype_id}", attempt=attempt
        ))

        # Extract text from response, skipping thinking blocks
        response_text = None
        for block in message.content:
            if hasattr(block, 'text'):
                response_text = block.text.strip()
                break

        if not response_text:
            raise ValueError("No text content in Claude response")

        # Strip markdown code fences if Claude wraps the JSON in ```json ... ```
        if response_text.startswith("```"):
            response_text = response_text.strip("`")
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            if getattr(message, 'stop_reason', None) == 'max_tokens':
                raise ValueError(
                    f"Response truncated (hit max_tokens limit) before valid JSON completed -- "
                    f"increase max_tokens. Truncated text: {response_text[-200:]}"
                ) from e
            raise ValueError(f"Claude response was not valid JSON: {response_text}") from e

        # Validate hierarchical structure
        is_valid, errors = validate_hierarchical_structure(data, marks)
        if not is_valid:
            raise ValueError(f"Invalid hierarchical structure: {'; '.join(errors)}")

        # Validate all math parts across the hierarchy
        for i, row in enumerate(data.get("question_structure", [])):
            self._validate_math_parts(row.get("parts", []), f"row[{i}].parts")
            if row.get("is_stem"):
                for j, child in enumerate(row.get("children", [])):
                    self._validate_math_parts(child.get("parts", []), f"row[{i}].child[{j}].parts")
                    self._validate_math_parts(child.get("answer", []), f"row[{i}].child[{j}].answer")
                    for k, step in enumerate(child.get("marking_steps", [])):
                        self._validate_math_parts(step.get("parts", []), f"row[{i}].child[{j}].marking_steps[{k}]")
            else:
                self._validate_math_parts(row.get("answer", []), f"row[{i}].answer")
                for k, step in enumerate(row.get("marking_steps", [])):
                    self._validate_math_parts(step.get("parts", []), f"row[{i}].marking_steps[{k}]")

        # Add Python-generated numbering
        numbered_data = _generate_numbering_for_hierarchy(data)

        # Return the hierarchical structure (will be processed by docgen)
        return numbered_data

    def _validate_math_parts(self, parts: list, context_label: str):
        """
        Run every "math"-type part through the real OMML converter before
        accepting this question -- an unsupported LaTeX construct here would
        otherwise ship as a silently-broken (or missing) equation in the
        final .docx. Raising here feeds into the existing generate_question()
        retry loop, same as a sympy verification failure or a JSON parse error.
        """
        if not isinstance(parts, list):
            raise ValueError(f"{context_label}: expected a list of parts, got {type(parts).__name__}")
        for i, part in enumerate(parts):
            if not isinstance(part, dict) or "type" not in part or "value" not in part:
                raise ValueError(f"{context_label}[{i}]: malformed part, expected {{type, value}}: {part}")
            if part["type"] == "math":
                try:
                    latex_to_omath(part["value"])
                except Exception as e:
                    raise ValueError(
                        f"{context_label}[{i}]: math part {part['value']!r} failed to render as a "
                        f"Word math object ({type(e).__name__}: {e}) -- only the supported DSL subset "
                        f"is allowed (^{{}}, _{{}}, \\frac{{}}{{}}, \\sqrt{{}}, \\sqrt[n]{{}}, \\cdot, and "
                        f"unicode symbols typed directly for everything else)"
                    ) from e
            elif part["type"] != "text":
                raise ValueError(f"{context_label}[{i}]: unknown part type {part['type']!r}, expected 'text' or 'math'")

    def _check_marking_fidelity(self, question: "GeneratedQuestion", archetype) -> Optional[str]:
        """
        Soft, non-blocking check: does the generated marking_steps tick count
        roughly match the archetype's own documented typical_breakdown length?
        This does NOT gate acceptance (unlike sympy verification) -- a
        differently-structured-but-correct breakdown isn't a wrong answer,
        just possibly a lower-fidelity match to the real memo convention this
        archetype was extracted from. Surfaced to the user as an informational
        flag so they can spot-check it before using the paper.
        """
        typical_breakdown = archetype.marking_pattern.get("typical_breakdown", [])
        if not typical_breakdown:
            return None

        expected_ticks = len(typical_breakdown)
        actual_ticks = sum(1 for s in question.marking_steps if s.get("tick_count", 0) > 0)

        if abs(actual_ticks - expected_ticks) > 1:
            return (
                f"This archetype's real marking memos typically show {expected_ticks} ticked "
                f"steps, but the generated marking guide has {actual_ticks} -- worth a quick "
                f"look before using this question."
            )
        return None

    NUMERIC_TOLERANCE = 0.02  # allows for 2-d.p. rounding in either direction

    def _verify_answer(self, question: GeneratedQuestion) -> tuple[bool, str]:
        """
        Independently re-solve question.sympy_problem with SymPy and compare
        the result against question.claimed_solution.

        This is the critical safety net: we do NOT trust Claude's stated
        answer -- we re-derive it from scratch and check the two agree.

        Returns (verified: bool, detail: str) where detail explains any mismatch.
        """
        try:
            if question.problem_type == "equation":
                return self._verify_equation(question)
            elif question.problem_type == "inequality":
                return self._verify_inequality(question)
            elif question.problem_type == "system":
                return self._verify_system(question)
            else:
                return False, f"Unknown problem_type '{question.problem_type}'"
        except Exception as e:
            question.sympy_error = str(e)
            return False, f"{type(e).__name__}: {e}"

    def _verify_equation(self, question: GeneratedQuestion) -> tuple[bool, str]:
        x = symbols('x', real=True)
        expr = parse_expr(question.sympy_problem, local_dict={'x': x})

        independent_solutions = solve(Eq(expr, 0), x)
        independent_numeric = sorted(
            float(s.evalf()) for s in independent_solutions if s.is_real
        )

        claimed = ast.literal_eval(question.claimed_solution)
        if not isinstance(claimed, (list, tuple)):
            claimed = [claimed]
        claimed_numeric = sorted(float(v) for v in claimed)

        if len(claimed_numeric) > len(independent_numeric):
            return False, (
                f"SymPy found only {len(independent_numeric)} real solution(s) "
                f"{independent_numeric}, but {len(claimed_numeric)} were claimed {claimed_numeric}"
            )

        # Claimed values must be a subset of the independently-solved set (within
        # tolerance) -- this allows legitimate rejection of extraneous/invalid
        # roots (e.g. a negative length, or a root that fails the original
        # unsquared equation), while still catching invented or wrong values.
        unmatched = []
        remaining_independent = list(independent_numeric)
        for claim in claimed_numeric:
            match = next(
                (v for v in remaining_independent if abs(v - claim) <= self.NUMERIC_TOLERANCE),
                None
            )
            if match is None:
                unmatched.append(claim)
            else:
                remaining_independent.remove(match)

        if unmatched:
            return False, (
                f"Claimed value(s) {unmatched} not found among SymPy's independent solutions {independent_numeric}"
            )

        if not claimed_numeric:
            return False, "No claimed solution values provided"

        return True, "OK"

    def _verify_inequality(self, question: GeneratedQuestion) -> tuple[bool, str]:
        x = symbols('x', real=True)
        relation = parse_expr(question.sympy_problem, local_dict={'x': x})

        independent_set = solve_univariate_inequality(relation, x, relational=False)
        claimed_set = sympify(
            question.claimed_solution,
            locals={'x': x, 'oo': oo, 'Interval': Interval, 'Union': Union, 'S': S}
        )

        if independent_set == claimed_set:
            return True, "OK"

        # Fall back to a numeric sanity check across a coarse sample grid,
        # in case the two are equal sets expressed in different (but valid) forms.
        sample_points = [p / 10 for p in range(-500, 501)]
        mismatches = 0
        for p in sample_points:
            in_indep = independent_set.contains(p)
            in_claim = claimed_set.contains(p)
            if bool(in_indep) != bool(in_claim):
                mismatches += 1

        if mismatches == 0:
            return True, "OK (verified via sample-point agreement)"

        return False, f"SymPy solved {independent_set}, claimed {claimed_set} -- sets disagree at {mismatches} sample points"

    def _verify_system(self, question: GeneratedQuestion) -> tuple[bool, str]:
        x, y = symbols('x y', real=True)
        parts = [p.strip() for p in question.sympy_problem.split(';')]
        if len(parts) != 2:
            return False, f"Expected 2 equations separated by ';', got: {question.sympy_problem}"

        eq1 = Eq(parse_expr(parts[0], local_dict={'x': x, 'y': y}), 0)
        eq2 = Eq(parse_expr(parts[1], local_dict={'x': x, 'y': y}), 0)

        raw_solutions = solve([eq1, eq2], [x, y])
        if isinstance(raw_solutions, dict):
            raw_solutions = [raw_solutions]

        independent_pairs = []
        for sol in raw_solutions:
            sx, sy = (sol.get(x), sol.get(y)) if isinstance(sol, dict) else (sol[0], sol[1])
            if sx is None or sy is None:
                continue
            if not (sx.is_real and sy.is_real):
                continue
            independent_pairs.append((round(float(sx.evalf()), 2), round(float(sy.evalf()), 2)))
        independent_pairs.sort()

        claimed = ast.literal_eval(question.claimed_solution)
        claimed_pairs = sorted((round(float(px), 2), round(float(py), 2)) for px, py in claimed)

        if len(independent_pairs) != len(claimed_pairs):
            return False, (
                f"SymPy found {len(independent_pairs)} solution pair(s) {independent_pairs}, "
                f"but {len(claimed_pairs)} were claimed {claimed_pairs}"
            )

        for indep, claim in zip(independent_pairs, claimed_pairs):
            if abs(indep[0] - claim[0]) > self.NUMERIC_TOLERANCE or abs(indep[1] - claim[1]) > self.NUMERIC_TOLERANCE:
                return False, f"SymPy solved {independent_pairs}, claimed {claimed_pairs} -- mismatch beyond tolerance"

        return True, "OK"


MIN_MARKS_PER_QUESTION = 2
COGNITIVE_LEVELS = ["knowledge", "routine", "complex", "problem_solving"]


def _allocate_marks_by_cognitive_level(target_marks: int, target_distribution: dict) -> dict:
    """
    Split target_marks across the four cognitive levels according to
    target_distribution percentages, using largest-remainder rounding so
    the integer totals sum EXACTLY to target_marks.

    This is the top of the grid-first pipeline: the whole-paper level
    totals are fixed here, before any archetype is selected for a
    specific slot or any leaf's level is decided. Archetype selection
    (select_archetypes) still uses target_distribution for its own
    sampling bias, but the marks-per-level plan computed here is the one
    actually carried through to leaf generation via _build_leaf_plan.
    """
    raw = {level: target_marks * target_distribution.get(level, 0) / 100 for level in COGNITIVE_LEVELS}
    floors = {level: int(raw[level]) for level in COGNITIVE_LEVELS}
    remainder = target_marks - sum(floors.values())

    by_largest_remainder = sorted(COGNITIVE_LEVELS, key=lambda l: raw[l] - floors[l], reverse=True)
    for i in range(remainder):
        floors[by_largest_remainder[i % len(by_largest_remainder)]] += 1

    return floors


def _build_leaf_plan(archetypes: list, marks_plan: list, level_totals: dict) -> list:
    """
    Assign each archetype slot a cognitive_targets dict (marks per
    cognitive level within that slot's marks) that draws down the
    whole-paper level_totals pool, so that summed across every slot, the
    planned distribution exactly matches level_totals.

    This is the leaf plan: archetype + marks + per-level target are all
    fixed here, BEFORE any Claude call is made for that slot. The
    rotating start level per slot avoids always draining the same level
    first, so early slots don't systematically starve later ones of a
    level they need.

    Returns a list of {"archetype", "marks", "cognitive_targets"} dicts,
    same length and order as `archetypes`.
    """
    pool = dict(level_totals)
    plan = []

    for i, (archetype, marks) in enumerate(zip(archetypes, marks_plan)):
        slot_targets = {level: 0 for level in COGNITIVE_LEVELS}
        remaining = marks
        start = i % len(COGNITIVE_LEVELS)
        order = COGNITIVE_LEVELS[start:] + COGNITIVE_LEVELS[:start]

        for level in order:
            if remaining == 0:
                break
            take = min(pool.get(level, 0), remaining)
            if take > 0:
                slot_targets[level] += take
                pool[level] -= take
                remaining -= take

        if remaining > 0:
            # Pool exhausted early (can happen at the rounding edge) --
            # assign the leftover to whichever level still has room,
            # falling back to "routine" if every pool is drained.
            fallback = next((l for l in COGNITIVE_LEVELS if pool.get(l, 0) > 0), "routine")
            slot_targets[fallback] += remaining
            pool[fallback] = max(0, pool.get(fallback, 0) - remaining)
            remaining = 0

        plan.append({
            "archetype": archetype,
            "marks": marks,
            "cognitive_targets": slot_targets
        })

    return plan


def _distribute_marks(archetypes: list, target_marks: int) -> list:
    """
    Compute an integer mark value per archetype that sums EXACTLY to
    target_marks, proportional to each archetype's own historical
    typical_total_marks (so a naturally-4-mark archetype still ends up
    bigger than a naturally-2-mark one, just scaled to hit the target,
    rather than every question being squeezed/stretched to the same size).

    Returns a list of ints, same length and order as `archetypes`.
    """
    weights = []
    for a in archetypes:
        w = a.marking_pattern.get("typical_total_marks")
        weights.append(w if w else 3)

    total_weight = sum(weights)
    raw = [target_marks * w / total_weight for w in weights]

    marks = [max(MIN_MARKS_PER_QUESTION, round(r)) for r in raw]

    # Rounding (and the MIN_MARKS_PER_QUESTION floor) can leave the sum
    # off-target by a few marks -- close the gap by adjusting the
    # largest-weight question(s), which absorbs the adjustment with the
    # least proportional distortion.
    diff = target_marks - sum(marks)
    order = sorted(range(len(marks)), key=lambda i: weights[i], reverse=True)
    idx_cycle = 0
    while diff != 0 and order:
        i = order[idx_cycle % len(order)]
        if diff > 0:
            marks[i] += 1
            diff -= 1
        elif marks[i] > MIN_MARKS_PER_QUESTION:
            marks[i] -= 1
            diff += 1
        idx_cycle += 1
        if idx_cycle > 10000:  # safety valve, should never trigger
            break

    return marks


def generate_paper(topic: str, num_questions: int = 5,
                  target_distribution: dict = None,
                  prefer_core: bool = True,
                  target_marks: int = None) -> dict:
    """
    Generate a complete set of questions for a paper.

    Args:
        target_marks: If given, the paper's marks are distributed across the
                     selected archetypes (proportional to each archetype's own
                     typical mark value) so the total EXACTLY equals this
                     number. If omitted, each question falls back to its
                     archetype's own historical typical mark value and the
                     paper total is whatever that happens to sum to.

    Returns:
        {
            "topic": topic,
            "questions": [hierarchical question_structure dict, ...],
            "total_marks": int,
            "cognitive_analysis": {...},   # computed from actual generated leaves
            "planned_level_totals": {...}  # what (a) targeted, for comparison
        }
    """
    if target_distribution is None:
        target_distribution = {
            'knowledge': 20,
            'routine': 35,
            'complex': 30,
            'problem_solving': 15
        }

    gen = QuestionGenerator(topic)
    gen.select_archetypes(num_questions, target_distribution, prefer_core)

    if target_marks is not None:
        min_possible = len(gen.selected_archetypes) * MIN_MARKS_PER_QUESTION
        if target_marks < min_possible:
            raise ValueError(
                f"Cannot fit {len(gen.selected_archetypes)} questions into {target_marks} marks "
                f"(each question needs at least {MIN_MARKS_PER_QUESTION} marks, so {min_possible} is the "
                f"minimum for this many questions). Reduce the number of questions or increase total marks."
            )
        marks_plan = _distribute_marks(gen.selected_archetypes, target_marks)
    else:
        # No explicit total requested -- fall back to each archetype's own
        # historical typical mark value, and let the paper total be
        # whatever that happens to sum to.
        marks_plan = []
        for a in gen.selected_archetypes:
            w = a.marking_pattern.get("typical_total_marks")
            marks_plan.append(w if w else 3)
        target_marks = sum(marks_plan)

    # (a) Whole-paper mark allocation by cognitive level -- fixed before any
    # archetype/leaf decision. This is what the printed grid is measured
    # against, and what every slot's cognitive_targets is carved out of.
    level_totals = _allocate_marks_by_cognitive_level(target_marks, target_distribution)

    # (b) Leaf plan: archetype + marks + per-level cognitive_targets fixed
    # per slot, BEFORE any Claude call for that slot.
    leaf_plan = _build_leaf_plan(gen.selected_archetypes, marks_plan, level_totals)

    questions = []
    total_marks = 0
    generation_errors = []

    for i, slot in enumerate(leaf_plan, 1):
        archetype = slot["archetype"]
        print(f"Generating question {i}/{num_questions} ({archetype.name}, "
              f"{slot['marks']} marks, targets {slot['cognitive_targets']})...")
        try:
            q = gen.generate_question(
                archetype.archetype_id,
                marks=slot["marks"],
                cognitive_targets=slot["cognitive_targets"]
            )
            if q:
                questions.append(q)
                total_marks += q.get("total_marks", 0)
                print(f"  ✓ Question {i} generated")
            else:
                error_msg = f"Question {i} ({archetype.archetype_id}): generation failed after retries"
                print(f"  ✗ {error_msg}")
                generation_errors.append(error_msg)
        except NonRetryableAPIError as e:
            # Stop the whole paper immediately -- this is a fatal API-level
            # problem (bad request/credentials/insufficient credit/exhausted
            # transient retries), not a per-question generation-quality
            # issue. Continuing to the next question would just repeat the
            # same failure and produce a misleadingly partial paper.
            print(f"  ✗ FATAL: {type(e.original).__name__}: {e.original} -- aborting paper generation")
            raise
        except Exception as e:
            error_msg = f"Question {i} ({archetype.archetype_id}): {type(e).__name__}: {e}"
            print(f"  ✗ {error_msg}")
            generation_errors.append(error_msg)

    # (d) Grid computed from the leaves as actually generated -- not from
    # the plan -- so any gap between planned and achieved is visible.
    cognitive_analysis = _analyze_cognitive_distribution(questions, target_distribution)
    usage_summary = print_usage_summary(gen.usage_log, label=topic)

    return {
        "topic": topic,
        "num_questions": len(questions),
        "total_marks": total_marks,
        "questions": questions,
        "cognitive_analysis": cognitive_analysis,
        "planned_level_totals": level_totals,
        "generation_errors": generation_errors,
        "usage_summary": usage_summary,
        "usage_log": gen.usage_log
    }


def _analyze_cognitive_distribution(questions: list, targets: dict) -> dict:
    """
    Analyze the cognitive distribution of generated questions, computed
    from the ACTUAL leaves Claude produced (a hierarchical question's
    flat rows and stem children), not from the plan handed to it. This is
    what the document's cognitive grid is built from, and what the app
    shows next to the target split so any shortfall from the plan --
    e.g. an archetype that couldn't be redesigned to reach its target
    level -- is visible rather than hidden.
    """
    distribution = {level: 0 for level in COGNITIVE_LEVELS}

    for q in questions:
        for row in q.get("question_structure", []):
            leaves = row.get("children", []) if row.get("is_stem") else [row]
            for leaf in leaves:
                level = leaf.get("cognitive_level")
                marks = leaf.get("marks")
                if level in distribution and isinstance(marks, int):
                    distribution[level] += marks

    total_marks = sum(distribution.values())

    percentages = {}
    for level, marks in distribution.items():
        pct = (marks / total_marks * 100) if total_marks > 0 else 0
        percentages[level] = round(pct, 1)

    return {
        "marks_by_level": distribution,
        "percentages_by_level": percentages,
        "target_distribution": targets,
        "variance": {
            level: round(percentages[level] - targets.get(level, 0), 1)
            for level in distribution.keys()
        }
    }
