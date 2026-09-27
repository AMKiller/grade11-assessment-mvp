import json
import random
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Archetype:
    archetype_id: str
    name: str
    description: str
    evidence_count: int
    cognitive_level_distribution: dict
    marking_pattern: dict
    language_notes: str
    source_examples: list
    usage_tier: str
    frequency_cap: int | None = None
    low_evidence: bool = False


class KnowledgeBase:
    def __init__(self):
        self.topics = {}
        # Set by sample_by_cognitive_distribution() on every call -- read it
        # right after calling to see whether archetype reuse was forced (pool
        # exhausted) or a named sub-topic had to be swapped in for coverage.
        # A plain instance attribute, not a return value, so the sampling
        # method's return type (list[Archetype]) stays unchanged for existing
        # callers/tests. See generate_paper()'s "diversity_diagnostics".
        self.last_sampling_diagnostics = {}
        self._load_kbs()

    def _load_kbs(self):
        base_path = Path(__file__).parent

        kbs = [
            ("Equations and Inequalities", "grade11_equations_and_inequalities_knowledge_base.json"),
            ("Exponents and Surds", "grade11_exponents_and_surds_knowledge_base.json"),
        ]

        for topic_name, filename in kbs:
            with open(base_path / filename, "r") as f:
                data = json.load(f)
                self.topics[topic_name] = {
                    "grade": data["grade"],
                    "archetypes": self._parse_archetypes(data["archetypes"]),
                    "raw": data
                }

    def _parse_archetypes(self, archetypes_list):
        parsed = []
        for arch in archetypes_list:
            usage_guidance = arch.get("usage_guidance", {})
            tier = usage_guidance.get("tier", "supplementary")
            frequency_cap = usage_guidance.get("frequency_cap", None)

            parsed.append(Archetype(
                archetype_id=arch["archetype_id"],
                name=arch["name"],
                description=arch["description"],
                evidence_count=arch["evidence_count"],
                cognitive_level_distribution=arch["cognitive_level_distribution"],
                marking_pattern=arch["marking_pattern"],
                language_notes=arch.get("language_notes", ""),
                source_examples=arch.get("source_examples", []),
                usage_tier=tier,
                frequency_cap=frequency_cap,
                low_evidence=arch.get("low_evidence", False)
            ))
        return parsed

    def get_archetypes(self, topic: str, tier_filter: list[str] = None):
        """
        Get archetypes for a topic, optionally filtered by usage tier.

        Args:
            topic: "Equations and Inequalities" or "Exponents and Surds"
            tier_filter: None (all tiers) or list of tier names to include
                        (e.g. ["core", "supplementary"])

        Returns:
            List of Archetype objects
        """
        if topic not in self.topics:
            raise ValueError(f"Topic '{topic}' not found. Available: {list(self.topics.keys())}")

        archetypes = self.topics[topic]["archetypes"]

        if tier_filter is None:
            return archetypes
        return [a for a in archetypes if a.usage_tier in tier_filter]

    def get_archetype(self, topic: str, archetype_id: str):
        """Get a specific archetype by ID."""
        for arch in self.get_archetypes(topic):
            if arch.archetype_id == archetype_id:
                return arch
        raise ValueError(f"Archetype '{archetype_id}' not found in topic '{topic}'")

    def sample_by_cognitive_distribution(self, topic: str,
                                        num_archetypes: int,
                                        target_distribution: dict = None,
                                        tier_filter: list[str] = None,
                                        seed: int = None):
        """
        Sample archetypes from a topic to approximate a cognitive distribution.

        Args:
            topic: Topic name
            num_archetypes: Number of archetypes to select
            target_distribution: Dict with keys 'knowledge', 'routine', 'complex', 'problem_solving'
                                 representing percentages. If None, uses balanced CAPS targets:
                                 {'knowledge': 20, 'routine': 35, 'complex': 30, 'problem_solving': 15}
            tier_filter: Tier names to restrict sampling to (e.g. ["core"] for production,
                        ["core", "supplementary"] for a more varied assessment)
            seed: Random seed for reproducibility

        Returns:
            List of selected Archetype objects
        """
        if seed is not None:
            random.seed(seed)

        if target_distribution is None:
            target_distribution = {
                'knowledge': 20,
                'routine': 35,
                'complex': 30,
                'problem_solving': 15
            }

        archetypes = self.get_archetypes(topic, tier_filter)
        if not archetypes:
            raise ValueError(f"No archetypes found for topic '{topic}' with tier filter {tier_filter}")

        selected = []
        forced_reuse_ids = []
        for _ in range(num_archetypes):
            target_level = self._pick_level_by_distribution(target_distribution)
            candidates = [a for a in archetypes
                         if a.cognitive_level_distribution.get(target_level, 0) > 0
                         and a not in selected]

            if not candidates:
                candidates = [a for a in archetypes if a not in selected]

            if not candidates:
                # Pool genuinely exhausted (num_archetypes > available
                # archetypes for this tier_filter) -- reuse is now
                # unavoidable. Allow it, but record exactly which archetype
                # had to repeat rather than silently under-supplying (the
                # old behaviour: this iteration would just contribute
                # nothing, quietly returning fewer archetypes than asked
                # for). See last_sampling_diagnostics.
                candidates = archetypes

            if candidates:
                choice = random.choice(candidates)
                if choice in selected:
                    forced_reuse_ids.append(choice.archetype_id)
                selected.append(choice)

        selected, subtopic_notes = self._ensure_subtopic_coverage(
            topic, selected, archetypes, target_distribution
        )

        self.last_sampling_diagnostics = {
            "forced_reuse_archetype_ids": forced_reuse_ids,
            "subtopic_coverage_swaps": subtopic_notes,
        }
        return selected

    def _ensure_subtopic_coverage(self, topic: str, selected: list,
                                 pool: list, target_distribution: dict) -> tuple:
        """
        Guard against a named sub-topic (e.g. "Inequalities" within
        "Equations and Inequalities") going entirely unrepresented by chance,
        even though the pool has dedicated archetypes for it. Sub-topics are
        derived generically from the topic name itself (split on " and "/
        "&"), not hardcoded to one topic -- so this applies the same way to
        "Exponents and Surds" -> ["Exponents", "Surds"].

        For each sub-topic keyword with no selected archetype whose name/
        description mentions it, and at least one unselected archetype in
        the pool that does, swaps one in for the selected archetype with the
        least cognitive-level overlap with the replacement (so the paper's
        planned K/R/C/PS balance is disturbed as little as possible).

        Returns (possibly-modified selected list, list of human-readable
        swap notes for reporting -- e.g. "swapped X for Y to cover
        'Inequalities'").
        """
        import re
        parts = [p.strip() for p in re.split(r"\s+and\s+|&", topic, flags=re.IGNORECASE) if p.strip()]
        if len(parts) < 2:
            return selected, []

        def singular_candidates(word: str) -> set:
            """Naive plural->singular variants, e.g. 'Inequalities' -> also
            tries 'inequality' (handles the -ies->-y irregular case that a
            plain rstrip('s') gets wrong: 'inequalities'.rstrip('s') would
            give 'inequalitie', not 'inequality')."""
            wl = word.lower()
            cands = {wl}
            if wl.endswith("ies"):
                cands.add(wl[:-3] + "y")
            if wl.endswith("s"):
                cands.add(wl[:-1])
            return cands

        notes = []
        for keyword in parts:
            kw_variants = singular_candidates(keyword)

            def mentions(a, variants=kw_variants):
                text = (a.name + " " + a.description).lower()
                return any(v in text for v in variants)

            if any(mentions(a) for a in selected):
                continue  # already covered

            replacement_candidates = [a for a in pool if mentions(a) and a not in selected]
            if not replacement_candidates:
                continue  # no dedicated archetype exists for this sub-topic at all

            replacement = random.choice(replacement_candidates)

            # Replace whichever selected archetype shares the LEAST cognitive
            # -level overlap with the replacement, to minimize disruption to
            # the already-chosen K/R/C/PS mix.
            def overlap(a):
                return sum(1 for lvl, v in a.cognitive_level_distribution.items()
                          if v > 0 and replacement.cognitive_level_distribution.get(lvl, 0) > 0)

            victim = min(selected, key=overlap) if selected else None
            if victim is None:
                continue

            idx = selected.index(victim)
            selected[idx] = replacement
            notes.append(
                f"swapped {victim.archetype_id} for {replacement.archetype_id} "
                f"to cover named sub-topic '{keyword}' (had no representation)"
            )

        return selected, notes

    def _pick_level_by_distribution(self, distribution: dict) -> str:
        """Pick a cognitive level based on target percentages."""
        total = sum(distribution.values())
        r = random.uniform(0, total)
        cumulative = 0
        for level, weight in distribution.items():
            cumulative += weight
            if r <= cumulative:
                return level
        return "routine"

    def validate_archetypes(self, topic: str, archetype_ids: list[str]) -> list[str]:
        """
        Check which archetype IDs exist in a topic.

        Returns:
            List of IDs that exist (for quick validation before generation)
        """
        valid = []
        try:
            archetypes = self.get_archetypes(topic)
            existing_ids = {a.archetype_id for a in archetypes}
            valid = [aid for aid in archetype_ids if aid in existing_ids]
        except ValueError:
            pass
        return valid
