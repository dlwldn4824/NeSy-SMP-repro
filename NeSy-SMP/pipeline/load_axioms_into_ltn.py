"""
Load pipeline_out/ltn_axioms.json and describe how to bind into LTN training.

Full torch/ltn wiring still lives in stratified_main.py; this module is the
bridge contract so training no longer hardcodes axiom lists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def load_axiom_bundle(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def split_axiom_kinds(bundle: dict) -> Dict[str, List[dict]]:
    out = {"data": [], "grounding": [], "implication": []}
    for a in bundle.get("axioms", []):
        out.setdefault(a["kind"], []).append(a)
    return out


def predicate_index(bundle: dict) -> Dict[str, dict]:
    return {p["predicate"]: p for p in bundle.get("predicates", [])}


def summarize(path: str | Path) -> str:
    bundle = load_axiom_bundle(path)
    parts = split_axiom_kinds(bundle)
    lines = [
        f"w_D={bundle['loss']['w_D']} w_K={bundle['loss']['w_K']}",
        f"predicates={len(bundle['predicates'])}",
        f"data={len(parts['data'])} grounding={len(parts['grounding'])} implication={len(parts['implication'])}",
        "",
        "Implications:",
    ]
    for a in parts["implication"]:
        lines.append(f"  - {a['formula']}")
    lines.append("Grounding (weak anchoring IR):")
    for a in parts["grounding"]:
        lines.append(f"  - {a['formula']}")
    return "\n".join(lines)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    p = root / "pipeline_out" / "ltn_axioms.json"
    if not p.exists():
        raise SystemExit("Run: python -m pipeline.run_pipeline")
    print(summarize(p))
