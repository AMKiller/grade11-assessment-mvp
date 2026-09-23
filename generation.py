import ast
import json
import os
from typing import Optional
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


class QuestionGenerator:
    def __init__(self, topic: str, api_key: str = None):
        self.topic = topic
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")

        self.kb = kb
        self.selected_archetypes = []

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
                         max_retries: int = 3) -> Optional[GeneratedQuestion]:
        """
        Generate a single question from an archetype, with sympy verification.

        Args:
            archetype_id: Which archetype to generate from
            marks: Marks for this question (if None, inferred from archetype pattern)
            max_retries: How many times to retry if verification fails

        Returns:
            GeneratedQuestion if successful, None if all retries exhausted
        """
        archetype = self.kb.get_archetype(self.topic, archetype_id)

        if marks is None:
            marks = archetype.marking_pattern.get("typical_total_marks", 3)
            if marks is None:
                marks = 3

        last_exception = None

        for attempt in range(max_retries):
            try:
                question = self._call_claude(archetype, marks)

                if question.problem_type == "unverifiable":
                    question.manual_review_required = True
                    question.sympy_error = (
                        "Not mechanically verifiable by SymPy (proof/identity/word problem archetype) "
                        "-- flagged for manual review, not independently confirmed."
                    )
                    return question

                verified, detail = self._verify_answer(question)
                if verified:
                    question.sympy_verified = True
                    return question
                else:
                    question.sympy_error = f"Independent SymPy solve disagreed with claimed answer: {detail}"
                    if attempt < max_retries - 1:
                        print(f"  Attempt {attempt + 1}/{max_retries}: verification failed ({detail}), retrying...")
                        continue
                    else:
                        print(f"  All {max_retries} attempts exhausted. Flagging for manual review.")
                        question.manual_review_required = True
                        return question

            except Exception as e:
                last_exception = e
                print(f"  Attempt {attempt + 1}/{max_retries}: {type(e).__name__}: {e}")
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"All {max_retries} attempts failed. Last error: {type(last_exception).__name__}: {last_exception}"
                    ) from last_exception

        return None

    def _call_claude(self, archetype, marks: int) -> GeneratedQuestion:
        """Call Claude to generate a question from an archetype."""
        system_prompt = f"""You are a Grade 11 Mathematics assessment generator for {self.topic}.

You will generate realistic exam-style questions based on established archetypes,
varying the numbers and context freely within the archetype's scope.

Respond ONLY with valid JSON, no other text, in this exact structure:
{{
    "question": "A list of {{type, value}} parts -- see MATH NOTATION rules below -- do NOT state the mark value anywhere inside this text (no '(4 marks)', no '[4]'); marks are shown separately in the document and must never be duplicated in the question wording",
    "answer": "A list of {{type, value}} parts, exactly as the final answer should appear on the marking guide -- see MATH NOTATION rules below",
    "marking_steps": "A list of ordered working steps for the marking guide -- see rules below",
    "problem_type": "equation | inequality | system | unverifiable",
    "sympy_problem": "A machine-parseable statement of the underlying math problem -- see rules below",
    "claimed_solution": "A machine-parseable Python literal of your claimed solution -- see rules below",
    "cognitive_level": "knowledge|routine|complex|problem_solving"
}}

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

Generate ONE new question in this archetype's style.
Vary the numbers and specific context - do NOT use the exact past-paper examples.
"""

        message = client.messages.create(
            model="claude-opus-5-5",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": archetype_context
                }
            ],
            system=system_prompt
        )

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

        self._validate_math_parts(data.get("question", []), "question")
        self._validate_math_parts(data.get("answer", []), "answer")
        for i, step in enumerate(data.get("marking_steps", [])):
            self._validate_math_parts(step.get("parts", []), f"marking_steps[{i}]")

        question = GeneratedQuestion(
            archetype_id=archetype.archetype_id,
            question_text=data["question"],
            answer_text=data["answer"],
            answer_expression=data.get("claimed_solution", ""),
            marks=marks,
            cognitive_level=data.get("cognitive_level", "routine"),
            problem_type=data.get("problem_type", "unverifiable"),
            sympy_problem=data.get("sympy_problem", ""),
            claimed_solution=data.get("claimed_solution", ""),
            marking_steps=data.get("marking_steps", [])
        )
        question.marking_fidelity_warning = self._check_marking_fidelity(question, archetype)
        return question

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
            "questions": [GeneratedQuestion.to_dict(), ...],
            "total_marks": int,
            "cognitive_analysis": {...}
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
        marks_plan = [None] * len(gen.selected_archetypes)

    questions = []
    total_marks = 0
    generation_errors = []

    for i, (archetype, planned_marks) in enumerate(zip(gen.selected_archetypes, marks_plan), 1):
        print(f"Generating question {i}/{num_questions} ({archetype.name}, target {planned_marks or 'archetype default'} marks)...")
        try:
            q = gen.generate_question(archetype.archetype_id, marks=planned_marks)
            if q:
                questions.append(q)
                total_marks += q.marks
                print(f"  ✓ Question {i} generated and verified")
            else:
                error_msg = f"Question {i} ({archetype.archetype_id}): generation/verification failed after retries"
                print(f"  ✗ {error_msg}")
                generation_errors.append(error_msg)
        except Exception as e:
            error_msg = f"Question {i} ({archetype.archetype_id}): {type(e).__name__}: {e}"
            print(f"  ✗ {error_msg}")
            generation_errors.append(error_msg)

    cognitive_analysis = _analyze_cognitive_distribution(questions, target_distribution)

    return {
        "topic": topic,
        "num_questions": len(questions),
        "total_marks": total_marks,
        "questions": [q.to_dict() for q in questions],
        "question_objects": questions,
        "cognitive_analysis": cognitive_analysis,
        "generation_errors": generation_errors
    }


def _analyze_cognitive_distribution(questions: list, targets: dict) -> dict:
    """Analyze the cognitive distribution of generated questions."""
    distribution = {
        "knowledge": 0,
        "routine": 0,
        "complex": 0,
        "problem_solving": 0
    }

    total_marks = sum(q.marks for q in questions)

    for q in questions:
        level = q.cognitive_level
        if level in distribution:
            distribution[level] += q.marks

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
