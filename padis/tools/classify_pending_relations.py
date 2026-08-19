"""Classify relation=pending rules into A/B/C buckets."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

RULES_PATH = Path("padis/outputs/padis_rules_raw.json")
OUT_JSON = Path("padis/outputs/pending_relation_classification.json")
OUT_MD = Path("padis/outputs/pending_relation_classification.md")


def normalize_pdf_text(text: str) -> str:
    t = (text or "").replace("\u00ad", "")
    t = re.sub(r"(\w)-\s+(\w)", r"\1\2", t)
    return re.sub(r"\s+", " ", t).strip().lower()

KNOWN_RELATIONS = {
    "increasesRiskOf",
    "decreasesRiskOf",
    "associatedWith",
    "preferredOver",
}

CLEAR_RELATION_CUES = [
    r"\bincreased\s+risk",
    r"\bincreases?\s+risk",
    r"\bassociated\s+with",
    r"\bpredicts?\s+(?:increased\s+)?risk",
    r"\bpredictor\b",
    r"\breduced\s+delirium",
    r"\bdecreased\s+(?:incidence|risk)",
    r"\blower\s+proportion",
    r"\bsignificantly\s+lower",
    r"\bprefer(?:able|red)\b",
    r"\brather\s+than\b",
    r"\bcompared\s+with\b.*\bdelirium\b",
    r"\bsignificant\s+reduction\s+in\s+delirium",
    r"\bassociation\s+with\s+delirium",
]

NO_CLEAR_RELATION_CUES = [
    r"^rationale:",
    r"^remarks:",
    r"^evidence gaps:",
    r"^conclusions:",
    r"^methods:",
    r"^results:",
    r"outcomes deemed",
    r"these included",
    r"these factors include",
    r"five rcts",
    r"delirium screening using",
    r"in the context of the criteria",
    r"received funding",
    r"clinical practice guidelines for",
    r"needs to be studied",
    r"remains unclear",
    r"is unknown",
    r"cannot fully elucidate",
    r"no relationship between delirium assessment",
    r"were similar between",
    r"not associated with a shorter",
]

CANDIDATE_MARKERS = [
    "requiresAssessmentOf",
    "shouldBeTreatedBefore",
    "sequencing",
    "treat before",
]


def has_regex(sl: str, patterns: List[str]) -> bool:
    return any(re.search(p, sl) for p in patterns)


def classify_rule(r: dict) -> Tuple[str, str]:
    if r.get("relation") != "pending":
        return "typed", "already typed"

    sl = normalize_pdf_text(r.get("source_text") or "")
    cand = (r.get("relation_candidate") or "").lower()

    if "null_effect_or_gap" in cand:
        return "B", "null-effect/gap; pending relation appropriate"

    if any(m.lower() in cand for m in CANDIDATE_MARKERS):
        return "C", "relation_candidate / sequencing or non-vocab pattern"

    if has_regex(sl, NO_CLEAR_RELATION_CUES):
        return "B", "descriptive/meta/rationale; pending appropriate"

    if has_regex(sl, CLEAR_RELATION_CUES):
        return "A", "clear directional/comparative cue but relation pending"

    # comparative delirium without explicit cue match
    if "delirium" in sl and ("compared with" in sl or "compared to" in sl):
        if any(k in sl for k in ["benefit", "rr", "reduction", "lower", "reduced"]):
            return "A", "comparative delirium outcome"

    if "association" in sl and "delirium" in sl:
        return "A", "association language present"

    return "B", "no clear subject-object relation claim"


def main() -> None:
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))["rules"]
    pending = [r for r in rules if r.get("relation") == "pending"]

    buckets: Dict[str, List[dict]] = {"A": [], "B": [], "C": []}
    reasons: Dict[str, Counter] = {"A": Counter(), "B": Counter(), "C": Counter()}

    for r in pending:
        cat, reason = classify_rule(r)
        if cat not in buckets:
            cat = "B"
        buckets[cat].append({**r, "_class_reason": reason})
        reasons[cat][reason] += 1

    out = {
        "total_rules": len(rules),
        "pending_count": len(pending),
        "counts": {k: len(v) for k, v in buckets.items()},
        "buckets": {
            k: [
                {
                    "rule_id": x["rule_id"],
                    "source_page": x["source_page"],
                    "source_type": x["source_type"],
                    "subject": x["subject"],
                    "relation_candidate": x.get("relation_candidate"),
                    "source_text": x["source_text"][:220],
                    "reason": x["_class_reason"],
                }
                for x in v[:8]
            ]
            for k, v in buckets.items()
        },
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    md: List[str] = [
        "# Pending relation classification",
        "",
        f"- total rules: {len(rules)}",
        f"- relation=pending: {len(pending)}",
        f"- A (clear but pending): {len(buckets['A'])}",
        f"- B (pending appropriate): {len(buckets['B'])}",
        f"- C (relation_candidate): {len(buckets['C'])}",
        "",
    ]
    for cat in ["A", "B", "C"]:
        md.append(f"## Category {cat} ({len(buckets[cat])})")
        for ex in buckets[cat][:5]:
            md.append(
                f"- **{ex['rule_id']}** (p{ex['source_page']}, {ex['source_type']}): {ex['source_text'][:160]}..."
            )
            md.append(f"  - reason: {ex['_class_reason']}")
        md.append("")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"[pending] A={len(buckets['A'])} B={len(buckets['B'])} C={len(buckets['C'])} -> {OUT_MD}")


if __name__ == "__main__":
    main()
