# -*- coding: utf-8 -*-
# ============================================================================
# 구조 가설 ① — 공리가 결과에 직접 닿도록 경로를 바꾼다
#
#   음성 대조군에서 공리 항이 무효로 나왔다(`docs/delirium/DELIRIUM_AXIOM_CONTROL_2026-10-04.md`).
#   원인 가설: 결과 헤드가 표현 h 를 그냥 받아버려서, 공리가 밀어 주는 개념·섬망 값이
#   결과로 가는 경로가 사실상 우회된다.
#
#   변형
#     base        지금 구조 (개념 + 섬망 → 사망 선형층)            = 안 1 의 5b
#     mono        위 선형층의 가중치를 **비음수**로 제약 (softplus)
#                 → 섬망 확률이 오르면 사망 확률이 내려갈 수 없다. 공리와 구조가 일치한다.
#     mediated    사망 = a·p_del + b  (**섬망만** 통과) → 공리가 결과에 직접 작용
#     twostage    1단계: 섬망 헤드 + 공리로 학습 후 고정 → 2단계: 사망 헤드만 학습
#
#   각 변형을 공리 없음 / 진짜 공리 / 가짜 공리(머리 무작위)로 돌려서
#   "구조를 바꾸면 진짜-가짜 차이가 생기나"를 본다.
#
# 사용: EDA_DATA=notes/eda python eda/35_structural_bottleneck.py [--seeds 42,7,2024]
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
import torch.nn as nn                                                # noqa: E402
import torch.nn.functional as F                                      # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score   # noqa: E402

OUTD = os.path.join(OUT, "stage35")
os.makedirs(OUTD, exist_ok=True)
SEEDS = [int(s) for s in args.seeds.split(",")]
REAL, REAL_W = make_axioms(True)


def fake_axioms(seed):
    # A4: 머리/부정을 새로 뽑으면 가짜 쪽 "사망" 머리가 진짜(13개 중 1개)보다 훨씬 많아져
    #     비교가 공리 내용이 아니라 머리 분포 차이가 된다. 그래서 **같은 집합을 섞기만** 한다.
    rng = random.Random(seed)
    heads = [a[4] for a in REAL]; negs = [a[5] for a in REAL]
    rng.shuffle(heads); rng.shuffle(negs)
    return [(nm, cn, sgn, thr, heads[i], negs[i], g)
            for i, (nm, cn, sgn, thr, hd, neg, g) in enumerate(REAL)], REAL_W


class Net3(nn.Module):
    """mode: base | mono | mediated | mediated_plus"""

    def __init__(self, nch, nstat, nconcept, mode, hid=64):
        super().__init__()
        self.mode = mode
        self.lstm = nn.LSTM(nch, hid, batch_first=True, bidirectional=True)
        self.att = nn.Linear(hid * 2, 1)
        self.stat = nn.Sequential(nn.Linear(nstat, hid), nn.ReLU())
        self.enc = nn.Sequential(nn.Linear(hid * 3, hid), nn.ReLU(), nn.Dropout(0.1))
        self.concept = nn.Linear(hid, nconcept)
        self.delirium = nn.Linear(hid, 1)
        nin = 1 if mode == "mediated" else nconcept + 1
        self.w = nn.Parameter(torch.zeros(nin))         # A3: 섬망 가중치만 softplus(비음수)
        self.bias = nn.Parameter(torch.zeros(1))
        self.out = nn.Linear(nin, 1)                    # base 전용

    def forward(self, x, s, z=None):
        o, _ = self.lstm(x)
        a = torch.softmax(self.att(o), 1)
        h = self.enc(torch.cat([(o * a).sum(1), self.stat(s)], 1))
        c = self.concept(h)
        d = self.delirium(h).squeeze(1)
        pd_ = torch.sigmoid(d)
        cz = torch.where(TYPE_C.to(c.device), torch.sigmoid(c), c)
        if self.mode == "mediated":
            feats = pd_.unsqueeze(1)
        else:
            feats = torch.cat([cz, pd_.unsqueeze(1)], 1)
        if self.mode == "base":
            logit = self.out(feats).squeeze(1)
        else:                                            # mono · mediated
            # A3: "섬망이 사망 위험을 높인다"만 부호를 고정한다. 다른 개념의 방향은
            #     공리가 정하지 않으므로 자유 가중치로 둔다(섬망 가중치는 feats 의 마지막).
            w_eff = (F.softplus(self.w) if self.mode == "mediated"
                     else torch.cat([self.w[:-1], F.softplus(self.w[-1:])]))
            logit = (feats * w_eff).sum(1) + self.bias
        return logit, c, d


