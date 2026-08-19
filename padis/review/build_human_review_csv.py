"""Build a human-review-friendly CSV from padis_rules_raw.json.

The CSV is meant for manual PADIS verification:
  approve / revise_approve / reject / defer

Does NOT auto-approve rules or build KG.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
DEFAULT_RULES = REPO / "padis/outputs/padis_rules_raw.json"
DEFAULT_GOLD = REPO / "padis/rules/gold_set_smoke.json"
DEFAULT_OUT = REPO / "padis/outputs/padis_rules_human_review.csv"
DEFAULT_LEGACY = REPO / "padis/outputs/padis_rules_review.csv"

REVIEW_COLUMNS = [
    "review_priority",
    "rule_id",
    "source_page",
    "source_text",
    "auto_source_type",
    "auto_subject",
    "auto_relation",
    "auto_object",
    "auto_negation_present",
    "relation_candidate",
    "in_gold_set",
    "review_decision",
    "approved?",
    "corrected_source_type",
    "corrected_subject",
    "corrected_relation",
    "corrected_object",
    "corrected_negation_present",
    "kg_edge_candidate",
    "mimic_availability",
    "experiment_usable",
    "reviewer_note",
    "rejection_reason",
    # reference / traceability (keep at end)
    "padis_domain",
    "source_section",
    "patient_population",
    "required_clinical_variables",
    "confidence",
    "review_status",
]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _truthy(v: Any) -> bool:
    return str(v or "").strip().lower() in {"yes", "y", "true", "1"}


def _load_gold_sentences(gold_path: Path) -> set[str]:
    if not gold_path.exists():
        return set()
    doc = json.loads(gold_path.read_text(encoding="utf-8"))
    gold_set = doc.get("gold_set", doc if isinstance(doc, list) else [])
    return {norm(g.get("sentence", "")) for g in gold_set if g.get("sentence")}


def _load_existing_review(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_id: Dict[str, dict] = {}
    for row in rows:
        rid = row.get("rule_id")
        if rid:
            by_id[rid] = row
    return by_id


def _review_priority(rule: dict) -> str:
    st = rule.get("source_type") or "pending"
    rel = rule.get("relation") or "pending"
    text = norm(rule.get("source_text") or "")

    meta_cues = [
        "received funding",
        "methods:",
        "results:",
        "objective:",
        "clinical practice guidelines for",
        "www.ccmjournal.org",
        "rationale: the outcomes deemed",
    ]
    if any(c in text for c in meta_cues):
        return "low"

    if st == "recommendation":
        return "high"
    if rel != "pending":
        return "high"
    if st in {"evidence", "no_recommendation", "risk_factor_statement"}:
        return "medium"
    if st == "research_gap":
        return "medium"
    return "low"


def _kg_edge_candidate(rule: dict) -> str:
    rel = rule.get("relation") or "pending"
    st = rule.get("source_type") or "pending"
    if rel == "pending":
        return "no"
    if st in {"research_gap", "pending"}:
        return "no"
    if st in {"recommendation", "evidence", "risk_factor_statement", "no_recommendation"}:
        return "maybe"
    return "undecided"


def _merge_existing(row: dict, existing: Optional[dict]) -> dict:
    if not existing:
        return row

    # Preserve prior reviewer work from legacy or human review CSV.
    for key in [
        "review_decision",
        "approved?",
        "corrected_source_type",
        "corrected_subject",
        "corrected_relation",
        "corrected_object",
        "corrected_negation_present",
        "reviewer_note",
        "rejection_reason",
        "kg_edge_candidate",
        "mimic_availability",
        "experiment_usable",
        "review_status",
    ]:
        if existing.get(key):
            row[key] = existing[key]

    # Legacy CSV used subject/relation/object/source_type without auto_ prefix.
    if not row.get("corrected_subject") and existing.get("corrected_subject"):
        row["corrected_subject"] = existing["corrected_subject"]
    if not row.get("corrected_relation") and existing.get("corrected_relation"):
        row["corrected_relation"] = existing["corrected_relation"]
    if not row.get("corrected_object") and existing.get("corrected_object"):
        row["corrected_object"] = existing["corrected_object"]
    return row


def build_rows(rules: List[dict], gold_sentences: set[str], existing_by_id: Dict[str, dict]) -> List[dict]:
    rows: List[dict] = []
    for r in rules:
        rid = r.get("rule_id")
        source_text = r.get("source_text") or ""
        row = {
            "review_priority": _review_priority(r),
            "rule_id": rid,
            "source_page": r.get("source_page"),
            "source_text": source_text,
            "auto_source_type": r.get("source_type"),
            "auto_subject": r.get("subject"),
            "auto_relation": r.get("relation"),
            "auto_object": r.get("object"),
            "auto_negation_present": r.get("negation_present"),
            "relation_candidate": r.get("relation_candidate"),
            "in_gold_set": "yes" if norm(source_text) in gold_sentences else "no",
            "review_decision": "",
            "approved?": "",
            "corrected_source_type": "",
            "corrected_subject": "",
            "corrected_relation": "",
            "corrected_object": "",
            "corrected_negation_present": "",
            "kg_edge_candidate": _kg_edge_candidate(r),
            "mimic_availability": r.get("mimic_availability") or "undecided",
            "experiment_usable": r.get("experiment_usable") or "no",
            "reviewer_note": r.get("reviewer_note") or "",
            "rejection_reason": r.get("rejection_reason") or "",
            "padis_domain": r.get("padis_domain"),
            "source_section": r.get("source_section"),
            "patient_population": r.get("patient_population"),
            "required_clinical_variables": ",".join(r.get("required_clinical_variables") or []),
            "confidence": r.get("confidence"),
            "review_status": r.get("review_status") or "pending",
        }
        prior = existing_by_id.get(rid) or existing_by_id.get(rid or "")
        rows.append(_merge_existing(row, prior))

    priority_order = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda x: (priority_order.get(x["review_priority"], 9), int(x.get("source_page") or 0), x["rule_id"]))
    return rows


def write_csv(rows: List[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def write_legacy_csv(rows: List[dict], out_path: Path) -> None:
    """Backward-compatible CSV for approve_rules.py."""
    legacy_cols = [
        "rule_id",
        "padis_domain",
        "source_page",
        "source_section",
        "source_text",
        "patient_population",
        "subject",
        "relation",
        "relation_candidate",
        "object",
        "recommendation_strength",
        "evidence_quality",
        "source_type",
        "required_clinical_variables",
        "mimic_availability",
        "confidence",
        "review_status",
        "approved?",
        "corrected_subject",
        "corrected_relation",
        "corrected_object",
        "reviewer_note",
        "experiment_usable",
        "negation_present",
        "rejection_reason",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=legacy_cols, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(
                {
                    "rule_id": row["rule_id"],
                    "padis_domain": row["padis_domain"],
                    "source_page": row["source_page"],
                    "source_section": row["source_section"],
                    "source_text": row["source_text"],
                    "patient_population": row["patient_population"],
                    "subject": row["auto_subject"],
                    "relation": row["auto_relation"],
                    "relation_candidate": row["relation_candidate"],
                    "object": row["auto_object"],
                    "recommendation_strength": "pending",
                    "evidence_quality": "pending",
                    "source_type": row["auto_source_type"],
                    "required_clinical_variables": row["required_clinical_variables"],
                    "mimic_availability": row["mimic_availability"],
                    "confidence": row["confidence"],
                    "review_status": row["review_status"],
                    "approved?": row.get("approved?") or "",
                    "corrected_subject": row.get("corrected_subject") or "",
                    "corrected_relation": row.get("corrected_relation") or "",
                    "corrected_object": row.get("corrected_object") or "",
                    "reviewer_note": row.get("reviewer_note") or "",
                    "experiment_usable": row.get("experiment_usable") or "no",
                    "negation_present": row.get("auto_negation_present"),
                    "rejection_reason": row.get("rejection_reason") or "",
                }
            )


def main() -> None:
    ap = argparse.ArgumentParser(description="Build human review CSV from extracted PADIS rules")
    ap.add_argument("--rules-json", type=Path, default=DEFAULT_RULES)
    ap.add_argument("--gold-json", type=Path, default=DEFAULT_GOLD)
    ap.add_argument("--out-csv", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--legacy-csv", type=Path, default=DEFAULT_LEGACY)
    ap.add_argument("--preserve-from", type=Path, default=DEFAULT_OUT, help="Existing review CSV to preserve edits")
    args = ap.parse_args()

    if not args.rules_json.exists():
        raise SystemExit(f"Missing rules JSON: {args.rules_json}")

    rules = json.loads(args.rules_json.read_text(encoding="utf-8")).get("rules", [])
    gold_sentences = _load_gold_sentences(args.gold_json)

    existing: Dict[str, dict] = {}
    if args.preserve_from.exists():
        existing.update(_load_existing_review(args.preserve_from))
    if args.legacy_csv.exists():
        existing.update(_load_existing_review(args.legacy_csv))

    rows = build_rows(rules, gold_sentences, existing)
    write_csv(rows, args.out_csv)
    write_legacy_csv(rows, args.legacy_csv)

    pri = {"high": 0, "medium": 0, "low": 0}
    kg = {"maybe": 0, "no": 0, "undecided": 0}
    for r in rows:
        pri[r["review_priority"]] += 1
        kg[r["kg_edge_candidate"]] = kg.get(r["kg_edge_candidate"], 0) + 1

    summary = {
        "generated_at": datetime.now().isoformat(),
        "total_rules": len(rows),
        "review_priority": pri,
        "kg_edge_candidate": kg,
        "in_gold_set_yes": sum(1 for r in rows if r["in_gold_set"] == "yes"),
        "human_review_csv": str(args.out_csv),
        "legacy_review_csv": str(args.legacy_csv),
    }
    summary_path = args.out_csv.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[human-review] wrote {len(rows)} rows -> {args.out_csv}")
    print(f"[human-review] legacy csv -> {args.legacy_csv}")
    print(f"[human-review] priority: {pri} | kg_edge_candidate: {kg} | in_gold_set: {summary['in_gold_set_yes']}")


if __name__ == "__main__":
    main()
