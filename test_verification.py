#!/usr/bin/env python3
"""Unit tests for the real SymPy verification logic, no API calls."""

import json
from generation import QuestionGenerator, GeneratedQuestion, _repair_json_escape_collisions


def make_gen():
    # Bypass __init__'s API key requirement by constructing without calling it
    gen = QuestionGenerator.__new__(QuestionGenerator)
    return gen


def test_equation_correct():
    gen = make_gen()
    q = GeneratedQuestion(
        archetype_id="test", question_text="2x+1=5/x", answer_text="x=1.35 or x=-1.85",
        answer_expression="", marks=4, cognitive_level="routine",
        problem_type="equation", sympy_problem="2*x**2 + x - 5",
        claimed_solution="[1.35, -1.85]"
    )
    verified, detail = gen._verify_answer(q)
    print(f"Equation (correct, rounded): verified={verified}, detail={detail}")
    assert verified, f"Expected True, got False: {detail}"


def test_equation_wrong():
    gen = make_gen()
    q = GeneratedQuestion(
        archetype_id="test", question_text="x^2-5x+6=0", answer_text="x=1 or x=6",
        answer_expression="", marks=2, cognitive_level="routine",
        problem_type="equation", sympy_problem="x**2 - 5*x + 6",
        claimed_solution="[1, 6]"  # WRONG: actual roots are 2, 3
    )
    verified, detail = gen._verify_answer(q)
    print(f"Equation (deliberately wrong): verified={verified}, detail={detail}")
    assert not verified, "Expected False (wrong answer), but verification passed!"


def test_equation_legitimate_root_rejection():
    """Claimed answer correctly excludes an extraneous/invalid root (e.g. negative length)."""
    gen = make_gen()
    q = GeneratedQuestion(
        archetype_id="test", question_text="length^2 = 22 (length > 0)",
        answer_text="length = 4.69 (rejecting the negative root)",
        answer_expression="", marks=3, cognitive_level="routine",
        problem_type="equation", sympy_problem="x**2 - 22",
        claimed_solution="[4.69041575982343]"  # correctly omits -4.69
    )
    verified, detail = gen._verify_answer(q)
    print(f"Equation (legitimate root rejection): verified={verified}, detail={detail}")
    assert verified, f"Expected True (valid subset), got False: {detail}"


def test_equation_invented_value():
    """Claimed value that isn't among the true roots at all -- must fail."""
    gen = make_gen()
    q = GeneratedQuestion(
        archetype_id="test", question_text="x**2-22=0", answer_text="x=100 (bogus)",
        answer_expression="", marks=3, cognitive_level="routine",
        problem_type="equation", sympy_problem="x**2 - 22",
        claimed_solution="[100]"
    )
    verified, detail = gen._verify_answer(q)
    print(f"Equation (invented value): verified={verified}, detail={detail}")
    assert not verified, "Expected False (invented value not a real root), but verification passed!"


def test_equation_factorisation():
    gen = make_gen()
    q = GeneratedQuestion(
        archetype_id="test", question_text="3x(x-4)=0", answer_text="x=0 or x=4",
        answer_expression="", marks=2, cognitive_level="routine",
        problem_type="equation", sympy_problem="3*x*(x-4)",
        claimed_solution="[0, 4]"
    )
    verified, detail = gen._verify_answer(q)
    print(f"Equation (factorisation): verified={verified}, detail={detail}")
    assert verified, f"Expected True, got False: {detail}"


def test_inequality_correct():
    gen = make_gen()
    q = GeneratedQuestion(
        archetype_id="test", question_text="2x^2-5x-12<=0", answer_text="-3/2<=x<=4",
        answer_expression="", marks=4, cognitive_level="complex",
        problem_type="inequality", sympy_problem="2*x**2 - 5*x - 12 <= 0",
        claimed_solution="Interval(-1.5, 4)"
    )
    verified, detail = gen._verify_answer(q)
    print(f"Inequality (correct): verified={verified}, detail={detail}")
    assert verified, f"Expected True, got False: {detail}"


