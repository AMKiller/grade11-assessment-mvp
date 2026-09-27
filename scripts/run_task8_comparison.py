#!/usr/bin/env python3
"""
Task 8 model-comparison run: Exponents & Surds (25 marks) + Equations &
Inequalities (25 marks), 50 marks total, against the live Claude API.
Model/thinking/effort config controlled by env vars read by generation.py
at import time (GENERATION_MODEL, GENERATION_THINKING_MODE,
GENERATION_EFFORT, GENERATION_MAX_TOKENS) -- run once per configuration.

Saves, per run:
  samples/task8_<basename>.docx        -- combined QP+MG+grid document
  samples/task8_<basename>.pdf
  samples/task8_<basename>_report.json      -- usage/cost/cognitive summary
  samples/task8_<basename>_raw_questions.json -- full generated question
      structures (parts/answer/marking_steps/sympy fields) for independent
      correctness verification -- NOT persisted by run_real_generation.py,
      needed here because this comparison requires re-checking every
      marking-guide answer by hand/sympy, not just the aggregate stats.

Usage:
    ANTHROPIC_API_KEY=... GENERATION_MODEL=claude-sonnet-5 \
        [GENERATION_EFFORT=low] python3 scripts/run_task8_comparison.py <basename>
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from generation import (
    generate_paper, GENERATION_MODEL, GENERATION_THINKING_MODE,
    GENERATION_EFFORT, GENERATION_MAX_TOKENS, MODELS_WITHOUT_DISABLED_THINKING,
    _analyze_cognitive_distribution, _summarize_usage,
)
from docgen import DocumentGenerator, _compute_actual_marks

TOPICS_MARKS = [
    ("Exponents and Surds", 25),
    ("Equations and Inequalities", 25),
]
NUM_QUESTIONS_PER_TOPIC = 5
TARGET_DISTRIBUTION = {"knowledge": 20, "routine": 35, "complex": 30, "problem_solving": 15}

METADATA = dict(
    task="Task 8",
    term="Term 3 2026",
    time_minutes=60,
    examiner="AE Killer",
    moderator="D Piters",
    grade="11",
)

PRICING = {
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}


def collect_leaf_detail(topics_data: list) -> dict:
    total_leaves = 0
    sympy_verified = 0
    manual_review = 0
    unverifiable = 0
    real_verification_failures = 0
    per_leaf = []
    unverifiable_detail = []
    failed_verification_detail = []
    constructed_count = 0
    constructed_detail = []
    cognitive_mismatch_count = 0
    cognitive_mismatch_detail = []

    for topic, questions in topics_data:
        for q in questions:
            archetype_id = q.get("archetype_id")
            planned = q.get("_planned_cognitive_targets", {})
            for row in q.get("question_structure", []):
                leaves = row.get("children", []) if row.get("is_stem") else [row]
                for leaf in leaves:
                    total_leaves += 1
                    actual_level = leaf.get("cognitive_level")
                    problem_type = leaf.get("problem_type")
                    archetype_match = leaf.get("archetype_match")
                    disagreement = leaf.get("cognitive_level_disagreement")
                    per_leaf.append({
                        "topic": topic, "archetype_id": archetype_id, "num": leaf.get("num"),
                        "marks": leaf.get("marks"), "problem_type": problem_type,
                        "actual_cognitive_level": actual_level,
                        "planned_cognitive_targets": planned,
                        "sympy_verified": leaf.get("sympy_verified"),
                        "manual_review_required": leaf.get("manual_review_required"),
                        "archetype_match": archetype_match,
                        "cognitive_level_disagreement": disagreement,
                    })
                    if problem_type == "unverifiable":
                        unverifiable += 1
                        unverifiable_detail.append({
                            "topic": topic, "archetype_id": archetype_id,
                            "num": leaf.get("num"), "marks": leaf.get("marks"),
                        })
                    if leaf.get("sympy_verified"):
                        sympy_verified += 1
                    if leaf.get("manual_review_required"):
                        manual_review += 1
                        if problem_type != "unverifiable":
                            real_verification_failures += 1
                            failed_verification_detail.append({
                                "topic": topic, "archetype_id": archetype_id,
                                "problem_type": problem_type, "sympy_error": leaf.get("sympy_error"),
                            })
                    if archetype_match == "constructed":
                        constructed_count += 1
                        constructed_detail.append({
                            "topic": topic, "archetype_id": archetype_id,
                            "num": leaf.get("num"), "marks": leaf.get("marks"),
                        })
                    if disagreement:
                        cognitive_mismatch_count += 1
                        cognitive_mismatch_detail.append({
                            "topic": topic, "archetype_id": archetype_id,
                            "num": leaf.get("num"), "marks": leaf.get("marks"),
                            "assigned_level": actual_level, "disagreement": disagreement,
                        })

    return {
        "total_leaves": total_leaves, "sympy_verified": sympy_verified,
        "manual_review_required": manual_review, "unverifiable_by_design": unverifiable,
        "real_verification_failures": real_verification_failures,
        "unverifiable_detail": unverifiable_detail,
        "failed_verification_detail": failed_verification_detail,
        "constructed_count": constructed_count,
        "constructed_detail": constructed_detail,
        "cognitive_mismatch_count": cognitive_mismatch_count,
        "cognitive_mismatch_detail": cognitive_mismatch_detail,
        "per_leaf": per_leaf,
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: run_task8_comparison.py <output_basename>", file=sys.stderr)
        sys.exit(1)

    out_basename = f"task8_{sys.argv[1]}"
    thinking_desc = (
        f"effort={GENERATION_EFFORT or 'low'} (thinking cannot be disabled on this model)"
        if GENERATION_MODEL in MODELS_WITHOUT_DISABLED_THINKING
        else f"thinking_mode={GENERATION_THINKING_MODE}, effort={GENERATION_EFFORT or '(unset)'}"
    )
    print(f"=== Task 8 comparison run -- model={GENERATION_MODEL}, {thinking_desc}, "
          f"max_tokens={GENERATION_MAX_TOKENS} ===\n")

    topics_data = []
    combined_usage_log = []
    combined_errors = []
    all_questions = []
    diversity_diagnostics = {}

    wall_start = time.time()
    for topic, marks in TOPICS_MARKS:
        print(f"--- Generating topic: {topic} ({marks} marks) ---")
        result = generate_paper(
            topic=topic,
            num_questions=NUM_QUESTIONS_PER_TOPIC,
            target_distribution=TARGET_DISTRIBUTION,
            target_marks=marks,
        )
        topics_data.append((topic, result["questions"]))
        combined_usage_log.extend(result["usage_log"])
        combined_errors.extend([f"[{topic}] {e}" for e in result.get("generation_errors", [])])
        all_questions.extend(result["questions"])
        diversity_diagnostics[topic] = result.get("diversity_diagnostics", {})
        archetype_ids = [q.get("archetype_id") for q in result["questions"]]
        print(f"  -> {result['num_questions']} questions, {result['total_marks']} marks")
        print(f"     archetypes used: {archetype_ids}")
        if diversity_diagnostics[topic].get("forced_reuse_archetype_ids"):
            print(f"     [diversity] forced reuse (pool exhausted): {diversity_diagnostics[topic]['forced_reuse_archetype_ids']}")
        if diversity_diagnostics[topic].get("subtopic_coverage_swaps"):
            for note in diversity_diagnostics[topic]["subtopic_coverage_swaps"]:
                print(f"     [diversity] {note}")
        print()
    wall_seconds = round(time.time() - wall_start, 1)

    question_groups = [(i + 1, qs) for i, (_, qs) in enumerate(topics_data)]
    actual_total_marks = _compute_actual_marks(question_groups)

    usage_summary = _summarize_usage(combined_usage_log)
    price = PRICING.get(GENERATION_MODEL)
    if price:
        cost = (usage_summary["total_input_tokens"] / 1_000_000 * price["input"]) + \
               (usage_summary["total_output_tokens"] / 1_000_000 * price["output"])
    else:
        cost = None
    usage_summary["cost_usd"] = round(cost, 4) if cost is not None else None
    usage_summary["pricing_used"] = price
    usage_summary["wall_clock_seconds"] = wall_seconds

    cognitive = _analyze_cognitive_distribution(all_questions, TARGET_DISTRIBUTION)
    leaf_detail = collect_leaf_detail(topics_data)

    report = {
        "model": GENERATION_MODEL,
        "thinking_mode": GENERATION_THINKING_MODE,
        "effort_applied": (
            (GENERATION_EFFORT or "low") if GENERATION_MODEL in MODELS_WITHOUT_DISABLED_THINKING
            else (GENERATION_EFFORT if GENERATION_THINKING_MODE != "disabled" and GENERATION_EFFORT else None)
        ),
        "max_tokens": GENERATION_MAX_TOKENS,
        "topics_marks": TOPICS_MARKS,
        "num_questions_per_topic": NUM_QUESTIONS_PER_TOPIC,
        "actual_total_marks": actual_total_marks,
        "requested_total_marks": sum(m for _, m in TOPICS_MARKS),
        "usage": usage_summary,
        "cognitive_distribution": cognitive,
        "verification": leaf_detail,
        "diversity_diagnostics": diversity_diagnostics,
        "generation_errors": combined_errors,
        "raw_usage_log": combined_usage_log,
    }

    print("\n=== REPORT (summary) ===")
    print(json.dumps({k: v for k, v in report.items() if k not in ("raw_usage_log", "verification")}, indent=2, default=str))

    samples_dir = Path(__file__).parent.parent / "samples"
    samples_dir.mkdir(exist_ok=True)

    # Full raw question structures -- needed for independent correctness
    # verification (report.json alone only has summary stats).
    raw_path = samples_dir / f"{out_basename}_raw_questions.json"
    raw_path.write_text(json.dumps(topics_data, indent=2, default=str))
    print(f"Saved: {raw_path}")

    docgen = DocumentGenerator(template_path=None)
    docx_bytes = docgen.generate_full_assessment(
        topics_data=topics_data,
        total_marks=sum(m for _, m in TOPICS_MARKS),
        target_distribution=TARGET_DISTRIBUTION,
        **METADATA,
    )

    docx_path = samples_dir / f"{out_basename}.docx"
    docx_path.write_bytes(docx_bytes)
    print(f"Saved: {docx_path}")

    report_path = samples_dir / f"{out_basename}_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"Saved: {report_path}")

    if combined_errors:
        print(f"\n⚠ {len(combined_errors)} slot(s) failed -- paper is {actual_total_marks}/"
              f"{sum(m for _, m in TOPICS_MARKS)} marks:")
        for e in combined_errors:
            print(f"  - {e}")

    print(f"\nConstructed (no archetype precedent) leaves: {leaf_detail['constructed_count']}")
    for d in leaf_detail["constructed_detail"]:
        print(f"  - {d}")
    print(f"Cognitive-level disagreements flagged: {leaf_detail['cognitive_mismatch_count']}")
    for d in leaf_detail["cognitive_mismatch_detail"]:
        print(f"  - {d}")

    print(f"\nWall clock: {wall_seconds}s")


if __name__ == "__main__":
    main()
