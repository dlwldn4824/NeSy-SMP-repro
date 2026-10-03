# -*- coding: utf-8 -*-
# ============================================================================
# 교수님 제안 — 추출 조건별/중복 KG 로 공리를 뽑아 비교한다 (2026-10-03 피드백 ②)
#
#   KG 범위 4종
#     A 합의(교집합)  zero ∩ one ∩ few          25 트리플
#     B 조건별        zero / one / few 각각      36 / 35 / 33
#     C 합집합        세 조건 합                 44
#     H 사람 KG       configs/padis_concepts.json 20   (현재 기준선)
#
#   각 KG → 실행 가능한 공리만 컴파일 → 같은 분할·같은 모델로 학습.
#   결과는 **원내 사망**(안 1 구조: 위험인자 → 섬망 → 사망). 섬망은 중간 개념.
#
#   술어 처리
#     increasesRiskOf  a → b
#     decreasesRiskOf  a → ¬b
#     associatedWith   a → b  (가중치 low — 원문이 연관만 진술)
#     hasNoEffectOn    공리로 만들지 않고, **같은 쌍의 다른 공리를 기각**하는 필터
#     precludes        a → CurrentUTA (평가 불능 가드)
#
# 사용: EDA_DATA=notes/eda python eda/30_kg_variants.py [--seeds 42,7,2024]
# ============================================================================
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = (HERE / "29_outcome_mortality.py").read_text(encoding="utf-8")
MARK = "# ================================================================ 실행"
exec(compile(SRC[: SRC.index(MARK)], "29_prefix", "exec"), globals())   # noqa: S102

import numpy as np                                                   # noqa: E402
import pandas as pd                                                  # noqa: E402
import torch                                                         # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score   # noqa: E402

RUNS = Path(r"C:\data\padis_fewshot\runs")
CFG = HERE.parent / "NeSy-SMP" / "configs" / "padis_concepts.json"
OUTD = os.path.join(OUT, "stage30")
os.makedirs(OUTD, exist_ok=True)

# ---------------------------------------------------------------- KG 집합
def load_cond(cond):
    s = set()
    for r in ("1", "2"):
        for f in glob.glob(str(RUNS / f"{cond}_run{r}" / "*.json")):
            for t in json.loads(Path(f).read_text(encoding="utf-8")):
                s.add((t["subject"], t["predicate"], t["object"]))
    return s


U = {c: load_cond(c) for c in ("zeroshot", "oneshot", "fewshot")}
HUMAN = {(t["subject"], t["predicate"], t["object"])
         for t in json.loads(CFG.read_text(encoding="utf-8"))["triples"]
         if not t["predicate"].startswith(("rdf-schema", "22-rdf", "hasOutcome"))}
KGS = {
    "A 합의(교집합)": U["zeroshot"] & U["oneshot"] & U["fewshot"],
    "B zero-shot": U["zeroshot"],
    "B one-shot": U["oneshot"],
    "B few-shot": U["fewshot"],
    "C 합집합": set().union(*U.values()),
    "H 사람 KG": HUMAN,
}

# ---------------------------------------------------------------- 개념 → 실행 조건
# (개념 id -> (우리 연속 개념 이름, 방향, 원 단위 임계))  방향 +1: 임계 이상이 참
MAPPING = {
    "Benzodiazepine": ("BenzoFrac", +1, 1e-6),
    "DeepSedation": ("RASSmin", -1, -4.0),
    "SedationIntensity": ("RASSnegmean", -1, -2.0),
    "SeverePain": ("PainNRSmax", +1, 4.0),
    "Age": ("Age", +1, 65.0),
    "Dexmedetomidine": ("DexmedFrac", +1, 1e-6),
    "Propofol": ("PropofolFrac", +1, 1e-6),
    "EarlyMobility": ("MobJHHLM", +1, 4.0),
    "Immobility": ("MobJHHLM", -1, 3.0),
}
if HAS_GAP:
    MAPPING |= {"BloodTransfusion": ("BloodTransfusion", +1, 0.5),
                "Dementia": ("Dementia", +1, 0.5),
                "Trauma": ("Trauma", +1, 0.5),
                "Hypertension": ("Hypertension", +1, 0.5)}
MAPPING = {k: v for k, v in MAPPING.items() if v[0] in CI}
HEADS = {"Delirium": "Delirium", "Death": "Death", "UnableToAssess": "CurrentUTA",
         "Assessable": "Assessable"}
PRED_W = {"increasesRiskOf": "strong", "decreasesRiskOf": "moderate",
          "associatedWith": "low", "precludes": "derived"}


