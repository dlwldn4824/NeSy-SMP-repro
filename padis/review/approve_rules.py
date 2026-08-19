from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Optional


def _truthy(v: str) -> bool:
    if v is None:
        return False
    s = str(v).strip().lower()
    return s in {"yes", "y", "true", "1", "approve", "revise_approve", "revised_approve"}


def _pick(row: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return default


def _should_approve(row: dict) -> bool:
    if _truthy(row.get("approved?")):
        return True
    decision = _pick(row, "review_decision").lower()
    return decision in {"approve", "revise_approve", "revised_approve"}


def _to_list_or_empty(v: str) -> list[str]:
    if v is None:
        return []
    s = str(v).strip()
    if not s:
        return []
    # CSV uses comma join for required_clinical_variables
    return [x.strip() for x in s.split(",") if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review-csv", type=Path, required=True)
    ap.add_argument("--out-approved", type=Path, default=Path("padis/outputs/padis_rules_approved.json"))
    args = ap.parse_args()

    out = {"generated_at": None, "approved_rules": []}
    approved: list[Dict[str, Any]] = []

    with args.review_csv.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if not _should_approve(row):
                continue

            rule_id = row.get("rule_id")
            subject = _pick(row, "corrected_subject", "auto_subject", "subject")
            relation = _pick(row, "corrected_relation", "auto_relation", "relation")
            obj = _pick(row, "corrected_object", "auto_object", "object")
            source_type = _pick(row, "corrected_source_type", "auto_source_type", "source_type")
            neg_raw = _pick(row, "corrected_negation_present", "auto_negation_present", "negation_present")

            approved.append(
                {
                    "rule_id": rule_id,
                    "padis_domain": row.get("padis_domain"),
                    "source_page": int(row.get("source_page") or 0),
                    "source_section": row.get("source_section"),
                    "source_text": row.get("source_text"),
                    "patient_population": row.get("patient_population"),
                    "subject": subject,
                    "relation": relation,
                    "relation_candidate": row.get("relation_candidate"),
                    "object": obj,
                    "recommendation_strength": row.get("recommendation_strength") or "pending",
                    "evidence_quality": row.get("evidence_quality") or "pending",
                    "source_type": source_type,
                    "required_clinical_variables": _to_list_or_empty(row.get("required_clinical_variables") or ""),
                    "mimic_availability": row.get("mimic_availability") or "undecided",
                    "confidence": float(row.get("confidence") or 0.0),
                    "review_status": "approved",
                    "reviewer_note": row.get("reviewer_note") or "",
                    "experiment_usable": row.get("experiment_usable") or "undecided",
                    "negation_present": _truthy(neg_raw),
                    "rejection_reason": row.get("rejection_reason") or None,
                    "kg_edge_candidate": _pick(row, "kg_edge_candidate", default="undecided"),
                }
            )

    from datetime import datetime

    out["generated_at"] = datetime.now().isoformat()
    out["approved_rules"] = approved
    args.out_approved.parent.mkdir(parents=True, exist_ok=True)
    args.out_approved.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[PADIS approve] approved rules: {len(approved)} -> {args.out_approved}")


if __name__ == "__main__":
    main()

