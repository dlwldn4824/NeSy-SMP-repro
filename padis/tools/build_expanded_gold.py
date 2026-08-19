"""Build expanded gold set (40 items) from PADIS rules + manual expected labels."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[2]
RULES_PATH = REPO / "padis/outputs/padis_rules_raw.json"
OUT_PATH = REPO / "padis/rules/gold_set_smoke.json"


def rule_text(rules: Dict[str, dict], rule_id: str) -> str:
    return rules[rule_id]["source_text"]


def page(rules: Dict[str, dict], rule_id: str) -> int:
    return int(rules[rule_id]["source_page"])


def main() -> None:
    rules_list = json.loads(RULES_PATH.read_text(encoding="utf-8"))["rules"]
    rules = {r["rule_id"]: r for r in rules_list}

    original: List[Dict[str, Any]] = json.loads(
        (REPO / "padis/rules/gold_set_smoke.json").read_text(encoding="utf-8")
    )["gold_set"]
    if len(original) != 15:
        # fallback: keep structure from known smoke set
        raise SystemExit(f"Expected 15 smoke items, got {len(original)}")

    for g in original:
        g["smoke_original"] = True
        g.setdefault("sentence_category", "mixed_smoke")

    smoke_cats = {
        "G-001": "comparative_outcome",
        "G-002": "recommendation",
        "G-003": "comparative_outcome",
        "G-004": "evidence",
        "G-005": "evidence",
        "G-006": "evidence",
        "G-007": "evidence",
        "G-008": "comparative_outcome",
        "G-009": "null_effect_negation",
        "G-010": "evidence",
        "G-011": "research_gap",
        "G-012": "null_effect_negation",
        "G-013": "null_effect_negation",
        "G-014": "research_gap",
        "G-015": "research_gap",
    }
    for g in original:
        g["sentence_category"] = smoke_cats.get(g["gold_id"], "mixed_smoke")

    new_items: List[Dict[str, Any]] = [
        {
            "gold_id": "G-016",
            "sentence_category": "recommendation",
            "rule_ref": "D-049",
            "expected_subject": "DexmedetomidineExposure",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "recommendation",
            "expected_negation_present": True,
        },
        {
            "gold_id": "G-017",
            "sentence_category": "recommendation",
            "rule_ref": "D-056",
            "expected_subject": "DexmedetomidineExposure",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "recommendation",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-018",
            "sentence_category": "recommendation",
            "rule_ref": "D-038",
            "expected_subject": "CAM_ICU",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "recommendation",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-019",
            "sentence_category": "recommendation",
            "rule_ref": "D-012",
            "expected_subject": "OpioidExposure",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "recommendation",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-020",
            "sentence_category": "evidence",
            "rule_ref": "D-029",
            "expected_subject": "BenzodiazepineExposure",
            "expected_relation": "associatedWith",
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-021",
            "sentence_category": "null_effect_negation",
            "rule_ref": "D-034",
            "expected_subject": "MechanicalVentilation",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": True,
        },
        {
            "gold_id": "G-022",
            "sentence_category": "null_effect_negation",
            "rule_ref": "D-047",
            "expected_subject": "Sedation",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": True,
        },
        {
            "gold_id": "G-023",
            "sentence_category": "comparative_outcome",
            "rule_ref": "D-051",
            "expected_subject": "DexmedetomidineExposure",
            "expected_relation": "decreasesRiskOf",
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-024",
            "sentence_category": "comparative_outcome",
            "rule_ref": "D-052",
            "expected_subject": "CAM_ICU",
            "expected_relation": "increasesRiskOf",
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-025",
            "sentence_category": "comparative_outcome",
            "rule_ref": "D-060",
            "expected_subject": "CAM_ICU",
            "expected_relation": "decreasesRiskOf",
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-026",
            "sentence_category": "comparative_outcome",
            "rule_ref": "D-045",
            "expected_subject": "RASS",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-027",
            "sentence_category": "evidence",
            "rule_ref": "D-019",
            "expected_subject": "MechanicalVentilation",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-028",
            "sentence_category": "evidence",
            "rule_ref": "D-035",
            "expected_subject": "CAM_ICU",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-029",
            "sentence_category": "research_gap",
            "rule_ref": "D-024",
            "expected_subject": "PropofolExposure",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "research_gap",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-030",
            "sentence_category": "research_gap",
            "rule_ref": "D-032",
            "expected_subject": "OpioidExposure",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "research_gap",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-031",
            "sentence_category": "research_gap",
            "rule_ref": "D-039",
            "expected_subject": "Agitation",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "research_gap",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-032",
            "sentence_category": "no_recommendation",
            "rule_ref": "D-058",
            "expected_subject": "DexmedetomidineExposure",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "no_recommendation",
            "expected_negation_present": True,
        },
        {
            "gold_id": "G-033",
            "sentence_category": "research_gap",
            "rule_ref": "D-068",
            "expected_subject": "MechanicalVentilation",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "research_gap",
            "expected_negation_present": True,
        },
        {
            "gold_id": "G-034",
            "sentence_category": "research_gap",
            "rule_ref": "D-007",
            "expected_subject": "Sedation",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "research_gap",
            "expected_negation_present": True,
        },
        {
            "gold_id": "G-035",
            "sentence_category": "null_effect_negation",
            "rule_ref": "D-055",
            "expected_subject": "Sedation",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": True,
        },
        {
            "gold_id": "G-036",
            "sentence_category": "evidence",
            "rule_ref": "D-048",
            "expected_subject": "Sedation",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-037",
            "sentence_category": "evidence",
            "rule_ref": "D-042",
            "expected_subject": "RASS",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-038",
            "sentence_category": "evidence",
            "rule_ref": "D-057",
            "expected_subject": "DexmedetomidineExposure",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-039",
            "sentence_category": "comparative_outcome",
            "rule_ref": "D-067",
            "expected_subject": "BenzodiazepineExposure",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "evidence",
            "expected_negation_present": False,
        },
        {
            "gold_id": "G-040",
            "sentence_category": "evidence",
            "rule_ref": "D-026",
            "expected_subject": "MechanicalVentilation",
            "expected_relation": None,
            "expected_object": "Delirium",
            "expected_source_type": "pending",
            "expected_negation_present": False,
        },
    ]

    expanded: List[Dict[str, Any]] = []
    for g in original:
        expanded.append({k: v for k, v in g.items() if k != "rule_ref"})

    for item in new_items:
        rid = item.pop("rule_ref")
        if rid not in rules:
            raise SystemExit(f"Missing rule {rid}")
        expanded.append(
            {
                **item,
                "smoke_original": False,
                "sentence": rule_text(rules, rid),
                "expected_source_page": page(rules, rid),
            }
        )

    doc = {
        "version": "expanded_smoke_v1",
        "description": "40-item balanced gold set; expected_* are manual labels (not copied from extraction).",
        "gold_set": expanded,
    }
    OUT_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[gold] wrote {len(expanded)} items -> {OUT_PATH}")

    from collections import Counter

    cats = Counter(g["sentence_category"] for g in expanded)
    print("[gold] sentence_category distribution:", dict(cats))


if __name__ == "__main__":
    main()
