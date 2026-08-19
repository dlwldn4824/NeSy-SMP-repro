from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--approved-json", type=Path, required=True)
    ap.add_argument("--out-kg", type=Path, default=Path("padis/outputs/padis_kg.json"))
    args = ap.parse_args()

    data = json.loads(args.approved_json.read_text(encoding="utf-8"))
    approved_rules: List[Dict[str, Any]] = data.get("approved_rules", data if isinstance(data, list) else [])
    if not approved_rules:
        raise SystemExit("No approved rules found. Did you run approve_rules.py with approved?=yes?")

    edges = []
    nodes = set()
    for r in approved_rules:
        rule_id = r.get("rule_id")
        subj = r.get("subject")
        rel = r.get("relation")
        obj = r.get("object")
        if not all([rule_id, subj, rel, obj]):
            # Skip incomplete rules; better to fail fast in later versions.
            continue
        edges.append(
            {
                "subject": subj,
                "relation": rel,
                "object": obj,
                "rule_id": rule_id,
            }
        )
        nodes.add(subj)
        nodes.add(obj)

    kg = {
        "kg_name": "PADIS_kg_phase1",
        "edges": edges,
        # Nodes are optional; helps quick sanity checks without duplicating source_text.
        "nodes": sorted(nodes),
    }

    args.out_kg.parent.mkdir(parents=True, exist_ok=True)
    args.out_kg.write_text(json.dumps(kg, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[PADIS KG] edges={len(edges)} -> {args.out_kg}")


if __name__ == "__main__":
    main()

