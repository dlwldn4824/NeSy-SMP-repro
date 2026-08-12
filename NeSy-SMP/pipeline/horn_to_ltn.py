from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .predicate_compiler import compile_predicates, concept_to_predicate_name


@dataclass
class AxiomIR:
    """Intermediate representation for LTN axioms (replaces hardcoded Forall/Implies)."""

    kind: str  # implication | grounding | data
    formula: str  # human-readable FOL
    head_predicate: str
    body_predicates: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    source: Optional[str] = None
    code_predicates: List[str] = field(default_factory=list)


_ATOM = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)")


def _parse_atoms(fragment: str) -> List[str]:
    return [m.group(1) for m in _ATOM.finditer(fragment or "")]


def _concept_maps(concepts_path: str | Path):
    preds = compile_predicates(concepts_path)
    by_concept = {p["concept_id"]: p for p in preds}
    by_snomed = {p["snomed_label"]: p for p in preds}
    by_pred = {p["predicate"]: p for p in preds}
    by_code = {p["code_predicate"]: p for p in preds}
    # alias lookup
    alias = {}
    with open(concepts_path, encoding="utf-8") as f:
        cfg = json.load(f)
    for c in cfg["concepts"]:
        for a in c.get("aliases", []) + [c["id"], c.get("snomed_label", "")]:
            if a:
                alias[a.lower()] = c["id"]
    return by_concept, by_snomed, by_pred, by_code, alias, preds


def resolve_predicate(name: str, concepts_path: str | Path) -> Dict[str, Any]:
    by_concept, by_snomed, by_pred, by_code, alias, _ = _concept_maps(concepts_path)
    if name in by_pred:
        return by_pred[name]
    if name in by_code:
        return by_code[name]
    if name in by_concept:
        return by_concept[name]
    if name in by_snomed:
        return by_snomed[name]
    # Death / Outcome → HighMortality
    if name in ("Death", "Outcome", "Mortality"):
        return {
            "predicate": "HighMortality",
            "code_predicate": "HighMortality",
            "concept_id": "Death",
        }
    cid = alias.get(name.lower())
    if cid and cid in by_concept:
        return by_concept[cid]
    # synthesize
    pred = concept_to_predicate_name(name, "high")
    return {"predicate": pred, "code_predicate": pred, "concept_id": name}


def compile_implications_from_kg(concepts_path: str | Path) -> List[AxiomIR]:
    """
    Direct KG path (no AnyBURL):
    (RiskFactor, increasesRiskOf, Death) → ∀x Pred(x) → HighMortality(x)
    """
    with open(concepts_path, encoding="utf-8") as f:
        cfg = json.load(f)
    axioms: List[AxiomIR] = []
    for t in cfg["triples"]:
        if t["object"] not in ("Death", "HighMortality"):
            continue
        if "risk" not in t["predicate"].lower() and t["predicate"] not in (
            "increasesRiskOf",
            "increaseRiskOf",
        ):
            continue
        body = resolve_predicate(t["subject"], concepts_path)
        head = resolve_predicate(t["object"], concepts_path)
        bp = body["predicate"]
        hp = head["predicate"]
        axioms.append(
            AxiomIR(
                kind="implication",
                formula=f"∀x: {bp}(x) → {hp}(x)",
                head_predicate=hp,
                body_predicates=[bp],
                source=f"kg:{t['subject']}-{t['predicate']}-{t['object']}",
                code_predicates=[body.get("code_predicate", bp), head.get("code_predicate", hp)],
            )
        )
    return axioms


def compile_grounding_axioms(concepts_path: str | Path) -> List[AxiomIR]:
    """
    Weak-anchoring IR (what stratified_main hardcodes as threshold Foralls):
    ∀x ∈ {feature ⊳ τ}: Pred(x)
    """
    axioms: List[AxiomIR] = []
    for p in compile_predicates(concepts_path):
        if p.get("threshold") is None or not p.get("feature_name"):
            continue
        if "Outcome" in p.get("roles", []):
            continue
        pol = p.get("polarity")
        thr = p["threshold"]
        feat = p["feature_name"]
        pred = p["predicate"]
        if pol == "high":
            mask = f"{feat}(x) > {thr}"
        elif pol == "low":
            mask = f"{feat}(x) < {thr}"
        elif pol == "trend_nondecreasing_above":
            mask = f"nondecreasing({feat}(x)) ∧ max({feat}(x)) > {thr}"
        else:
            continue
        axioms.append(
            AxiomIR(
                kind="grounding",
                formula=f"∀x ∈ {{{mask}}}: {pred}(x)",
                head_predicate=pred,
                body_predicates=[],
                source=f"threshold:{feat}:{thr}",
                code_predicates=[p.get("code_predicate", pred)],
            )
        )
    return axioms


