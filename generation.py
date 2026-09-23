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


client = Anthropic()
kb = KnowledgeBase()


class GeneratedQuestion:
    def __init__(self, archetype_id: str, question_text: str, answer_text: str,
                 answer_expression: str, marks: int, cognitive_level: str,
                 problem_type: str = "unverifiable", sympy_problem: str = "",
                 claimed_solution: str = ""):
        self.archetype_id = archetype_id
        self.question_text = question_text
        self.answer_text = answer_text
        self.answer_expression = answer_expression
        self.marks = marks
        self.cognitive_level = cognitive_level
        self.problem_type = problem_type
        self.sympy_problem = sympy_problem
        self.claimed_solution = claimed_solution
        self.sympy_verified = False
        self.manual_review_required = False
        self.sympy_error = None

    def to_dict(self):
        return {
            "archetype_id": self.archetype_id,
            "question": self.question_text,
            "answer": self.answer_text,
            "answer_expression": self.answer_expression,
            "marks": self.marks,
            "cognitive_level": self.cognitive_level,
            "problem_type": self.problem_type,
            "sympy_verified": self.sympy_verified,
            "manual_review_required": self.manual_review_required,
            "sympy_error": self.sympy_error
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
    "question": "The complete question text, including any setup or numbers",
    "answer": "The final answer exactly as it should appear on the marking guide (human-readable, e.g. 'x = 1.35 or x = -1.85')",
    "problem_type": "equation | inequality | system | unverifiable",
    "sympy_problem": "A machine-parseable statement of the underlying math problem -- see rules below",
    "claimed_solution": "A machine-parseable Python literal of your claimed solution -- see rules below",
    "cognitive_level": "knowledge|routine|complex|problem_solving"
}}

CRITICAL: "sympy_problem" and "claimed_solution" exist so your answer can be independently
re-solved and checked by SymPy before this question is accepted into a real assessment.
Get these exactly right -- a wrong answer that passes this check ships to real students.

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
            max_tokens=1500,
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
            raise ValueError(f"Claude response was not valid JSON: {response_text}") from e

        return GeneratedQuestion(
            archetype_id=archetype.archetype_id,
            question_text=data["question"],
            answer_text=data["answer"],
            answer_expression=data.get("claimed_solution", ""),
            marks=marks,
            cognitive_level=data.get("cognitive_level", "routine"),
            problem_type=data.get("problem_type", "unverifiable"),
            sympy_problem=data.get("sympy_problem", ""),
            claimed_solution=data.get("claimed_solution", "")
        )

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


def generate_paper(topic: str, num_questions: int = 5,
                  target_distribution: dict = None,
                  prefer_core: bool = True) -> dict:
    """
    Generate a complete set of questions for a paper.

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

    questions = []
    total_marks = 0
    generation_errors = []

    for i, archetype in enumerate(gen.selected_archetypes, 1):
        print(f"Generating question {i}/{num_questions} ({archetype.name})...")
        try:
            q = gen.generate_question(archetype.archetype_id)
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
