from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Tuple

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import OWL, RDF, RDFS, XSD

from .relations import load_relation_vocab, normalize_relation


Triple = Tuple[str, str, str]


def load_concepts(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_rdf_graph(
    concepts_path: str | Path,
    relation_vocab_path: str | Path | None = None,
) -> Graph:
    """
    Data-driven replacement for hardcoded create_ckg.py.
    Reads clinical_concepts.json triples → RDF.
    """
    cfg = load_concepts(concepts_path)
    vocab = load_relation_vocab(relation_vocab_path) if relation_vocab_path else None

    ns = cfg["namespaces"]
    CKG = Namespace(ns["ckg"])
    SNOMED = Namespace(ns["snomed"])
    SCHEMA = Namespace(ns["schema"])

    g = Graph()
    g.bind("ckg", CKG)
    g.bind("snomed", SNOMED)
    g.bind("schema", SCHEMA)
    g.bind("rdfs", RDFS)
    g.bind("owl", OWL)

    # Outcomes / patient scaffolding (structural, not clinical extraction)
    g.add((SNOMED.Death, RDFS.subClassOf, SNOMED.Outcome))
    g.add((SNOMED.Death, RDF.type, SNOMED.Outcome))
    g.add((SNOMED.PatientDischargedAlive, RDFS.subClassOf, SNOMED.Outcome))
    g.add((SNOMED.Patient, SNOMED.hasOutcome, SNOMED.Death))
    g.add((SNOMED.Patient, SNOMED.hasOutcome, SNOMED.PatientDischargedAlive))

    by_id = {c["id"]: c for c in cfg["concepts"]}

    for c in cfg["concepts"]:
        node = SNOMED[c["snomed_label"]]
        for role in c.get("roles", []):
            g.add((node, RDFS.subClassOf, SNOMED[role]))
        # threshold literals for weak-anchoring sources
        pol = c.get("polarity")
        thr = c.get("threshold")
        if thr is not None and pol in ("high", "trend_nondecreasing_above"):
            g.add((node, SCHEMA.greaterOrEqual, Literal(thr, datatype=XSD.float)))
        if thr is not None and pol == "low":
            g.add((node, SCHEMA.lessOrEqual, Literal(thr, datatype=XSD.float)))

    for t in cfg["triples"]:
        rel = t["predicate"]
        if vocab is not None:
            rel_n = normalize_relation(rel, vocab)
            if rel_n is None:
                raise ValueError(f"Relation not in closed vocab: {rel}")
            rel = rel_n
        s = by_id[t["subject"]]["snomed_label"]
        o = by_id[t["object"]]["snomed_label"]
        # schema.org style predicates used in original create_ckg
        if rel in ("increasesRiskOf", "increaseRiskOf"):
            g.add((SNOMED[s], SCHEMA.increasesRiskOf, SNOMED[o]))
            # keep legacy alias used in create_ckg.py
            g.add((SNOMED[s], SCHEMA.increaseRiskOf, SNOMED[o]))
        elif rel == "causedBy":
            g.add((SNOMED[s], SNOMED.causedBy, SNOMED[o]))
        elif rel == "associatedWith":
            g.add((SNOMED[s], SCHEMA.associatedWith, SNOMED[o]))
        elif rel == "subClassOf":
            g.add((SNOMED[s], RDFS.subClassOf, SNOMED[o]))
        else:
            g.add((SNOMED[s], SCHEMA[rel], SNOMED[o]))

    return g


def graph_to_triples(g: Graph) -> List[Triple]:
    triples: List[Triple] = []
    for s, p, o in g:
        if isinstance(o, Literal):
            continue
        triples.append((str(s).split("/")[-1], str(p).split("/")[-1], str(o).split("/")[-1]))
    return triples


def export_anyburl_triples(g: Graph, out_path: str | Path) -> Path:
    """
    Export KG as tab-separated subject predicate object for AnyBURL / c_clause.
    Format expected by extract_rules.py path_train (pkg.txt).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for s, p, o in graph_to_triples(g):
        lines.append(f"{s}\t{p}\t{o}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def merge_extracted_triples(
    concepts_path: str | Path,
    extracted: Iterable[dict],
    out_path: str | Path,
) -> Path:
    """
    Merge guideline-extracted triples into a concepts JSON copy.
    extracted items: {subject, predicate, object, evidence?}
    """
    cfg = load_concepts(concepts_path)
    existing = {(t["subject"], t["predicate"], t["object"]) for t in cfg["triples"]}
    for t in extracted:
        key = (t["subject"], t["predicate"], t["object"])
        if key not in existing:
            cfg["triples"].append(
                {
                    "subject": t["subject"],
                    "predicate": t["predicate"],
                    "object": t["object"],
                    "evidence": t.get("evidence"),
                }
            )
            existing.add(key)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path
