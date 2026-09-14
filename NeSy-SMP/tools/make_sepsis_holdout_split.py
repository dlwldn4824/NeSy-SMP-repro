# -*- coding: utf-8 -*-
"""sepsis gold 관계 트리플을 few-shot 예시(examples) / 채점용(heldout) 으로 나눈다.

왜: 기존 규칙 전부를 예시로 보여주고 같은 규칙으로 채점하면 일치는 아무것도 증명하지 못한다
    (PADIS 선행 실행: 예시 12개 전부가 gold 20개 안, 맞힌 7개 중 5개가 예시).
    → 예시로 보여준 것은 채점에서 따로 떼고, 보여주지 않은 held-out 에서만 recall 을 잰다.

분할 단위는 트리플이 아니라 '주어 개념 그룹'이다.
  같은 주어가 양쪽에 걸치면(예: Cancer→Death 는 예시, Cancer→Sepsis 는 held-out)
  모델이 원문 없이 "동반질환은 둘 다 올린다" 패턴으로 held-out 을 맞힐 수 있다.
  별칭이 겹치는 개념(MeanArterialPressure 별칭에 hypotension, LactateNotClearing 의 라벨이 Lactate)은
  한 그룹으로 묶는다.

사용:
  python tools/make_sepsis_holdout_split.py            # tools/sepsis_holdout_split.json 생성
  python tools/make_sepsis_holdout_split.py --seed 7   # 다른 시드
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")

NORM_REL = {"increaseRiskOf": "increasesRiskOf"}
EXCLUDE_PREFIX = ("rdf-schema", "22-rdf", "subClassOf", "type", "hasOutcome")

CATEGORY = {
    "lab_vital_risk": ["Lactate", "LactateNotClearing", "Bilirubin", "Platelet", "CReactiveProtein",
                       "WhiteBloodCells", "MeanArterialPressure", "Hypotension", "Age"],
    "comorbidity": ["Cancer", "Pneumonia", "HIV", "CirrhosisOfLiver", "KidneyDisease",
                    "CardiacInsufficiency", "ChronicDisease"],
    "sepsis_septicshock": ["Sepsis", "SepticShock"],
}
# 별칭/라벨이 겹쳐 서로의 힌트가 되는 개념은 같은 쪽에 둔다
ALIAS_GROUPS = [["Lactate", "LactateNotClearing"], ["MeanArterialPressure", "Hypotension"]]
# 예시로 뽑을 그룹 수 (카테고리별). 나머지는 held-out.
N_EX_UNITS = {"lab_vital_risk": 3, "comorbidity": 3, "sepsis_septicshock": 1}
EX_TRIPLE_RANGE = (10, 12)   # 30개 중 약 1/3 을 예시로


def norm(s, p, o):
    return (s, NORM_REL.get(p, p), o)


def load_gold_union():
    cfg = json.loads((ROOT / "configs" / "clinical_concepts.json").read_text(encoding="utf-8"))
    src = {}
    for t in cfg["triples"]:
        k = norm(t["subject"], t["predicate"], t["object"])
        if not k[1].startswith(EXCLUDE_PREFIX):
            src.setdefault(k, set()).add("clinical_concepts.json")
    for ln in (ROOT / "rules" / "pkg.txt").read_text(encoding="utf-8").splitlines():
        p = ln.strip().split("\t")
        if len(p) != 3:
            continue
        k = norm(*p)
        if not k[1].startswith(EXCLUDE_PREFIX):
            src.setdefault(k, set()).add("pkg.txt")
    return src


def category_of(subj):
    for c, members in CATEGORY.items():
        if subj in members:
            return c
    raise KeyError(f"카테고리 미지정 개념: {subj}")


def build_units(gold):
    grouped = {m: g[0] for g in ALIAS_GROUPS for m in g}
    units = {}
    for t in gold:
        key = grouped.get(t[0], t[0])
        units.setdefault(key, []).append(t)
    return units


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260915)
    ap.add_argument("--out", type=Path, default=ROOT / "tools" / "sepsis_holdout_split.json")
    args = ap.parse_args()

    src = load_gold_union()
    gold = sorted(src)
    units = build_units(gold)
    rels_all = {t[1] for t in gold}
    singleton_rels = {r for r, n in Counter(t[1] for t in gold).items() if n == 1}
    forced_ho = {u for u, ts in units.items() if any(t[1] in singleton_rels for t in ts)}

    by_cat = {}
    for u in sorted(units):
        by_cat.setdefault(category_of(units[u][0][0]), []).append(u)

    rng = random.Random(args.seed)
    chosen = None
    for attempt in range(1, 20001):
        ex_units = set()
        for cat, us in by_cat.items():
            pool = [u for u in us if u not in forced_ho]
            ex_units |= set(rng.sample(pool, N_EX_UNITS[cat]))
        ex = [t for u in ex_units for t in units[u]]
        ho = [t for u in units if u not in ex_units for t in units[u]]
        ok = (EX_TRIPLE_RANGE[0] <= len(ex) <= EX_TRIPLE_RANGE[1]
              and {t[1] for t in ho} == rels_all
              and {t[1] for t in ex} == rels_all - singleton_rels
              and {category_of(t[0]) for t in ex} == set(CATEGORY)
              and {category_of(t[0]) for t in ho} == set(CATEGORY))
        if ok:
            chosen = (sorted(ex), sorted(ho), attempt)
            break
    if chosen is None:
        sys.exit("제약을 만족하는 분할을 찾지 못함")
    ex, ho, attempt = chosen

    def rec(t):
        return {"subject": t[0], "predicate": t[1], "object": t[2],
                "category": category_of(t[0]), "source": sorted(src[t])}

    def summary(ts):
        return {"n": len(ts),
                "by_relation": dict(sorted(Counter(t[1] for t in ts).items())),
                "by_category": dict(sorted(Counter(category_of(t[0]) for t in ts).items())),
                "by_object": dict(sorted(Counter(t[2] for t in ts).items()))}

    out = {
        "name": "sepsis_holdout_split",
        "seed": args.seed,
        "rejection_attempt": attempt,
        "rationale": (
            "기존 sepsis 규칙 전부를 few-shot 예시로 주고 같은 규칙으로 채점하면 일치가 추출 능력을 증명하지 못한다(순환). "
            "그래서 gold 관계 트리플(clinical_concepts.json triples ∪ rules/pkg.txt, increaseRiskOf→increasesRiskOf 로 오타 통합, "
            "subClassOf/type/hasOutcome 제외)을 서로소인 examples 와 heldout 으로 나눈다. 프롬프트에는 examples 만 넣고, "
            "추출 성능(recall)은 heldout 에서만 잰다. examples 적중은 '형식을 따라 했다'는 뜻일 뿐 참고치다. "
            "분할 단위는 주어 개념 그룹이라 heldout 주어는 예시에 한 번도 주어로 나오지 않는다(별칭이 겹치는 Lactate/LactateNotClearing, "
            "MeanArterialPressure/Hypotension 은 한 그룹). 카테고리(lab/vital 위험인자, 동반질환, Sepsis/SepticShock)마다 양쪽에 최소 1그룹, "
            "관계 increasesRiskOf·associatedWith 는 양쪽 모두에 들어가게 층화했다. causedBy 는 gold 에 1개(Hypotension→Sepsis)뿐이라 "
            "양쪽을 동시에 채울 수 없어 heldout 에 두었다 — 예시 없이 술어 목록만 보고 내는지 본다. "
            "시드 고정 + 제약 만족할 때까지 재추첨(rejection sampling)이라 같은 시드면 같은 분할이 나온다. "
            "주의: gold 일치는 근거 지지를 보장하지 않는다(regex 기준선 12개 중 근거가 실제로 지지하는 것은 약 2개) — "
            "held-out recall 은 반드시 근거 검토(review CSV)와 같이 본다."
        ),
        "gold_definition": {
            "sources": ["configs/clinical_concepts.json#triples", "rules/pkg.txt"],
            "normalize": NORM_REL,
            "excluded_predicates": ["rdf-schema#subClassOf", "22-rdf-syntax-ns#type", "hasOutcome"],
            "n_total": len(gold),
        },
        "categories": CATEGORY,
        "alias_groups": ALIAS_GROUPS,
        "n_example_units_per_category": N_EX_UNITS,
        "summary": {"examples": summary(ex), "heldout": summary(ho)},
        "examples": [rec(t) for t in ex],
        "heldout": [rec(t) for t in ho],
    }
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"gold 관계 트리플 {len(gold)}개 -> examples {len(ex)} / heldout {len(ho)}  (seed {args.seed}, 시도 {attempt})")
    for name, ts in (("examples", ex), ("heldout", ho)):
        s = summary(ts)
        print(f"  {name:8s} 관계 {s['by_relation']}  카테고리 {s['by_category']}")
        for t in ts:
            print(f"      {t[0]} -{t[1]}-> {t[2]}")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
