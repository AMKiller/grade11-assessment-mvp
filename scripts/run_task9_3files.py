#!/usr/bin/env python3
"""
Task 9's exact 3-topic, 50-mark, uneven-split configuration (Equations and
Inequalities 20 / Exponents and Surds 15 / Trigonometry 15), re-run through
the same generate_paper() path the real app.py UI uses, but now producing
THREE separate deliverable files (question paper .docx, marking guide .docx,
cognitive grid .xlsx) instead of one combined .docx -- the new baseline for
the separate-prompt-caching test to come.

Usage:
    ANTHROPIC_API_KEY=... [GENERATION_MODEL=claude-opus-5-5] \
        python3 scripts/run_task9_3files.py task9_opus55_low_3files
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

TOPICS_MARKS = [
    ("Equations and Inequalities", 20),
    ("Exponents and Surds", 15),
    ("Trigonometry (reduction formulae, trig equations & general solutions)", 15),
]
NUM_QUESTIONS_PER_TOPIC = 5
TARGET_DISTRIBUTION = {"knowledge": 20, "routine": 35, "complex": 30, "problem_solving": 15}

PRICING = {
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00},
}

METADATA = dict(
    task="Task 9",
    term="Term 3 2026",
    time_minutes=90,
    examiner="AE Killer",
    moderator="D Piters",
    grade="11",
)


def collect_leaf_detail(topics_data: list) -> dict:
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
        print("Usage: run_task9_3files.py <output_basename>", file=sys.stderr)
        sys.exit(1)

    out_basename = sys.argv[1]
    thinking_desc = (
        f"effort={GENERATION_EFFORT} (thinking cannot be disabled on this model)"
        if GENERATION_MODEL in MODELS_WITHOUT_DISABLED_THINKING
        else f"thinking_mode={GENERATION_THINKING_MODE}, effort={GENERATION_EFFORT or '(unset)'}"
    )
    print(f"=== Task 9 3-file baseline run -- model={GENERATION_MODEL}, {thinking_desc}, "
          f"max_tokens={GENERATION_MAX_TOKENS} ===\n")

    topics_data = []
    combined_usage_log = []
    combined_errors = []
    all_questions = []

    import time as _time
    wall_start = _time.time()

    for topic, marks in TOPICS_MARKS:
        print(f"--- Generating topic: {topic} (target {marks} marks) ---")
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
        print(f"  -> {result['num_questions']} questions, {result['total_marks']} marks\n")

    wall_clock_seconds = round(_time.time() - wall_start, 1)

    question_groups = [(i + 1, qs) for i, (_, qs) in enumerate(topics_data)]
    actual_total_marks = _compute_actual_marks(question_groups)

    usage_summary = _summarize_usage(combined_usage_log)
    usage_summary["wall_clock_seconds"] = wall_clock_seconds
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

    requested_total = sum(m for _, m in TOPICS_MARKS)

    report = {
        "model": GENERATION_MODEL,
        "thinking_mode": GENERATION_THINKING_MODE,
        "effort_applied": (
            (GENERATION_EFFORT or "low") if GENERATION_MODEL in MODELS_WITHOUT_DISABLED_THINKING
            else (GENERATION_EFFORT if GENERATION_THINKING_MODE != "disabled" and GENERATION_EFFORT else None)
        ),
        "max_tokens": GENERATION_MAX_TOKENS,
        "deliverable_structure": "3 separate files (QP .docx, MG .docx, grid .xlsx) -- new baseline, not the old combined-file format",
        "topics": [t for t, _ in TOPICS_MARKS],
        "marks_per_topic": {t: m for t, m in TOPICS_MARKS},
        "num_questions_per_topic": NUM_QUESTIONS_PER_TOPIC,
        "actual_total_marks": actual_total_marks,
        "requested_total_marks": requested_total,
        "usage": usage_summary,
        "cognitive_distribution": cognitive,
        "verification": leaf_detail,
        "generation_errors": combined_errors,
        "raw_usage_log": combined_usage_log,
    }

    print("\n=== REPORT (summary) ===")
    print(json.dumps({k: v for k, v in report.items() if k not in ("raw_usage_log", "verification")}, indent=2, default=str))

    # --- Document generation: 3 separate files ---
    docgen = DocumentGenerator(template_path=None)
    qp_bytes = docgen.generate_question_paper(
        topics_data=topics_data,
        total_marks=requested_total,
        **METADATA,
    )
    mg_bytes = docgen.generate_marking_guide(
        topics_data=topics_data,
        total_marks=requested_total,
        task=METADATA["task"],
        term=METADATA["term"],
        grade=METADATA["grade"],
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
              f"{requested_total} marks:")
        for e in combined_errors:
            print(f"  - {e}")
    else:
        print(f"\n✓ No generation errors. {actual_total_marks}/{requested_total} marks. "
              f"Cost: ${usage_summary['cost_usd']}, wall clock: {wall_clock_seconds}s")


if __name__ == "__main__":
    main()
