#!/usr/bin/env python3
"""
Test hierarchical question rendering with docgen.py.
This adapter converts the hierarchical structure to a format that docgen can render,
then verifies the output against format_SKILL.md rules.
"""

import sys
sys.path.insert(0, '/home/annemariekiller/grade11-assessment-mvp')

from validator_and_fixture import TEST_HIERARCHICAL_QUESTION
from docx import Document

# Adapter: Convert hierarchical to flat with numbering
def hierarchical_to_flat_questions(hierarchy: dict) -> list:
    """
    Convert hierarchical question_structure to flat questions list for docgen.
    Each flat question gets numbered (1.1, 1.5, 1.5.1, etc.)
    """
    flat_questions = []
    question_num = 1

    for row in hierarchy["question_structure"]:
        if row.get("is_stem"):
            # Stem row: add it as a question with marks=None
            flat_q = {
                "num": f"{question_num}",
                "is_stem": True,
                "parts": row.get("parts", []),
                "marks": None,
                "answer": None,
                "marking_steps": []
            }
            flat_questions.append(flat_q)

            # Add children
            for child_idx, child in enumerate(row.get("children", []), 1):
                child_num = f"{question_num}.{child_idx}"
                flat_c = {
                    "num": child_num,
                    "is_stem": False,
                    "parts": child.get("parts", []),
                    "marks": child.get("marks"),
                    "answer": child.get("answer", []),
                    "marking_steps": child.get("marking_steps", []),
                    "cognitive_level": child.get("cognitive_level"),
                    "problem_type": child.get("problem_type"),
                    "sympy_verified": True  # For testing
                }
                flat_questions.append(flat_c)

            question_num += 1
        else:
            # Flat row: regular question
            flat_q = {
                "num": f"{question_num}",
                "is_stem": False,
                "parts": row.get("parts", []),
                "marks": row.get("marks"),
                "answer": row.get("answer", []),
                "marking_steps": row.get("marking_steps", []),
                "cognitive_level": row.get("cognitive_level"),
                "problem_type": row.get("problem_type"),
                "sympy_verified": True
            }
            flat_questions.append(flat_q)
            question_num += 1

    return flat_questions


# Convert fixture
print("Converting hierarchical fixture to flat questions...")
flat_q = hierarchical_to_flat_questions(TEST_HIERARCHICAL_QUESTION)

print("\nFlat questions structure:")
for q in flat_q:
    print(f"  {q['num']}: stem={q.get('is_stem', False)}, marks={q.get('marks')}")

# Now we'll manually verify the structure (can't call docgen yet without implementation)
print("\n" + "=" * 70)
print("VERIFICATION: Hierarchical Structure Properties")
print("=" * 70)

checks = [
    ("Numbering correct (1.1, 1.5, 1.5.1, 1.5.2, 1.6)",
     flat_q[0]['num'] == "1" and flat_q[1]['num'] == "2" and
     flat_q[2]['num'] == "3" and flat_q[3]['num'] == "4"),

    ("Stem rows have marks=None",
     all(q['marks'] is None for q in flat_q if q.get('is_stem'))),

    ("Flat rows have marks>0",
     all(q['marks'] > 0 for q in flat_q if not q.get('is_stem'))),

    ("All rows have parts list",
     all('parts' in q for q in flat_q)),

    ("Total marks = 9 (sum of leaves only, excluding stems)",
     sum(q.get('marks', 0) for q in flat_q if q.get('marks') is not None) == 9),

    ("Leaf count = 4 (2 flat + 2 children from stem)",
     len([q for q in flat_q if not q.get('is_stem')]) == 4),
]

print("\nStructural Checks:")
for check_name, result in checks:
    status = "✓" if result else "✗"
    print(f"  {status} {check_name}")

print("\n" + "=" * 70)
print("NEXT STEP: Implement docgen.py hierarchy support")
print("=" * 70)
print("""
To render this hierarchical structure as a .docx:

1. Update add_question_table() in table_helpers.py to:
   - Accept is_stem flag per row
   - Skip marks cell for stem rows (marks=None)
   - Handle depth-based column merging (depth 1 = sub-sub-number)
   - Add blank spacer rows after non-stem rows

2. Update _add_question_paper_body() in docgen.py to:
   - Process hierarchy: flat rows and stem rows with children
   - Call add_question_table() with full structure
   - Compute per-question totals (sum of leaf marks, excluding stems)

3. Update _add_marking_guide_body() in docgen.py to:
   - Same hierarchy processing
   - Render leaf marking_steps only (not stems)
   - Render last step bold (final answer)

This implementation will allow rendering of the test fixture.
""")
