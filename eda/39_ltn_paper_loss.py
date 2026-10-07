# -*- coding: utf-8 -*-
# ============================================================================
# 랩 피드백 반영 — LTN 라이브러리 연산 + **논문식 loss** 로 다시 확인
#
#   지금까지 섬망 쪽 실험(eda/23·29~37)은
#     loss = BCE(사망) + w_c·개념손실 + w_axiom·(1 − sat_K)      ← 더하는 형태
#   였다. 논문·원저자 코드는
#     loss = 1 − ( w_D·SatAgg(데이터 공리) + w_K·SatAgg(지식 공리) ),  w_D + w_K = 1
#   즉 **합이 1인 비율로 섞는 형태**다 (w_D=0.8 · w_K=0.2).
#   → 두 설계는 공리 항의 상대 크기가 다르고, 우리 가중치 스윕(0.2·1.0·2.0)은
#     논문식에서는 애초에 불가능한 값이다. 음성 대조군 결론이 loss 설계 탓인지 확인한다.
#
#   사용한 라이브러리 연산 (원저자 코드와 동일):
#     ltn.fuzzy_ops.ImpliesReichenbach  (함축 1−a+ab)
#     ltn.fuzzy_ops.AggregPMeanError    (전칭 ∀, p=2 / 음성 데이터 공리는 p=6)
#     ltn.fuzzy_ops.SatAgg              (공리 집합 집계)
#     ltn.fuzzy_ops.NotStandard         (부정 1−x)
#   * 모델을 ltn.Predicate 로 감싸면 공리마다 trunk 를 다시 forward 하게 되어(13배) 비용만 늘고
#     수치는 동일하므로, trunk 는 배치당 1회 계산하고 라이브러리 연산을 그 위에 적용했다.
#
#   변형: w_K ∈ {0.0, 0.1, 0.2, 0.5, 0.8} (w_D = 1 − w_K) × 진짜/가짜 공리
#
# 사용: EDA_DATA=notes/eda python eda/39_ltn_paper_loss.py [--seeds 42,7,2024]
# ============================================================================
from __future__ import annotations

import os
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = (HERE / "29_outcome_mortality.py").read_text(encoding="utf-8")
exec(compile(SRC[: SRC.index("# ================================================================ 실행")],
             "29_prefix", "exec"), globals())   # noqa: S102

import ltn                                                           # noqa: E402
import numpy as np                                                   # noqa: E402
import pandas as pd                                                  # noqa: E402
import torch                                                         # noqa: E402
import torch.nn as nn                                                # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score   # noqa: E402

OUTD = os.path.join(OUT, "stage39")
os.makedirs(OUTD, exist_ok=True)
SEEDS = [int(s) for s in args.seeds.split(",")]
IMP = ltn.fuzzy_ops.ImpliesReichenbach()
NOT = ltn.fuzzy_ops.NotStandard()
A2 = ltn.fuzzy_ops.AggregPMeanError(p=2)
A6 = ltn.fuzzy_ops.AggregPMeanError(p=6)
SAT = ltn.fuzzy_ops.SatAgg()
REAL, _ = make_axioms(True)


def fake_axioms(seed):
    rng = random.Random(seed)
    return [(nm, cn, sgn, thr, rng.choice(["Delirium", "Death"]), rng.random() < 0.5, g)
            for nm, cn, sgn, thr, hd, neg, g in REAL]


def membership(row, c, p_del):
    nm, cn, sgn, thr, hd, neg, g = row
    if cn is None:
        return p_del
    z = c[:, CI[cn]]
    return (torch.sigmoid(z) if CTYPE_C[CI[cn]] == "bin"
            else torch.sigmoid(sgn * (z - thr) / TAU))


def sat_data(p_death, y):
    """논문 데이터 공리: ∀x⁺ P(x⁺) · ∀x⁻ ¬P(x⁻) (후자는 p=6, 원저자 코드와 동일)."""
    f = []
    pos, neg = y > 0.5, y <= 0.5
    if pos.any():
        f.append(A2(p_death[pos], dim=0))
    if neg.any():
        f.append(A6(NOT(p_death[neg]), dim=0))
    return SAT(*f)


def sat_knowledge(ax, c, p_del, p_death):
    f = []
    for row in ax:
        a = membership(row, c, p_del)
        b = p_del if row[4] == "Delirium" else (p_death if row[4] == "Death"
                                                else torch.sigmoid(c[:, CI[row[4]]]))
        if row[5]:
            b = NOT(b)
        f.append(A2(IMP(a, b), dim=0))
    return SAT(*f) if f else torch.ones((), device=p_death.device)