def compile_kg(triples):
    """트리플 집합 -> (공리 리스트, 가중치, 기각·미매핑 내역)"""
    no_effect = {(s, o) for s, p, o in triples if p == "hasNoEffectOn"}
    ax, dropped, unmapped = [], [], []
    for s, p, o in sorted(triples):
        if p == "hasNoEffectOn":
            continue
        if (s, o) in no_effect:                       # 같은 쌍에 '효과 없음'이 있으면 기각
            dropped.append(f"{s}-{p}->{o}")
            continue
        if p not in PRED_W:
            unmapped.append(f"{s}-{p}->{o} (술어 미지원)")
            continue
        if s not in MAPPING:
            unmapped.append(f"{s}-{p}->{o} (주어 미매핑)")
            continue
        if p == "precludes":
            head = "CurrentUTA" if o in ("Assessable", "UnableToAssess") else None
        else:
            head = HEADS.get(o)
        if head is None or (head not in ("Delirium", "Death") and head not in CI):
            unmapped.append(f"{s}-{p}->{o} (결과 미매핑)")
            continue
        cn, sgn, raw = MAPPING[s]
        thr = 0.5 if CTYPE_C[CI[cn]] == "bin" else _zthr(cn, raw)
        ax.append((f"{s}-{p}->{o}", cn, sgn, thr, head, p == "decreasesRiskOf", PRED_W[p]))
    w = torch.tensor([GRADE_W[a[6]] for a in ax], dtype=torch.float32)
    return ax, (w / w.sum() if len(ax) else w), dropped, unmapped


head("[KG 범위별] 실행 가능한 공리 수")
rows, AXSETS = [], {}
for nm, tr in KGS.items():
    ax, w, dropped, unmapped = compile_kg(tr)
    AXSETS[nm] = (ax, w)
    rows.append({"KG": nm, "트리플": len(tr), "실행 가능 공리": len(ax),
                 "효과없음으로 기각": len(dropped), "미매핑": len(unmapped),
                 "결과=섬망": sum(1 for a in ax if a[4] == "Delirium"),
                 "결과=사망": sum(1 for a in ax if a[4] == "Death"),
                 "결과=평가불능": sum(1 for a in ax if a[4] == "CurrentUTA")})
    print(f"  {nm:16s} 트리플 {len(tr):3d} -> 공리 {len(ax):2d}"
          f" (기각 {len(dropped)} · 미매핑 {len(unmapped)})")
    for u in unmapped[:4]:
        print(f"       · {u}")
KT = pd.DataFrame(rows)
KT.to_csv(os.path.join(OUTD, "kg_axiom_counts.csv"), index=False, encoding="utf-8-sig")
print()
print(KT.to_string(index=False))

# ---------------------------------------------------------------- 학습 비교
SEEDS = [int(s) for s in args.seeds.split(",")]
head(f"[학습] 결과 = 원내 사망 · KG 범위별 LTN (시드 {len(SEEDS)}개) · device={DEV}")
idx_te = np.where(in_te)[0]
ylab = Y_DEATH
base = 100 * ylab[idx_te].mean()
res_rows, sat_rows = [], []

# 기준선: 공리 없음 (안 1 의 4m)
for nm, kw in [("기준선 공리 없음 (4m)", dict(bottleneck=True, w_concept=1.0, w_mediator=1.0,
                                              w_axiom=0.0))]:
    ps = [run(nm, target="hosp", seed=s, quiet=True, **kw)["p"] for s in SEEDS]
    res_rows.append((nm, 0, ps))

for nm, (ax, w) in AXSETS.items():
    if not len(ax):
        continue
    ps = []
    for s in SEEDS:
        r = run(f"LTN {nm}", target="hosp", seed=s, quiet=True, bottleneck=True,
                w_concept=1.0, w_mediator=1.0, w_axiom=0.2, ax_override=(ax, w))
        ps.append(r["p"])
        if s == SEEDS[0] and r["sat"] is not None:
            for a_, v_ in zip(r["ax"], r["sat"]):
                sat_rows.append({"KG": nm, "공리": a_, "만족도": round(float(v_), 3)})
    res_rows.append((f"LTN {nm}", len(ax), ps))

out = []
for nm, nax, ps in res_rows:
    auc = [100 * roc_auc_score(ylab[idx_te], p) for p in ps]
    apr = [100 * average_precision_score(ylab[idx_te], p) for p in ps]
    out.append({"모델": nm, "공리 수": nax, "AUROC": round(np.mean(auc), 1),
                "AUROC SD": round(np.std(auc), 2), "AUPRC": round(np.mean(apr), 1),
                "정규화 AUPRC": round(100 * (np.mean(apr) - base) / (100 - base), 1)})
    print(f"  {nm:30s} 공리 {nax:2d} · AUROC {np.mean(auc):5.1f}±{np.std(auc):.2f}"
          f" · AUPRC {np.mean(apr):5.1f}", flush=True)
R = pd.DataFrame(out)
R.to_csv(os.path.join(OUTD, "kg_variant_results.csv"), index=False, encoding="utf-8-sig")
head(f"[결과] KG 범위별 (기저 {base:.1f}%)")
print(R.to_string(index=False))
if sat_rows:
    S_ = pd.DataFrame(sat_rows)
    S_.to_csv(os.path.join(OUTD, "kg_variant_axiom_sat.csv"), index=False, encoding="utf-8-sig")
    print("\n공리 만족도 (KG별 상위/하위 3개)")
    for kg, g in S_.groupby("KG"):
        g = g.sort_values("만족도")
        lo = " · ".join(f"{r['공리']} {r['만족도']:.2f}" for _, r in g.head(3).iterrows())
        hi = " · ".join(f"{r['공리']} {r['만족도']:.2f}" for _, r in g.tail(3).iterrows())
        print(f"  {kg:16s} 낮음: {lo}   |   높음: {hi}")
print(f"\n-> {OUTD}")
