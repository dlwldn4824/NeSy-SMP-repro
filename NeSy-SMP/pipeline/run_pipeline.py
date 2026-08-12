#!/usr/bin/env python3
"""
Automated knowledge pipeline (replaces hardcoded create_ckg + FOL axioms).

Stages:
  1) guideline text → triples (or use curated clinical_concepts.json)
  2) triples → RDF KG + AnyBURL pkg.txt
  3) KG (+ optional Horn rules) → LTN axiom IR JSON
  4) predicates JSON for model wiring

Usage (from NeSy-SMP root):
  python -m pipeline.run_pipeline
  python -m pipeline.run_pipeline --guideline path/to/ssc_notes.txt
  python -m pipeline.run_pipeline --rules rules/process-rule-filtered.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .build_kg import build_rdf_graph, export_anyburl_triples, merge_extracted_triples
from .guideline_extract import bootstrap_from_seed, extract_from_file, extract_from_pdf
from .horn_to_ltn import write_axiom_bundle
from .predicate_compiler import compile_predicates


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONCEPTS = ROOT / "configs" / "clinical_concepts.json"
DEFAULT_RELVOCAB = ROOT / "configs" / "relation_vocab.json"
DEFAULT_OUT = ROOT / "pipeline_out"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concepts", type=Path, default=DEFAULT_CONCEPTS)
    ap.add_argument("--rel-vocab", type=Path, default=DEFAULT_RELVOCAB)
    ap.add_argument("--guideline", type=Path, default=None, help="plain-text guideline excerpts")
    ap.add_argument("--pdf", type=Path, default=None, help="guideline PDF (e.g. Surviving Sepsis 2021)")
    ap.add_argument("--use-seed-guidelines", action="store_true", help="run seed SSC-like sentences")
    ap.add_argument("--rules", type=Path, default=None, help="filtered AnyBURL rules TSV")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    concepts_path = args.concepts

    # --- 1) optional guideline extraction → merge triples ---
    if args.pdf or args.guideline or args.use_seed_guidelines:
        if args.pdf:
            extracted, _ = extract_from_pdf(
                args.pdf,
                args.concepts,
                args.rel_vocab,
                text_out=args.out / "guideline_extracted.txt",
            )
        elif args.guideline:
            extracted = extract_from_file(args.guideline, args.concepts, args.rel_vocab)
        else:
            extracted = bootstrap_from_seed(args.concepts, args.rel_vocab)
        merged = args.out / "clinical_concepts.merged.json"
        concepts_path = merge_extracted_triples(args.concepts, extracted, merged)
        (args.out / "extracted_triples.json").write_text(
            json.dumps(extracted, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[1] extracted {len(extracted)} triples → {merged}")
        for t in extracted:
            print(f"    - {t['subject']} --{t['predicate']}--> {t['object']}")
    else:
        print(f"[1] using curated concepts: {concepts_path}")

    # --- 2) RDF + AnyBURL export ---
    g = build_rdf_graph(concepts_path, args.rel_vocab)
    ttl = args.out / "clinical_kg.ttl"
    g.serialize(ttl, format="turtle")
    pkg = export_anyburl_triples(g, ROOT / "rules" / "pkg.txt")
    print(f"[2] RDF → {ttl} | AnyBURL triples → {pkg} ({len(g)} triples)")

    # --- 3) predicates ---
    predicates = compile_predicates(concepts_path)
    pred_path = args.out / "predicates.json"
    pred_path.write_text(json.dumps(predicates, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[3] predicates → {pred_path} ({len(predicates)})")

    # --- 4) Horn/KG → LTN axiom IR ---
    rules = args.rules
    if rules is None:
        cand = ROOT / "rules" / "process-rule-filtered.csv"
        rules = cand if cand.exists() else None
    bundle = write_axiom_bundle(concepts_path, args.out / "ltn_axioms.json", rules)
    print(
        f"[4] LTN axioms → {args.out / 'ltn_axioms.json'} "
        f"(data={bundle['counts']['data']}, grounding={bundle['counts']['grounding']}, "
        f"implication={bundle['counts']['implication']})"
    )
    print("Done. Next: wire pipeline_out/ltn_axioms.json into training loop (replace hardcoded Forall/Implies).")


if __name__ == "__main__":
    main()
