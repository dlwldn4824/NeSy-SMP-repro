# -*- coding: utf-8 -*-
# ============================================================================
# [추가 실험] 공리를 **사망용으로 재타깃**하면 달라지는가
#
#   29_ 의 "예측 대상을 임상 결과로 변경" 실험(§6-1)은 공리를 그대로 두고 타깃만 바꿨다.
#   위험인자 공리 11개의 머리가 전부 Delirium 이었으므로 **사망 로짓으로 가는 공리는
#   0~3개**뿐이었고, 그 설정으로는 "타깃 선택이 원인인지"를 판정할 수 없다.
#   여기서 공리의 머리를 바꿔 같은 질문을 제대로 묻는다.
#
#     A 공리 없음
#     B 원래 KG (머리 = 섬망) + 섬망→사망        ← 29_ 의 5b 와 같은 설정
#     C 재타깃 KG (위험인자 11개의 머리를 **사망**으로)
#     D 재타깃 KG + 섬망→사망
#     E 재타깃 가짜 (머리는 사망 그대로, 앞부분 개념을 공리 사이에서 재배치) ← 음성 대조군
#
#   읽는 법 — C·D 가 A 보다 뚜렷이 높고 E 보다도 높으면 "공리를 결과에 맞춰 쓰면 작동한다"가 된다.
#            C·D ≈ A ≈ E 면 머리를 맞춰도 전달되지 않는다는 뜻이고, 그러면 원인은 대상이 아니라
#            구조(개념 병목 뒤에 선형 결합 하나)라는 쪽이 남는다.
#
#   주의 — 재타깃은 **지식의 타당성을 바꾸는 조작**이다. "벤조디아제핀 → 사망" 은 PADIS 가
#          뒷받침하지 않는다. 그래서 이 실험은 임상 주장이 아니라 **구조 진단**으로만 쓴다.
#
# 사용: EDA_DATA=notes/eda python eda/41_retarget_axioms.py [--seeds 42,7,2024]
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

OUTD = os.path.join(OUT, "stage41")
os.makedirs(OUTD, exist_ok=True)
SEEDS = [int(s) for s in args.seeds.split(",")]


def _w(ax):
    w = torch.tensor([GRADE_W[a[6]] for a in ax], dtype=torch.float32)
    return w / w.sum()


def retarget(ax):
    """머리가 Delirium 인 공리를 Death 로 바꾼다 (부정·앞부분은 그대로)."""
    return [(nm.replace("Delirium", "Death"), cn, sgn, thr,
             "Death" if hd == "Delirium" else hd, neg, g)
            for nm, cn, sgn, thr, hd, neg, g in ax]


def fake_antecedents(ax, seed):
    """앞부분(개념·방향·임계값)을 공리 사이에서 재배치 — 집합·머리·부정은 보존."""
    rng = random.Random(seed)
    idx = [i for i, a in enumerate(ax) if a[1] is not None]
    ants = [(ax[i][1], ax[i][2], ax[i][3]) for i in idx]
    rng.shuffle(ants)
    out = list(ax)
    for k, i in enumerate(idx):
        nm, cn, sgn, thr, hd, neg, g = ax[i]
        out[i] = (nm, ants[k][0], ants[k][1], ants[k][2], hd, neg, g)
    return out


RISK = [a for a in AX_RISK]
MED = list(AX_MED)
RETARGETED = retarget(RISK)

VARIANTS = [
    ("A 공리 없음", None, 0.0),
    ("B 원래 KG(머리=섬망) + 섬망→사망", RISK + MED, 0.2),
    ("C 재타깃 KG(머리=사망)", RETARGETED, 0.2),
    ("D 재타깃 KG + 섬망→사망", RETARGETED + MED, 0.2),
    ("E 재타깃 가짜(앞부분 재배치)", "fake", 0.2),
    ("C' 재타깃 KG (w .5)", RETARGETED, 0.5),
]

head(f"[추가] 공리를 사망용으로 재타깃하면 달라지는가 · 시드 {len(SEEDS)}개 · 원내 사망")
print(f"위험인자 공리 {len(RISK)}개 · 재타깃 후 머리: "
      f"{sorted({a[4] for a in RETARGETED})}")
rows, sat_rows = [], []
for nm, ax, w in VARIANTS:
    aucs, aprs = [], []
    last = None
    for s_ in SEEDS:
        if ax is None:
            ov = None
        elif ax == "fake":
            f = fake_antecedents(RETARGETED, s_)
            ov = (f, _w(f))
        else:
            ov = (ax, _w(ax))
        r = run(nm, bottleneck=True, w_concept=1.0, w_mediator=1.0, w_axiom=w,
                target="hosp", seed=s_, quiet=True, ax_override=ov)
        y = Y_DEATH[r["idx"]]
        aucs.append(100 * roc_auc_score(y, r["p"]))
        aprs.append(100 * average_precision_score(y, r["p"]))
        last = r
    rows.append({"변형": nm, "w_axiom": w, "AUROC": round(np.mean(aucs), 2),
                 "SD": round(np.std(aucs), 2), "AUPRC": round(np.mean(aprs), 2)})
    print(f"  {nm:34s} AUROC {np.mean(aucs):6.2f}±{np.std(aucs):.2f} · AUPRC {np.mean(aprs):6.2f}",
          flush=True)
    if last is not None and last.get("sat") is not None and ax not in (None, "fake"):
        for a_, s2 in zip(last["ax"], np.atleast_1d(last["sat"])):
            sat_rows.append({"변형": nm, "공리": a_[0], "머리": a_[4], "만족도": round(float(s2), 4)})

T = pd.DataFrame(rows)
T.to_csv(os.path.join(OUTD, "retarget.csv"), index=False, encoding="utf-8-sig")
if sat_rows:
    pd.DataFrame(sat_rows).to_csv(os.path.join(OUTD, "retarget_axiom_sat.csv"),
                                  index=False, encoding="utf-8-sig")
head("[결과] 공리 재타깃")
print(T.to_string(index=False))
r = {x["변형"]: x["AUROC"] for x in rows}
print(f"\n재타깃 C − 공리 없음 A        {r['C 재타깃 KG(머리=사망)'] - r['A 공리 없음']:+.2f}")
print(f"재타깃 C − 원래 KG B          {r['C 재타깃 KG(머리=사망)'] - r['B 원래 KG(머리=섬망) + 섬망→사망']:+.2f}")
print(f"재타깃 C − 재타깃 가짜 E      {r['C 재타깃 KG(머리=사망)'] - r['E 재타깃 가짜(앞부분 재배치)']:+.2f}")
print("\n마지막 줄이 시드 SD 보다 크면 '머리를 결과에 맞추면 공리가 전달된다'는 증거가 된다.")
print(f"\n-> {OUTD}")
