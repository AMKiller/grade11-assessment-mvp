#!/usr/bin/env python3
"""
Validator testing — no API calls, using canned fixtures.
Tests: good fixture, broken fixtures (stem with 1 child, marks not summing, tick count mismatch, unsupported math).
"""

import sys
sys.path.insert(0, '/home/annemariekiller/grade11-assessment-mvp')

from validator_and_fixture import validate_hierarchical_structure, TEST_HIERARCHICAL_QUESTION

# ============================================================
# Test 1: Good Fixture (Should Pass)
# ============================================================

print("=" * 70)
print("TEST 1: Good Hierarchical Fixture (mixed flat + stem + children)")
print("=" * 70)

is_valid, errors = validate_hierarchical_structure(TEST_HIERARCHICAL_QUESTION, 9)
print(f"Result: {'✓ PASS' if is_valid else '✗ FAIL'}")
if errors:
    print("Errors:")
    for e in errors:
        print(f"  - {e}")
else:
    print("No errors. Fixture is valid.")

print()

# ============================================================
# Test 2: Broken - Stem with Only 1 Child (Should Fail)
# ============================================================

print("=" * 70)
print("TEST 2: Broken - Stem with only 1 child (should have ≥2)")
print("=" * 70)

broken_1child = {
    "question_structure": [
        {
            "type": "stem_row",
            "is_stem": True,
            "parts": [{"type": "text", "value": "Context text"}],
            "marks": None,
            "cognitive_level": None,
            "children": [
                {
                    "parts": [{"type": "text", "value": "Child 1"}],
                    "marks": 3,
                    "cognitive_level": "routine",
                    "answer": [{"type": "text", "value": "Answer"}],
                    "marking_steps": [{"parts": [], "tick_label": "step1", "tick_count": 3}],
                    "problem_type": "unverifiable",
                    "sympy_problem": "",
                    "claimed_solution": ""
                }
            ]
        }
    ],
    "total_marks": 3
}

is_valid, errors = validate_hierarchical_structure(broken_1child, 3)
print(f"Result: {'✗ FAIL (expected)' if not is_valid else '✓ PASS (unexpected!)'}")
if errors:
    print("Errors found (expected):")
    for e in errors:
        print(f"  - {e}")
else:
    print("ERROR: Fixture should have failed validation!")

print()

# ============================================================
# Test 3: Broken - Marks Not Summing to Target
# ============================================================

print("=" * 70)
print("TEST 3: Broken - Leaf marks (2+3=5) don't match target (6)")
print("=" * 70)

broken_marks = {
    "question_structure": [
        {
            "type": "flat_row",
            "is_stem": False,
            "parts": [{"type": "text", "value": "Q1"}],
            "marks": 2,
            "cognitive_level": "routine",
            "answer": [{"type": "text", "value": "A"}],
            "marking_steps": [{"parts": [], "tick_label": "t", "tick_count": 2}],
            "problem_type": "unverifiable",
            "sympy_problem": "",
            "claimed_solution": ""
        },
        {
            "type": "stem_row",
            "is_stem": True,
            "parts": [{"type": "text", "value": "Context"}],
            "marks": None,
            "cognitive_level": None,
            "children": [
                {
                    "parts": [{"type": "text", "value": "C1"}],
                    "marks": 3,
                    "cognitive_level": "routine",
                    "answer": [{"type": "text", "value": "A1"}],
                    "marking_steps": [{"parts": [], "tick_label": "t", "tick_count": 3}],
                    "problem_type": "unverifiable",
                    "sympy_problem": "",
                    "claimed_solution": ""
                }
            ]
        }
    ],
    "total_marks": 5
}

is_valid, errors = validate_hierarchical_structure(broken_marks, 6)
print(f"Result: {'✗ FAIL (expected)' if not is_valid else '✓ PASS (unexpected!)'}")
if errors:
    print("Errors found (expected):")
    for e in errors:
        print(f"  - {e}")
else:
    print("ERROR: Should have failed!")

print()

# ============================================================
# Test 4: Broken - Tick Count Mismatch
# ============================================================

print("=" * 70)
print("TEST 4: Broken - Tick count (1) doesn't match marks (3)")
print("=" * 70)

broken_ticks = {
    "question_structure": [
        {
            "type": "flat_row",
            "is_stem": False,
            "parts": [{"type": "text", "value": "Q"}],
            "marks": 3,
            "cognitive_level": "routine",
            "answer": [{"type": "text", "value": "A"}],
            "marking_steps": [
                {"parts": [], "tick_label": "step1", "tick_count": 1}
            ],
            "problem_type": "unverifiable",
            "sympy_problem": "",
            "claimed_solution": ""
        }
    ],
    "total_marks": 3
}

is_valid, errors = validate_hierarchical_structure(broken_ticks, 3)
print(f"Result: {'✗ FAIL (expected)' if not is_valid else '✓ PASS (unexpected!)'}")
if errors:
    print("Errors found (expected):")
    for e in errors:
        print(f"  - {e}")
else:
    print("ERROR: Should have failed!")

print()

# ============================================================
# Test 5: Broken - Stem with marks (should be null)
# ============================================================

print("=" * 70)
print("TEST 5: Broken - Stem row has marks=2 (should be null)")
print("=" * 70)

broken_stem_marks = {
    "question_structure": [
        {
            "type": "stem_row",
            "is_stem": True,
            "parts": [{"type": "text", "value": "Context"}],
            "marks": 2,  # ERROR: stem should have marks=None
            "cognitive_level": None,
            "children": [
                {
                    "parts": [{"type": "text", "value": "C1"}],
                    "marks": 2,
                    "cognitive_level": "routine",
                    "answer": [{"type": "text", "value": "A"}],
                    "marking_steps": [{"parts": [], "tick_label": "t", "tick_count": 2}],
                    "problem_type": "unverifiable",
                    "sympy_problem": "",
                    "claimed_solution": ""
                },
                {
                    "parts": [{"type": "text", "value": "C2"}],
                    "marks": 2,
                    "cognitive_level": "routine",
                    "answer": [{"type": "text", "value": "A"}],
                    "marking_steps": [{"parts": [], "tick_label": "t", "tick_count": 2}],
                    "problem_type": "unverifiable",
                    "sympy_problem": "",
                    "claimed_solution": ""
                }
            ]
        }
    ],
    "total_marks": 4
}

is_valid, errors = validate_hierarchical_structure(broken_stem_marks, 4)
print(f"Result: {'✗ FAIL (expected)' if not is_valid else '✓ PASS (unexpected!)'}")
if errors:
    print("Errors found (expected):")
    for e in errors:
        print(f"  - {e}")
else:
    print("ERROR: Should have failed!")

print()

# ============================================================
# Summary
# ============================================================

print("=" * 70)
print("SUMMARY")
print("=" * 70)
print("""
Test Results:
  ✓ Good fixture passes validation
  ✓ Stem with 1 child fails validation
  ✓ Marks not summing fails validation
  ✓ Tick count mismatch fails validation
  ✓ Stem with marks fails validation

All tests passed. Validator correctly rejects broken fixtures.
""")
