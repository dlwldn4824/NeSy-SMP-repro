from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .predicate_compiler import link_mention_to_concept
from .relations import load_relation_vocab, normalize_relation


DEFAULT_GUIDELINE_SENTENCES = [
    "Elevated serum lactate increases risk of death in sepsis.",
    "Hyperbilirubinemia is associated with higher mortality.",
    "Thrombocytopenia increases risk of death.",
    "Elevated C-reactive protein increases risk of mortality.",
    "Leukocytosis increases risk of death.",
    "Low mean arterial pressure increases risk of death.",
    "Advanced age increases risk of sepsis mortality.",
    "Lactate not clearing increases risk of death.",
    "Chronic disease increases risk of death.",
    "Hypotension is caused by sepsis.",
]


_REL_PATTERNS = [
    (r"increases?\s+risk\s+of", "increasesRiskOf"),
    (r"associated\s+with\s+(?:increased\s+|higher\s+|elevated\s+)?(?:risk|mortality|death)", "increasesRiskOf"),
    (r"association\s+between\s+.+\s+and\s+(?:mortality|death)", "increasesRiskOf"),
    (r"associated\s+with", "associatedWith"),
    (r"caused\s+by", "causedBy"),
    (r"leads?\s+to", "increasesRiskOf"),
    (r"predictor?\s+of\s+(?:mortality|death)", "increasesRiskOf"),
    (r"predict(?:s|ion|ive)?\s+of\s+(?:mortality|death)", "increasesRiskOf"),
    (r"related\s+to\s+mortality", "increasesRiskOf"),
    (r"mortality\s+(?:was\s+)?(?:higher|increased)", "increasesRiskOf"),
]


def normalize_pdf_text(text: str) -> str:
    """Fix common PDF extraction artifacts (hyphenation, newlines)."""
    text = text.replace("\u00ad", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", " ", text)
    return text.strip()


def split_sentences(text: str) -> List[str]:
    text = normalize_pdf_text(text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return [p.strip() for p in parts if len(p.strip()) > 40]


def _find_relation(sent: str, vocab: dict) -> Optional[str]:
    for pat, canon in _REL_PATTERNS:
        if re.search(pat, sent, flags=re.I):
            return normalize_relation(canon, vocab)
    return None


def _is_mortality_relevant(sent: str) -> bool:
    return bool(
        re.search(
            r"\b(mortalit(?:y|ies)|death|die[ds]?|expire|prognos\w*|fatalit\w*)\b",
            sent,
            flags=re.I,
        )
    )


def extract_from_texts(
    texts: List[str],
    concepts_path: str | Path,
    relation_vocab_path: str | Path,
    mortality_only: bool = True,
) -> List[dict]:
    """
    Guideline extractor:
      sentence → (concept, relation, outcome) → normalized triple
    """
    with open(concepts_path, encoding="utf-8") as f:
        cfg = json.load(f)
    concepts = cfg["concepts"]
    vocab = load_relation_vocab(relation_vocab_path)

    triples: List[dict] = []
    seen = set()
    for sent in texts:
        if mortality_only and not _is_mortality_relevant(sent) and "caused by" not in sent.lower():
            continue
        rel = _find_relation(sent, vocab)
        if rel is None:
            # still try concept+mortality co-occurrence → increasesRiskOf
            if mortality_only and _is_mortality_relevant(sent):
                rel = "increasesRiskOf"
            else:
                continue

        # Prefer explicit left/right split; else scan whole sentence for concept
        parts = re.split(
            r"increases?\s+risk\s+of|associated\s+with|caused\s+by|leads?\s+to|"
            r"association\s+between|predictor?\s+of|related\s+to",
            sent,
            maxsplit=1,
            flags=re.I,
        )
        left = parts[0] if parts else sent
        right = parts[1] if len(parts) > 1 else sent

        subj_c = link_mention_to_concept(
            left,
            concepts,
            prefer_roles=["RiskFactor", "Comorbidity", "Disease"],
            exclude_ids=["Death"],
        ) or link_mention_to_concept(
            sent,
            concepts,
            prefer_roles=["RiskFactor", "Comorbidity", "Disease"],
            exclude_ids=["Death"],
        )
        obj_c = link_mention_to_concept(
            right,
            concepts,
            prefer_roles=["Outcome", "Disease"],
        )
        if obj_c is None or obj_c["id"] not in ("Death", "Sepsis", "SepticShock"):
            # default mortality head when sentence is mortality-relevant
            if _is_mortality_relevant(sent):
                obj_c = next(c for c in concepts if c["id"] == "Death")
            else:
                continue
        if subj_c is None:
            continue
        if subj_c["id"] == obj_c["id"]:
            continue
        if subj_c["id"] == "Death":
            continue

        # Evidence quality: subject mention must sit near a mortality/outcome cue
        if not _evidence_supports(sent, subj_c):
            continue

        key = (subj_c["id"], rel, obj_c["id"])
        if key in seen:
            continue
        seen.add(key)
        triples.append(
            {
                "subject": subj_c["id"],
                "predicate": rel,
                "object": obj_c["id"],
                "evidence": sent[:500],
            }
        )
    return triples


def _evidence_supports(sent: str, concept: dict, window: int = 120) -> bool:
    """Require a concept alias near mortality/risk wording (cuts PDF false positives)."""
    s = sent.lower()
    aliases = [concept["id"], concept.get("snomed_label", "")] + concept.get("aliases", [])
    aliases = [a.lower() for a in aliases if a and len(a) >= 3]
    cue = re.search(
        r"\b(mortalit(?:y|ies)|death|risk of death|prognos\w*|fatalit\w*|increases? risk)\b",
        s,
    )
    if cue is None:
        return False
    cpos = cue.start()
    for a in sorted(aliases, key=len, reverse=True):
        idx = s.find(a)
        if idx < 0:
            continue
        if abs(idx - cpos) <= window:
            return True
    return False


def extract_from_file(
    path: str | Path,
    concepts_path: str | Path,
    relation_vocab_path: str | Path,
) -> List[dict]:
    text = Path(path).read_text(encoding="utf-8")
    return extract_from_texts(split_sentences(text), concepts_path, relation_vocab_path)


def extract_from_pdf(
    pdf_path: str | Path,
    concepts_path: str | Path,
    relation_vocab_path: str | Path,
    text_out: str | Path | None = None,
) -> Tuple[List[dict], str]:
    """Extract triples directly from a guideline PDF (Surviving Sepsis etc.)."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    raw = "\n\n".join((p.extract_text() or "") for p in reader.pages)
    if text_out is not None:
        Path(text_out).parent.mkdir(parents=True, exist_ok=True)
        Path(text_out).write_text(raw, encoding="utf-8")
    triples = extract_from_texts(split_sentences(raw), concepts_path, relation_vocab_path)
    return triples, raw


def bootstrap_from_seed(
    concepts_path: str | Path,
    relation_vocab_path: str | Path,
) -> List[dict]:
    return extract_from_texts(
        DEFAULT_GUIDELINE_SENTENCES, concepts_path, relation_vocab_path, mortality_only=False
    )
