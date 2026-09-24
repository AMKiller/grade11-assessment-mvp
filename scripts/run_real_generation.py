#!/usr/bin/env python3
"""
Real (non-mock) generation run: 2 topics x 5 questions, 50 marks total,
against the live Claude API. Writes the combined .docx to samples/ and
prints a full usage/cognitive/verification report to stdout as JSON
(also saved as a sidecar .json next to the .docx).

Model is controlled by the GENERATION_MODEL env var, read by generation.py
at import time -- so this script must be invoked once per model in a
separate process (a single run covers exactly one model).

Usage:
    ANTHROPIC_API_KEY=... [GENERATION_MODEL=claude-opus-5-5] \
        python3 scripts/run_real_generation.py <output_basename>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from generation import generate_paper, GENERATION_MODEL
from docgen import DocumentGenerator

TOPICS = ["Equations and Inequalities", "Exponents and Surds"]
MARKS_PER_TOPIC = 25  # 50 total split evenly across 2 topics
NUM_QUESTIONS_PER_TOPIC = 5
TARGET_DISTRIBUTION = {"knowledge": 20, "routine": 35, "complex": 30, "problem_solving": 15}

PRICING = {
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00},
}


def collect_leaf_verification(questions: list) -> dict:
    total_leaves = 0
    sympy_verified = 0
    manual_review = 0
    unverifiable = 0
    failed_detail = []

    for q in questions:
        for row in q.get("question_structure", []):
            leaves = row.get("children", []) if row.get("is_stem") else [row]
            for leaf in leaves:
                total_leaves += 1
                if leaf.get("problem_type") == "unverifiable":
                    unverifiable += 1
                if leaf.get("sympy_verified"):
                    sympy_verified += 1
                if leaf.get("manual_review_required"):
                    manual_review += 1
                    failed_detail.append({
                        "archetype_id": q.get("archetype_id"),
                        "problem_type": leaf.get("problem_type"),
                        "sympy_error": leaf.get("sympy_error"),
                    })

    return {
        "total_leaves": total_leaves,
        "sympy_verified": sympy_verified,
        "manual_review_required": manual_review,
        "unverifiable_by_design": unverifiable,
        "failed_detail": failed_detail,
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: run_real_generation.py <output_basename>", file=sys.stderr)
        sys.exit(1)

    out_basename = sys.argv[1]
    print(f"=== Real generation run -- model={GENERATION_MODEL} ===\n")

    topics_data = []
    combined_usage_log = []
    combined_errors = []
    all_questions = []

    for topic in TOPICS:
        print(f"--- Generating topic: {topic} ---")
        result = generate_paper(
            topic=topic,
            num_questions=NUM_QUESTIONS_PER_TOPIC,
            target_distribution=TARGET_DISTRIBUTION,
            target_marks=MARKS_PER_TOPIC,
        )
        topics_data.append((topic, result["questions"]))
        combined_usage_log.extend(result["usage_log"])
        combined_errors.extend([f"[{topic}] {e}" for e in result.get("generation_errors", [])])
        all_questions.extend(result["questions"])
        print(f"  -> {result['num_questions']} questions, {result['total_marks']} marks\n")

    total_marks = sum(m for _, qs in topics_data for m in [sum(
        leaf.get("marks", 0) or 0
        for q in qs
        for leaf in (
            [c for row in q.get("question_structure", []) for c in (row.get("children", []) if row.get("is_stem") else [row])]
        )
    )])

    # --- Usage / cost report ---
    total_calls = len(combined_usage_log)
    retries = sum(1 for r in combined_usage_log if r["attempt"] > 1)
    total_input = sum(r["input_tokens"] for r in combined_usage_log)
    total_output = sum(r["output_tokens"] for r in combined_usage_log)
    total_cache_read = sum(r["cache_read_input_tokens"] for r in combined_usage_log)
    total_cache_write = sum(r["cache_creation_input_tokens"] for r in combined_usage_log)

    price = PRICING.get(GENERATION_MODEL)
    if price:
        cost = (total_input / 1_000_000 * price["input"]) + (total_output / 1_000_000 * price["output"])
    else:
        cost = None

    # --- Cognitive distribution (actual, across both topics combined) ---
    from generation import _analyze_cognitive_distribution
    cognitive = _analyze_cognitive_distribution(all_questions, TARGET_DISTRIBUTION)

    # --- Verification / manual review ---
    verification = collect_leaf_verification(all_questions)

    report = {
        "model": GENERATION_MODEL,
        "topics": TOPICS,
        "num_questions_per_topic": NUM_QUESTIONS_PER_TOPIC,
        "target_marks_per_topic": MARKS_PER_TOPIC,
        "usage": {
            "total_calls": total_calls,
            "retries": retries,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "cache_read_tokens": total_cache_read,
            "cache_creation_tokens": total_cache_write,
            "cost_usd": round(cost, 4) if cost is not None else None,
            "pricing_used": price,
        },
        "cognitive_distribution": cognitive,
        "verification": verification,
        "generation_errors": combined_errors,
        "raw_usage_log": combined_usage_log,
    }

    print("\n=== REPORT ===")
    print(json.dumps(report, indent=2, default=str))

    # --- Document generation ---
    docgen = DocumentGenerator(template_path=None)
    docx_bytes = docgen.generate_full_assessment(
        topics_data=topics_data,
        total_marks=MARKS_PER_TOPIC * len(TOPICS),
        task="Task",
        term="Term 2",
        time_minutes=90,
        grade="11",
        target_distribution=TARGET_DISTRIBUTION,
    )

    samples_dir = Path(__file__).parent.parent / "samples"
    samples_dir.mkdir(exist_ok=True)
    docx_path = samples_dir / f"{out_basename}.docx"
    docx_path.write_bytes(docx_bytes)
    print(f"\nSaved: {docx_path}")

    report_path = samples_dir / f"{out_basename}_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"Saved: {report_path}")


if __name__ == "__main__":
    main()
