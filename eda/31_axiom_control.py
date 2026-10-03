# -*- coding: utf-8 -*-
# ============================================================================
# 1순위 — 공리가 왜 무효인지 못 박는다 (음성 대조군 + 가중치·집계 탐색)
#
#   가짜 공리(머리를 무작위로 바꾼 것)와 진짜 공리의 성능이 같으면
#   → 공리 항이 학습에 영향을 주지 못한다는 증거. 설계 문제로 범위가 좁혀진다.
#
#   변형
#     real            위험인자→섬망 + 섬망→사망            (안 1 의 5b)
#     shuffled-head   머리를 무작위 재배정 + 부정 무작위     ← 음성 대조군
#     shuffled-ante   앞부분(개념)을 무작위 재배정           ← 음성 대조군 2
#     risk-only       위험인자→섬망만
#     med-only        섬망→사망만
#     w sweep         real 에 가중치 0.2 / 0.5 / 1.0 / 2.0
#     min-agg         전칭 집계를 최악 위반(min)으로          ← 공리 압력을 키운다
#
#   4순위 지표도 같이 — 고정 특이도(88·90%)에서의 민감도·경보율.
#
# 사용: EDA_DATA=notes/eda python eda/31_axiom_control.py [--seeds 42,7,2024]
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
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve   # noqa: E402

OUTD = os.path.join(OUT, "stage31")
os.makedirs(OUTD, exist_ok=True)
SEEDS = [int(s) for s in args.seeds.split(",")]

AGG = {"mode": "p2"}          # axiom_sat 가 참조한다 (min 집계 실험용)
_orig_sat = axiom_sat


def axiom_sat(ax, w, c, p_del, p_death, per_axiom=False):            # noqa: F811
    sats = []
    for nm, cn, sgn, thr, hd, neg, _g in ax:
        a = p_del if cn is None else (
            torch.sigmoid(c[:, CI[cn]]) if CTYPE_C[CI[cn]] == "bin"
            else torch.sigmoid(sgn * (c[:, CI[cn]] - thr) / TAU))
        b = p_del if hd == "Delirium" else (p_death if hd == "Death"
                                            else torch.sigmoid(c[:, CI[hd]]))
        if neg:
            b = 1.0 - b
        sat = 1.0 - a + a * b
        if AGG["mode"] == "min":
            sats.append(sat.min())
        else:
            sats.append(1.0 - torch.sqrt(torch.clamp(((1.0 - sat) ** 2).mean(), min=1e-9)))
    s = torch.stack(sats)
    return s if per_axiom else (s * w.to(s.device)).sum()


globals()["axiom_sat"] = axiom_sat

REAL, REAL_W = make_axioms(True)
HEADS_POOL = ["Delirium", "Death"]


def shuffled_heads(seed):
    rng = random.Random(seed)
    ax = [(nm, cn, sgn, thr, rng.choice(HEADS_POOL), rng.random() < 0.5, g)
          for nm, cn, sgn, thr, hd, neg, g in REAL]
    return ax, REAL_W


def shuffled_antecedents(seed):
    rng = random.Random(seed)
    pool = [a[1] for a in REAL if a[1] is not None]
    out = []
    for nm, cn, sgn, thr, hd, neg, g in REAL:
        if cn is None:
            out.append((nm, cn, sgn, thr, hd, neg, g))
            continue
        new = rng.choice(pool)
        out.append((nm, new, sgn, _zthr(new, 0.0) if CTYPE_C[CI[new]] != "bin" else 0.5,
                    hd, neg, g))
    return out, REAL_W


def subset(pred):
    ax = [a for a in REAL if pred(a)]
    w = torch.tensor([GRADE_W[a[6]] for a in ax], dtype=torch.float32)
    return ax, w / w.sum()


def ops_metrics(y, p, spec=0.90):
    """고정 특이도에서의 민감도·경보율 (임상 운영 지표).
    특이도 = 음성 중 임계값 미만 비율 → 임계값은 음성 점수의 spec 분위수."""
    thr = float(np.quantile(p[y == 0], spec))
    sens = 100 * float((p[y == 1] >= thr).mean())
    alert = 100 * float((p >= thr).mean())
    return round(sens, 1), round(alert, 1)


