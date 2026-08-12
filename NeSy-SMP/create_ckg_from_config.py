"""Drop-in data-driven replacement for create_ckg.py hardcoded triples."""

from pathlib import Path

from pipeline.build_kg import build_rdf_graph, export_anyburl_triples

try:
    from utils import visualize
except Exception:  # optional viz deps
    visualize = None

ROOT = Path(__file__).resolve().parent
g = build_rdf_graph(
    ROOT / "configs" / "clinical_concepts.json",
    ROOT / "configs" / "relation_vocab.json",
)
export_anyburl_triples(g, ROOT / "rules" / "pkg.txt")
out = ROOT / "pipeline_out" / "clinical_kg.ttl"
out.parent.mkdir(parents=True, exist_ok=True)
g.serialize(out, format="turtle")
print(f"Wrote {out} ({len(g)} triples) and rules/pkg.txt")
if visualize is not None:
    visualize(g)
