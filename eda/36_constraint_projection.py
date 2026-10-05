# -*- coding: utf-8 -*-
# ============================================================================
# 구조 가설 ② — 공리를 손실이 아니라 **추론 시 제약**으로 쓴다
#
#   학습은 공리 없이 하고(기준선), 예측만 공리를 만족하도록 보정한다.
#   함축 a → b 는 b ≥ a 일 때 완전 만족이므로, 위반분을 λ 만큼 끌어올린다.
#       p' = p + λ · max(0, a_max − p)        a_max = 결과가 b 인 공리들의 앞부분 최대 진리값
#   학습을 건드리지 않으므로 "공리 손실이 전달되지 않는" 문제를 우회한다.
#
#   보정 대상: 사망 확률(결과가 Death 인 공리) · 섬망 확률(결과가 Delirium 인 공리)
#   λ 스윕 0.1 / 0.25 / 0.5 / 1.0 · 가짜 공리로 같은 보정(음성 대조군)
#
# 사용: EDA_DATA=notes/eda python eda/36_constraint_projection.py [--seeds 42,7,2024]
# ============================================================================
from __future__ import annotations

import os
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = (HERE / "29_outcome_mortality.py").read_text(encoding="utf-8")
exec(compile(SRC[: SRC.index("# ================================================================ 실행")],
             "29_prefix", "exec"), globals())   # noqa: S102

import numpy as np                                                   # noqa: E402
import pandas as pd                                                  # noqa: E402
import torch                                                         # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score   # noqa: E402

OUTD = os.path.join(OUT, "stage36")
os.makedirs(OUTD, exist_ok=True)
SEEDS = [int(s) for s in args.seeds.split(",")]
REAL, REAL_W = make_axioms(True)


def fake(seed):
    rng = random.Random(seed)
    return [(nm, cn, sgn, thr, rng.choice(["Delirium", "Death"]), rng.random() < 0.5, g)
            for nm, cn, sgn, thr, hd, neg, g in REAL]


def antecedent(ax_row, c, p_del):
    """공리 앞부분의 진리값 (학습 때와 같은 membership)."""
    nm, cn, sgn, thr, hd, neg, g = ax_row
    if cn is None:
        return p_del
    z = c[:, CI[cn]]
    return (1 / (1 + np.exp(-z)) if CTYPE_C[CI[cn]] == "bin"
            else 1 / (1 + np.exp(-sgn * (z - thr) / TAU)))


def project(p_death, p_del, c, ax, lam):
    """결과가 Death 인 공리로 사망 확률을, Delirium 인 공리로 섬망 확률을 끌어올린다."""
    a_death = np.zeros_like(p_death)
    a_del = np.zeros_like(p_del)
    for row in ax:
        a = antecedent(row, c, p_del)
        if row[5]:                      # decreasesRiskOf: 머리가 ¬b → 아래로 누른다
            tgt = a_death if row[4] == "Death" else a_del
            np.minimum(tgt, 1.0, out=tgt)   # 아래로 누르는 쪽은 아래에서 따로 처리
            continue
        if row[4] == "Death":
            a_death = np.maximum(a_death, a)
        elif row[4] == "Delirium":
            a_del = np.maximum(a_del, a)
    p1 = p_death + lam * np.clip(a_death - p_death, 0, None)
    # ¬b 공리(덱스메데토미딘·조기거동)는 상한으로 작용: b ≤ 1 − a
    for row in ax:
        if not row[5]:
            continue
        a = antecedent(row, c, p_del)
        if row[4] == "Death":
            p1 = p1 - lam * np.clip(p1 - (1.0 - a), 0, None)
    return np.clip(p1, 0, 1)


head(f"[구조 가설 ②] 추론 시 제약 투영 (결과 = 원내 사망, 시드 {len(SEEDS)}개)")
idx_te = np.where(in_te)[0]
y = Y_DEATH[idx_te]
rows = []
runs = []
for s in SEEDS:
    r = run("기준선(공리 없음)", target="hosp", seed=s, quiet=True, bottleneck=True,
            w_concept=1.0, w_mediator=1.0, w_axiom=0.0)
    runs.append(r)
auc0 = [100 * roc_auc_score(y, r["p"]) for r in runs]
apr0 = [100 * average_precision_score(y, r["p"]) for r in runs]
rows.append({"보정": "없음 (기준선)", "λ": 0.0, "공리": "-", "AUROC": round(np.mean(auc0), 2),
             "SD": round(np.std(auc0), 2), "AUPRC": round(np.mean(apr0), 2)})
print(f"  기준선            AUROC {np.mean(auc0):6.2f}±{np.std(auc0):.2f} · AUPRC {np.mean(apr0):6.2f}")

for kind in ("진짜 공리", "가짜 공리"):
    for lam in (0.1, 0.25, 0.5, 1.0):
        auc, apr = [], []
        for s, r in zip(SEEDS, runs):
            ax = REAL if kind == "진짜 공리" else fake(s)
            p1 = project(r["p"], r["p_del"], r["c"], ax, lam)
            auc.append(100 * roc_auc_score(y, p1))
            apr.append(100 * average_precision_score(y, p1))
        rows.append({"보정": kind, "λ": lam, "공리": len(REAL), "AUROC": round(np.mean(auc), 2),
                     "SD": round(np.std(auc), 2), "AUPRC": round(np.mean(apr), 2)})
        print(f"  {kind} λ={lam:<4} AUROC {np.mean(auc):6.2f}±{np.std(auc):.2f}"
              f" · AUPRC {np.mean(apr):6.2f}", flush=True)

T = pd.DataFrame(rows)
T.to_csv(os.path.join(OUTD, "projection.csv"), index=False, encoding="utf-8-sig")
head("[결과] 추론 시 제약 투영")
print(T.to_string(index=False))
print("\n보정이 기준선보다 낮으면 → 공리가 **예측과 충돌**한다는 직접 증거다"
      " (학습 경로 문제와 별개).")
print(f"\n-> {OUTD}")
