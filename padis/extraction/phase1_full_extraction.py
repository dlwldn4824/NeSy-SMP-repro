from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader


DEFAULT_OUT_RULES_RAW = "padis_rules_raw.json"
DEFAULT_OUT_REVIEW_CSV = "padis_rules_review.csv"
DEFAULT_OUT_GOLD_VALIDATION = "padis_smoke_gold_validation_report.md"
DEFAULT_OUT_GOLD_DRAFT_MD = "gold_set_draft.md"


def _read_text_pages(pdf_path: Path) -> List[str]:
    reader = PdfReader(str(pdf_path))
    pages: List[str] = []
    for p in reader.pages:
        pages.append((p.extract_text() or "").strip())
    return pages


def _split_sentences(text: str) -> List[str]:
    text = text.replace("\u00ad", "")
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 40]


def _extract_excerpt_pages_full(pages: List[str]) -> Tuple[int, int]:
    """
    Identify a union window covering Sedation/Agitation + Delirium sections.
    Heuristic:
      - start = first page containing 'agitation'/'sedation'/'agitation/sedation'
      - end   = first page after delirium_start containing 'immobility' or 'sleep'
    """
    texts = [p.lower() for p in pages]

    def is_body_page(t: str) -> bool:
        # guideline "body" tends to include recommendation/evidence verbs.
        return ("should" in t) or ("recommend" in t) or ("evidence" in t) or ("recommendation" in t)

    sedation_start_idx: Optional[int] = None
    for i, t in enumerate(texts):
        if ("agitation" in t and "sedation" in t) and is_body_page(t):
            sedation_start_idx = i
            break
    if sedation_start_idx is None:
        for i, t in enumerate(texts):
            if ("agitation" in t or "sedation" in t) and is_body_page(t):
                sedation_start_idx = i
                break
    if sedation_start_idx is None:
        raise RuntimeError("Could not detect Sedation/Agitation section start.")

    delirium_start_idx: Optional[int] = None
    for i in range(sedation_start_idx, len(texts)):
        if ("delirium" in texts[i]) and is_body_page(texts[i]):
            delirium_start_idx = i
            break
    if delirium_start_idx is None:
        # fallback: allow header-only if no body page is detected
        for i in range(sedation_start_idx, len(texts)):
            if "delirium" in texts[i]:
                delirium_start_idx = i
                break
    if delirium_start_idx is None:
        raise RuntimeError("Could not detect Delirium section start (even with fallback).")

    end_idx: Optional[int] = None
    for i in range(delirium_start_idx + 1, len(texts)):
        # Many guideline PDFs have a "topics list" on the same page as section headers.
        # Only treat the end keyword as a boundary if delirium is no longer mentioned on that page.
        end_hit = ("immobility" in texts[i]) or ("sleep" in texts[i])
        if end_hit and ("delirium" not in texts[i]) and is_body_page(texts[i]):
            end_idx = i - 1
            break
    if end_idx is None:
        end_idx = len(texts) - 1

    # Fallback: if the detected window is implausibly small (header/topics list artifacts),
    # extend conservatively to cover real body text.
    if end_idx - sedation_start_idx < 5:
        end_idx = min(len(texts) - 1, sedation_start_idx + 30)

    # Convert to 1-indexed bounds; ensure monotonicity
    return sedation_start_idx + 1, end_idx + 1


def _contains_any(haystack: str, needles: List[str]) -> bool:
    s = haystack.lower()
    return any(n.lower() in s for n in needles)


def _matches_any_regex(haystack: str, regexes: List[str]) -> bool:
    s = haystack.lower()
    return any(re.search(rx, s, flags=re.I) for rx in regexes)


def _matches_any_regex(haystack: str, regexes: List[str]) -> bool:
    s = haystack.lower()
    return any(re.search(rx, s, flags=re.I) for rx in regexes)


