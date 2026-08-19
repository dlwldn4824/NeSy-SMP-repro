"""Build markdown review pack for review_priority=high rows only.

No auto-approval — blank reviewer fields for human completion.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CSV = REPO / "padis/outputs/padis_rules_human_review.csv"
DEFAULT_OUT = REPO / "padis/outputs/padis_high24_human_review_pack.md"


def _field(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def build_pack(rows: list[dict]) -> str:
    lines: list[str] = [
        "# PADIS Human Review Pack — High Priority (24 items)",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Source: `{DEFAULT_CSV.as_posix()}`",
        f"- Filter: `review_priority = high`",
        f"- Count: {len(rows)}",
        "",
        "Instructions:",
        "1. Compare each `source_text` against PADIS PDF original.",
        "2. Fill reviewer fields only — **do not auto-approve in code**.",
        "3. Use `reviewer_decision`: approve | revise_approve | reject | defer",
        "4. Set `direct_kg_edge`: yes | no | defer (only for approve/revise_approve)",
        "",
        "---",
        "",
    ]

    for i, row in enumerate(rows, start=1):
        rid = _field(row, "rule_id")
        lines.extend(
            [
                f"## {i}. {rid} (page {_field(row, 'source_page')})",
                "",
                "### Auto extraction",
                f"- **rule_id**: `{rid}`",
                f"- **source_page**: {_field(row, 'source_page')}",
                f"- **auto_source_type**: `{_field(row, 'auto_source_type')}`",
                f"- **auto_subject**: `{_field(row, 'auto_subject')}`",
                f"- **auto_relation**: `{_field(row, 'auto_relation')}`",
                f"- **auto_object**: `{_field(row, 'auto_object')}`",
                f"- **auto_negation_present**: `{_field(row, 'auto_negation_present')}`",
                f"- **kg_edge_candidate**: `{_field(row, 'kg_edge_candidate')}`",
                f"- **in_gold_set**: `{_field(row, 'in_gold_set')}`",
                "",
                "### PADIS source_text",
                "",
                f"> {_field(row, 'source_text')}",
                "",
                "### Reviewer (fill in)",
                "",
                "- **reviewer_decision**: ",
                "- **corrected_subject**: ",
                "- **corrected_relation**: ",
                "- **corrected_object**: ",
                "- **direct_kg_edge**: ",
                "- **reviewer_note**: ",
                "",
                "---",
                "",
            ]
        )

    lines.extend(
        [
            "## Summary tally (fill after review)",
            "",
            "| reviewer_decision | count |",
            "|-------------------|-------|",
            "| approve | |",
            "| revise_approve | |",
            "| reject | |",
            "| defer | |",
            "",
            "| direct_kg_edge | count |",
            "|----------------|-------|",
            "| yes | |",
            "| no | |",
            "| defer | |",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"Missing: {args.csv}")

    with args.csv.open("r", encoding="utf-8-sig") as f:
        all_rows = list(csv.DictReader(f))

    high_rows = [r for r in all_rows if _field(r, "review_priority") == "high"]
    if not high_rows:
        raise SystemExit("No high-priority rows found.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_pack(high_rows), encoding="utf-8")
    print(f"[review-pack] wrote {len(high_rows)} items -> {args.out}")


if __name__ == "__main__":
    main()
