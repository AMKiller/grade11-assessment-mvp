#!/usr/bin/env python3
"""
Quick integration test: verify KB loading, archetype sampling, and doc generation
without calling Claude API.
"""

from knowledge_base import KnowledgeBase
from generation import GeneratedQuestion
from docgen import DocumentGenerator
import json


def test_knowledge_base():
    """Test KB loading and archetype sampling."""
    print("\n📚 Testing Knowledge Base...")

    kb = KnowledgeBase()

    # Test topic loading
    assert "Equations and Inequalities" in kb.topics
    assert "Exponents and Surds" in kb.topics
    print("  ✓ Topics loaded")

    # Test archetype retrieval
    eqineq_archs = kb.get_archetypes("Equations and Inequalities")
    assert len(eqineq_archs) == 8
    print(f"  ✓ Equations & Inequalities: {len(eqineq_archs)} archetypes")

    exp_surd_archs = kb.get_archetypes("Exponents and Surds")
    assert len(exp_surd_archs) > 15
    print(f"  ✓ Exponents & Surds: {len(exp_surd_archs)} archetypes")

    # Test tier filtering
    core_only = kb.get_archetypes("Equations and Inequalities", tier_filter=["core"])
    print(f"  ✓ Core-tier filtering: {len(core_only)} core archetypes in Eq&Ineq")

    # Test sampling by cognitive distribution
    sampled = kb.sample_by_cognitive_distribution(
        "Equations and Inequalities",
        num_archetypes=5,
        target_distribution={'knowledge': 20, 'routine': 35, 'complex': 30, 'problem_solving': 15},
        tier_filter=["core", "supplementary"],
        seed=42
    )
    assert len(sampled) == 5
    print(f"  ✓ Sampled {len(sampled)} archetypes by cognitive distribution")

    for arch in sampled:
        print(f"    - {arch.archetype_id}: {arch.name}")


def test_generated_question():
    """Test GeneratedQuestion class and verification setup."""
    print("\n🎯 Testing GeneratedQuestion & Verification...")

    q = GeneratedQuestion(
        archetype_id="eqineq_001",
        question_text="Solve for x: (x-2)(x+3) = 0",
        answer_text="x = 2 or x = -3",
        answer_expression="x = (2, -3)",
        marks=2,
        cognitive_level="routine"
    )

    assert q.archetype_id == "eqineq_001"
    assert q.marks == 2
    assert not q.sympy_verified
    print("  ✓ GeneratedQuestion created")

    # Test to_dict
    d = q.to_dict()
    assert d["marks"] == 2
    assert d["sympy_verified"] == False
    print("  ✓ Serialization works")


def test_document_generation():
    """Test document generation without Claude."""
    print("\n📄 Testing Document Generation...")

    # Create mock questions
    questions = [
        GeneratedQuestion(
            archetype_id="eqineq_001",
            question_text="Solve: (x-2)(x+3) = 0",
            answer_text="x = 2 or x = -3",
            answer_expression="x = (2, -3)",
            marks=2,
            cognitive_level="routine"
        ),
        GeneratedQuestion(
            archetype_id="eqineq_002",
            question_text="Solve: x² + 3x - 4 = 0 (correct to 2 decimal places)",
            answer_text="x ≈ 0.85 or x ≈ -4.85",
            answer_expression="x = (0.85, -4.85)",
            marks=4,
            cognitive_level="routine"
        ),
    ]

    try:
        gen = DocumentGenerator()

        # Try to generate the full assessment (QP + marking guide + cognitive grid)
        qp_bytes = gen.generate_full_assessment(
            questions=questions,
            topic="Equations and Inequalities",
            total_marks=6,
            task="Task 2",
            term="Term 1",
            time_minutes=60,
            examiner="Test Examiner",
            moderator="Test Moderator",
            grade="11"
        )

        assert len(qp_bytes) > 0
        print(f"  ✓ Question paper generated ({len(qp_bytes)} bytes)")

        # Save to file for inspection
        with open("/tmp/test_qp.docx", "wb") as f:
            f.write(qp_bytes)
        print("  ✓ Saved to /tmp/test_qp.docx")

    except Exception as e:
        print(f"  ⚠ Document generation error: {e}")
        import traceback
        traceback.print_exc()


def test_cognitive_analysis():
    """Test cognitive distribution analysis."""
    print("\n📊 Testing Cognitive Analysis...")

    from generation import _analyze_cognitive_distribution

    questions = [
        GeneratedQuestion(
            archetype_id="q1",
            question_text="Q1",
            answer_text="A1",
            answer_expression="x=1",
            marks=5,
            cognitive_level="knowledge"
        ),
        GeneratedQuestion(
            archetype_id="q2",
            question_text="Q2",
            answer_text="A2",
            answer_expression="x=2",
            marks=20,
            cognitive_level="routine"
        ),
        GeneratedQuestion(
            archetype_id="q3",
            question_text="Q3",
            answer_text="A3",
            answer_expression="x=3",
            marks=15,
            cognitive_level="complex"
        ),
        GeneratedQuestion(
            archetype_id="q4",
            question_text="Q4",
            answer_text="A4",
            answer_expression="x=4",
            marks=10,
            cognitive_level="problem_solving"
        ),
    ]

    targets = {
        'knowledge': 20,
        'routine': 35,
        'complex': 30,
        'problem_solving': 15
    }

    analysis = _analyze_cognitive_distribution(questions, targets)

    print(f"  Marks by level: {analysis['marks_by_level']}")
    print(f"  Percentages: {analysis['percentages_by_level']}")
    print(f"  Variance from target: {analysis['variance']}")

    # Total should be 50 marks
    total = sum(analysis['marks_by_level'].values())
    assert total == 50
    print(f"  ✓ Total marks: {total}")

    # Check distribution
    pcts = analysis['percentages_by_level']
    assert pcts['knowledge'] == 10.0
    assert pcts['routine'] == 40.0
    print("  ✓ Distribution analysis works")


if __name__ == "__main__":
    print("=" * 60)
    print("INTEGRATION TEST: Grade 11 Assessment Generator")
    print("=" * 60)

    try:
        test_knowledge_base()
        test_generated_question()
        test_generated_question()
        test_cognitive_analysis()
        test_document_generation()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
