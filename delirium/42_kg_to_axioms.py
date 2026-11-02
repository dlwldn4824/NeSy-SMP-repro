# -*- coding: utf-8 -*-
# ============================================================================
# KG 트리플 JSON → PADIS 공리 (33_kg_variants_v2.py 의 compile_kg 만 떼어낸 것)
#
#   입력: [{"subject", "predicate", "object"}, ...] 형식 JSON 파일 1개 이상 (여러 개면 합집합)
#   출력: 공리 목록 JSON + 23_stage34_bilstm_cbm.py 의 AXIOMS 자리에 붙여 넣을 코드
#
#   변환 규칙은 33_ 과 같다.
#     1. hasNoEffectOn 은 공리로 만들지 않고, 같은 (주어, 목적어) 쌍의 다른 트리플을 기각한다.
#     2. 주어는 MAPPING 으로 MIMIC 개념·임계값에, 목적어는 HEADS 로 모델 출력에 대응시킨다.
#        대응이 없으면 미매핑으로 버린다.
#     3. 근거 등급은 술어로 정한다 (PRED_W). 가중치는 GRADE_W 를 합 1 로 정규화한 값.
#
#   MIMIC 데이터 없이 돈다. 임계값은 원 단위로 내보내고, 표준화(z)는 23_ 의 _zthr 가 한다.
#   PhysicalRestraint · MechanicalVentilation · OpioidUse · Melatonin 은 33_ 에서 회수한 개념이라
#   23_ 에는 없다 — 23_ 에 붙일 때는 이 4개 공리를 빼거나 개념을 먼저 추가해야 한다.
#
# 사용: python delirium/42_kg_to_axioms.py triples_one.json [triples_few.json ...] [-o axioms.json]
# ============================================================================
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# 개념 이름 -> (모델 개념, 방향(+1: 임계 이상이 참), 원 단위 임계, 이진 여부)
MAPPING = {
    "Benzodiazepine": ("BenzoFrac", +1, 1e-6, False),
    "DeepSedation": ("RASSmin", -1, -4.0, False),
    "SedationIntensity": ("RASSnegmean", -1, -2.0, False),
    "SeverePain": ("PainNRSmax", +1, 4.0, False),
    "Age": ("Age", +1, 65.0, False),
    "Dexmedetomidine": ("DexmedFrac", +1, 1e-6, False),
    "EarlyMobility": ("MobJHHLM", +1, 4.0, False),
    "Immobility": ("MobJHHLM", -1, 3.0, False),
    "BloodTransfusion": ("BloodTransfusion", +1, 0.5, True),
    "Dementia": ("Dementia", +1, 0.5, True),
    "Trauma": ("Trauma", +1, 0.5, True),
    "Hypertension": ("Hypertension", +1, 0.5, True),
    # 33_ 에서 회수한 개념 (23_ 에는 없음)
    "PhysicalRestraint": ("PhysicalRestraint", +1, 0.5, True),
    "MechanicalVentilation": ("MechanicalVentilation", +1, 0.5, True),
    "OpioidUse": ("OpioidUse", +1, 0.5, True),
    "Melatonin": ("Melatonin", +1, 0.5, True),
}
RECOVERED = {"PhysicalRestraint", "MechanicalVentilation", "OpioidUse", "Melatonin"}
HEADS = {"Delirium": "Delirium", "Death": "Death", "UnableToAssess": "CurrentUTA",
         "Assessable": "Assessable", "Immobility": "MobJHHLM"}
PRED_W = {"increasesRiskOf": "strong", "decreasesRiskOf": "moderate",
          "associatedWith": "low", "precludes": "derived"}
GRADE_W = {"strong": 1.0, "moderate": 0.6, "low": 0.3, "cohort": 0.3, "derived": 0.5,
           "inconclusive": 0.2}


def load_triples(paths):
    s = set()
    for p in paths:
        for t in json.loads(Path(p).read_text(encoding="utf-8")):
            s.add((t["subject"], t["predicate"], t["object"]))
    return s


def compile_kg(triples):
    no_effect = {(s, o) for s, p, o in triples if p == "hasNoEffectOn"}
    ax, dropped, unmapped = [], [], []
    for s, p, o in sorted(triples):
        if p == "hasNoEffectOn":
            continue
        if (s, o) in no_effect:
            dropped.append(f"{s}-{p}->{o}"); continue
        if p not in PRED_W or s not in MAPPING:
            unmapped.append(f"{s}-{p}->{o}"); continue
        head = "CurrentUTA" if p == "precludes" and o in ("Assessable", "UnableToAssess") \
            else HEADS.get(o)
        if head is None:
            unmapped.append(f"{s}-{p}->{o}"); continue
        cn, sgn, raw, is_bin = MAPPING[s]
        ax.append({"name": f"{s}-{p}->{o}", "concept": cn, "sign": sgn,
                   "threshold": 0.5 if is_bin else raw, "binary": is_bin, "head": head,
                   "negated_head": p == "decreasesRiskOf", "grade": PRED_W[p],
                   "recovered_concept": s in RECOVERED})
    tot = sum(GRADE_W[a["grade"]] for a in ax)
    for a in ax:
        a["weight"] = round(GRADE_W[a["grade"]] / tot, 4)
    return ax, dropped, unmapped


def as_23_code(ax):
    """23_ 의 AXIOMS 튜플 형식: (이름, 개념, 방향, 임계z, head, head 부정, GRADE).

    23_ 은 섬망 예측 모델이라 Death 출력이 없고, 회수 개념 4개도 없다 — 둘 다 주석으로 뺀다.
    """
    lines = ["AXIOMS = ["]
    for a in ax:
        thr = "0.5" if a["binary"] else f'_zthr("{a["concept"]}", {a["threshold"]})'
        row = (f'("{a["name"]}", "{a["concept"]}", {a["sign"]:+d}, {thr}, '
               f'"{a["head"]}", {a["negated_head"]}, "{a["grade"]}"),')
        if a["head"] == "Death":
            lines.append(f"    # {row}  # 23_ 에 Death 출력 없음")
        elif a["recovered_concept"]:
            lines.append(f"    # {row}  # 23_ 에 없는 개념")
        else:
            lines.append(f"    {row}")
    lines.append("]")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("triples", nargs="+", help="트리플 JSON 파일 (여러 개면 합집합)")
    ap.add_argument("-o", "--out", default="axioms.json")
    args = ap.parse_args()

    tr = load_triples(args.triples)
    ax, dropped, unmapped = compile_kg(tr)
    Path(args.out).write_text(json.dumps(
        {"inputs": args.triples, "n_triples": len(tr), "axioms": ax,
         "dropped_by_no_effect": dropped, "unmapped": unmapped},
        ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"트리플 {len(tr)} -> 공리 {len(ax)} (효과없음 기각 {len(dropped)} · 미매핑 {len(unmapped)})")
    for a in ax:
        print(f"  {a['name']:45s} {a['grade']:9s} w={a['weight']}")
    if dropped:
        print("기각:", ", ".join(dropped))
    print(f"\n저장: {args.out}\n\n# --- 23_stage34_bilstm_cbm.py 에 붙여 넣을 코드 ---")
    print(as_23_code(ax))


if __name__ == "__main__":
    main()
