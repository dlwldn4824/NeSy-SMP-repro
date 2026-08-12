from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


_POLARITY_PREFIX = {
    "high": "High",
    "low": "Low",
    "trend_nondecreasing_above": "",  # use explicit predicate if given
}


def _pascal(name: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def concept_to_predicate_name(
    concept_id: str,
    polarity: Optional[str] = None,
    explicit: Optional[str] = None,
) -> str:
    """
    SNOMED/concept + state → FOL predicate name.
    e.g. Lactate + high → HighLactate
    """
    if explicit:
        return explicit
    if concept_id in ("Death", "Mortality"):
        return "HighMortality"
    prefix = _POLARITY_PREFIX.get((polarity or "").lower(), "")
    base = _pascal(concept_id)
    if prefix and not base.startswith(prefix):
        return f"{prefix}{base}"
    return base


def compile_predicates(concepts_path: str | Path) -> List[Dict[str, Any]]:
    """Compile clinical_concepts.json → predicate specs consumed by LTN wiring."""
    with open(concepts_path, encoding="utf-8") as f:
        cfg = json.load(f)

    out: List[Dict[str, Any]] = []
    for c in cfg["concepts"]:
        if "predicate" not in c and c.get("roles") == ["Disease"]:
            continue
        pred = concept_to_predicate_name(
            c["id"], c.get("polarity"), c.get("predicate")
        )
        if pred is None:
            continue
        # skip pure disease nodes without risk/outcome role unless predicate set
        if "predicate" not in c and "RiskFactor" not in c.get("roles", []) and "Outcome" not in c.get("roles", []):
            continue
        out.append(
            {
                "concept_id": c["id"],
                "snomed_label": c.get("snomed_label", c["id"]),
                "snomed_id": c.get("snomed_id"),
                "aliases": c.get("aliases", []),
                "predicate": pred,
                "code_predicate": c.get("code_predicate", pred),
                "feature_name": c.get("feature_name"),
                "polarity": c.get("polarity"),
                "threshold": c.get("threshold"),
                "roles": c.get("roles", []),
            }
        )
    return out


def link_mention_to_concept(
    text: str,
    concepts: List[dict],
    prefer_roles: Optional[List[str]] = None,
    exclude_ids: Optional[List[str]] = None,
) -> Optional[dict]:
    """Naive alias matching for guideline NER → SNOMED concept linking."""
    t = text.lower().strip()
    exclude = set(exclude_ids or [])
    best = None
    best_len = -1
    for c in concepts:
        if c["id"] in exclude:
            continue
        if prefer_roles and not any(r in c.get("roles", []) for r in prefer_roles):
            # still allow if no roles filter match later; soft preference via score
            role_bonus = 0
        else:
            role_bonus = 10 if prefer_roles else 0
        candidates = [c["id"], c.get("snomed_label", "")] + c.get("aliases", [])
        for a in candidates:
            if not a:
                continue
            al = a.lower()
            if al in t or (len(t) > 3 and t in al):
                score = len(al) + role_bonus
                if score > best_len:
                    best = c
                    best_len = score
    return best
