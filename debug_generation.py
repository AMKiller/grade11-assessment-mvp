#!/usr/bin/env python3
"""
Debug script: test generation with real Claude API to identify failures.
Usage: ANTHROPIC_API_KEY=sk-ant-... python3 debug_generation.py
"""

import os
from generation import QuestionGenerator

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("❌ ANTHROPIC_API_KEY not set")
    exit(1)

print("Testing Claude API generation...")
print(f"API Key: {api_key[:20]}...")

try:
    gen = QuestionGenerator("Equations and Inequalities", api_key=api_key)
    gen.select_archetypes(num_questions=2, prefer_core=True)

    print(f"\n✓ Selected {len(gen.selected_archetypes)} archetypes:")
    for arch in gen.selected_archetypes:
        print(f"  - {arch.archetype_id}: {arch.name}")

    print("\nGenerating questions...")
    for i, arch in enumerate(gen.selected_archetypes, 1):
        print(f"\n  Question {i}/{len(gen.selected_archetypes)} ({arch.archetype_id})...")
        q = gen.generate_question(arch.archetype_id, max_retries=2)
        if q:
            print(f"    ✓ Generated: {q.question_text[:50]}...")
            print(f"    ✓ Answer: {q.answer_text}")
            print(f"    ✓ Verified: {q.sympy_verified}")
        else:
            print(f"    ❌ Failed after retries")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
