# validator.py - Hierarchical question structure validator

def validate_hierarchical_structure(data: dict, target_marks: int) -> tuple[bool, list[str]]:
    """
    Validate a hierarchical question structure before sending to docgen.

    Args:
        data: The JSON returned by Claude (question_structure + total_marks)
        target_marks: The marks allocated to this QUESTION (from mark distribution)

    Returns:
        (is_valid, errors) where errors is a list of validation failure strings
    """
    errors = []

    # Check top-level structure
    if not isinstance(data, dict):
        return False, ["Response must be a dict"]

    if "question_structure" not in data:
        errors.append("Missing 'question_structure' key")
        return False, errors

    structure = data.get("question_structure", [])
    if not isinstance(structure, list):
        errors.append("'question_structure' must be a list")
        return False, errors

    if not structure:
        errors.append("'question_structure' cannot be empty")
        return False, errors

    # Validate each row
    total_leaf_marks = 0
    leaf_count = 0
    seen_stems = {}  # stem_index -> children_count

    for i, row in enumerate(structure):
        if not isinstance(row, dict):
            errors.append(f"Row {i}: must be a dict, got {type(row).__name__}")
            continue

        is_stem = row.get("is_stem", False)
        marks = row.get("marks")
        cognitive_level = row.get("cognitive_level")

        # STEM VALIDATION
        if is_stem:
            if marks is not None:
                errors.append(f"Row {i}: stem row must have marks=null, got {marks}")
            if cognitive_level is not None:
                errors.append(f"Row {i}: stem row must have cognitive_level=null, got {cognitive_level}")

            children = row.get("children", [])
            if not isinstance(children, list) or len(children) < 2:
                errors.append(f"Row {i}: stem row must have ≥2 children, got {len(children)}")

            seen_stems[i] = len(children)

            # Validate each child
            for j, child in enumerate(children):
                child_marks = child.get("marks")
                child_level = child.get("cognitive_level")

                if not isinstance(child_marks, int) or child_marks <= 0:
                    errors.append(f"Row {i}, child {j}: marks must be >0, got {child_marks}")
                else:
                    total_leaf_marks += child_marks
                    leaf_count += 1

                if child_level not in ["knowledge", "routine", "complex", "problem_solving"]:
                    errors.append(f"Row {i}, child {j}: cognitive_level must be K/R/C/P, got '{child_level}'")

                # Validate child structure (question, answer, marking_steps)
                if "parts" not in child:
                    errors.append(f"Row {i}, child {j}: missing 'parts' (question)")
                if "answer" not in child:
                    errors.append(f"Row {i}, child {j}: missing 'answer'")
                if "marking_steps" not in child:
                    errors.append(f"Row {i}, child {j}: missing 'marking_steps'")

                # Validate tick count vs marks
                marking_steps = child.get("marking_steps", [])
                tick_sum = sum(step.get("tick_count", 0) for step in marking_steps)
                if tick_sum != child_marks:
                    errors.append(
                        f"Row {i}, child {j}: marking_steps tick_count sums to {tick_sum}, "
                        f"but marks={child_marks}"
                    )

        # FLAT ROW VALIDATION
        else:
            if not isinstance(marks, int) or marks <= 0:
                errors.append(f"Row {i}: flat row marks must be >0, got {marks}")
            else:
                total_leaf_marks += marks
                leaf_count += 1

            if cognitive_level not in ["knowledge", "routine", "complex", "problem_solving"]:
                errors.append(f"Row {i}: cognitive_level must be K/R/C/P, got '{cognitive_level}'")

            # Validate structure
            if "parts" not in row:
                errors.append(f"Row {i}: missing 'parts' (question)")
            if "answer" not in row:
                errors.append(f"Row {i}: missing 'answer'")
            if "marking_steps" not in row:
                errors.append(f"Row {i}: missing 'marking_steps'")

            # Validate tick count
            marking_steps = row.get("marking_steps", [])
            tick_sum = sum(step.get("tick_count", 0) for step in marking_steps)
            if tick_sum != marks:
                errors.append(
                    f"Row {i}: marking_steps tick_count sums to {tick_sum}, but marks={marks}"
                )

    # Validate total marks
    if total_leaf_marks != target_marks:
        errors.append(
            f"Total leaf marks {total_leaf_marks} does not match target {target_marks}"
        )

    return len(errors) == 0, errors