def train(mode, w_axiom, ax, axw, seed, target="hosp", epochs=None, twostage=False, bs=2048):
    epochs = epochs or args.epochs
    torch.manual_seed(seed); np.random.seed(seed)
    yt = Yt_death if target == "hosp" else Yt_d7
    ylab = Y_DEATH if target == "hosp" else Y_D7
    m = Net3(NCH, len(SFEAT), CtC.shape[1], mode).to(DEV)
    bce = nn.BCEWithLogitsLoss(reduction="none")
    idx_tr, idx_va, idx_te = np.where(in_tr)[0], np.where(in_val)[0], np.where(in_te)[0]

    def epoch_pass(params, use_task, use_concept_axiom):
        opt = torch.optim.Adam(params, lr=1e-3)
        best, best_state, bad = -1, None, 0
        for ep in range(epochs):
            m.train()
            perm = np.random.permutation(idx_tr)      # A1: 에폭마다 전체를 한 번 섞는다
            for i in range(0, len(idx_tr), bs):
                j = perm[i:i + bs]
                xb, sb = Xt[j].to(DEV), St[j].to(DEV)
                logit, c, dlog = m(xb, sb)
                loss = torch.zeros((), device=DEV)
                if use_task:
                    loss = loss + bce(logit, yt[j].to(DEV)).mean()
                if use_concept_axiom:
                    cb, mb = CtC[j].to(DEV), MtC[j].to(DEV)
                    lb = torch.where(TYPE_C.to(DEV).unsqueeze(0), bce(c, cb), (c - cb) ** 2)
                    loss = loss + (lb * mb).sum() / mb.sum().clamp(min=1)
                    lm = Lt_del[j].to(DEV)
                    loss = loss + (bce(dlog, Yt_del[j].to(DEV)) * lm).sum() / lm.sum().clamp(min=1)
                    if w_axiom > 0:
                        loss = loss + w_axiom * (1.0 - axiom_sat(ax, axw, c, torch.sigmoid(dlog),
                                                                 torch.sigmoid(logit)))
                opt.zero_grad(); loss.backward(); opt.step()
            m.eval()
            with torch.no_grad():
                pv = np.concatenate([torch.sigmoid(m(Xt[j].to(DEV), St[j].to(DEV))[0]).cpu().numpy()
                                     for j in np.array_split(idx_va, max(1, len(idx_va) // 8192))])
            ap = average_precision_score(ylab[idx_va], pv)
            if ap > best:
                best, best_state, bad = ap, {k: v.detach().clone() for k, v in m.state_dict().items()}, 0
            else:
                bad += 1
                if bad >= 2:
                    break
        if best_state:
            m.load_state_dict(best_state)

    if twostage:
        # 1단계: 개념·섬망 + 공리만 (사망 손실 없음) → 2단계: 사망 헤드만
        epoch_pass([p for n, p in m.named_parameters() if not n.startswith(("w", "bias", "out"))],
                   use_task=False, use_concept_axiom=True)
        for n, p in m.named_parameters():
            if not n.startswith(("w", "bias", "out")):
                p.requires_grad_(False)
        epoch_pass([p for n, p in m.named_parameters() if n.startswith(("w", "bias", "out"))],
                   use_task=True, use_concept_axiom=False)
    else:
        epoch_pass(list(m.parameters()), use_task=True, use_concept_axiom=True)

    m.eval()
    with torch.no_grad():
        parts = [m(Xt[j].to(DEV), St[j].to(DEV))
                 for j in np.array_split(idx_te, max(1, len(idx_te) // 8192))]
        p = np.concatenate([torch.sigmoid(x[0]).cpu().numpy() for x in parts])
        sat = np.mean([axiom_sat(ax, axw, x[1], torch.sigmoid(x[2]), torch.sigmoid(x[0]),
                                 per_axiom=True).cpu().numpy() for x in parts], 0) if w_axiom > 0 else None
    return p, sat


head(f"[구조 가설 ①] 공리 경로 바꾸기 (결과 = 원내 사망, 시드 {len(SEEDS)}개)")
idx_te = np.where(in_te)[0]
y = Y_DEATH[idx_te]
rows = []
MODES = [("base (현재 구조)", "base", False), ("mono (비음수 가중)", "mono", False),
         ("mediated (섬망만 통과)", "mediated", False),
         ("twostage (섬망 고정 후 사망)", "mono", True)]
for nm, mode, two in MODES:
    for axn, mk in [("공리 없음", None), ("진짜 공리", lambda s: (REAL, REAL_W)),
                    ("가짜 공리", fake_axioms)]:
        ps = []
        for s in SEEDS:
            if mk is None:
                ax, axw, w = REAL, REAL_W, 0.0
            else:
                ax, axw = mk(s); w = 0.2
            p, _ = train(mode, w, ax, axw, s, twostage=two)
            ps.append(p)
        auc = [100 * roc_auc_score(y, p) for p in ps]
        apr = [100 * average_precision_score(y, p) for p in ps]
        rows.append({"구조": nm, "공리": axn, "AUROC": round(np.mean(auc), 2),
                     "SD": round(np.std(auc), 2), "AUPRC": round(np.mean(apr), 2)})
        print(f"  {nm:26s} {axn:7s} AUROC {np.mean(auc):6.2f}±{np.std(auc):.2f}"
              f" · AUPRC {np.mean(apr):6.2f}", flush=True)

T = pd.DataFrame(rows)
T.to_csv(os.path.join(OUTD, "structural.csv"), index=False, encoding="utf-8-sig")
head("[결과] 구조별 · 공리 유무")
print(T.pivot(index="구조", columns="공리", values="AUROC").to_string())
print("\n진짜 − 가짜 (구조별)")
pv = T.pivot(index="구조", columns="공리", values="AUROC")
for k in pv.index:
    print(f"  {k:26s} {pv.loc[k, '진짜 공리'] - pv.loc[k, '가짜 공리']:+.2f}"
          f"   (공리 없음 대비 {pv.loc[k, '진짜 공리'] - pv.loc[k, '공리 없음']:+.2f})")
print(f"\n-> {OUTD}")