def parse_horn_rule(rule: str) -> Optional[Dict[str, Any]]:
    """
    Parse AnyBURL / filtered rule strings.
    Supports:
      Head(x) <= Body1(x), Body2(x)
      Head(x) <- Body1(x) ∧ Body2(x)
      Death(x) ← Lactate(x)
    """
    if not isinstance(rule, str):
        return None
    r = rule.strip()
    for sep in ("<=", "<-", "←", ":-"):
        if sep in r:
            head, body = r.split(sep, 1)
            break
    else:
        # sometimes "Head <= Body" already split columns
        return None
    head_atoms = _parse_atoms(head)
    body_atoms = _parse_atoms(body)
    if not head_atoms:
        # bare symbol head
        head_atoms = [head.strip().split("(")[0]]
    return {"head": head_atoms[0], "body": body_atoms, "raw": rule}


def compile_horn_rules(
    rules_csv: str | Path,
    concepts_path: str | Path,
    min_confidence: float = 0.8,
) -> List[AxiomIR]:
    """
    Horn clause file (filter_rules output) → LTN implication axiom IR.
    Death(x) ← Lactate(x) ∧ Platelet(x)
      ⇒ ∀x: HighLactate(x) ∧ LowPlatelets(x) → HighMortality(x)
    """
    import pandas as pd

    path = Path(rules_csv)
    if not path.exists():
        return []

    df = pd.read_csv(path, sep="\t")
    axioms: List[AxiomIR] = []
    for _, row in df.iterrows():
        conf = float(row.get("confidence", 1.0))
        if conf < min_confidence:
            continue
        rule = row.get("rule", "")
        parsed = parse_horn_rule(str(rule))
        if parsed is None:
            # try head/body columns
            head = str(row.get("head", ""))
            body = str(row.get("body", ""))
            head_atoms = _parse_atoms(head) or ([head] if head else [])
            body_atoms = _parse_atoms(body)
            if not head_atoms:
                continue
            parsed = {"head": head_atoms[0], "body": body_atoms, "raw": rule or f"{head}<={body}"}

        head_r = resolve_predicate(parsed["head"], concepts_path)
        # only mortality/outcome heads (paper filter)
        if head_r["predicate"] not in ("HighMortality",) and parsed["head"] not in (
            "Death",
            "Outcome",
            "HighMortality",
        ):
            continue

        body_resolved = [resolve_predicate(b, concepts_path) for b in parsed["body"]]
        body_names = [b["predicate"] for b in body_resolved]
        if not body_names:
            continue
        conj = " ∧ ".join(f"{b}(x)" for b in body_names)
        hp = head_r["predicate"]
        axioms.append(
            AxiomIR(
                kind="implication",
                formula=f"∀x: {conj} → {hp}(x)",
                head_predicate=hp,
                body_predicates=body_names,
                confidence=conf,
                source=str(parsed["raw"]),
                code_predicates=[b.get("code_predicate", b["predicate"]) for b in body_resolved]
                + [head_r.get("code_predicate", hp)],
            )
        )
    return axioms


def compile_data_axioms() -> List[AxiomIR]:
    return [
        AxiomIR(
            kind="data",
            formula="∀x+: HighMortality(x+)",
            head_predicate="HighMortality",
            source="label:positive",
            code_predicates=["HighMortality"],
        ),
        AxiomIR(
            kind="data",
            formula="∀x-: ¬HighMortality(x-)",
            head_predicate="HighMortality",
            source="label:negative",
            code_predicates=["HighMortality"],
        ),
    ]


def write_axiom_bundle(
    concepts_path: str | Path,
    out_json: str | Path,
    rules_csv: str | Path | None = None,
) -> dict:
    """Full knowledge bundle: data + grounding + KG implications (+ optional Horn)."""
    axioms = []
    axioms.extend(compile_data_axioms())
    axioms.extend(compile_grounding_axioms(concepts_path))
    axioms.extend(compile_implications_from_kg(concepts_path))
    if rules_csv and Path(rules_csv).exists():
        axioms.extend(compile_horn_rules(rules_csv, concepts_path))

    # de-duplicate by formula
    seen = set()
    uniq = []
    for a in axioms:
        if a.formula in seen:
            continue
        seen.add(a.formula)
        uniq.append(a)

    predicates = compile_predicates(concepts_path)
    bundle = {
        "predicates": predicates,
        "axioms": [asdict(a) for a in uniq],
        "loss": {"w_D": 0.8, "w_K": 0.2, "formula": "1 - (w_D * SatAgg(K_D) + w_K * SatAgg(K_K))"},
        "counts": {
            "predicates": len(predicates),
            "data": sum(1 for a in uniq if a.kind == "data"),
            "grounding": sum(1 for a in uniq if a.kind == "grounding"),
            "implication": sum(1 for a in uniq if a.kind == "implication"),
        },
    }
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return bundle
