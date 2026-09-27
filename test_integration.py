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

    # docgen.py now consumes hierarchical question dicts (question_structure
    # + total_marks), not flat GeneratedQuestion objects -- see generation.py's
    # grid-first redesign and docgen.py's _flatten_topic_hierarchy().
    def flat_question(archetype_id, question_text, answer_text, marks, cognitive_level):
        return {
            "archetype_id": archetype_id,
            "total_marks": marks,
            "question_structure": [{
                "is_stem": False,
                "parts": [{"type": "text", "value": question_text}],
                "marks": marks,
                "cognitive_level": cognitive_level,
                "answer": [{"type": "text", "value": answer_text}],
                "marking_steps": [{"parts": [{"type": "text", "value": answer_text}],
                                    "tick_label": "answer", "tick_count": marks}],
                "problem_type": "unverifiable"
            }]
        }

    questions = [
        flat_question("eqineq_001", "Solve: (x-2)(x+3) = 0", "x = 2 or x = -3", 2, "routine"),
        flat_question("eqineq_002", "Solve: x² + 3x - 4 = 0 (correct to 2 decimal places)",
                       "x ≈ 0.85 or x ≈ -4.85", 4, "routine"),
    ]

    # No try/except here -- a failure must propagate and fail the whole
    # suite loudly, not print a "⚠" warning and let the run report success
    # (this exact pattern previously masked a real regression, see STATUS.md).
    gen = DocumentGenerator()

    topics_data = [("Equations and Inequalities", questions)]

    qp_bytes = gen.generate_question_paper(
        topics_data=topics_data,
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
    with open("/tmp/test_qp.docx", "wb") as f:
        f.write(qp_bytes)
    print("  ✓ Saved to /tmp/test_qp.docx")

    mg_bytes = gen.generate_marking_guide(
        topics_data=topics_data,
        total_marks=6,
        task="Task 2",
        term="Term 1",
        grade="11"
    )
    assert len(mg_bytes) > 0
    print(f"  ✓ Marking guide generated ({len(mg_bytes)} bytes)")
    with open("/tmp/test_mg.docx", "wb") as f:
        f.write(mg_bytes)
    print("  ✓ Saved to /tmp/test_mg.docx")

    grid_bytes = gen.generate_cognitive_grid_xlsx(topics_data=topics_data)
    assert len(grid_bytes) > 0
    print(f"  ✓ Cognitive grid generated ({len(grid_bytes)} bytes)")
    with open("/tmp/test_grid.xlsx", "wb") as f:
        f.write(grid_bytes)
    print("  ✓ Saved to /tmp/test_grid.xlsx")


def test_cognitive_analysis():
    """Test cognitive distribution analysis."""
    print("\n📊 Testing Cognitive Analysis...")

    from generation import _analyze_cognitive_distribution

    # _analyze_cognitive_distribution now reads leaves out of hierarchical
    # question_structure dicts (flat rows and stem children), not flat
    # GeneratedQuestion objects -- see generation.py's grid-first redesign.
    def flat_leaf(num, marks, level):
        return {
            "num": num, "is_stem": False, "parts": [{"type": "text", "value": f"Q{num}"}],
            "marks": marks, "cognitive_level": level,
            "answer": [{"type": "text", "value": f"A{num}"}], "marking_steps": []
        }

    questions = [
        {"question_structure": [flat_leaf(1, 5, "knowledge")], "total_marks": 5},
        {"question_structure": [flat_leaf(2, 20, "routine")], "total_marks": 20},
        {"question_structure": [flat_leaf(3, 15, "complex")], "total_marks": 15},
        {"question_structure": [flat_leaf(4, 10, "problem_solving")], "total_marks": 10},
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
    import sys

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
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
