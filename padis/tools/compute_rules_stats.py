from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


RULES_PATH = Path("padis/outputs/padis_rules_raw.json")
GOLD_PATH = Path("padis/rules/gold_set_smoke.json")


def main() -> None:
    d = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    rules = d["rules"]

    print("rules", len(rules))
    print("source_type", dict(Counter(r.get("source_type") for r in rules)))
    print("relation", dict(Counter(r.get("relation") for r in rules)))
    print(
        "relation_pending",
        sum(1 for r in rules if (r.get("relation") == "pending")),
    )
    print(
        "negation_present_true",
        sum(1 for r in rules if (r.get("negation_present") is True)),
    )

    print(
        "experiment_usable",
        dict(Counter(r.get("experiment_usable") for r in rules)),
    )

    if GOLD_PATH.exists():
        gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
        gold_set = gold.get("gold_set", gold if isinstance(gold, list) else [])
        print("gold_set_size", len(gold_set))


if __name__ == "__main__":
    main()