def train(w_k, ax, seed, epochs=None, bs=2048, w_concept=1.0, w_mediator=1.0):
    """loss = 1 − (w_D·SatAgg(D) + w_K·SatAgg(K)),  w_D = 1 − w_K.
    개념·중간개념 지도는 유지한다(개념 헤드가 없으면 공리 자체를 쓸 수 없다)."""
    epochs = epochs or args.epochs
    torch.manual_seed(seed); np.random.seed(seed)
    w_d = 1.0 - w_k
    m = Net2(NCH, len(SFEAT), Z.shape[1], CtC.shape[1], bottleneck=True, mediator=True).to(DEV)
    opt = torch.optim.Adam(m.parameters(), lr=1e-3)
    bce = nn.BCEWithLogitsLoss(reduction="none")
    idx_tr, idx_va, idx_te = np.where(in_tr)[0], np.where(in_val)[0], np.where(in_te)[0]
    best, best_state, bad = -1, None, 0
    for ep in range(epochs):
        m.train()
        for i in range(0, len(idx_tr), bs):
            j = np.random.permutation(idx_tr)[i:i + bs] if i == 0 else idx_tr[i:i + bs]
            xb, sb, yb = Xt[j].to(DEV), St[j].to(DEV), Yt_death[j].to(DEV)
            logit, c, dlog = m(xb, sb)
            p_death, p_del = torch.sigmoid(logit), torch.sigmoid(dlog)
            loss = 1.0 - (w_d * sat_data(p_death, yb)
                          + w_k * sat_knowledge(ax, c, p_del, p_death))
            cb, mb = CtC[j].to(DEV), MtC[j].to(DEV)
            lb = torch.where(TYPE_C.to(DEV).unsqueeze(0), bce(c, cb), (c - cb) ** 2)
            loss = loss + w_concept * (lb * mb).sum() / mb.sum().clamp(min=1)
            lm = Lt_del[j].to(DEV)
            loss = loss + w_mediator * (bce(dlog, Yt_del[j].to(DEV)) * lm).sum() / lm.sum().clamp(min=1)
            opt.zero_grad(); loss.backward(); opt.step()
        m.eval()
        with torch.no_grad():
            pv = np.concatenate([torch.sigmoid(m(Xt[k].to(DEV), St[k].to(DEV))[0]).cpu().numpy()
                                 for k in np.array_split(idx_va, max(1, len(idx_va) // 8192))])
        ap = average_precision_score(Y_DEATH[idx_va], pv)
        if ap > best:
            best, best_state, bad = ap, {k: v.detach().clone() for k, v in m.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 2:
                break
    m.load_state_dict(best_state); m.eval()
    with torch.no_grad():
        pt = np.concatenate([torch.sigmoid(m(Xt[k].to(DEV), St[k].to(DEV))[0]).cpu().numpy()
                             for k in np.array_split(idx_te, max(1, len(idx_te) // 8192))])
    return pt


head(f"[랩 피드백] LTN 라이브러리 연산 + 논문식 loss (w_D + w_K = 1) · 시드 {len(SEEDS)}개")
print("라이브러리:", ltn.__file__)
idx_te = np.where(in_te)[0]
y = Y_DEATH[idx_te]
rows = []
VARIANTS = [("w_K=0.0 (지식 없음)", 0.0, "real"), ("w_K=0.1", 0.1, "real"),
            ("w_K=0.2 (논문값)", 0.2, "real"), ("w_K=0.5", 0.5, "real"),
            ("w_K=0.8", 0.8, "real"),
            ("w_K=0.2 가짜 공리", 0.2, "fake"), ("w_K=0.5 가짜 공리", 0.5, "fake")]
for nm, wk, kind in VARIANTS:
    aucs, aprs = [], []
    for s_ in SEEDS:
        ax = REAL if kind == "real" else fake_axioms(s_)
        p = train(wk, ax, s_)
        aucs.append(100 * roc_auc_score(y, p)); aprs.append(100 * average_precision_score(y, p))
    rows.append({"변형": nm, "w_D": round(1 - wk, 2), "w_K": wk, "공리": kind,
                 "AUROC": round(np.mean(aucs), 2), "SD": round(np.std(aucs), 2),
                 "AUPRC": round(np.mean(aprs), 2)})
    print(f"  {nm:20s} w_D={1-wk:.1f} w_K={wk:.1f} · AUROC {np.mean(aucs):6.2f}±{np.std(aucs):.2f}"
          f" · AUPRC {np.mean(aprs):6.2f}", flush=True)

T = pd.DataFrame(rows)
T.to_csv(os.path.join(OUTD, "ltn_paper_loss.csv"), index=False, encoding="utf-8-sig")
head("[결과] 논문식 loss")
print(T.to_string(index=False))
r = {x["변형"]: x["AUROC"] for x in rows}
print(f"\n논문값(w_K=0.2) − 지식 없음(w_K=0)   {r['w_K=0.2 (논문값)'] - r['w_K=0.0 (지식 없음)']:+.2f}")
print(f"진짜 − 가짜 (w_K=0.2)              {r['w_K=0.2 (논문값)'] - r['w_K=0.2 가짜 공리']:+.2f}")
print(f"진짜 − 가짜 (w_K=0.5)              {r['w_K=0.5'] - r['w_K=0.5 가짜 공리']:+.2f}")
print("\n이 값들이 기존 더하기형 loss 결과(진짜−가짜 +0.01)와 같으면 'loss 설계 무관',")
print("크게 다르면 기존 섬망 실험의 결론은 loss 설계 때문이었다는 뜻이다.")
print(f"\n-> {OUTD}")
