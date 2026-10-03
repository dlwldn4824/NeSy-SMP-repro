# -*- coding: utf-8 -*-
# ============================================================================
# 2순위 (분석) — 회수한 개념 4종을 붙여 KG 범위 비교를 다시 한다
#
#   32_ 가 뽑은 억제대·기계환기·오피오이드·멜라토닌을 **앵커 창(24h) 플래그 개념**으로 추가하고,
#   30_ 과 같은 방식으로 KG 범위별(A 합의 · B 조건별 · C 합집합 · H 사람) 공리를 컴파일·학습한다.
#   공리 수가 늘어난 만큼 "자동 추출 KG 가 사람 KG 보다 떨어지나"를 공정하게 볼 수 있다.
#
# 사용: EDA_DATA=notes/eda python eda/33_kg_variants_v2.py [--seeds 42,7,2024]
# ============================================================================
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = (HERE / "29_outcome_mortality.py").read_text(encoding="utf-8")
exec(compile(SRC[: SRC.index("# ================================================================ 실행")],
             "29_prefix", "exec"), globals())   # noqa: S102

import numpy as np                                                   # noqa: E402
import pandas as pd                                                  # noqa: E402
import torch                                                         # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score   # noqa: E402

RUNS = Path(r"C:\data\padis_fewshot\runs")
CFG = HERE.parent / "NeSy-SMP" / "configs" / "padis_concepts.json"
EV = Path(os.environ.get("EDA_DATA", "notes/eda")) / "_axiom_padis2_events.parquet"
OUTD = os.path.join(OUT, "stage33")
os.makedirs(OUTD, exist_ok=True)
SEEDS = [int(s) for s in args.seeds.split(",")]

# ---------------------------------------------------------------- 회수 개념을 앵커 창 플래그로
head("[개념 추가] 32_ 산출물 → 앵커 창 24h 플래그")
ev = pd.read_parquet(EV)
hr = cam["hr"].to_numpy(float)
sid = cam["stay_id"].to_numpy()
NEWC = ["PhysicalRestraint", "MechanicalVentilation", "OpioidUse", "Melatonin"]
SRC2 = {"PhysicalRestraint": "Restraint", "MechanicalVentilation": "MechVent",
        "OpioidUse": "Opioid", "Melatonin": "Melatonin"}
flags = {}
for name, var in SRC2.items():
    d = ev[ev["var"] == var]
    by = {k: np.sort(g["hr"].to_numpy(float)) for k, g in d.groupby("stay_id", sort=False)}
    f = np.zeros(len(cam), np.float32)
    for i, (s_, h_) in enumerate(zip(sid, hr)):
        a = by.get(s_)
        if a is None:
            continue
        lo, hi = np.searchsorted(a, [h_ - 24.0, h_])
        if hi > lo:
            f[i] = 1.0
    flags[name] = f
    print(f"  {name:22s} 앵커 양성 {100*f.mean():5.1f}% · train {100*f[in_tr].mean():5.1f}%")

# 개념 벡터·정적 입력에 붙인다 (개념을 예측하려면 입력에도 있어야 한다 — 23_ 와 같은 원칙)
_add = np.stack([flags[c] for c in NEWC], 1)
CtC = torch.cat([CtC, torch.from_numpy(_add)], 1)
MtC = torch.cat([MtC, torch.ones(len(cam), len(NEWC))], 1)
TYPE_C = torch.cat([TYPE_C, torch.ones(len(NEWC), dtype=torch.bool)])
CONCEPTS_C = list(CONCEPTS_C) + NEWC
CTYPE_C = list(CTYPE_C) + ["bin"] * len(NEWC)
CI = {n: i for i, n in enumerate(CONCEPTS_C)}
St = torch.cat([St, torch.from_numpy(_add)], 1)
SFEAT = list(SFEAT) + NEWC
globals().update(CtC=CtC, MtC=MtC, TYPE_C=TYPE_C, CONCEPTS_C=CONCEPTS_C, CTYPE_C=CTYPE_C,
                 CI=CI, St=St, SFEAT=SFEAT)
print(f"개념 {len(CONCEPTS_C)}개 · 정적 입력 {len(SFEAT)}개")

# ---------------------------------------------------------------- KG 집합·컴파일 (30_ 과 동일 규칙)
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
KGS = {"A 합의(교집합)": U["zeroshot"] & U["oneshot"] & U["fewshot"],
       "B zero-shot": U["zeroshot"], "B one-shot": U["oneshot"], "B few-shot": U["fewshot"],
       "C 합집합": set().union(*U.values()), "H 사람 KG": HUMAN}

MAPPING = {
    "Benzodiazepine": ("BenzoFrac", +1, 1e-6),
    "DeepSedation": ("RASSmin", -1, -4.0),
    "SedationIntensity": ("RASSnegmean", -1, -2.0),
    "SeverePain": ("PainNRSmax", +1, 4.0),
    "Age": ("Age", +1, 65.0),
    "Dexmedetomidine": ("DexmedFrac", +1, 1e-6),
    "EarlyMobility": ("MobJHHLM", +1, 4.0),
    "Immobility": ("MobJHHLM", -1, 3.0),
    # 2순위로 회수한 것
    "PhysicalRestraint": ("PhysicalRestraint", +1, 0.5),
    "MechanicalVentilation": ("MechanicalVentilation", +1, 0.5),
    "OpioidUse": ("OpioidUse", +1, 0.5),
    "Melatonin": ("Melatonin", +1, 0.5),
}
if HAS_GAP:
    MAPPING |= {"BloodTransfusion": ("BloodTransfusion", +1, 0.5),
                "Dementia": ("Dementia", +1, 0.5), "Trauma": ("Trauma", +1, 0.5),
                "Hypertension": ("Hypertension", +1, 0.5)}