# ============================================================
# TEST FIXTURE: Canned hierarchical question
# ============================================================

TEST_HIERARCHICAL_QUESTION = {
    "question_structure": [
        {
            "type": "flat_row",
            "is_stem": False,
            "parts": [
                {"type": "text", "value": "Solve for "},
                {"type": "math", "value": "x"}
            ],
            "marks": 2,
            "cognitive_level": "routine",
            "answer": [{"type": "math", "value": "x = 2,5"}],
            "marking_steps": [
                {
                    "parts": [
                        {"type": "math", "value": "2x - 5 = 0"}
                    ],
                    "tick_label": "standard form",
                    "tick_count": 1
                },
                {
                    "parts": [
                        {"type": "math", "value": "x = 2,5"}
                    ],
                    "tick_label": "answer",
                    "tick_count": 1
                }
            ],
            "problem_type": "equation",
            "sympy_problem": "2*x - 5",
            "claimed_solution": "[2.5]"
        },
        {
            "type": "stem_row",
            "is_stem": True,
            "parts": [
                {"type": "text", "value": "Sipho borrows R500 000 at 6% p.a. compound interest."}
            ],
            "marks": None,
            "cognitive_level": None,
            "children": [
                {
                    "parts": [
                        {"type": "text", "value": "Calculate the amount owed after 5 years."}
                    ],
                    "marks": 2,
                    "cognitive_level": "routine",
                    "answer": [{"type": "math", "value": "R669 113,35"}],
                    "marking_steps": [
                        {
                            "parts": [
                                {"type": "math", "value": "A = P(1 + i)^{n}"}
                            ],
                            "tick_label": "formula",
                            "tick_count": 1
                        },
                        {
                            "parts": [
                                {"type": "math", "value": "A = 500000(1,06)^{5} = 669 113,35"}
                            ],
                            "tick_label": "substitution and calculation",
                            "tick_count": 1
                        }
                    ],
                    "problem_type": "unverifiable",
                    "sympy_problem": "",
                    "claimed_solution": ""
                },
                {
                    "parts": [
                        {"type": "text", "value": "How many years to pay back at current rate?"}
                    ],
                    "marks": 3,
                    "cognitive_level": "complex",
                    "answer": [{"type": "math", "value": "n \\approx 12,5 \\text{ years}"}],
                    "marking_steps": [
                        {
                            "parts": [
                                {"type": "math", "value": "1 000 000 = 500 000(1,06)^{n}"}
                            ],
                            "tick_label": "set up equation",
                            "tick_count": 1
                        },
                        {
                            "parts": [
                                {"type": "math", "value": "2 = (1,06)^{n}"}
                            ],
                            "tick_label": "simplify",
                            "tick_count": 1
                        },
                        {
                            "parts": [
                                {"type": "math", "value": "n = \\frac{\\ln 2}{\\ln 1,06} \\approx 12,5"}
                            ],
                            "tick_label": "logarithmic solution",
                            "tick_count": 1
                        }
                    ],
                    "problem_type": "unverifiable",
                    "sympy_problem": "",
                    "claimed_solution": ""
                }
            ]
        },
        {
            "type": "flat_row",
            "is_stem": False,
            "parts": [
                {"type": "text", "value": "Factorize: "},
                {"type": "math", "value": "x^{2} - 3x - 10"}
            ],
            "marks": 2,
            "cognitive_level": "routine",
            "answer": [
                {"type": "math", "value": "(x - 5)(x + 2)"}
            ],
            "marking_steps": [
                {
                    "parts": [
                        {"type": "math", "value": "(x - 5)(x + 2)"}
                    ],
                    "tick_label": "factors",
                    "tick_count": 2
                }
            ],
            "problem_type": "equation",
            "sympy_problem": "x**2 - 3*x - 10",
            "claimed_solution": "[]"
        }
    ],
    "total_marks": 9  # 2 (flat) + 2+3 (stem children) + 2 (flat) = 9
}


# Test the fixture
if __name__ == "__main__":
    is_valid, errors = validate_hierarchical_structure(TEST_HIERARCHICAL_QUESTION, 9)
    print(f"Validation result: {is_valid}")
    if errors:
        print("Errors:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("✓ Fixture is valid!")
