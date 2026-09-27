#!/usr/bin/env python3
"""
Real (non-mock) generation run: 2 topics x 5 questions, 50 marks total,
against the live Claude API. Writes the combined .docx/.pdf to samples/ and
prints a full usage/cognitive/verification report to stdout as JSON
(also saved as a sidecar .json next to the .docx).

Model AND thinking/effort config are controlled by env vars read by
generation.py at import time (GENERATION_MODEL, GENERATION_THINKING_MODE,
GENERATION_EFFORT, GENERATION_MAX_TOKENS) -- so this script must be invoked
once per configuration in a separate process.

Usage:
    ANTHROPIC_API_KEY=... [GENERATION_MODEL=claude-opus-5-5] \
        [GENERATION_THINKING_MODE=disabled] [GENERATION_EFFORT=low] \
        python3 scripts/run_real_generation.py <output_basename>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from generation import (
    generate_paper, GENERATION_MODEL, GENERATION_THINKING_MODE,
    GENERATION_EFFORT, GENERATION_MAX_TOKENS, MODELS_WITHOUT_DISABLED_THINKING,
    _analyze_cognitive_distribution, _summarize_usage,
)
from docgen import DocumentGenerator, _compute_actual_marks

TOPICS = ["Equations and Inequalities", "Exponents and Surds"]
MARKS_PER_TOPIC = 25  # 50 total split evenly across 2 topics
NUM_QUESTIONS_PER_TOPIC = 5
TARGET_DISTRIBUTION = {"knowledge": 20, "routine": 35, "complex": 30, "problem_solving": 15}

PRICING = {
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00},
}


def collect_leaf_detail(topics_data: list) -> dict:
    """
    Walk every generated leaf and record, per leaf: which archetype/topic it
    came from, its planned cognitive target (the slot-level dict fixed before
    generation -- see generate_paper()'s _planned_cognitive_targets tag) vs.
    its actual cognitive_level, verification outcome, and problem_type.
    """
    total_leaves = 0
    sympy_verified = 0
    manual_review = 0
    unverifiable = 0
    real_verification_failures = 0
    per_leaf = []
    unverifiable_detail = []
    failed_verification_detail = []

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
                    entry = {
                        "topic": topic,
                        "archetype_id": archetype_id,
                        "num": leaf.get("num"),
                        "marks": leaf.get("marks"),
                        "problem_type": problem_type,
                        "actual_cognitive_level": actual_level,
                        "planned_cognitive_targets": planned,
                        "sympy_verified": leaf.get("sympy_verified"),
                        "manual_review_required": leaf.get("manual_review_required"),
                    }
                    per_leaf.append(entry)

                    if problem_type == "unverifiable":
                        unverifiable += 1
                        unverifiable_detail.append({
                            "topic": topic,
                            "archetype_id": archetype_id,
                            "num": leaf.get("num"),
                            "marks": leaf.get("marks"),
                        })
                    if leaf.get("sympy_verified"):
                        sympy_verified += 1
                    if leaf.get("manual_review_required"):
                        manual_review += 1
                        if problem_type != "unverifiable":
                            real_verification_failures += 1
                            failed_verification_detail.append({
                                "topic": topic,
                                "archetype_id": archetype_id,
                                "problem_type": problem_type,
                                "sympy_error": leaf.get("sympy_error"),
                            })

    return {
        "total_leaves": total_leaves,
        "sympy_verified": sympy_verified,
        "manual_review_required": manual_review,
        "unverifiable_by_design": unverifiable,
        "real_verification_failures": real_verification_failures,
        "unverifiable_detail": unverifiable_detail,
        "failed_verification_detail": failed_verification_detail,
        "per_leaf": per_leaf,
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: run_real_generation.py <output_basename>", file=sys.stderr)
        sys.exit(1)

    out_basename = sys.argv[1]
    thinking_desc = (
        f"effort={GENERATION_EFFORT} (thinking cannot be disabled on this model)"
        if GENERATION_MODEL in MODELS_WITHOUT_DISABLED_THINKING
        else f"thinking_mode={GENERATION_THINKING_MODE}, effort={GENERATION_EFFORT or '(unset)'}"
    )
    print(f"=== Real generation run -- model={GENERATION_MODEL}, {thinking_desc}, "
          f"max_tokens={GENERATION_MAX_TOKENS} ===\n")

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

    # Single source of truth for the actual mark total -- same helper docgen
    # itself now uses, so the report and the printed document can never
    # disagree (see docgen.py's 2026-09-24 totals fix).
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
        "topics": TOPICS,
        "num_questions_per_topic": NUM_QUESTIONS_PER_TOPIC,
        "target_marks_per_topic": MARKS_PER_TOPIC,
        "actual_total_marks": actual_total_marks,
        "requested_total_marks": MARKS_PER_TOPIC * len(TOPICS),
        "usage": usage_summary,
        "cognitive_distribution": cognitive,
        "verification": leaf_detail,
        "generation_errors": combined_errors,
        "raw_usage_log": combined_usage_log,
    }

    print("\n=== REPORT (summary) ===")
    print(json.dumps({k: v for k, v in report.items() if k not in ("raw_usage_log", "verification")}, indent=2, default=str))
    print(json.dumps({"usage": usage_summary}, indent=2, default=str))

    # --- Document generation ---
    # Deliberately still builds/saves a document even when generation_errors
    # is non-empty, so all configurations in this comparison run are
    # visible side-by-side -- the app.py-level "don't silently ship a
    # partial paper" gate belongs in the teacher-facing UI, not this
    # internal comparison script. actual_total_marks is always correct
    # regardless (see docgen.py's fix), so a partial paper's document will
    # honestly show its own short total rather than the requested one.
    docgen = DocumentGenerator(template_path=None)
    requested_total = MARKS_PER_TOPIC * len(TOPICS)
    qp_bytes = docgen.generate_question_paper(
        topics_data=topics_data,
        total_marks=requested_total,
        task="Task",
        term="Term 2",
        time_minutes=90,
        grade="11",
    )
    mg_bytes = docgen.generate_marking_guide(
        topics_data=topics_data,
        total_marks=requested_total,
        task="Task",
        term="Term 2",
        grade="11",
    )
    grid_bytes = docgen.generate_cognitive_grid_xlsx(
        topics_data=topics_data,
        target_distribution=TARGET_DISTRIBUTION,
    )

    samples_dir = Path(__file__).parent.parent / "samples"
    samples_dir.mkdir(exist_ok=True)
    qp_path = samples_dir / f"{out_basename}.qp.docx"
    qp_path.write_bytes(qp_bytes)
    print(f"\nSaved: {qp_path}")
    mg_path = samples_dir / f"{out_basename}.mg.docx"
    mg_path.write_bytes(mg_bytes)
    print(f"Saved: {mg_path}")
    grid_path = samples_dir / f"{out_basename}.grid.xlsx"
    grid_path.write_bytes(grid_bytes)
    print(f"Saved: {grid_path}")

    report_path = samples_dir / f"{out_basename}_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"Saved: {report_path}")

    if combined_errors:
        print(f"\n⚠ {len(combined_errors)} slot(s) failed -- paper is {actual_total_marks}/"
              f"{MARKS_PER_TOPIC * len(TOPICS)} marks:")
        for e in combined_errors:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
