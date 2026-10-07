# -*- coding: utf-8 -*-
# ============================================================================
# [실험 D3] 논문식 손실 + LTN 라이브러리 연산으로 **섬망 자체를 예측**한다
#
#   지금까지 논문식 확인(eda/39)은 "섬망용 PADIS 공리로 사망을 예측"하는 설정에서만 했다.
#   랩 지적의 핵심은 **대상 불일치**였다 — 공리의 결과(섬망)와 예측 목표(사망)가 다르면
#   공리가 무효로 보이는 게 당연할 수 있다. 그래서 목표를 공리와 같은 **섬망**으로 맞춘다.
#
#     예측 목표 : 섬망(CAM-ICU 양성) · 라벨이 있는 앵커만 평가
#     손실      : 1 − ( w_D·SatAgg(데이터 공리) + w_K·SatAgg(지식 공리) ),  w_D + w_K = 1
#     공리      : AX_RISK 11개 — 전부 머리가 Delirium 이므로 **모델의 주 출력**을 가리킨다
#                 (Delirium→Death 는 사망 헤드가 없으므로 제외)
#     음성 대조 : 머리가 모두 같아 머리 섞기는 무의미하다. 대신 **앞부분(개념·방향·임계값)을
#                 공리 사이에서 재배치**하고 부정도 재배치한다 — 집합은 그대로 두어
#                 "공리 수·강도"가 아니라 "어느 개념이 어느 결과에 붙는가"만 바꾼다.
#
#   읽는 법 — 여기서 진짜−가짜가 커지면 "공리는 대상이 맞을 때 작동한다"가 되고,
#            여기서도 0 이면 손실·대상 어느 쪽도 원인이 아니라는 뜻이 된다.
#
# 사용: EDA_DATA=notes/eda python eda/40_ltn_paper_loss_delirium.py [--seeds 42,7,2024]
#       ANTECEDENT=data 로 공리 앞부분을 관측값에 직접 묶을 수 있다 (기본은 모델 예측값)
# ============================================================================
from __future__ import annotations

import os
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANTE = os.environ.get("ANTECEDENT", "pred")
SRC = (HERE / "29_outcome_mortality.py").read_text(encoding="utf-8")
exec(compile(SRC[: SRC.index("# ================================================================ 실행")],
             "29_prefix", "exec"), globals())   # noqa: S102

import ltn                                                           # noqa: E402
import numpy as np                                                   # noqa: E402
import pandas as pd                                                  # noqa: E402
import torch                                                         # noqa: E402
import torch.nn as nn                                                # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score   # noqa: E402

OUTD = os.path.join(OUT, "stage40" + ("_data" if ANTE == "data" else ""))
os.makedirs(OUTD, exist_ok=True)
SEEDS = [int(s) for s in args.seeds.split(",")]
IMP = ltn.fuzzy_ops.ImpliesReichenbach()
NOT = ltn.fuzzy_ops.NotStandard()
A2 = ltn.fuzzy_ops.AggregPMeanError(p=2)
A6 = ltn.fuzzy_ops.AggregPMeanError(p=6)
SAT = ltn.fuzzy_ops.SatAgg()

# 머리가 Delirium 인 공리만 (AX_MED 의 Delirium→Death 는 사망 헤드가 없으므로 제외)
REAL = [a for a in make_axioms(False)[0] if a[4] == "Delirium"]
_w = torch.tensor([GRADE_W[a[6]] for a in REAL], dtype=torch.float32)
REAL_W = _w / _w.sum()


def fake_axioms(seed):
    """앞부분(개념·방향·임계값)과 부정을 공리 사이에서 재배치한다 — 집합은 보존."""
    rng = random.Random(seed)
    ants = [(a[1], a[2], a[3]) for a in REAL]
    negs = [a[5] for a in REAL]
    rng.shuffle(ants); rng.shuffle(negs)
    return [(nm, ants[i][0], ants[i][1], ants[i][2], hd, negs[i], g)
            for i, (nm, cn, sgn, thr, hd, neg, g) in enumerate(REAL)]


def membership(row, c, obs=None, obs_mask=None):
    nm, cn, sgn, thr, hd, neg, g = row
    i = CI[cn]
    if ANTE == "data" and obs is not None:
        v = obs[:, i]
        a = v.clamp(0, 1) if CTYPE_C[i] == "bin" else torch.sigmoid(sgn * (v - thr) / TAU)
        return a * obs_mask[:, i]
    z = c[:, i]
    return (torch.sigmoid(z) if CTYPE_C[i] == "bin"
            else torch.sigmoid(sgn * (z - thr) / TAU))


def sat_data(p_del, y, lab):
    """데이터 공리 — 섬망 라벨이 **관찰된** 앵커만 쓴다 (원본과 같은 p=2 / 음성 p=6)."""
    f = []
    pos = (y > 0.5) & (lab > 0.5)
    neg = (y <= 0.5) & (lab > 0.5)
    if pos.any():
        f.append(A2(p_del[pos], dim=0))
    if neg.any():
        f.append(A6(NOT(p_del[neg]), dim=0))
    return SAT(*f) if f else torch.ones((), device=p_del.device)


def sat_knowledge(ax, c, p_del, obs=None, obs_mask=None):
    f = []
    for row in ax:
        a = membership(row, c, obs, obs_mask)
        b = NOT(p_del) if row[5] else p_del
        f.append(A2(IMP(a, b), dim=0))
    return SAT(*f) if f else torch.ones((), device=p_del.device)


