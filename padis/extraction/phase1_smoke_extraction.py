from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader


DEFAULT_OUT_RULES_RAW = "padis_rules_raw.json"
DEFAULT_OUT_REVIEW_CSV = "padis_rules_review.csv"
DEFAULT_OUT_GOLD_VALIDATION = "padis_smoke_gold_validation_report.md"
DEFAULT_OUT_MIMIC_COVERAGE = "mimic_coverage_report_smoke.md"
DEFAULT_OUT_MIMIC_COVERAGE_FINAL_NAME = "mimic_coverage_report.md"


def _read_text_pages(pdf_path: Path) -> List[str]:
    reader = PdfReader(str(pdf_path))
    pages: List[str] = []
    for p in reader.pages:
        pages.append((p.extract_text() or "").strip())
    return pages


def _split_sentences(text: str) -> List[str]:
    # Keep it simple and deterministic; guideline PDFs often have messy spacing.
    text = text.replace("\u00ad", "")  # soft hyphen
    text = re.sub(r"\s+", " ", text).strip()
    # Split on punctuation boundaries.
    parts = re.split(r"(?<=[.!?])\s+", text)
    # Filter ultra-short fragments.
    return [p.strip() for p in parts if len(p.strip()) >= 40]


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def _contains_any(haystack: str, needles: List[str]) -> bool:
    s = haystack.lower()
    return any(n.lower() in s for n in needles)


@dataclass
class ConceptHit:
    concept_id: str
    matched_keyword: str


def _keyword_hits(sentence: str) -> Dict[str, ConceptHit]:
    """
    Very small PADIS concept hit list for Phase 1 smoke extraction.
    Keep this conservative: if we can't confidently map, leave it out.
    """
    s = sentence.lower()

    # subject-side (exposure / condition)
    meds = [
        ("BenzodiazepineExposure", ["benzodiazepine", "lorazepam", "midazolam"]),
        ("PropofolExposure", ["propofol"]),
        ("DexmedetomidineExposure", ["dexmedetomidine", "precedex"]),
        ("OpioidExposure", ["opioid", "morphine", "fentanyl"]),
    ]
    states = [
        ("Delirium", ["delirium"]),
        ("Agitation", ["agitation"]),
        ("Sedation", ["sedation", "sedated"]),
        ("Pain", ["pain"]),
        ("MechanicalVentilation", ["mechanical ventilation", "ventilated"]),
    ]
    assessments = [
        ("RASS", ["rass"]),
        ("CAM_ICU", ["cam-icu", "camicu", "confusion assessment method"]),
    ]

    out: Dict[str, ConceptHit] = {}
    for concept_id, keywords in meds + states + assessments:
        for kw in keywords:
            if kw.lower() in s:
                out[concept_id] = ConceptHit(concept_id=concept_id, matched_keyword=kw)
                break
    return out


def _infer_source_type(sentence: str) -> str:
    sl = sentence.lower()
    # Negative/safety cues
    if _contains_any(sl, ["no recommendation", "not recommended", "insufficient evidence", "lack of evidence"]):
        if _contains_any(sl, ["no recommendation", "not recommended"]):
            return "no_recommendation"
        return "research_gap"
    # Common guideline verbs
    if _contains_any(sl, ["should", "recommend", "recommended", "advised", "suggest", "suggested"]):
        return "recommendation"
    # Risk-factor-ish cues
    if _contains_any(sl, ["risk", "increase", "increases", "associated with", "higher", "mortality"]):
        return "risk_factor_statement"
    # Evidence-y phrasing fallback
    if _contains_any(sl, ["evidence", "studies", "data", "clinical trial", "observational"]):
        return "evidence"
    return "pending"


