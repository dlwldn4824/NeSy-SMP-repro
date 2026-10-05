# -*- coding: utf-8 -*-
# ============================================================================
# 구조 가설 ③ — 공리를 성능이 아니라 **감사·설명 지표**로 쓴다
#
#   공리 만족도를 환자 단위로 계산해서
#     (a) 사망/생존 군의 분포 차이 (논문 Fig.8 과 같은 분석)
#     (b) 만족도가 낮은 환자에서 모델이 더 틀리나 (오류 분석)
#     (c) 공리별 '정보량' — 켜진 환자의 사망률 vs 전체 사망률
#   을 낸다. 성능이 1등이 아니어도 보고할 수 있는 결과물이다.
#
# 사용: EDA_DATA=notes/eda python eda/37_axiom_audit.py [--seeds 42]
# ============================================================================
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = (HERE / "29_outcome_mortality.py").read_text(encoding="utf-8")
exec(compile(SRC[: SRC.index("# ================================================================ 실행")],
             "29_prefix", "exec"), globals())   # noqa: S102

import numpy as np                                                   # noqa: E402
import pandas as pd                                                  # noqa: E402
import torch                                                         # noqa: E402
from sklearn.metrics import roc_auc_score                            # noqa: E402

OUTD = os.path.join(OUT, "stage37")
os.makedirs(OUTD, exist_ok=True)
SEEDS = [int(s) for s in args.seeds.split(",")]
REAL, REAL_W = make_axioms(True)

head("[구조 가설 ③] 공리 만족도를 감사 지표로")
idx_te = np.where(in_te)[0]
y = Y_DEATH[idx_te]
r = run("LTN +섬망→사망", target="hosp", seed=SEEDS[0], quiet=True, bottleneck=True,
        w_concept=1.0, w_mediator=1.0, w_axiom=0.2, use_med_axiom=True)
p, p_del, c = r["p"], r["p_del"], r["c"]


def ante(row):
    nm, cn, sgn, thr, hd, neg, g = row
    if cn is None:
        return p_del
    z = c[:, CI[cn]]
    return (1 / (1 + np.exp(-z)) if CTYPE_C[CI[cn]] == "bin"
            else 1 / (1 + np.exp(-sgn * (z - thr) / TAU)))


# 환자 단위 공리별 만족도 (Reichenbach: 1 - a + a*b)
rows, per_pt = [], []
for row in REAL:
    a = ante(row)
    b = p_del if row[4] == "Delirium" else p
    if row[5]:
        b = 1.0 - b
    sat = 1.0 - a + a * b
    per_pt.append(sat)
    on = a > 0.5
    rows.append({"공리": row[0], "GRADE": row[6], "켜진 환자%": round(100 * on.mean(), 1),
                 "켜진 환자 사망률%": round(100 * y[on].mean(), 1) if on.any() else None,
                 "전체 사망률%": round(100 * y.mean(), 1),
                 "만족도(사망)": round(float(sat[y == 1].mean()), 3),
                 "만족도(생존)": round(float(sat[y == 0].mean()), 3),
                 "만족도 차": round(float(sat[y == 1].mean() - sat[y == 0].mean()), 3)})
A = pd.DataFrame(rows).sort_values("만족도 차")
A.to_csv(os.path.join(OUTD, "axiom_audit.csv"), index=False, encoding="utf-8-sig")
print(A.to_string(index=False))

S = np.stack(per_pt, 1)
mean_sat = S.mean(1)
head("[오류 분석] 만족도 낮은 환자에서 모델이 더 틀리나")
q = pd.qcut(mean_sat, 5, labels=False, duplicates="drop")
rows2 = []
for k in sorted(set(q)):
    m = q == k
    rows2.append({"만족도 5분위": k + 1, "평균 만족도": round(float(mean_sat[m].mean()), 3),
                  "n": int(m.sum()), "사망률%": round(100 * y[m].mean(), 1),
                  "AUROC": round(100 * roc_auc_score(y[m], p[m]), 1) if len(set(y[m])) > 1 else None,
                  "평균 예측": round(float(p[m].mean()), 3),
                  "보정 오차(예측−실제)": round(float(p[m].mean() - y[m].mean()), 3)})
E = pd.DataFrame(rows2)
E.to_csv(os.path.join(OUTD, "axiom_audit_error.csv"), index=False, encoding="utf-8-sig")
print(E.to_string(index=False))

head("[요약]")
print(f"공리 평균 만족도 — 사망군 {S[y==1].mean():.3f} · 생존군 {S[y==0].mean():.3f}")
print(f"만족도 최하위 5분위 AUROC {E['AUROC'].iloc[0]} vs 최상위 {E['AUROC'].iloc[-1]}")
print("공리별 '켜진 환자 사망률'이 전체 사망률과 크게 다르면 그 공리는 위험층을 가려낸다 —")
print("성능이 아니라 이 표가 공리의 임상적 가치를 보여주는 산출물이다.")
print(f"\n-> {OUTD}")
