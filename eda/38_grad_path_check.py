# -*- coding: utf-8 -*-
# ============================================================================
# 공리가 사망 예측까지 **실제로 닿는가** — 기울기로 직접 확인
#
#   손실을 따로 역전파해서 파라미터 묶음별 기울기 크기를 재고,
#   공리별로 ∂sat/∂p_death 가 0 인지(= 결과 경로와 무관) 본다.
#
#   확인 1  공리 손실의 기울기가 사망 출력층(out)·백본(lstm)에 들어가나
#   확인 2  공리마다 사망 확률에 대한 민감도 — 0 이면 그 공리는 결과와 무관
#   확인 3  과제 손실 대비 공리 손실 기울기의 상대 크기 (w=0.2 가중 포함)
#
# 사용: EDA_DATA=notes/eda python eda/38_grad_path_check.py
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
import torch.nn as nn                                                # noqa: E402

OUTD = os.path.join(OUT, "stage38")
os.makedirs(OUTD, exist_ok=True)
GROUPS = {"lstm (백본)": "lstm", "att": "att", "stat": "stat", "enc": "enc",
          "concept (개념 헤드)": "concept", "delirium (중간 개념 헤드)": "delirium",
          "out (사망 출력층)": "out"}


def gnorm(m, loss):
    g = torch.autograd.grad(loss, [p for p in m.parameters() if p.requires_grad],
                            retain_graph=True, allow_unused=True)
    names = [n for n, p in m.named_parameters() if p.requires_grad]
    out = {}
    for label, pref in GROUPS.items():
        v = [float(x.norm()) for n, x in zip(names, g) if x is not None and n.startswith(pref)]
        out[label] = float(np.sqrt(sum(t ** 2 for t in v))) if v else 0.0
    return out


torch.manual_seed(SEED)
m = Net2(NCH, len(SFEAT), Z.shape[1], CtC.shape[1], bottleneck=True, mediator=True).to(DEV)
bce = nn.BCEWithLogitsLoss(reduction="none")
j = np.where(in_tr)[0][:2048]
xb, sb = Xt[j].to(DEV), St[j].to(DEV)
logit, c, dlog = m(xb, sb)
p_death, p_del = torch.sigmoid(logit), torch.sigmoid(dlog)

L_task = bce(logit, Yt_death[j].to(DEV)).mean()
cb, mb = CtC[j].to(DEV), MtC[j].to(DEV)
L_con = (torch.where(TYPE_C.to(DEV).unsqueeze(0), bce(c, cb), (c - cb) ** 2) * mb).sum() / mb.sum()
lm = Lt_del[j].to(DEV)
L_med = (bce(dlog, Yt_del[j].to(DEV)) * lm).sum() / lm.sum().clamp(min=1)
ax, axw = make_axioms(True)
L_ax = 1.0 - axiom_sat(ax, axw, c, p_del, p_death)

head("[확인 1] 손실별 기울기 크기 (파라미터 묶음)")
rows = []
for nm, L in [("과제 손실 (사망 BCE)", L_task), ("개념 손실", L_con),
              ("중간 개념(섬망) 손실", L_med), ("공리 손실 (1−sat)", L_ax),
              ("공리 손실 × w=0.2", 0.2 * L_ax)]:
    g = gnorm(m, L)
    rows.append({"손실": nm, **{k: round(v, 6) for k, v in g.items()}})
    print(f"  {nm:22s} " + " · ".join(f"{k.split()[0]} {v:.5f}" for k, v in g.items()), flush=True)
T = pd.DataFrame(rows)
T.to_csv(os.path.join(OUTD, "grad_norms.csv"), index=False, encoding="utf-8-sig")
print()
print(T.to_string(index=False))

head("[확인 2] 공리별 — 사망 확률에 대한 민감도 ∂sat/∂p_death")
rows2 = []
for row in ax:
    s1 = axiom_sat([row], torch.ones(1), c, p_del, p_death)
    gd = torch.autograd.grad(s1, [m.out.weight, m.out.bias], retain_graph=True, allow_unused=True)
    g_out = float(np.sqrt(sum(float(x.norm()) ** 2 for x in gd if x is not None)))
    gp = torch.autograd.grad(s1, logit, retain_graph=True, allow_unused=True)[0]
    rows2.append({"공리": row[0], "머리": row[4],
                  "∂sat/∂사망로짓 L2": round(float(gp.norm()) if gp is not None else 0.0, 8),
                  "사망 출력층 기울기": round(g_out, 8),
                  "만족도": round(float(s1), 4)})
    print(f"  {row[0]:34s} 머리={row[4]:8s} ∂/∂사망로짓 {rows2[-1]['∂sat/∂사망로짓 L2']:.6f}"
          f" · out 기울기 {g_out:.6f}", flush=True)
T2 = pd.DataFrame(rows2)
T2.to_csv(os.path.join(OUTD, "axiom_grad_to_death.csv"), index=False, encoding="utf-8-sig")

n_zero = int((T2["∂sat/∂사망로짓 L2"] == 0).sum())
head("[확인 3] 요약")
print(f"공리 {len(ax)}개 중 사망 로짓에 기울기가 **0 인 것 {n_zero}개** "
      f"(= 그 공리는 결과 예측 경로와 무관)")
g_task = gnorm(m, L_task)["out (사망 출력층)"]
g_ax = gnorm(m, 0.2 * L_ax)["out (사망 출력층)"]
print(f"사망 출력층 기울기 — 과제 손실 {g_task:.5f} vs 공리 손실(w=0.2) {g_ax:.5f}"
      f"  → 비율 {g_ax / max(g_task, 1e-12):.4f}")
g_task_b = gnorm(m, L_task)["lstm (백본)"]
g_ax_b = gnorm(m, 0.2 * L_ax)["lstm (백본)"]
print(f"백본 기울기        — 과제 손실 {g_task_b:.5f} vs 공리 손실(w=0.2) {g_ax_b:.5f}"
      f"  → 비율 {g_ax_b / max(g_task_b, 1e-12):.4f}")
print(f"\n-> {OUTD}")