def _infer_relation(sentence: str, subject_id: str, object_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (relation, relation_candidate).
    - relation: only from closed vocab if we are confident
    - relation_candidate: always fill (for human review), even if not closed-vocab confident
    """
    sl = sentence.lower()

    rel_vocab = [
        "increasesRiskOf",
        "decreasesRiskOf",
        "associatedWith",
        "preferredOver",
        "requiresAssessmentOf",
        "shouldBeTreatedBefore",
    ]

    negated = bool(re.search(r"\bnot\b|\bno\b", sl))
    # preferredOver
    if "rather than" in sl or "prefer" in sl or "preferably" in sl:
        # heuristic: medicationA rather than medicationB
        if subject_id != object_id:
            return "preferredOver", "preferredOver (heuristic: rather than/prefer)"

    # increases/decreases/associated
    if any(k in sl for k in ["increases risk", "increases", "higher risk", "risk of", "associated with", "increased"]):
        if negated and object_id.lower() == "delirium":
            # Don't guess negated causality; leave candidate only.
            return None, "negation/unknown direction (human review)"
        if "associated with" in sl or "associated" in sl:
            return "associatedWith", "associatedWith"
        return "increasesRiskOf", "increasesRiskOf (risk/increase cue)"

    if any(k in sl for k in ["decreases", "lower", "reduced", "less likely"]):
        return "decreasesRiskOf", "decreasesRiskOf (reduction cue)"

    # fallback
    # Keep directionless candidate for review.
    cand = f"unknown_relation (subject={subject_id}, object={object_id})"
    # If there is an assessment keyword, treat as requiresAssessmentOf candidate.
    if _contains_any(sl, ["assess", "assessment"]):
        cand = "requiresAssessmentOf candidate (needs review)"
        if subject_id and object_id:
            return None, cand
    return None, cand


def _infer_negation(sentence: str) -> bool:
    sl = sentence.lower()
    return bool(re.search(r"\bnot\b|\bno\b|\bwithout\b", sl))


def _required_clinical_variables(subject_id: str, object_id: str) -> List[str]:
    # Minimal variable requirements for feasibility smoke checks.
    # (We intentionally do NOT proxy unavailable concepts.)
    req: List[str] = []
    exposure_map = {
        "BenzodiazepineExposure": ["benzodiazepine_exposure"],
        "PropofolExposure": ["propofol_exposure"],
        "DexmedetomidineExposure": ["dexmedetomidine_exposure"],
        "OpioidExposure": ["opioid_exposure"],
    }
    if subject_id in exposure_map:
        req.extend(exposure_map[subject_id])
    if object_id in ["Delirium"]:
        # In PADIS, CAM-ICU and/or RASS are common. We keep them as required variables.
        req.extend(["CAM-ICU", "RASS", "delirium_assessment"])
    if object_id in ["Agitation", "Sedation"]:
        req.extend(["RASS"])
    if object_id == "MechanicalVentilation":
        req.extend(["mechanical_ventilation"])
    return sorted(set(req))


def _concept_to_rule_skeleton(
    sentence: str,
    source_page: int,
) -> Optional[Dict[str, Any]]:
    hits = _keyword_hits(sentence)
    if not hits:
        return None

    # object/object-like: prioritize delirium mentions if present
    object_id = hits.get("Delirium") or hits.get("Agitation") or hits.get("Sedation") or hits.get("MechanicalVentilation")
    # subject: pick first exposure state if present
    subject_id = (
        hits.get("BenzodiazepineExposure")
        or hits.get("PropofolExposure")
        or hits.get("DexmedetomidineExposure")
        or hits.get("OpioidExposure")
        or hits.get("Pain")
    )
    if subject_id is None or object_id is None:
        return None
    subject_id_str = subject_id.concept_id
    object_id_str = object_id.concept_id

    if subject_id_str == object_id_str:
        return None

    source_type = _infer_source_type(sentence)
    relation, relation_candidate = _infer_relation(sentence, subject_id_str, object_id_str)

    rule_id = None  # filled later
    neg = _infer_negation(sentence)
    required_vars = _required_clinical_variables(subject_id_str, object_id_str)

    return {
        "rule_id": rule_id,
        "padis_domain": "A-PADIS",
        "source_page": source_page,
        "source_section": "smoke_extract_sedation_delirium (unknown until full parsing)",
        "source_text": sentence[:500],
        "recommendation_text": sentence[:500],
        "patient_population": "Adult ICU",
        "subject": subject_id_str,
        "relation": relation or "pending",
        "relation_candidate": relation_candidate,
        "object": object_id_str,
        "recommendation_strength": "pending",
        "evidence_quality": "pending",
        "source_type": source_type,
        "required_clinical_variables": required_vars,
        "mimic_availability": "undecided",
        "confidence": 0.4 if relation is None else 0.7,
        "review_status": "pending",
        "rejection_reason": None,
        "reviewer_note": None,
        "experiment_usable": "undecided",
        "negation_present": neg,
    }


def _extract_excerpt_pages(pages: List[str], excerpt_pages: int) -> Tuple[int, int, List[str]]:
    """
    Choose a conservative excerpt window around first hits for Sedation/Delirium.
    Returns (start_page_1indexed, end_page_1indexed, excerpt_pages_text).
    """
    page_indices: List[int] = []
    for i, txt in enumerate(pages):
        t = txt.lower()
        if "delirium" in t or "cam-icu" in t or "rass" in t or "agitation" in t or "sedation" in t:
            page_indices.append(i)
            # start at first meaningful page
            break

    if not page_indices:
        raise RuntimeError("Could not find Sedation/Delirium keywords in any PDF page.")

    start_idx = page_indices[0]
    end_idx = min(len(pages) - 1, start_idx + max(0, excerpt_pages - 1))
    excerpt_texts = pages[start_idx : end_idx + 1]
    return start_idx + 1, end_idx + 1, excerpt_texts


def _load_gold_set(path: Path) -> List[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("gold_set", data if isinstance(data, list) else [])


def _normalize_for_match(s: str) -> str:
    return _normalize_ws(s).lower()


def _gold_validation(
    rules: List[dict],
    gold_set: List[dict],
    out_path: Path,
) -> None:
    """
    Compare extraction results against a small manually curated gold set.
    Gold item format expected:
      { gold_id, sentence, expected_subject, expected_relation, expected_object, expected_source_type, expected_negation_present, expected_source_page }
    """
    if not gold_set:
        out_path.write_text(
            "# Gold smoke validation\n\n"
            "gold_set file not found or empty. Fill `padis/rules/gold_set_smoke.json` with 10~20 sentences and rerun.\n",
            encoding="utf-8",
        )
        return

    # Build index by normalized sentence text.
    rule_by_sentence: Dict[str, List[dict]] = {}
    for r in rules:
        key = _normalize_for_match(r.get("source_text", ""))
        rule_by_sentence.setdefault(key, []).append(r)

    rows: List[str] = []
    correct = 0
    total = 0
    for g in gold_set:
        total += 1
        g_sentence = g.get("sentence", "")
        key = _normalize_for_match(g_sentence)
        cand_rules = rule_by_sentence.get(key, [])

        if not cand_rules:
            rows.append(f"- {g.get('gold_id')}: NO_MATCH")
            continue

        # Pick first candidate (should be unique in smoke mode)
        r = cand_rules[0]
        ok = True
        checks = [
            ("subject", g.get("expected_subject"), r.get("subject")),
            ("object", g.get("expected_object"), r.get("object")),
            ("source_type", g.get("expected_source_type"), r.get("source_type")),
            ("negation_present", g.get("expected_negation_present"), r.get("negation_present")),
        ]
        # relation direction may be "pending"; allow "pending" mismatch but count it.
        checks.append(("relation", g.get("expected_relation"), r.get("relation")))

        for name, exp, got in checks:
            if exp is None:
                continue
            if got != exp:
                ok = False
                break

        if ok:
            correct += 1
            rows.append(f"- {g.get('gold_id')}: OK")
        else:
            rows.append(
                f"- {g.get('gold_id')}: MISMATCH "
                f"(exp subject={g.get('expected_subject')}, got={r.get('subject')}; "
                f"exp rel={g.get('expected_relation')}, got={r.get('relation')}; "
                f"exp object={g.get('expected_object')}, got={r.get('object')}; "
                f"page exp={g.get('expected_source_page')}, got={r.get('source_page')})"
            )

    acc = correct / max(1, total)
    md = [
        "# Gold smoke validation",
        "",
        f"- gold items: {total}",
        f"- exact match (all checked fields): {correct} / {total} (acc={acc:.2f})",
        "",
        "## Per-item",
        *rows,
        "",
    ]
    out_path.write_text("\n".join(md), encoding="utf-8")


def _create_review_csv(rules: List[dict], out_csv: Path) -> None:
    # CSV writer without dependency on pandas.
    import csv

    # Use a stable column set to keep review manageable.
    cols = [
        "rule_id",
        "padis_domain",
        "source_page",
        "source_section",
        "source_text",
        "patient_population",
        "subject",
        "relation",
        "relation_candidate",
        "object",
        "recommendation_strength",
        "evidence_quality",
        "source_type",
        "required_clinical_variables",
        "mimic_availability",
        "confidence",
        "review_status",
        "approved?",
        "corrected_subject",
        "corrected_relation",
        "corrected_object",
        "reviewer_note",
        "experiment_usable",
        "negation_present",
        "rejection_reason",
    ]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rules:
            # lists → join for CSV friendliness
            r2 = dict(r)
            r2["required_clinical_variables"] = ",".join(r2.get("required_clinical_variables") or [])
            # Human review fields (editable)
            r2["approved?"] = ""
            r2["corrected_subject"] = ""
            r2["corrected_relation"] = ""
            r2["corrected_object"] = ""
            # Keep reviewer_note initial empty (not the extracted reviewer_note)
            r2["reviewer_note"] = r2.get("reviewer_note") or ""
            w.writerow({c: r2.get(c) for c in cols})


def _extract_current_feature_schema(repo_root: Path) -> Tuple[List[str], List[str]]:
    """
    Parse NeSy-SMP/data/preprocessing.py for numeric features (column_num) and comorbidity columns.
    This is only used for 'light feasibility check' in Phase 1.
    """
    prep = repo_root / "NeSy-SMP" / "data" / "preprocessing.py"
    if not prep.exists():
        return [], []
    text = prep.read_text(encoding="utf-8")

    col_match = re.search(r"for column_num in \\[(.*?)\\]:", text, flags=re.S)
    cols: List[str] = []
    if col_match:
        cols = re.findall(r'"([^"]+)"', col_match.group(1))

    comorb_match = re.search(r"comorbidities\\s*=\\s*\\[(.*?)\\]\\s*\\n", text, flags=re.S)
    comorbs: List[str] = []
    if comorb_match:
        comorbs = re.findall(r"'([^']+)'", comorb_match.group(1))

    # Normalize to lower for match
    cols_norm = [c.lower() for c in cols]
    comorbs_norm = [c.lower() for c in comorbs]
    return cols_norm, comorbs_norm


def _feasibility_by_feature_schema(required_vars: List[str], feature_cols: List[str], comorbs: List[str]) -> str:
    """
    Return experiment_usable:
      - yes: all required vars appear in available schema keywords
      - partial: some appear
      - no: none appear
      - undecided: fallback when we can't map required var → schema keyword
    """
    if not required_vars:
        return "undecided"

    # Very conservative matching: treat CAM-ICU/RASS/propofol/etc as unavailable
    # unless the schema explicitly contains them.
    required_norm = [v.lower() for v in required_vars]
    hits = []
    for v in required_norm:
        if v in feature_cols or v in comorbs:
            hits.append(v)
        else:
            # allow loose match: remove underscores and punctuation
            v_loose = re.sub(r"[^a-z0-9]", "", v)
            col_loose_hits = [c for c in feature_cols if re.sub(r"[^a-z0-9]", "", c).find(v_loose) >= 0]
            if col_loose_hits:
                hits.append(v)

    if len(hits) == 0:
        return "no"
    if len(hits) == len(required_norm):
        return "yes"
    return "partial"


def _run_feasibility_update(
    rules: List[dict],
    repo_root: Path,
    out_md: Path,
) -> List[dict]:
    feature_cols, comorbs = _extract_current_feature_schema(repo_root)
    # Count by experiment_usable
    counts = {"yes": 0, "partial": 0, "no": 0, "undecided": 0}

    updated: List[dict] = []
    for r in rules:
        req_vars = r.get("required_clinical_variables") or []
        usable = _feasibility_by_feature_schema(req_vars, feature_cols, comorbs)
        r2 = dict(r)
        r2["experiment_usable"] = usable
        updated.append(r2)
        counts[usable] = counts.get(usable, 0) + 1

    md_lines = [
        "# MIMIC feasibility (smoke)",
        "",
        "This is a *light* feasibility check using the current repo's feature schema "
        "(from `NeSy-SMP/data/preprocessing.py`), not full cohort coverage.",
        "",
        "## Counts (by rule)",
        f"- yes: {counts['yes']}",
        f"- partial: {counts['partial']}",
        f"- no: {counts['no']}",
        f"- undecided: {counts['undecided']}",
        "",
        "## Notes",
        "- If PADIS variables (CAM-ICU/RASS/sedatives) are absent from current schema, rules will be marked `no` or `partial`.",
        "- After full mapping + coverage, this report should be replaced by a true cohort-level coverage analysis.",
        "",
    ]
    out_md.write_text("\n".join(md_lines), encoding="utf-8")
    return updated


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--excerpt-pages", type=int, default=4)
    ap.add_argument("--gold-set-json", type=Path, default=Path("padis/rules/gold_set_smoke.json"))
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = args.pdf
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    pages = _read_text_pages(pdf_path)
    start_page, end_page, excerpt_pages_text = _extract_excerpt_pages(pages, args.excerpt_pages)
    print(f"[PADIS smoke] excerpt pages: {start_page}..{end_page}")

    rules: List[dict] = []
    rule_counter = 0
    # Extract candidates per page.
    for rel_page_idx, page_text in enumerate(excerpt_pages_text):
        abs_page = start_page + rel_page_idx
        sentences = _split_sentences(page_text)
        for sent in sentences:
            sk = _concept_to_rule_skeleton(sent, abs_page)
            if sk is None:
                continue
            rule_counter += 1
            rule_id = f"D-{rule_counter:03d}"
            sk["rule_id"] = rule_id
            rules.append(sk)

    # Cap for smoke readability.
    rules = rules[:200]
    raw_out = args.out_dir / DEFAULT_OUT_RULES_RAW
    raw_out.write_text(json.dumps({"generated_at": dt.datetime.now().isoformat(), "rules": rules}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[PADIS smoke] extracted rules(raw): {len(rules)} -> {raw_out}")

    # Gold validation (before human review)
    gold_set = _load_gold_set(args.gold_set_json)
    gold_report_out = args.out_dir / DEFAULT_OUT_GOLD_VALIDATION
    _gold_validation(rules, gold_set, gold_report_out)
    print(f"[PADIS smoke] gold report: {gold_report_out}")

    # Lightweight MIMIC feasibility check immediately after smoke extraction.
    mimic_report_out = args.out_dir / DEFAULT_OUT_MIMIC_COVERAGE
    rules = _run_feasibility_update(rules, repo_root=repo_root, out_md=mimic_report_out)
    # Update raw json with experiment_usable field
    raw_out.write_text(json.dumps({"generated_at": dt.datetime.now().isoformat(), "rules": rules}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[PADIS smoke] mimic feasibility: {mimic_report_out}")

    # Also write the expected filename for Phase 1 deliverable listing.
    mimic_report_final = args.out_dir / DEFAULT_OUT_MIMIC_COVERAGE_FINAL_NAME
    try:
        mimic_report_final.write_text(mimic_report_out.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        # If anything fails, don't block extraction; just warn.
        print(f"[WARN] could not write {mimic_report_final}")

    # Human review CSV (pending by default, but with experiment_usable already filled).
    review_csv_out = args.out_dir / DEFAULT_OUT_REVIEW_CSV
    _create_review_csv(rules, review_csv_out)
    print(f"[PADIS smoke] review csv: {review_csv_out}")


if __name__ == "__main__":
    main()

