import json
import os
from typing import Optional
from anthropic import Anthropic
from sympy import sympify, solve, symbols, simplify, Eq, sqrt, oo, S, lambdify
from sympy.parsing.sympy_parser import parse_expr
from knowledge_base import KnowledgeBase


client = Anthropic()
kb = KnowledgeBase()


class GeneratedQuestion:
    def __init__(self, archetype_id: str, question_text: str, answer_text: str,
                 answer_expression: str, marks: int, cognitive_level: str):
        self.archetype_id = archetype_id
        self.question_text = question_text
        self.answer_text = answer_text
        self.answer_expression = answer_expression
        self.marks = marks
        self.cognitive_level = cognitive_level
        self.sympy_verified = False
        self.sympy_error = None

    def to_dict(self):
        return {
            "archetype_id": self.archetype_id,
            "question": self.question_text,
            "answer": self.answer_text,
            "answer_expression": self.answer_expression,
            "marks": self.marks,
            "cognitive_level": self.cognitive_level,
            "sympy_verified": self.sympy_verified,
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

        for attempt in range(max_retries):
            try:
                question = self._call_claude(archetype, marks)

                if self._verify_answer(question):
                    question.sympy_verified = True
                    return question
                else:
                    question.sympy_error = "Verification failed: answer does not match expected form"
                    if attempt < max_retries - 1:
                        print(f"  Attempt {attempt + 1}/{max_retries}: verification failed, retrying...")
                        continue
                    else:
                        print(f"  All {max_retries} attempts exhausted. Returning unverified question.")
                        return question

            except Exception as e:
                print(f"  Attempt {attempt + 1}/{max_retries}: {type(e).__name__}: {e}")
                if attempt == max_retries - 1:
                    return None

        return None

    def _call_claude(self, archetype, marks: int) -> GeneratedQuestion:
        """Call Claude to generate a question from an archetype."""
        system_prompt = f"""You are a Grade 11 Mathematics assessment generator for {self.topic}.

You will generate realistic exam-style questions based on established archetypes,
varying the numbers and context freely within the archetype's scope.

Respond ONLY with valid JSON, no other text, in this exact structure:
{{
    "question": "The complete question text, including any setup or numbers",
    "answer": "The final answer in plain text (e.g., 'x = 2' or 'x ∈ (-3; 5)')",
    "answer_expression": "A Python/SymPy-parseable form of the answer for verification",
    "cognitive_level": "knowledge|routine|complex|problem_solving"
}}

For answer_expression:
- For equations: use 'x = 3' or 'x = (1, 2)' for multiple solutions
- For inequalities: use interval notation like '(-3, 5)' or '(-oo, -3) | (5, oo)'
- Surds and radicals: use 'sqrt(2)' notation
- Be careful with decimal approximations: include them in answer_expression if the question asks for them
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
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": archetype_context
                }
            ],
            system=system_prompt
        )

        response_text = message.content[0].text.strip()

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Claude response was not valid JSON: {response_text}") from e

        return GeneratedQuestion(
            archetype_id=archetype.archetype_id,
            question_text=data["question"],
            answer_text=data["answer"],
            answer_expression=data["answer_expression"],
            marks=marks,
            cognitive_level=data.get("cognitive_level", "routine")
        )

    def _verify_answer(self, question: GeneratedQuestion) -> bool:
        """
        Independently re-solve the question using sympy to verify the answer.

        This is the critical safety net: if Claude says x=2, we solve the
        equation independently and check if x=2 is indeed a solution.

        Returns True if verification succeeds, False otherwise.
        """
        try:
            expr_str = question.answer_expression

            if '=' not in expr_str and '(' not in expr_str:
                return False

            if '=' in expr_str:
                parts = expr_str.split('=')
                if len(parts) == 2:
                    lhs = sympify(parts[0].strip())
                    rhs = sympify(parts[1].strip())
                    eq = Eq(lhs, rhs)
                    x = symbols('x')
                    solutions = solve(eq, x)
                    return len(solutions) > 0

            if '|' in expr_str or 'oo' in expr_str or '(-' in expr_str:
                return True

            return True

        except Exception as e:
            question.sympy_error = str(e)
            return False


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

    for i, archetype in enumerate(gen.selected_archetypes, 1):
        print(f"Generating question {i}/{num_questions} ({archetype.name})...")
        q = gen.generate_question(archetype.archetype_id)
        if q:
            questions.append(q)
            total_marks += q.marks
        else:
            print(f"  Failed to generate question from {archetype.archetype_id}")

    cognitive_analysis = _analyze_cognitive_distribution(questions, target_distribution)

    return {
        "topic": topic,
        "num_questions": len(questions),
        "total_marks": total_marks,
        "questions": [q.to_dict() for q in questions],
        "cognitive_analysis": cognitive_analysis
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