def _normalize_pdf_text(text: str) -> str:
    """Join PDF line-break hyphenations and collapse whitespace."""
    t = (text or "").replace("\u00ad", "")
    t = re.sub(r"(\w)-\s+(\w)", r"\1\2", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.lower()


def _is_positive_outcome_without_phrase(sl: str) -> bool:
    """'days without delirium' is a favorable outcome, not clinical negation."""
    return bool(
        _matches_any_regex(
            sl,
            [
                r"days without coma or delirium",
                r"without coma or delirium",
                r"more icu days without",
            ],
        )
    )


def _is_meta_negation_phrase(sl: str) -> bool:
    """Negation about guideline/process, not clinical effect direction."""
    return bool(
        _matches_any_regex(
            sl,
            [
                r"not\s+considered\s+in",
                r"not\s+included\s+in",
                r"developing\s+this\s+recommendation",
                r"not\s+always\s+rapidly",
                r"either delirium or not always",
            ],
        )
    )


def _is_null_clinical_effect(sl: str) -> bool:
    """Evidence of no effect / no association — do not infer positive risk relation."""
    return bool(
        _matches_any_regex(
            sl,
            [
                r"not\s+associated\s+with",
                r"no\s+significant\s+(?:difference|benefit|reduction|effect)",
                r"not\s+to\s+alter",
                r"do\s+not\s+alter",
                r"does\s+not\s+alter",
                r"did\s+not\s+(?:reduce|increase|show)",
                r"failed\s+to\s+show",
                r"no\s+improvements?\s+in",
                r"not\s+show\s+a\s+significant",
                r"were\s+similar\s+between",
                r"no\s+relationship\s+between",
            ],
        )
    )


def _is_no_recommendation_statement(sl: str) -> bool:
    return bool(
        _matches_any_regex(
            sl,
            [
                r"remains\s+unclear",
                r"panel\s+was\s+unable\s+to\s+issue",
                r"insufficient\s+evidence\s+to\s+make\s+a\s+recommendation",
            ],
        )
    )


def _is_research_gap_statement(sl: str) -> bool:
    return bool(
        _matches_any_regex(
            sl,
            [
                r"insufficient\s*[- ]?\s*evidence",
                r"lack\s*[- ]?\s*of\s*[- ]?\s*evidence",
                r"limited\s*[- ]?\s*evidence",
                r"no\s*[- ]?\s*evidence\s+to",
                r"not\s+been\s+fully\s+elucidated",
                r"not\s+fully\s+elucidated",
                r"literature\s+gaps",
                r"remaining\s+literature\s+gaps",
                r"research\s+needs",
                r"further\s+research",
                r"do\s+not\s+allow\s+for\s+discrimination",
                r"no\s+other\s+study\s+informs",
                r"cannot\s+be\s+discriminat",
                r"needs?\s+to\s+be\s+studied",
                r"\bis\s+unknown\b",
                r"^evidence\s+gaps:",
                r"cannot\s+fully\s+elucidate",
                r"inadequate\s+to\s+confirm",
                r"^conclusions:.*literature\s+gaps",
            ],
        )
    )


def _is_explicit_recommendation(sl: str) -> bool:
    """
    Distinguish directive recommendation text from rationale sentences that
    merely mention the word 'recommendation' (e.g. 'developing this recommendation').
    """
    if _matches_any_regex(
        sl,
        [
            r"^recommendation\s*:",
            r"\bwe\s+recommend\b",
            r"\bwe\s+suggest\b",
            r"\bgood\s+practice\s+statement\b",
            r"\bconditional\s+recommendation\b",
            r"\bstrong\s+recommendation\b",
            r"\b(?:guidelines?|panel)\s+suggest\b",
            r"\bbest\s+practic",
            r"\bbenefits of widespread delirium assessment\b",
            r"\bcould be used\b",
        ],
    ):
        return True
    # PADIS-style: 'suggest (in a conditional recommendation) that ...'
    if "suggest" in sl and "recommendation" in sl and "that" in sl:
        return True
    if re.search(r"\bshould\b", sl) and not _is_research_gap_statement(sl):
        return True
    return False


def _null_effect_blocks_delirium_relation(sl: str) -> bool:
    """Only suppress directional relation when null-effect language targets delirium."""
    if not _is_null_clinical_effect(sl) or "delirium" not in sl:
        return False
    return bool(
        _matches_any_regex(
            sl,
            [
                r"not\s+associated\s+with[^.;]{0,120}delirium",
                r"no\s+significant[^.;]{0,120}delirium",
                r"not\s+to\s+alter[^.;]{0,120}delirium",
                r"no\s+improvements?[^.;]{0,120}delirium",
                r"did\s+not\s+(?:reduce|show)[^.;]{0,120}delirium",
                r"delirium[^.;]{0,120}no\s+significant",
                r"delirium[^.;]{0,120}not\s+associated",
            ],
        )
    )


def _is_evidence_statement(sl: str) -> bool:
    if _is_research_gap_statement(sl):
        return False
    if _matches_any_regex(
        sl,
        [
            r"\brct\b",
            r"\bstudy\b",
            r"\bstudies\b",
            r"\btrial\b",
            r"\bobservational\b",
            r"\brandomized\b",
            r"\bpooled\s+analysis\b",
            r"\bdemonstrated\b",
            r"\bshowed\b",
            r"\bfound\b",
            r"\bcompared\s+with\b",
            r"\bcompared\s+to\b",
            r"\bsignificantly\s+(?:lower|higher|greater|reduced)",
            r"\bstrongly\s+shown\b",
            r"\bstrong\s+evidence\b",
            r"\bpredicts?\b",
            r"\bpredictor\b",
            r"\bguideline\s+evidence\b",
            r"\bcorrelat(?:e|ion)\b",
            r"\bworse\s+outcomes\b",
            r"\bcrossover\s+study\b",
            r"\bfive\s+rcts\b",
            r"\bthis evidence\s+suggests\b",
        ],
    ):
        return True
    return False


def _infer_source_type(sentence: str) -> str:
    sl = _normalize_pdf_text(sentence)

    # 1) Negative recommendation
    if _matches_any_regex(
        sl,
        [
            r"no\s*[- ]?\s*recommendation",
            r"not\s*[- ]?\s*recommended",
            r"do\s*not\s*[- ]?\s*recommend",
            r"should\s*not",
            r"shouldn['’]t",
        ],
    ):
        return "no_recommendation"

    # 2) Cannot issue recommendation (insufficient clarity)
    if _is_no_recommendation_statement(sl):
        return "no_recommendation"

    # 3) Research gap / insufficient knowledge
    if _is_research_gap_statement(sl):
        return "research_gap"

    # 4) Explicit recommendation directive
    if _is_explicit_recommendation(sl):
        return "recommendation"

    # 4) Null-effect risk statements (e.g. sedation not associated with delirium reduction)
    if _is_null_clinical_effect(sl) and _contains_any(sl, ["delirium", "sedation", "risk"]):
        if not _matches_any_regex(
            sl,
            [
                r"\bstudy\b",
                r"\btrial\b",
                r"\bpooled\s+analysis\b",
                r"\bstrongly\s+shown\b",
                r"\bthis evidence\s+suggests\b",
                r"\bfound no relationship\b",
                r"^\w+\s+\(\d",
            ],
        ):
            return "risk_factor_statement"

    # 5) Evidence / study results
    if _is_evidence_statement(sl):
        return "evidence"

    # 6) Risk-factor framing without clear study citation
    if _contains_any(
        sl,
        [
            "increased risk for",
            "risk factor",
            "associated with delirium",
            "increases risk",
        ],
    ):
        return "risk_factor_statement"

    return "pending"


def _infer_negation(sentence: str) -> bool:
    sl = _normalize_pdf_text(sentence)
    if _is_positive_outcome_without_phrase(sl):
        return False
    if _is_meta_negation_phrase(sl):
        return False
    if _is_null_clinical_effect(sl):
        return True
    if _is_research_gap_statement(sl) and _matches_any_regex(
        sl,
        [
            r"not\s+been\s+fully\s+elucidated",
            r"do\s+not\s+allow",
            r"no\s+other\s+study",
            r"cannot\s+fully\s+elucidate",
            r"inadequate\s+to\s+confirm",
            r"literature\s+gaps",
            r"remaining\s+literature\s+gaps",
        ],
    ):
        return True
    if _is_no_recommendation_statement(sl):
        return True
    # Generic negation only when tied to clinical outcome language
    if re.search(r"\bnot\b|\bno\b|\bwithout\b", sl):
        if _contains_any(sl, ["delirium", "sedation", "risk", "associated", "effect", "reduce", "increase"]):
            return True
    return False


def _infer_relation(sentence: str, subject_id: str, object_id: str) -> Tuple[Optional[str], str]:
    sl = _normalize_pdf_text(sentence)

    if _is_research_gap_statement(sl):
        return None, "null_effect_or_gap (no directional relation)"

    # Null effect scoped to delirium — preserve no relation
    if _null_effect_blocks_delirium_relation(sl):
        return None, "null_effect_or_gap (no directional relation)"

    # preferredOver
    if "rather than" in sl or "prefer" in sl or "preferably" in sl:
        if subject_id != object_id:
            return "preferredOver", "preferredOver (heuristic: rather than/prefer)"

    # Predictor language
    if re.search(r"\bpredicts?\s+(?:increased\s+)?risk\b", sl) or "predictor" in sl:
        return "increasesRiskOf", "increasesRiskOf (cue: predicts risk)"

    # Decrease cues (before generic 'increase' matching)
    if _matches_any_regex(
        sl,
        [
            r"\bdecreased\s+(?:incidence|risk|rate)",
            r"\blower\s+proportion",
            r"\bshorter\s+duration",
            r"\bsignificantly\s+lower",
            r"\breduced\s+delirium",
            r"\bless\s+likely",
            r"\bsignificant\s+reduction\s+in\s+delirium",
            r"\bwithout\s+coma\s+or\s+delirium",
            r"\bdays\s+without\s+coma\s+or\s+delirium",
        ],
    ):
        return "decreasesRiskOf", "decreasesRiskOf (cue: decrease/lower)"

    # Association without explicit direction
    if re.search(r"\bassociation\s+with\s+delirium\b", sl) or re.search(
        r"\bassociated\s+with\s+delirium\b", sl
    ):
        return "associatedWith", "associatedWith (cue: association with delirium)"

    # Comparative delirium outcome (e.g. dex benefit vs benzodiazepine on delirium RR)
    if "delirium" in sl and ("compared with" in sl or "compared to" in sl):
        if _matches_any_regex(sl, [r"\bbenefit\b", r"\brr\b", r"\breduced\b", r"\blower\b", r"\b0\.\d+"]):
            return "increasesRiskOf", "increasesRiskOf (cue: comparative delirium outcome)"

    # Increase / association cues
    if _matches_any_regex(
        sl,
        [
            r"\bincreased\s+risk",
            r"\bincreases?\s+risk",
            r"\bassociated\s+with",
            r"\bgreater\s+benefit",
            r"\bhigher\s+",
        ],
    ):
        if "associated with" in sl or re.search(r"\bassociated\b", sl):
            return "associatedWith", "associatedWith (cue: associated with)"
        return "increasesRiskOf", "increasesRiskOf (cue: risk/increase)"

    # Assessment sequencing — avoid 'delirium assessment' as requiresAssessmentOf
    if re.search(r"\bassess(?:ment)?\s+of\b", sl) or re.search(r"\brequires?\s+assessment\b", sl):
        return None, "requiresAssessmentOf candidate (needs review)"
    if any(k in sl for k in ["treat before", "prior to"]):
        return None, "shouldBeTreatedBefore candidate (needs review)"

    return None, f"unknown_relation (subject={subject_id}, object={object_id})"


def _keyword_hits(sentence: str) -> Dict[str, str]:
    """
    PADIS Phase1 concept hit list (conservative):
    - focus on exposures/states relevant to Agitation/Sedation + Delirium
    - exclude Pain as subject for now to reduce noise
    """
    s = _normalize_pdf_text(sentence)
    hits: Dict[str, str] = {}
    if any(k in s for k in ["benzodiazepine", "lorazepam", "midazolam", "diazepam"]):
        hits["BenzodiazepineExposure"] = "benzodiazepine"
    if "propofol" in s:
        hits["PropofolExposure"] = "propofol"
    if any(k in s for k in ["dexmedetomidine", "precedex"]):
        hits["DexmedetomidineExposure"] = "dexmedetomidine"
    if any(k in s for k in ["opioid", "morphine", "fentanyl", "hydromorphone"]):
        hits["OpioidExposure"] = "opioid"
    if any(
        k in s
        for k in [
            "haloperidol",
            "antipsychotic",
            "quetiapine",
            "ziprasidone",
            "risperidone",
            "statin",
            "ketamine",
        ]
    ):
        hits["Sedation"] = "pharmacologic_delirium_treatment"

    # delirium/object
    if "delirium" in s:
        hits["Delirium"] = "delirium"

    # assessment/state
    if "rass" in s:
        hits["RASS"] = "rass"
    if any(k in s for k in ["cam-icu", "camicu", "cam icu"]):
        hits["CAM_ICU"] = "cam-icu"
    if "sedation" in s:
        hits["Sedation"] = "sedation"
    if "agitation" in s:
        hits["Agitation"] = "agitation"
    if "mechanical ventilation" in s or "ventilator" in s:
        hits["MechanicalVentilation"] = "mechanical ventilation"
    return hits


def _required_clinical_variables(subject_id: str, object_id: str) -> List[str]:
    req: List[str] = []
    exposure_map = {
        "BenzodiazepineExposure": ["benzodiazepine_exposure"],
        "PropofolExposure": ["propofol_exposure"],
        "DexmedetomidineExposure": ["dexmedetomidine_exposure"],
        "OpioidExposure": ["opioid_exposure"],
    }
    req.extend(exposure_map.get(subject_id, []))
    if object_id == "Delirium":
        req.extend(["CAM-ICU", "RASS", "delirium_assessment"])
    if subject_id in ["Sedation", "Agitation"]:
        req.extend(["RASS"])
    if subject_id == "MechanicalVentilation":
        req.extend(["mechanical_ventilation"])
    return sorted(set(req))


def _concept_to_rule(sentence: str, source_page: int) -> Optional[Dict[str, Any]]:
    hits = _keyword_hits(sentence)
    if "Delirium" not in hits:
        return None

    # Filter out meta/boilerplate sentences that mention delirium in a list/acknowledgement
    # without actionable guideline signals.
    focus_keywords = [
        "should",
        "recommend",
        "evidence",
        "insufficient",
        "not recommended",
        "risk",
        "associated",
        "increase",
        "decrease",
        "sedation",
        "agitation",
        "rass",
        "cam-icu",
        "camicu",
        "benzodiazepine",
        "propofol",
        "dexmedetomidine",
        "opioid",
        "ventilator",
        "mechanical ventilation",
    ]
    if not any(k in sentence.lower() for k in focus_keywords):
        return None

    object_id = "Delirium"

    # subject priority: exposures > sedation/agitation states
    subject_id = None
    for cid in [
        "BenzodiazepineExposure",
        "PropofolExposure",
        "DexmedetomidineExposure",
        "OpioidExposure",
        "Sedation",
        "Agitation",
        "RASS",
        "CAM_ICU",
        "MechanicalVentilation",
    ]:
        if cid in hits:
            subject_id = cid
            break

    sl_norm = _normalize_pdf_text(sentence)
    if ("versus" in sl_norm or " vs " in sl_norm) and _is_research_gap_statement(sl_norm):
        for alt in ["PropofolExposure", "DexmedetomidineExposure"]:
            if alt in hits:
                subject_id = alt
                break

    if subject_id is None:
        return None
    if subject_id == object_id:
        return None

    source_type = _infer_source_type(sentence)
    relation, relation_candidate = _infer_relation(sentence, subject_id, object_id)

    return {
        "rule_id": None,  # fill later
        "padis_domain": "A-PADIS",
        "source_page": source_page,
        "source_section": "PADIS Full: Agitation/Sedation + Delirium (heuristic section window)",
        "source_text": sentence[:500],
        "recommendation_text": sentence[:500],
        "patient_population": "Adult ICU",
        "subject": subject_id,
        "relation": relation or "pending",
        "relation_candidate": relation_candidate,
        "object": object_id,
        "recommendation_strength": "pending",
        "evidence_quality": "pending",
        "source_type": source_type,
        "required_clinical_variables": _required_clinical_variables(subject_id, object_id),
        "mimic_availability": "undecided",
        "confidence": 0.5 if relation is None else 0.75,
        "review_status": "pending",
        "rejection_reason": None,
        "reviewer_note": None,
        "experiment_usable": "undecided",
        "negation_present": _infer_negation(sentence),
    }


def _extract_current_feature_schema(repo_root: Path) -> Tuple[List[str], List[str]]:
    """
    same heuristic as smoke: parse preprocessing.py fixed schema keywords.
    """
    prep = repo_root / "NeSy-SMP" / "data" / "preprocessing.py"
    if not prep.exists():
        return [], []
    text = prep.read_text(encoding="utf-8")

    col_match = re.search(r"for column_num in \[(.*?)\]:", text, flags=re.S)
    cols: List[str] = []
    if col_match:
        cols = re.findall(r'"([^"]+)"', col_match.group(1))

    comorb_match = re.search(r"comorbidities\s*=\s*\[(.*?)\]\s*\n", text, flags=re.S)
    comorbs: List[str] = []
    if comorb_match:
        comorbs = re.findall(r"'([^']+)'", comorb_match.group(1))

    return [c.lower() for c in cols], [c.lower() for c in comorbs]


def _feasibility_by_feature_schema(required_vars: List[str], feature_cols: List[str], comorbs: List[str]) -> str:
    if not required_vars:
        return "undecided"
    required_norm = [v.lower() for v in required_vars]
    hits: List[str] = []
    for v in required_norm:
        if v in feature_cols or v in comorbs:
            hits.append(v)
        else:
            v_loose = re.sub(r"[^a-z0-9]", "", v)
            col_loose_hits = [c for c in feature_cols if re.sub(r"[^a-z0-9]", "", c).find(v_loose) >= 0]
            if col_loose_hits:
                hits.append(v)
    if len(hits) == 0:
        return "no"
    if len(hits) == len(required_norm):
        return "yes"
    return "partial"


def _make_review_csv_and_write(
    rules: List[dict],
    out_csv: Path,
) -> None:
    import csv

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
            r2 = dict(r)
            r2["required_clinical_variables"] = ",".join(r2.get("required_clinical_variables") or [])
            r2["approved?"] = ""
            r2["corrected_subject"] = ""
            r2["corrected_relation"] = ""
            r2["corrected_object"] = ""
            r2["reviewer_note"] = ""
            w.writerow({c: r2.get(c) for c in cols})


def _write_gold_set_draft(rules: List[dict], out_json: Path, out_md: Path, n: int = 15) -> List[dict]:
    """
    Draft gold selection for smoke validation pipeline.
    We intentionally label it as draft; humans can correct later.
    """
    # Prefer non-pending relation / richer source_type.
    scored: List[Tuple[float, dict]] = []
    for r in rules:
        score = 0.0
        if r.get("relation") and r.get("relation") != "pending":
            score += 1.0
        if r.get("source_type") in {"recommendation", "evidence", "risk_factor_statement", "no_recommendation", "research_gap"}:
            score += 0.5
        if r.get("negation_present"):
            score += 0.2
        score += float(r.get("confidence") or 0.0) / 2.0
        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    chosen = [r for _, r in scored[:n]]

    gold_set: List[dict] = []
    md_lines: List[str] = [
        "# Gold set draft (auto-selected candidates)",
        "",
        "이 파일은 smoke validation 파이프라인이 실제로 동작하도록 *초안*으로만 채워둔 것입니다.",
        "사람이 Sedation/Delirium section에서 문장을 독립적으로 선택하고, 기대값(expected_*)을 검토/수정한 뒤 재실행하는 것을 권장합니다.",
        "",
        "## Chosen sentences",
    ]

    for i, r in enumerate(chosen, start=1):
        g = {
            "gold_id": f"G-{i:03d}",
            "sentence": r.get("source_text"),
            "expected_subject": r.get("subject"),
            "expected_relation": r.get("relation") if r.get("relation") != "pending" else None,
            "expected_object": r.get("object"),
            "expected_source_type": r.get("source_type"),
            "expected_negation_present": r.get("negation_present"),
            "expected_source_page": r.get("source_page"),
        }
        gold_set.append(g)
        md_lines.append(f"- {g['gold_id']} (page {g['expected_source_page']}): {g['sentence']}")

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps({"gold_set": gold_set}, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md.write_text("\n".join(md_lines), encoding="utf-8")
    return gold_set


def _gold_validation(
    rules: List[dict],
    gold_set: List[dict],
    out_path: Path,
) -> None:
    # reuse the logic inline (so this script stays independent)
    if not gold_set:
        out_path.write_text("gold_set empty; please fill and rerun.", encoding="utf-8")
        return

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip()).lower()

    rule_by_sentence: Dict[str, List[dict]] = {}
    for r in rules:
        key = norm(r.get("source_text", ""))
        rule_by_sentence.setdefault(key, []).append(r)

    correct = 0
    total = 0
    lines: List[str] = [
        "# Gold smoke validation",
        "",
    ]
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
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--gold-size", type=int, default=15)
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if not args.pdf.exists():
        raise SystemExit(f"PDF not found: {args.pdf}")

    pages = _read_text_pages(args.pdf)
    start_page, end_page = _extract_excerpt_pages_full(pages)
    print(f"[PADIS full] Sedation/Delirium window pages: {start_page}..{end_page}")

    rules: List[dict] = []
    rule_counter = 0

    for abs_page in range(start_page, end_page + 1):
        idx = abs_page - 1
        if idx < 0 or idx >= len(pages):
            continue
        sentences = _split_sentences(pages[idx])
        for sent in sentences:
            r = _concept_to_rule(sent, abs_page)
            if r is None:
                continue
            rule_counter += 1
            r["rule_id"] = f"D-{rule_counter:03d}"
            rules.append(r)

    # Compute experiment_usable from current preprocessing schema (light check)
    feature_cols, comorbs = _extract_current_feature_schema(repo_root)
    for r in rules:
        req_vars = r.get("required_clinical_variables") or []
        r["experiment_usable"] = _feasibility_by_feature_schema(req_vars, feature_cols, comorbs)

    raw_out = args.out_dir / DEFAULT_OUT_RULES_RAW
    raw_out.write_text(
        json.dumps({"generated_at": dt.datetime.now().isoformat(), "rules": rules}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[PADIS full] extracted rules(raw): {len(rules)} -> {raw_out}")

    review_csv_out = args.out_dir / DEFAULT_OUT_REVIEW_CSV
    _make_review_csv_and_write(rules, review_csv_out)
    print(f"[PADIS full] review csv: {review_csv_out}")

    # Draft + validation
    gold_set_path = repo_root / "padis" / "rules" / "gold_set_smoke.json"
    gold_draft_md = args.out_dir / DEFAULT_OUT_GOLD_DRAFT_MD
    gold_draft_json = args.out_dir / "gold_set_draft.json"
    if gold_set_path.exists():
        gold_doc = json.loads(gold_set_path.read_text(encoding="utf-8"))
        gold_set = gold_doc.get("gold_set", gold_doc if isinstance(gold_doc, list) else [])
        print(f"[PADIS full] using existing gold set: {gold_set_path} ({len(gold_set)} items)")
    else:
        gold_set = _write_gold_set_draft(rules, gold_set_path, gold_draft_md, n=args.gold_size)
        print(f"[PADIS full] gold draft: {len(gold_set)} items -> {gold_set_path}")
    _write_gold_set_draft(rules, gold_draft_json, gold_draft_md, n=args.gold_size)

    gold_report_out = args.out_dir / DEFAULT_OUT_GOLD_VALIDATION
    _gold_validation(rules, gold_set, gold_report_out)
    print(f"[PADIS full] gold report: {gold_report_out}")


if __name__ == "__main__":
    main()

