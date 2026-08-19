from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List


RULES_PATH = Path("padis/outputs/padis_rules_raw.json")
GOLD_PATH = Path("padis/rules/gold_set_smoke.json")
OUT_REPORT = Path("padis/outputs/padis_smoke_gold_validation_report.md")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def main() -> None:
    if not RULES_PATH.exists():
        raise SystemExit(f"Missing: {RULES_PATH}")
    if not GOLD_PATH.exists():
        raise SystemExit(f"Missing: {GOLD_PATH}")

    rules = json.loads(RULES_PATH.read_text(encoding="utf-8")).get("rules", [])
    gold_doc = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    gold_set = gold_doc.get("gold_set", gold_doc if isinstance(gold_doc, list) else [])

    if not gold_set:
        OUT_REPORT.write_text("gold_set empty; please fill and rerun.", encoding="utf-8")
        print("[gold] gold_set empty")
        return

    rule_by_sentence: Dict[str, List[dict]] = {}
    for r in rules:
        key = norm(r.get("source_text", ""))
        rule_by_sentence.setdefault(key, []).append(r)

    lines: List[str] = [
        "# Gold smoke validation (rules fixed; gold updated)",
        "",
    ]

    correct = 0
    total = 0
    for g in gold_set:
        total += 1
        key = norm(g.get("sentence", ""))
        cand = rule_by_sentence.get(key, [])
        if not cand:
            lines.append(f"- {g.get('gold_id')}: NO_MATCH")
            continue
        r = cand[0]

        ok = True
        checks = [
            ("source_type", g.get("expected_source_type"), r.get("source_type")),
            ("subject", g.get("expected_subject"), r.get("subject")),
            ("object", g.get("expected_object"), r.get("object")),
            ("negation_present", g.get("expected_negation_present"), r.get("negation_present")),
            ("source_page", g.get("expected_source_page"), r.get("source_page")),
            ("relation", g.get("expected_relation"), r.get("relation")),
        ]
        for _, exp, got in checks:
            if exp is None:
                continue
            if exp != got:
                ok = False
                break

        if ok:
            correct += 1
            lines.append(f"- {g.get('gold_id')}: OK")
        else:
            lines.append(f"- {g.get('gold_id')}: MISMATCH (got subject={r.get('subject')}, rel={r.get('relation')}, object={r.get('object')})")

    acc = correct / max(1, total)
    lines.extend(["", f"- exact-match count: {correct}/{total} (acc={acc:.2f})"])
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"[gold] done: {correct}/{total} (acc={acc:.2f}) -> {OUT_REPORT}")


if __name__ == "__main__":
    main()

