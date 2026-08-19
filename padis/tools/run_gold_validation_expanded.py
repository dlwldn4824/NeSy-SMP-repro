from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

RULES_PATH = Path("padis/outputs/padis_rules_raw.json")
GOLD_PATH = Path("padis/rules/gold_set_smoke.json")
OUT_REPORT = Path("padis/outputs/padis_gold_validation_expanded_report.md")

FIELDS = [
    ("source_type", "expected_source_type"),
    ("subject", "expected_subject"),
    ("object", "expected_object"),
    ("negation_present", "expected_negation_present"),
    ("source_page", "expected_source_page"),
    ("relation", "expected_relation"),
]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def acc(correct: int, total: int) -> float:
    return correct / max(1, total)


def eval_gold(g: dict, r: Optional[dict]) -> Tuple[bool, List[str], Dict[str, bool]]:
    if r is None:
        return False, ["NO_MATCH"], {}

    field_ok: Dict[str, bool] = {}
    failures: List[str] = []
    for got_key, exp_key in FIELDS:
        exp = g.get(exp_key)
        if exp is None:
            continue
        got = r.get(got_key)
        ok = exp == got
        field_ok[got_key] = ok
        if not ok:
            failures.append(f"{got_key}: exp={exp!r} got={got!r}")
    return len(failures) == 0, failures, field_ok


def is_original(g: dict) -> bool:
    if "smoke_original" in g:
        return bool(g["smoke_original"])
    gid = g.get("gold_id", "")
    try:
        return int(gid.split("-")[1]) <= 15
    except (IndexError, ValueError):
        return False


def report_subset(title: str, subset: List[Tuple[dict, bool, List[str], Dict[str, bool]]]) -> List[str]:
    lines = [f"## {title}"]
    total = len(subset)
    exact = sum(1 for _, ok, _, __ in subset if ok)
    lines.append(f"- exact match: {exact}/{total} ({acc(exact, total):.2f})")

    for field, exp_key in FIELDS:
        n = c = 0
        for g, _, _, field_ok in subset:
            if g.get(exp_key) is None:
                continue
            n += 1
            if field_ok.get(field, False):
                c += 1
        if n:
            lines.append(f"- {field} accuracy: {c}/{n} ({acc(c, n):.2f})")

    mism = [(g, fails) for g, ok, fails, _ in subset if not ok]
    if mism:
        lines.append(f"- mismatches: {', '.join(g['gold_id'] for g, _ in mism)}")
        for g, fails in mism:
            lines.append(
                f"  - {g['gold_id']} ({g.get('sentence_category', '')}): {'; '.join(fails)}"
            )
    lines.append("")
    return lines


def main() -> None:
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8")).get("rules", [])
    gold_set = json.loads(GOLD_PATH.read_text(encoding="utf-8")).get("gold_set", [])

    rule_by_sentence: Dict[str, List[dict]] = {}
    for r in rules:
        rule_by_sentence.setdefault(norm(r.get("source_text", "")), []).append(r)

    rows: List[Tuple[dict, bool, List[str], Dict[str, bool]]] = []
    for g in gold_set:
        cand = rule_by_sentence.get(norm(g.get("sentence", "")), [])
        ok, failures, field_ok = eval_gold(g, cand[0] if cand else None)
        rows.append((g, ok, failures, field_ok))

    lines: List[str] = [
        "# Gold validation (expanded set)",
        "",
        f"- total gold items: {len(rows)}",
        "",
    ]

    lines.extend(report_subset("Overall", rows))
    orig_rows = [r for r in rows if is_original(r[0])]
    new_rows = [r for r in rows if not is_original(r[0])]
    lines.extend(report_subset(f"Original smoke ({len(orig_rows)})", orig_rows))
    lines.extend(report_subset(f"New gold ({len(new_rows)})", new_rows))

    cat_stats: Dict[str, List[bool]] = defaultdict(list)
    for g, ok, _, __ in rows:
        cat_stats[g.get("sentence_category", "unknown")].append(ok)

    lines.append("## By sentence_category")
    for cat, oks in sorted(cat_stats.items()):
        lines.append(f"- {cat}: {sum(oks)}/{len(oks)} ({acc(sum(oks), len(oks)):.2f})")
    lines.append("")

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")
    exact_all = sum(1 for _, ok, _, __ in rows if ok)
    print(f"[gold-expanded] {exact_all}/{len(rows)} ({acc(exact_all, len(rows)):.2f}) -> {OUT_REPORT}")


if __name__ == "__main__":
    main()