def train(w_k, ax, seed, epochs=None, bs=2048, w_concept=1.0):
    """주 출력이 섬망이다. 개념 지도는 유지한다(개념 헤드가 없으면 공리를 쓸 수 없다)."""
    epochs = epochs or args.epochs
    torch.manual_seed(seed); np.random.seed(seed)
    w_d = 1.0 - w_k
    m = Net2(NCH, len(SFEAT), Z.shape[1], CtC.shape[1], bottleneck=True, mediator=False).to(DEV)
    opt = torch.optim.Adam(m.parameters(), lr=1e-3)
    bce = nn.BCEWithLogitsLoss(reduction="none")
    # 평가는 섬망 라벨이 있는 앵커만. 학습은 공리 항 때문에 라벨 없는 앵커도 쓴다.
    idx_tr = np.where(in_tr)[0]
    idx_va = np.where(in_val & (LDEL > 0.5))[0]
    idx_te = np.where(in_te & (LDEL > 0.5))[0]
    best, best_state, bad = -1, None, 0
    for ep in range(epochs):
        m.train()
        perm = np.random.permutation(idx_tr)
        for i in range(0, len(perm), bs):
            j = perm[i:i + bs]
            xb, sb = Xt[j].to(DEV), St[j].to(DEV)
            logit, c, _ = m(xb, sb)
            p_del = torch.sigmoid(logit)
            cb, mb = CtC[j].to(DEV), MtC[j].to(DEV)
            loss = 1.0 - (w_d * sat_data(p_del, Yt_del[j].to(DEV), Lt_del[j].to(DEV))
                          + w_k * sat_knowledge(ax, c, p_del, cb, mb))
            lb = torch.where(TYPE_C.to(DEV).unsqueeze(0), bce(c, cb), (c - cb) ** 2)
            loss = loss + w_concept * (lb * mb).sum() / mb.sum().clamp(min=1)
            opt.zero_grad(); loss.backward(); opt.step()
        m.eval()
        with torch.no_grad():
            pv = np.concatenate([torch.sigmoid(m(Xt[k].to(DEV), St[k].to(DEV))[0]).cpu().numpy()
                                 for k in np.array_split(idx_va, max(1, len(idx_va) // 8192))])
        ap = average_precision_score(Y_DEL[idx_va], pv)
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
    return pt, idx_te


head(f"[D3] 논문식 손실로 **섬망** 예측 · 공리 {len(REAL)}개(머리=Delirium) · 시드 {len(SEEDS)}개")
print("라이브러리:", ltn.__file__, "· 공리 앞부분:", "관측값(data)" if ANTE == "data" else "모델 예측값(pred)")
print("공리:", ", ".join(a[0] for a in REAL))
rows = []
VARIANTS = [("w_K=0.0 (지식 없음)", 0.0, "real"), ("w_K=0.1", 0.1, "real"),
            ("w_K=0.2 (논문값)", 0.2, "real"), ("w_K=0.5", 0.5, "real"),
            ("w_K=0.8", 0.8, "real"),
            ("w_K=0.2 가짜 공리", 0.2, "fake"), ("w_K=0.5 가짜 공리", 0.5, "fake")]
for nm, wk, kind in VARIANTS:
    aucs, aprs = [], []
    for s_ in SEEDS:
        ax = REAL if kind == "real" else fake_axioms(s_)
        p, idx_te = train(wk, ax, s_)
        y = Y_DEL[idx_te]
        aucs.append(100 * roc_auc_score(y, p)); aprs.append(100 * average_precision_score(y, p))
    rows.append({"변형": nm, "w_D": round(1 - wk, 2), "w_K": wk, "공리": kind,
                 "AUROC": round(np.mean(aucs), 2), "SD": round(np.std(aucs), 2),
                 "AUPRC": round(np.mean(aprs), 2)})
    print(f"  {nm:20s} w_D={1-wk:.1f} w_K={wk:.1f} · AUROC {np.mean(aucs):6.2f}±{np.std(aucs):.2f}"
          f" · AUPRC {np.mean(aprs):6.2f}", flush=True)

T = pd.DataFrame(rows)
T.to_csv(os.path.join(OUTD, "ltn_paper_loss_delirium.csv"), index=False, encoding="utf-8-sig")
head("[결과] 논문식 손실 · 섬망 예측")
print(T.to_string(index=False))
r = {x["변형"]: x["AUROC"] for x in rows}
print(f"\n논문값(w_K=0.2) − 지식 없음(w_K=0)   {r['w_K=0.2 (논문값)'] - r['w_K=0.0 (지식 없음)']:+.2f}")
print(f"진짜 − 가짜 (w_K=0.2)              {r['w_K=0.2 (논문값)'] - r['w_K=0.2 가짜 공리']:+.2f}")
print(f"진짜 − 가짜 (w_K=0.5)              {r['w_K=0.5'] - r['w_K=0.5 가짜 공리']:+.2f}")
print("\n사망 예측 설정(eda/39)의 진짜−가짜 −0.01 과 비교한다.")
print("여기서 차이가 커지면 '대상 불일치가 원인'이고, 여기서도 0 이면 대상도 원인이 아니다.")
print(f"\n-> {OUTD}")
