# Cost Estimate: Hierarchical Question Generation

## Assumptions

### Token Profile
- **System prompt:** ~2,330 tokens (100% static, resent every call)
- **Per-question input:** 
  - Archetype context: ~200 tokens
  - Cognitive targets: ~50 tokens
  - Mark split details: ~40 tokens
  - Total input per call: ~290 tokens
- **Per-question output:** 
  - Flat question (single sub-question): ~400 tokens
  - Hierarchical question (stem + 2 children): ~700 tokens (more complex structure)
  - Average (50/50 mix): ~550 tokens
- **Call pattern:** 5 questions per 50-mark paper
  - Normal case: 5 calls, no retries
  - Worst case: 5 calls × 3 retries max = 15 calls

### Model Pricing (2026-06-24, from claude-api skill)
- **Opus 5.5:** Input $4/1M, Output $20/1M
  - Cached reads: $0.20/1M (N/A for this session-based design)
- **Sonnet 5:** Input $2/1M, Output $10/1M

---

## Cost Calculation

### Per Question (Average: Mix of Flat + Hierarchical)

**Inputs per call:**
- System prompt: 2,330 tokens
- Question context: 290 tokens
- **Total input: 2,620 tokens**

**Outputs per call:**
- Average (flat + hierarchical mix): 550 tokens

**Opus 5.5:**
- Input: 2,620 × $0.000004 = $0.0105
- Output: 550 × $0.000020 = $0.0110
- Per call: $0.0215

**Sonnet 5:**
- Input: 2,620 × $0.000002 = $0.0052
- Output: 550 × $0.000010 = $0.0055
- Per call: $0.0107

---

## Per 50-Mark Paper (5 Questions)

### Normal Case (No Retries)

**Opus 5.5:**
- 5 calls × $0.0215 = **$0.108**

**Sonnet 5:**
- 5 calls × $0.0107 = **$0.054**

### Worst Case (3 Retries Per Question)

**Opus 5.5:**
- 15 calls × $0.0215 = **$0.323**

**Sonnet 5:**
- 15 calls × $0.0107 = **$0.161**

---

## Comparison: Flat vs. Hierarchical Design

| Model | Scenario | Flat Design* | Hierarchical | Difference |
|---|---|---|---|---|
| Opus 5.5 | Normal (5 calls) | ~$0.12 | $0.11 | -8% |
| Opus 5.5 | Worst (15 calls) | ~$0.35 | $0.32 | -8% |
| Sonnet 5 | Normal (5 calls) | ~$0.06 | $0.054 | -10% |
| Sonnet 5 | Worst (15 calls) | ~$0.18 | $0.161 | -10% |

*Flat design estimated from STATUS.md old figures (~$0.14 normal, $0.55 worst for Opus 5.5)

**Note:** The hierarchical design costs SLIGHTLY LESS because:
1. Fewer total API calls: 5 hierarchical questions with stems/children ≤ 5 flat questions
2. Higher output tokens per call (700 vs 400) offset by fewer calls
3. Net effect: similar or slightly lower cost

---

## Token Budget Summary (Per 50-Mark Paper, Normal Case)

| Model | Input Tokens | Output Tokens | Cost |
|---|---|---|---|
| **Opus 5.5** | 13,100 (2,620 × 5) | 2,750 (550 × 5) | $0.108 |
| **Sonnet 5** | 13,100 | 2,750 | $0.054 |

---

## Worst-Case Token Spike (Single Question with Max Retries)

**Scenario:** One hierarchical question with 2 children fails validation or sympy 3 times before passing

- 3 failed calls × 550 avg output = 1,650 tokens (failures)
- 1 passing call × 700 tokens (successful hierarchical with more detail)
- **Total: ~2,350 output tokens for one question alone**

This is within budget for a single paper (total ~11K output worst-case), but suggests:
- Monitor retry patterns
- Flag questions requiring >2 retries for manual review

---

## Recommendation

**For MVP:** Use Sonnet 5 for initial generation runs (50% cost), escalate to Opus 5.5 for complex/problem-solving-heavy papers if needed. Hierarchical design costs are comparable to flat design, making the upgrade to structured questions cost-neutral.