MAPPING = {k: v for k, v in MAPPING.items() if v[0] in CI}
HEADS = {"Delirium": "Delirium", "Death": "Death", "UnableToAssess": "CurrentUTA",
         "Assessable": "Assessable", "Immobility": "MobJHHLM"}
PRED_W = {"increasesRiskOf": "strong", "decreasesRiskOf": "moderate",
          "associatedWith": "low", "precludes": "derived"}


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
        head_ = "CurrentUTA" if p == "precludes" and o in ("Assessable", "UnableToAssess") \
            else HEADS.get(o)
        if head_ is None or (head_ not in ("Delirium", "Death") and head_ not in CI):
            unmapped.append(f"{s}-{p}->{o}"); continue
        cn, sgn, raw = MAPPING[s]
        thr = 0.5 if CTYPE_C[CI[cn]] == "bin" else _zthr(cn, raw)
        ax.append((f"{s}-{p}->{o}", cn, sgn, thr, head_, p == "decreasesRiskOf", PRED_W[p]))
    w = torch.tensor([GRADE_W[a[6]] for a in ax], dtype=torch.float32)
    return ax, (w / w.sum() if len(ax) else w), dropped, unmapped


head("[KG 범위별] 개념 회수 후 실행 가능 공리 수")
rows, AXSETS = [], {}
for nm, tr in KGS.items():
    ax, w, dropped, unmapped = compile_kg(tr)
    AXSETS[nm] = (ax, w)
    rows.append({"KG": nm, "트리플": len(tr), "실행 가능 공리": len(ax),
                 "기각": len(dropped), "미매핑": len(unmapped),
                 "결과=섬망": sum(1 for a in ax if a[4] == "Delirium"),
                 "결과=사망": sum(1 for a in ax if a[4] == "Death"),
                 "결과=기타": sum(1 for a in ax if a[4] not in ("Delirium", "Death"))})
    print(f"  {nm:16s} 트리플 {len(tr):3d} -> 공리 {len(ax):2d} (기각 {len(dropped)} · 미매핑 {len(unmapped)})")
KT = pd.DataFrame(rows)
KT.to_csv(os.path.join(OUTD, "kg_axiom_counts_v2.csv"), index=False, encoding="utf-8-sig")
print(); print(KT.to_string(index=False))

head(f"[학습] 결과 = 원내 사망 · 개념 회수 후 KG 범위별 (시드 {len(SEEDS)}개)")
idx_te = np.where(in_te)[0]
y = Y_DEATH[idx_te]
base = 100 * y.mean()
res, sat_rows = [], []
ps0 = [run("기준선", target="hosp", seed=s, quiet=True, bottleneck=True, w_concept=1.0,
           w_mediator=1.0, w_axiom=0.0)["p"] for s in SEEDS]
res.append(("기준선 공리 없음", 0, ps0))
for nm, (ax, w) in AXSETS.items():
    if not len(ax):
        continue
    ps = []
    for s in SEEDS:
        r = run(f"LTN {nm}", target="hosp", seed=s, quiet=True, bottleneck=True, w_concept=1.0,
                w_mediator=1.0, w_axiom=0.2, ax_override=(ax, w))
        ps.append(r["p"])
        if s == SEEDS[0] and r["sat"] is not None:
            for a_, v_ in zip(r["ax"], r["sat"]):
                sat_rows.append({"KG": nm, "공리": a_, "만족도": round(float(v_), 3)})
    res.append((f"LTN {nm}", len(ax), ps))

out = []
for nm, nax, ps in res:
    auc = [100 * roc_auc_score(y, p) for p in ps]
    apr = [100 * average_precision_score(y, p) for p in ps]
    out.append({"모델": nm, "공리 수": nax, "AUROC": round(np.mean(auc), 2),
                "AUROC SD": round(np.std(auc), 2), "AUPRC": round(np.mean(apr), 2)})
    print(f"  {nm:28s} 공리 {nax:2d} · AUROC {np.mean(auc):6.2f}±{np.std(auc):.2f}"
          f" · AUPRC {np.mean(apr):6.2f}", flush=True)
R = pd.DataFrame(out)
R.to_csv(os.path.join(OUTD, "kg_variant_results_v2.csv"), index=False, encoding="utf-8-sig")
head(f"[결과] 개념 회수 후 (기저 {base:.1f}%)")
print(R.to_string(index=False))
if sat_rows:
    pd.DataFrame(sat_rows).to_csv(os.path.join(OUTD, "kg_variant_axiom_sat_v2.csv"),
                                  index=False, encoding="utf-8-sig")
print(f"\n-> {OUTD}")
