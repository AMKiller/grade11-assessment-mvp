#!/usr/bin/env python3
"""
Validator testing -- no API calls, using canned fixtures.
Tests: good fixture, broken fixtures (stem with 1 child, marks not summing,
tick count mismatch, stem with marks).

Every case below is a real assertion, not a printed opinion -- previously
this file printed "PASS (expected)"/"FAIL (expected)" labels and a
hardcoded "All tests passed" summary regardless of what validate_
hierarchical_structure() actually returned, so it could never fail even
if the validator broke. Fixed to raise AssertionError (and exit non-zero)
on any mismatch -- see STATUS.md's note on tests that must fail loudly.
"""

import sys
sys.path.insert(0, '/home/annemariekiller/grade11-assessment-mvp')

from validator_and_fixture import validate_hierarchical_structure, TEST_HIERARCHICAL_QUESTION


def test_good_fixture_passes():
    print("=" * 70)
    print("TEST 1: Good Hierarchical Fixture (mixed flat + stem + children)")
    print("=" * 70)
    is_valid, errors = validate_hierarchical_structure(TEST_HIERARCHICAL_QUESTION, 9)
    assert is_valid, f"expected valid fixture to pass, got errors: {errors}"
    print("  ✓ PASS, no errors")


def test_stem_with_one_child_fails():
    print("\n" + "=" * 70)
    print("TEST 2: Broken - Stem row with only 1 child (should have ≥2)")
    print("=" * 70)
    broken = {
        "question_structure": [{
            "type": "stem_row", "is_stem": True,
            "parts": [{"type": "text", "value": "Context text"}],
            "marks": None, "cognitive_level": None,
            "children": [{
                "parts": [{"type": "text", "value": "Child 1"}],
                "marks": 3, "cognitive_level": "routine",
                "answer": [{"type": "text", "value": "Answer"}],
                "marking_steps": [{"parts": [], "tick_label": "step1", "tick_count": 3}],
                "problem_type": "unverifiable", "sympy_problem": "", "claimed_solution": ""
            }]
        }],
        "total_marks": 3
    }
    is_valid, errors = validate_hierarchical_structure(broken, 3)
    assert not is_valid, "expected stem with 1 child to fail validation, but it passed"
    assert any("child" in e.lower() for e in errors), f"expected a child-count error, got: {errors}"
    print(f"  ✓ FAIL as expected: {errors}")


def test_marks_not_summing_fails():
    print("\n" + "=" * 70)
    print("TEST 3: Broken - Leaf marks (2+3=5) don't match target (6)")
    print("=" * 70)
    broken = {
        "question_structure": [
            {
                "type": "flat_row", "is_stem": False,
                "parts": [{"type": "text", "value": "Q1"}],
                "marks": 2, "cognitive_level": "routine",
                "answer": [{"type": "text", "value": "A"}],
                "marking_steps": [{"parts": [], "tick_label": "t", "tick_count": 2}],
                "problem_type": "unverifiable", "sympy_problem": "", "claimed_solution": ""
            },
            {
                "type": "stem_row", "is_stem": True,
                "parts": [{"type": "text", "value": "Context"}],
                "marks": None, "cognitive_level": None,
                "children": [{
                    "parts": [{"type": "text", "value": "C1"}],
                    "marks": 3, "cognitive_level": "routine",
                    "answer": [{"type": "text", "value": "A1"}],
                    "marking_steps": [{"parts": [], "tick_label": "t", "tick_count": 3}],
                    "problem_type": "unverifiable", "sympy_problem": "", "claimed_solution": ""
                }]
            }
        ],
        "total_marks": 5
    }
    is_valid, errors = validate_hierarchical_structure(broken, 6)
    assert not is_valid, "expected mismatched marks to fail validation, but it passed"
    assert any("marks" in e.lower() for e in errors), f"expected a marks-mismatch error, got: {errors}"
    print(f"  ✓ FAIL as expected: {errors}")


def test_tick_count_mismatch_fails():
    print("\n" + "=" * 70)
    print("TEST 4: Broken - Tick count (1) doesn't match marks (3)")
    print("=" * 70)
    broken = {
        "question_structure": [{
            "type": "flat_row", "is_stem": False,
            "parts": [{"type": "text", "value": "Q"}],
            "marks": 3, "cognitive_level": "routine",
            "answer": [{"type": "text", "value": "A"}],
            "marking_steps": [{"parts": [], "tick_label": "step1", "tick_count": 1}],
            "problem_type": "unverifiable", "sympy_problem": "", "claimed_solution": ""
        }],
        "total_marks": 3
    }
    is_valid, errors = validate_hierarchical_structure(broken, 3)
    assert not is_valid, "expected tick-count mismatch to fail validation, but it passed"
    assert any("tick" in e.lower() for e in errors), f"expected a tick-count error, got: {errors}"
    print(f"  ✓ FAIL as expected: {errors}")


def test_stem_with_marks_fails():
    print("\n" + "=" * 70)
    print("TEST 5: Broken - Stem row has marks=2 (should be null)")
    print("=" * 70)
    broken = {
        "question_structure": [{
            "type": "stem_row", "is_stem": True,
            "parts": [{"type": "text", "value": "Context"}],
            "marks": 2,  # ERROR: stem should have marks=None
            "cognitive_level": None,
            "children": [
                {
                    "parts": [{"type": "text", "value": "C1"}],
                    "marks": 2, "cognitive_level": "routine",
                    "answer": [{"type": "text", "value": "A"}],
                    "marking_steps": [{"parts": [], "tick_label": "t", "tick_count": 2}],
                    "problem_type": "unverifiable", "sympy_problem": "", "claimed_solution": ""
                },
                {
                    "parts": [{"type": "text", "value": "C2"}],
                    "marks": 2, "cognitive_level": "routine",
                    "answer": [{"type": "text", "value": "A"}],
                    "marking_steps": [{"parts": [], "tick_label": "t", "tick_count": 2}],
                    "problem_type": "unverifiable", "sympy_problem": "", "claimed_solution": ""
                }
            ]
        }],
        "total_marks": 4
    }
    is_valid, errors = validate_hierarchical_structure(broken, 4)
    assert not is_valid, "expected stem with marks set to fail validation, but it passed"
    assert any("marks=null" in e.lower() or "marks" in e.lower() for e in errors), f"expected a stem-marks error, got: {errors}"
    print(f"  ✓ FAIL as expected: {errors}")


if __name__ == "__main__":
    import sys as _sys

    tests = [
        test_good_fixture_passes,
        test_stem_with_one_child_fails,
        test_marks_not_summing_fails,
        test_tick_count_mismatch_fails,
        test_stem_with_marks_fails,
    ]

    try:
        for t in tests:
            t()
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"\nAll {len(tests)} tests passed.\n")
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        _sys.exit(1)