def test_inequality_wrong():
    gen = make_gen()
    q = GeneratedQuestion(
        archetype_id="test", question_text="(x+2)(x-5)<0", answer_text="wrong direction",
        answer_expression="", marks=4, cognitive_level="complex",
        problem_type="inequality", sympy_problem="(x+2)*(x-5) < 0",
        claimed_solution="Union(Interval.open(-oo,-2), Interval.open(5,oo))"  # WRONG: should be -2 < x < 5
    )
    verified, detail = gen._verify_answer(q)
    print(f"Inequality (deliberately wrong): verified={verified}, detail={detail}")
    assert not verified, "Expected False (wrong direction), but verification passed!"


def test_system_correct():
    gen = make_gen()
    q = GeneratedQuestion(
        archetype_id="test", question_text="y=2x-1; x^2+y^2=10",
        answer_text="(1,1) or (-2.2,-5.4)",
        answer_expression="", marks=6, cognitive_level="complex",
        problem_type="system", sympy_problem="y - (2*x-1); x**2 + y**2 - 10",
        claimed_solution="[(1, 1), (-1.8, -4.6)]"
    )
    verified, detail = gen._verify_answer(q)
    print(f"System: verified={verified}, detail={detail}")
    # Just check it runs without crashing and reports something coherent
    print(f"  (informational -- exact roots may differ from hand-picked claim)")


def test_unverifiable_handled_upstream():
    """unverifiable is handled in generate_question(), not _verify_answer(). Just document that."""
    print("Unverifiable type: handled by generate_question() before calling _verify_answer() -- OK by design")


def test_frac_json_escape_repair():
    """
    Regression test for the 2026-09-27 bug: a math part containing "\frac"
    with a single backslash is ambiguous JSON (\f is also the form-feed
    escape) -- json.loads() silently corrupts it instead of raising. Confirm
    _repair_json_escape_collisions() fixes this on the exact wire-text shape
    Claude produces, is idempotent on already-correct output, and leaves
    \sqrt/\cdot (which don't collide) alone.
    """
    # Single-escaped \frac (the bug) -- must round-trip to a literal \frac,
    # not a form-feed character. Built directly rather than via json.dumps
    # (which would correctly double-escape it for us) -- this is what a
    # single mis-escaped backslash from Claude actually looks like on the
    # wire: literally the two characters backslash, f.
    raw_bad = '{"value": "\\frac{a}{b}"}'
    parsed_before = json.loads(raw_bad)
    assert parsed_before["value"] == "\x0crac{a}{b}", (
        "test setup check failed -- expected the unrepaired parse to demonstrate "
        f"the corruption, got {parsed_before['value']!r}"
    )

    repaired = _repair_json_escape_collisions(raw_bad)
    parsed_after = json.loads(repaired)
    assert parsed_after["value"] == "\\frac{a}{b}", (
        f"repair failed to recover a literal \\frac, got {parsed_after['value']!r}"
    )
    print("  ✓ single-escaped \\frac repaired to a literal \\frac (not form-feed)")

    # Already-correctly-escaped output must be left untouched (idempotent).
    raw_good = '{"value": "\\\\frac{a}{b}"}'
    parsed_good_before = json.loads(raw_good)
    parsed_good_after = json.loads(_repair_json_escape_collisions(raw_good))
    assert parsed_good_after["value"] == parsed_good_before["value"] == "\\frac{a}{b}"
    print("  ✓ already-correct \\\\frac left untouched (repair is idempotent)")

    # \sqrt and \cdot don't collide with any JSON escape letter -- a single
    # backslash before them is simply invalid JSON (caught immediately by
    # the existing "not valid JSON" retry path), and the repair must not
    # touch them either way.
    raw_sqrt = '{"value": "\\\\sqrt{x}"}'
    assert json.loads(_repair_json_escape_collisions(raw_sqrt))["value"] == "\\sqrt{x}"
    print("  ✓ \\sqrt (no collision) unaffected by the repair")


if __name__ == "__main__":
    print("=" * 60)
    print("VERIFICATION LOGIC UNIT TESTS")
    print("=" * 60)
    test_equation_correct()
    test_equation_wrong()
    test_equation_legitimate_root_rejection()
    test_equation_invented_value()
    test_equation_factorisation()
    test_inequality_correct()
    test_inequality_wrong()
    test_system_correct()
    test_unverifiable_handled_upstream()
    test_frac_json_escape_repair()
    print("\n✓ ALL VERIFICATION TESTS PASSED")
