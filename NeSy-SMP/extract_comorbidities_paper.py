"""논문 원문대로 동반질환 추출 — HPI · PMH 섹션만.

논문 §4 (De Santis et al., EAAI 2026):
  "Comorbidities are extracted from unstructured clinical notes using spaCy-based NER combined with rule-based pattern
   matching. Our custom NLP pipeline focuses on History of Present Illness and Past Medical History sections to identify
   clinically relevant pre-existing conditions."

원문에 없는 세부는 공개 코드(extract_comorbidities.py)를 그대로 따른다:
  - medspaCy 파이프라인(pyrush · target_matcher · context · sectionizer)과 TargetRule 26개 · 정규화(copd·cad)
  - 엔티티 선택: doc._.context_graph.edges 중 modifier 가 NEGATED_EXISTENCE / FAMILY 가 아닌 target
원문을 따라 추가한 것:
  - target 의 section_category 가 history_of_present_illness 또는 past_medical_history 인 것만 남긴다.

참고용으로 같은 문서 처리에서 두 변형도 함께 저장한다 (주 결과 아님):
  B_sec : doc.ents 중 부정·가족력이 아닌 것 (HPI·PMH 섹션)
  A_all : 공개 코드 그대로 (섹션 제한 없음)

사용: python extract_comorbidities_paper.py --notes C:/Users/dlwld/Downloads/discharge_icu.csv.gz \
        --out-dir C:/data/mimic-iv-derived [--hadm-list cohort.csv] [--workers 16] [--limit 200]
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

TARGETS = ["cancer", "pneumonia", "cirrhosis", "dementia", "kidney disease", "kidney failure", "leukemia",
           "hypertension", "HIV", "COPD", "Chronic Obstructive Pulmonary Disease", "diabetes", "diabetes mellitus",
           "trauma", "coronary artery disease", "Coronary Artery Disease", "cad", "heart failure",
           "atrial fibrillation", "acute kidney injury", "peptic ulcer disease", "cerebrovascular accident",
           "metastatic disease", "metastatic cancer", "lymphoma", "AIDS"]
SECTIONS = {"history_of_present_illness", "past_medical_history"}
COMORBIDITIES = ["acute kidney injury", "aids", "atrial fibrillation", "cad", "cancer", "cerebrovascular accident",
                 "cirrhosis", "copd", "dementia", "diabetes", "diabetes mellitus", "heart failure", "hiv",
                 "hypertension", "kidney disease", "kidney failure", "leukemia", "lymphoma", "metastatic cancer",
                 "metastatic disease", "peptic ulcer disease", "pneumonia", "trauma"]
_NLP = None


def norm(t):
    t = t.lower()
    return {"chronic obstructive pulmonary disease": "copd", "coronary artery disease": "cad"}.get(t, t)


def _init():
    global _NLP
    import logging
    import sys as _sys
    try:                                   # PyRuSH 가 loguru DEBUG 를 대량 출력한다 — 결과와 무관, 끈다
        from loguru import logger
        logger.remove()
        logger.add(_sys.stderr, level="WARNING")
    except ImportError:
        pass
    logging.disable(logging.INFO)
    import medspacy
    from medspacy.ner import TargetRule
    _NLP = medspacy.load(medspacy_enable=["medspacy_pyrush", "medspacy_target_matcher", "medspacy_context",
                                          "medspacy_sectionizer"])
    _NLP.get_pipe("medspacy_target_matcher").add([TargetRule(t, "PROBLEM") for t in TARGETS])


def _work(batch):
    out = []
    for hadm_id, text in batch:
        doc = _NLP(text)
        a_sec, a_all, b_sec = set(), set(), set()
        for target, modifier in doc._.context_graph.edges:
            if modifier.rule.category not in ("NEGATED_EXISTENCE", "FAMILY"):
                a_all.add(norm(target.text))
                if target._.section_category in SECTIONS:
                    a_sec.add(norm(target.text))
        for e in doc.ents:
            if not (e._.is_negated or e._.is_family) and e._.section_category in SECTIONS:
                b_sec.add(norm(e.text))
        out.append((hadm_id, a_sec, b_sec, a_all))
    return out


def wide(rows, idx):
    recs = {}
    for hadm_id, s in rows:
        recs.setdefault(hadm_id, set()).update(s)
    df = pd.DataFrame([{"hadm_id": h, **{c: int(c in s) for c in COMORBIDITIES}} for h, s in recs.items()])
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notes", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--hadm-list", type=Path, default=None, help="hadm_id 열이 있는 CSV (이 입원만 처리)")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tag", type=str, default="paper")
    args = ap.parse_args()
    t0 = time.time()

    notes = pd.read_csv(args.notes, usecols=["hadm_id", "note_type", "text"])
    if args.hadm_list is not None:
        keep = set(pd.read_csv(args.hadm_list, usecols=["hadm_id"]).hadm_id)
        notes = notes[notes.hadm_id.isin(keep)]
    if args.limit:
        notes = notes.head(args.limit)
    items = list(zip(notes.hadm_id.astype("int64"), notes.text.fillna("")))
    print(f"notes {len(items):,} · hadm {notes.hadm_id.nunique():,} · types {notes.note_type.value_counts().to_dict()}",
          flush=True)
    batches = [items[i:i + args.batch] for i in range(0, len(items), args.batch)]
    res = []
    if args.workers <= 1:
        _init()
        for i, b in enumerate(batches):
            res += _work(b)
    else:
        with ProcessPoolExecutor(max_workers=args.workers, initializer=_init) as ex:
            for i, r in enumerate(ex.map(_work, batches, chunksize=1)):
                res += r
                if (i + 1) % 20 == 0:
                    el = time.time() - t0
                    print(f"  {len(res):,}/{len(items):,} notes · {el/60:.1f} min · ETA {el/len(res)*(len(items)-len(res))/60:.1f} min",
                          flush=True)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for k, name in [(1, f"comorbidities_{args.tag}_wide.csv"), (2, f"comorbidities_{args.tag}_Bsec_wide.csv"),
                    (3, f"comorbidities_{args.tag}_Aall_wide.csv")]:
        w = wide([(r[0], r[k]) for r in res], None)
        w.to_csv(args.out_dir / name, index=False)
        prev = (w[COMORBIDITIES].mean() * 100).round(1).sort_values(ascending=False)
        any_ = (w[COMORBIDITIES].sum(axis=1) > 0).mean() * 100
        print(f"\n{name}: hadm {len(w):,} · 1개 이상 {any_:.1f}%\n{prev.head(12).to_string()}", flush=True)
    print(f"\n총 {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
