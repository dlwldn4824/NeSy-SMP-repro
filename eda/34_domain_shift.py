# -*- coding: utf-8 -*-
# ============================================================================
# 3순위 — 도메인 이동(연도) 정식 평가 + 4순위 운영 지표
#
#   학습·검증은 2008–2016 입실만, 평가는 2020–2022 만. 환자는 겹치지 않는다.
#   "공리가 도메인 이동에 더 강한가"를 본다 — 성능 1등이 아니어도 NeSy 기여 주장이 가능한 지점.
#   같은 모델을 ① 같은 시대 내부 평가(2008–2016 보류분) ② 2020–22 외부 평가로 둘 다 재서
#   **떨어지는 폭**을 비교한다.
#
# 결과: 원내 사망 · 앵커 후 7일 내 사망
# 사용: EDA_DATA=notes/eda python eda/34_domain_shift.py [--seeds 42,7,2024]
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
from sklearn.metrics import average_precision_score, roc_auc_score   # noqa: E402
from xgboost import XGBClassifier                                    # noqa: E402

OUTD = os.path.join(OUT, "stage34")
os.makedirs(OUTD, exist_ok=True)
SEEDS = [int(s) for s in args.seeds.split(",")]

_stb = b.set_index("stay_id")
era = cam["stay_id"].map(_stb["anchor_year_group"]).to_numpy()
OLD = np.isin(era, ["2008 - 2010", "2011 - 2013", "2014 - 2016"])
NEW = era == "2020 - 2022"
head("[분할] 연도 기반 도메인 이동")
print(f"2008-2016 앵커 {int(OLD.sum()):,} · 2017-2019 {int((~OLD & ~NEW).sum()):,} · "
      f"2020-2022 {int(NEW.sum()):,}")

# 환자 단위로 old 를 train/val/내부test 로, new 는 전부 외부 test
rng = np.random.default_rng(SEED)
pats_old = np.unique(cam.loc[OLD, "subject_id"])
rng.shuffle(pats_old)
n = len(pats_old)
tr_p = set(pats_old[: int(n * 0.6)])
va_p = set(pats_old[int(n * 0.6): int(n * 0.75)])
te_p = set(pats_old[int(n * 0.75):])
subj = cam["subject_id"].to_numpy()
IN_TR = OLD & np.isin(subj, list(tr_p))
IN_VAL = OLD & np.isin(subj, list(va_p))
IN_TE_IN = OLD & np.isin(subj, list(te_p))        # 같은 시대 내부 평가
IN_TE_OUT = NEW                                   # 외부 평가
print(f"train {int(IN_TR.sum()):,} · val {int(IN_VAL.sum()):,} · "
      f"내부 test {int(IN_TE_IN.sum()):,} · 외부 test(2020-22) {int(IN_TE_OUT.sum()):,}")
for nm, msk in [("원내 사망", Y_DEATH), ("7일 내 사망", Y_D7)]:
    print(f"  {nm} 기저 — train {100*msk[IN_TR].mean():.1f}% · "
          f"내부 {100*msk[IN_TE_IN].mean():.1f}% · 외부 {100*msk[IN_TE_OUT].mean():.1f}%")

# run() 이 보는 전역 분할을 바꿔 끼운다 (정규화 통계는 23_ 기본 분할 기준 — 한계에 적는다)
globals()["in_tr"], globals()["in_val"] = IN_TR, IN_VAL


def ops(y, p, spec=0.90):
    thr = float(np.quantile(p[y == 0], spec))
    return round(100 * float((p[y == 1] >= thr).mean()), 1), round(100 * float((p >= thr).mean()), 1)


VARIANTS = [
    ("3  BiLSTM", dict(bottleneck=False, w_concept=0.0, w_mediator=0.0, w_axiom=0.0)),
    ("4c CBM", dict(bottleneck=True, w_concept=1.0, w_mediator=0.0, w_axiom=0.0)),
    ("4m CBM+mediator", dict(bottleneck=True, w_concept=1.0, w_mediator=1.0, w_axiom=0.0)),
    ("5b LTN +섬망→사망", dict(bottleneck=True, w_concept=1.0, w_mediator=1.0,
                              w_axiom=0.2, use_med_axiom=True)),
    ("5c LTN w=0.5", dict(bottleneck=True, w_concept=1.0, w_mediator=1.0,
                          w_axiom=0.5, use_med_axiom=True)),
]
rows = []
for tgt, tname in [("hosp", "원내 사망"), ("d7", "7일 내 사망")]:
    ylab = Y_DEATH if tgt == "hosp" else Y_D7
    head(f"[학습] 2008-2016 학습 → 2020-22 평가 · 결과 = {tname}")
    # XGB
    x = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.05, subsample=0.8,
                      colsample_bytree=0.8, eval_metric="aucpr", random_state=SEED,
                      n_jobs=-1, tree_method="hist")
    x.fit(Z[IN_TR], ylab[IN_TR].astype(int))
    preds = {"2z XGB": [(x.predict_proba(Z[IN_TE_IN])[:, 1], x.predict_proba(Z[IN_TE_OUT])[:, 1])]}
    for nm, kw in VARIANTS:
        preds[nm] = []
        for s in SEEDS:
            globals()["in_te"] = IN_TE_IN
            r_in = run(nm, target=tgt, seed=s, quiet=True, **kw)
            globals()["in_te"] = IN_TE_OUT
            r_out = run(nm, target=tgt, seed=s, quiet=True, **kw)
            preds[nm].append((r_in["p"], r_out["p"]))
    for nm, ps in preds.items():
        ai = [100 * roc_auc_score(ylab[IN_TE_IN], p[0]) for p in ps]
        ao = [100 * roc_auc_score(ylab[IN_TE_OUT], p[1]) for p in ps]
        pi = [100 * average_precision_score(ylab[IN_TE_IN], p[0]) for p in ps]
        po = [100 * average_precision_score(ylab[IN_TE_OUT], p[1]) for p in ps]
        so = [ops(ylab[IN_TE_OUT], p[1], 0.90)[0] for p in ps]
        rows.append({"결과": tname, "모델": nm,
                     "내부 AUROC": round(np.mean(ai), 2), "외부 AUROC": round(np.mean(ao), 2),
                     "하락": round(np.mean(ai) - np.mean(ao), 2), "외부 SD": round(np.std(ao), 2),
                     "내부 AUPRC": round(np.mean(pi), 2), "외부 AUPRC": round(np.mean(po), 2),
                     "외부 민감도@특이도90": round(np.mean(so), 1), "시드": len(ps)})
        print(f"  {nm:20s} 내부 {np.mean(ai):6.2f} → 외부 {np.mean(ao):6.2f}"
              f" (하락 {np.mean(ai)-np.mean(ao):+.2f}) · 외부 민감도@90 {np.mean(so):4.1f}", flush=True)

T = pd.DataFrame(rows)
T.to_csv(os.path.join(OUTD, "domain_shift.csv"), index=False, encoding="utf-8-sig")
head("[결과] 도메인 이동")
print(T.to_string(index=False))
print("\n'하락'이 작을수록 연도 이동에 강하다. 공리 모델(5b·5c)의 하락이 "
      "공리 없는 모델(4m)보다 작으면 — 성능 1등이 아니어도 기여가 된다.")
print(f"\n-> {OUTD}")