VARIANTS = [
    ("real (5b)", lambda s: (REAL, REAL_W), 0.2, "p2"),
    ("control: 머리 무작위", shuffled_heads, 0.2, "p2"),
    ("control: 개념 무작위", shuffled_antecedents, 0.2, "p2"),
    ("risk-only", lambda s: subset(lambda a: a[4] == "Delirium"), 0.2, "p2"),
    ("med-only (섬망→사망)", lambda s: subset(lambda a: a[4] == "Death"), 0.2, "p2"),
    ("real w=0.5", lambda s: (REAL, REAL_W), 0.5, "p2"),
    ("real w=1.0", lambda s: (REAL, REAL_W), 1.0, "p2"),
    ("real w=2.0", lambda s: (REAL, REAL_W), 2.0, "p2"),
    ("real min-agg w=0.2", lambda s: (REAL, REAL_W), 0.2, "min"),
    ("real min-agg w=1.0", lambda s: (REAL, REAL_W), 1.0, "min"),
]

head(f"[1순위] 공리 음성 대조군 · 가중치·집계 탐색 (결과 = 원내 사망, 시드 {len(SEEDS)}개)")
idx_te = np.where(in_te)[0]
y = Y_DEATH[idx_te]
base = 100 * y.mean()
rows, sat_rows = [], []

ps0 = [run("기준선 공리 없음", target="hosp", seed=s, quiet=True, bottleneck=True,
           w_concept=1.0, w_mediator=1.0, w_axiom=0.0)["p"] for s in SEEDS]
todo = [("기준선 공리 없음 (4m)", 0, ps0)]

for nm, mk, w_ax, agg in VARIANTS:
    ps = []
    for s in SEEDS:
        AGG["mode"] = agg
        ax, axw = mk(s)
        r = run(nm, target="hosp", seed=s, quiet=True, bottleneck=True, w_concept=1.0,
                w_mediator=1.0, w_axiom=w_ax, ax_override=(ax, axw))
        ps.append(r["p"])
        if s == SEEDS[0] and r["sat"] is not None:
            for a_, v_ in zip(r["ax"], r["sat"]):
                sat_rows.append({"변형": nm, "공리": a_, "만족도": round(float(v_), 3)})
    AGG["mode"] = "p2"
    todo.append((f"{nm} (w={w_ax}, {agg})", len(ax), ps))

for nm, nax, ps in todo:
    auc = [100 * roc_auc_score(y, p) for p in ps]
    apr = [100 * average_precision_score(y, p) for p in ps]
    s90 = [ops_metrics(y, p, 0.90)[0] for p in ps]
    s88 = [ops_metrics(y, p, 0.88)[0] for p in ps]
    rows.append({"변형": nm, "공리 수": nax, "AUROC": round(np.mean(auc), 2),
                 "AUROC SD": round(np.std(auc), 2), "AUPRC": round(np.mean(apr), 2),
                 "민감도@특이도90": round(np.mean(s90), 1),
                 "민감도@특이도88": round(np.mean(s88), 1)})
    print(f"  {nm:30s} 공리 {nax:2d} · AUROC {np.mean(auc):6.2f}±{np.std(auc):.2f}"
          f" · AUPRC {np.mean(apr):6.2f} · 민감도@90 {np.mean(s90):4.1f}", flush=True)

T = pd.DataFrame(rows)
T.to_csv(os.path.join(OUTD, "axiom_control.csv"), index=False, encoding="utf-8-sig")
head(f"[결과] 기저 {base:.1f}%")
print(T.to_string(index=False))
if sat_rows:
    pd.DataFrame(sat_rows).to_csv(os.path.join(OUTD, "axiom_control_sat.csv"),
                                  index=False, encoding="utf-8-sig")
_b = T.loc[T["변형"].str.startswith("기준선"), "AUROC"].iloc[0]
_r = T.loc[T["변형"].str.startswith("real (5b)"), "AUROC"].iloc[0]
_c = T.loc[T["변형"].str.contains("머리 무작위"), "AUROC"].iloc[0]
print(f"\n진짜 공리 − 기준선   {_r-_b:+.2f}")
print(f"가짜 공리 − 기준선   {_c-_b:+.2f}")
print(f"진짜 − 가짜          {_r-_c:+.2f}   <- 시드 SD 보다 작으면 '공리 항이 무효'")
print(f"\n-> {OUTD}")
