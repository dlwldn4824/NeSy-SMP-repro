# -*- coding: utf-8 -*-
# ============================================================================
# 안 1 — 결과를 섬망 발생이 아니라 **임상 결과(원내 사망)** 로 바꾼다.
#        섬망은 결과가 아니라 **중간 개념(mediator)** 으로 둔다.
#
#   공리 구조:  위험인자(진정·통증·거동·나이·동반질환) → Delirium → Death
#   섬망 라벨(CAM-ICU)은 중간 개념의 지도 신호로만 쓴다. 결과 라벨은 사망이므로
#   라벨 미관찰(UTA) 앵커도 평가에 포함된다 — 23_ 에서 29% 를 버려야 했던 문제가 사라진다.
#
# 데이터·분할·시계열·요약벡터 Z·개념 정의는 eda/23_stage34_bilstm_cbm.py 의
# 전처리부를 그대로 exec 해서 재사용한다 (한 글자도 다시 쓰지 않는다).
#
# 비교 모델
#   2z XGB            요약 벡터 Z (상한 기준)
#   3  BiLSTM         개념·공리 없음
#   4c CBM            연속 개념 병목
#   4m +mediator      개념 + 섬망 중간 개념 지도
#   5a LTN (위험인자→섬망 공리만)
#   5b LTN (+ 섬망→사망 공리)        <- 안 1 의 핵심
#   5c LTN (+ 섬망→사망, w_K 0.5)
#
# 지표: 원내 사망 AUROC·AUPRC (기저 대비 정규화), stay 단위 집계, 2020-22 외부검증
# 사용: EDA_DATA=notes/eda python eda/29_outcome_mortality.py [--seeds 42,7,2024]
# ============================================================================
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--seeds", default="42,7,2024")
ap.add_argument("--epochs", type=int, default=10)
ap.add_argument("--tag", default="stage29")
args = ap.parse_args()

HERE = Path(__file__).resolve().parent
SRC = (HERE / "23_stage34_bilstm_cbm.py").read_text(encoding="utf-8")
MARK = "# ================================================================ PADIS 공리"
exec(compile(SRC[: SRC.index(MARK)], "23_prefix", "exec"), globals())   # noqa: S102

import numpy as np                                                   # noqa: E402
import pandas as pd                                                  # noqa: E402
import torch                                                         # noqa: E402
import torch.nn as nn                                                # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score   # noqa: E402

OUTD = os.path.join(OUT, args.tag)
os.makedirs(OUTD, exist_ok=True)

# ================================================================ 결과 라벨 (사망)
head("[라벨] 결과를 원내 사망으로 교체")
_st = b.set_index("stay_id")
cam["hosp_death"] = cam["stay_id"].map(_st["hospital_expire_flag"]).astype(float)
_dt = pd.to_datetime(_st["deathtime"])
_anchor_t = cam["stay_id"].map(intime) + pd.to_timedelta(cam["hr"], unit="h")
_dgap = (cam["stay_id"].map(_dt) - _anchor_t).dt.total_seconds() / 3600.0
cam["death_7d"] = ((_dgap >= 0) & (_dgap <= 24 * 7)).astype(float)
cam["death_gap_h"] = _dgap

Y_DEATH = cam["hosp_death"].to_numpy(np.float32)
Y_D7 = cam["death_7d"].to_numpy(np.float32)
Y_DEL = cam["y"].to_numpy(np.float32)            # 섬망 (중간 개념 지도용)
LDEL = L.astype(np.float32)                      # 섬망 라벨 관찰 마스크

print(f"앵커 전체 {len(cam):,} · 섬망 라벨 있는 앵커 {int(L.sum()):,} ({100*L.mean():.1f}%)")
for nm, yy in [("원내 사망", Y_DEATH), ("앵커 후 7일 내 사망", Y_D7)]:
    print(f"  {nm}: 앵커 기준 {100*yy.mean():.1f}% · "
          f"test 앵커 {100*yy[in_te].mean():.1f}% · "
          f"stay 단위 {100*cam.groupby('stay_id')[('hosp_death' if nm.startswith('원내') else 'death_7d')].first().mean():.1f}%")

Yt_death = torch.from_numpy(Y_DEATH)
Yt_d7 = torch.from_numpy(Y_D7)
Yt_del = torch.from_numpy(Y_DEL)
Lt_del = torch.from_numpy(LDEL)

# ================================================================ 공리
# 23_ 의 AXIOMS 를 그대로 쓰되 head 를 **중간 개념 p_del** 로 받고,
# 안 1 의 핵심인 Delirium → Death 를 추가한다.
CI = {n: i for i, n in enumerate(CONCEPTS_C)}
TAU = 0.35
GRADE_W = {"strong": 1.0, "moderate": 0.6, "low": 0.3, "cohort": 0.3, "derived": 0.5,
           "inconclusive": 0.2}


def _zthr(name, raw):
    i = CI[name]
    return float((raw - _cmu[i]) / _csd[i])


# (이름, 개념, 방향, 임계z, head, head 부정, GRADE)   head: Delirium | Death | 개념명
AX_RISK = [
    ("Benzo→Delirium", "BenzoFrac", +1, _zthr("BenzoFrac", 1e-6), "Delirium", False, "strong"),
    ("DeepSedation→Delirium", "RASSmin", -1, _zthr("RASSmin", -4.0), "Delirium", False, "low"),
    ("SedationIntensity→Delirium", "RASSnegmean", -1, _zthr("RASSnegmean", -2.0), "Delirium", False, "cohort"),
    ("SeverePain→Delirium", "PainNRSmax", +1, _zthr("PainNRSmax", 4.0), "Delirium", False, "inconclusive"),
    ("OlderAge→Delirium", "Age", +1, _zthr("Age", 65.0), "Delirium", False, "strong"),
    ("Dexmed→¬Delirium", "DexmedFrac", +1, _zthr("DexmedFrac", 1e-6), "Delirium", True, "moderate"),
    ("EarlyMobility→¬Delirium", "MobJHHLM", +1, _zthr("MobJHHLM", 4.0), "Delirium", True, "low"),
]
if HAS_GAP:
    AX_RISK += [
        ("BloodTransfusion→Delirium", "BloodTransfusion", +1, 0.5, "Delirium", False, "strong"),
        ("Dementia→Delirium", "Dementia", +1, 0.5, "Delirium", False, "strong"),
        ("Trauma→Delirium", "Trauma", +1, 0.5, "Delirium", False, "strong"),
        ("Hypertension→Delirium", "Hypertension", +1, 0.5, "Delirium", False, "moderate"),
    ]
# 중간 개념 → 결과. PADIS 2018 원문은 이 규칙을 뒷받침하지 않는다 (docs/kg/KG_PADIS_FOLLOWUP_2026-09-23.md §1)
# → 출처 등급을 external 로 따로 둔다.
AX_MED = [("Delirium→Death", None, 0, 0.0, "Death", False, "external")]
GRADE_W["external"] = 0.5
# 고령·깊은 진정은 사망 쪽으로도 널리 쓰이는 규칙이라 비교용으로 따로 둔다 (기본 비활성)
AX_DIRECT = [
    ("OlderAge→Death", "Age", +1, _zthr("Age", 65.0), "Death", False, "external"),
    ("DeepSedation→Death", "RASSmin", -1, _zthr("RASSmin", -4.0), "Death", False, "cohort"),
]


def make_axioms(use_med: bool, use_direct: bool = False):
    ax = list(AX_RISK) + (list(AX_MED) if use_med else []) + (list(AX_DIRECT) if use_direct else [])
    w = torch.tensor([GRADE_W[a[6]] for a in ax], dtype=torch.float32)
    return ax, w / w.sum()


def axiom_sat(ax, w, c, p_del, p_death, per_axiom=False):
    """함축은 Reichenbach(1-a+ab), 전칭은 pMeanError(p=2). 23_ 와 같은 식."""
    sats = []
    for nm, cn, sgn, thr, hd, neg, _g in ax:
        if cn is None:                       # Delirium → Death
            a = p_del
        else:
            z = c[:, CI[cn]]
            a = (torch.sigmoid(z) if CTYPE_C[CI[cn]] == "bin"
                 else torch.sigmoid(sgn * (z - thr) / TAU))
        b = p_del if hd == "Delirium" else (p_death if hd == "Death" else torch.sigmoid(c[:, CI[hd]]))
        if neg:
            b = 1.0 - b
        sat = 1.0 - a + a * b
        sats.append(1.0 - torch.sqrt(torch.clamp(((1.0 - sat) ** 2).mean(), min=1e-9)))
    s = torch.stack(sats)
    return s if per_axiom else (s * w.to(s.device)).sum()


# ================================================================ 모델
class Net2(nn.Module):
    """사망 출력 + 연속 개념 + 섬망 중간 개념 헤드."""

    def __init__(self, nch, nstat, nz, nconcept, hid=64, bottleneck=False, mediator=False):
        super().__init__()
        self.bottleneck, self.mediator = bottleneck, mediator
        self.lstm = nn.LSTM(nch, hid, batch_first=True, bidirectional=True)
        self.att = nn.Linear(hid * 2, 1)
        self.stat = nn.Sequential(nn.Linear(nstat, hid), nn.ReLU())
        self.enc = nn.Sequential(nn.Linear(hid * 3, hid), nn.ReLU(), nn.Dropout(0.1))
        self.concept = nn.Linear(hid, nconcept)
        self.delirium = nn.Linear(hid, 1)
        nin = (nconcept + (1 if mediator else 0)) if bottleneck else hid
        self.out = nn.Linear(nin, 1)

    def forward(self, x, s, z=None):
        o, _ = self.lstm(x)
        w = torch.softmax(self.att(o), 1)
        h = self.enc(torch.cat([(o * w).sum(1), self.stat(s)], 1))
        c = self.concept(h)
        d = self.delirium(h).squeeze(1)
        if self.bottleneck:
            feats = [torch.where(TYPE_C.to(c.device), torch.sigmoid(c), c)]
            if self.mediator:
                feats.append(torch.sigmoid(d).unsqueeze(1))
            return self.out(torch.cat(feats, 1)).squeeze(1), c, d
        return self.out(h).squeeze(1), c, d


def run(name, *, bottleneck, w_concept, w_mediator, w_axiom, use_med_axiom=False,
        use_direct=False, target="hosp", seed=SEED, epochs=None, quiet=False, bs=2048,
        ax_override=None):
    epochs = epochs or args.epochs
    torch.manual_seed(seed); np.random.seed(seed)
    yt = Yt_death if target == "hosp" else Yt_d7
    ylab = Y_DEATH if target == "hosp" else Y_D7
    ax, axw = ax_override if ax_override is not None else make_axioms(use_med_axiom, use_direct)
    m = Net2(NCH, len(SFEAT), Z.shape[1], CtC.shape[1],
             bottleneck=bottleneck, mediator=w_mediator > 0).to(DEV)
    opt = torch.optim.Adam(m.parameters(), lr=1e-3)
    bce = nn.BCEWithLogitsLoss(reduction="none")
    idx_tr = np.where(in_tr)[0]            # 결과 라벨은 모든 앵커에 있다
    idx_va, idx_te = np.where(in_val)[0], np.where(in_te)[0]
    best, best_state, bad = -1, None, 0
    for ep in range(epochs):
        m.train()
        perm = np.random.permutation(idx_tr)
        tot = 0.0
        for i in range(0, len(perm), bs):
            j = perm[i:i + bs]
            xb, sb = Xt[j].to(DEV), St[j].to(DEV)
            logit, c, dlog = m(xb, sb)
            loss = bce(logit, yt[j].to(DEV)).mean()
            if w_concept > 0:
                cb, mb = CtC[j].to(DEV), MtC[j].to(DEV)
                lb = torch.where(TYPE_C.to(DEV).unsqueeze(0), bce(c, cb), (c - cb) ** 2)
                loss = loss + w_concept * (lb * mb).sum() / mb.sum().clamp(min=1)
            if w_mediator > 0:
                lm = Lt_del[j].to(DEV)
                loss = loss + w_mediator * (bce(dlog, Yt_del[j].to(DEV)) * lm).sum() / lm.sum().clamp(min=1)
            if w_axiom > 0:
                loss = loss + w_axiom * (1.0 - axiom_sat(ax, axw, c, torch.sigmoid(dlog),
                                                         torch.sigmoid(logit)))
            opt.zero_grad(); loss.backward(); opt.step()
            tot += float(loss.detach()) * len(j)
        m.eval()
        with torch.no_grad():
            pv = np.concatenate([torch.sigmoid(m(Xt[j].to(DEV), St[j].to(DEV))[0]).cpu().numpy()
                                 for j in np.array_split(idx_va, max(1, len(idx_va) // 8192))])
        ap = average_precision_score(ylab[idx_va], pv)
        if not quiet:
            print(f"  {name} ep{ep+1} loss={tot/len(perm):.4f} val_AUPRC={100*ap:.1f}", flush=True)
        if ap > best:
            best, best_state, bad = ap, {k: v.detach().clone() for k, v in m.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 2:
                break
    m.load_state_dict(best_state); m.eval()
    with torch.no_grad():
        parts = [m(Xt[j].to(DEV), St[j].to(DEV)) for j in np.array_split(idx_te, max(1, len(idx_te) // 8192))]
        pt = np.concatenate([torch.sigmoid(p[0]).cpu().numpy() for p in parts])
        pd_del = np.concatenate([torch.sigmoid(p[2]).cpu().numpy() for p in parts])
        cc = np.concatenate([p[1].cpu().numpy() for p in parts])
        sat = None
        if w_axiom > 0:
            sat = np.mean([axiom_sat(ax, axw, p[1], torch.sigmoid(p[2]), torch.sigmoid(p[0]),
                                     per_axiom=True).cpu().numpy() for p in parts], 0)
    return dict(idx=idx_te, p=pt, p_del=pd_del, c=cc, sat=sat, ax=[a[0] for a in ax], model=m)


# ================================================================ 실행
VARIANTS = [
    ("3  BiLSTM", dict(bottleneck=False, w_concept=0.0, w_mediator=0.0, w_axiom=0.0)),
    ("4c CBM 연속", dict(bottleneck=True, w_concept=1.0, w_mediator=0.0, w_axiom=0.0)),
    ("4m CBM+섬망 mediator", dict(bottleneck=True, w_concept=1.0, w_mediator=1.0, w_axiom=0.0)),
    ("5a LTN 위험인자만 (w .2)", dict(bottleneck=True, w_concept=1.0, w_mediator=1.0,
                                     w_axiom=0.2, use_med_axiom=False)),
    ("5b LTN +섬망→사망 (w .2)", dict(bottleneck=True, w_concept=1.0, w_mediator=1.0,
                                     w_axiom=0.2, use_med_axiom=True)),
    ("5c LTN +섬망→사망 (w .5)", dict(bottleneck=True, w_concept=1.0, w_mediator=1.0,
                                     w_axiom=0.5, use_med_axiom=True)),
    ("5d LTN +직접 사망 공리 (w .2)", dict(bottleneck=True, w_concept=1.0, w_mediator=1.0,
                                          w_axiom=0.2, use_med_axiom=True, use_direct=True)),
]
SEEDS = [int(s) for s in args.seeds.split(",")]
TARGETS = [("hosp", "원내 사망"), ("d7", "앵커 후 7일 내 사망")]

era = cam["stay_id"].map(_st["anchor_year_group"]).to_numpy()
stay = cam["stay_id"].to_numpy()

from xgboost import XGBClassifier    # noqa: E402

allrows, satrows = [], []
for tgt, tname in TARGETS:
    head(f"[학습] 결과 = {tname} · device={DEV}")
    ylab = Y_DEATH if tgt == "hosp" else Y_D7
    idx_te = np.where(in_te)[0]
    base = 100 * ylab[idx_te].mean()
    # XGB (같은 Z)
    x = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.05, subsample=0.8,
                      colsample_bytree=0.8, eval_metric="aucpr", random_state=SEED,
                      n_jobs=-1, tree_method="hist")
    x.fit(Z[in_tr], ylab[in_tr].astype(int))
    px = x.predict_proba(Z[idx_te])[:, 1]
    runs = {"2z XGB (같은 Z)": [px]}
    for nm, kw in VARIANTS:
        runs[nm] = []
        for sd in SEEDS:
            r = run(nm, target=tgt, seed=sd, quiet=(sd != SEEDS[0]), **kw)
            runs[nm].append(r["p"])
            if r["sat"] is not None and sd == SEEDS[0]:
                for a, s_ in zip(r["ax"], r["sat"]):
                    satrows.append({"결과": tname, "모델": nm, "공리": a, "만족도": round(float(s_), 3)})
    # 평가
    ext = np.isin(era[idx_te], ["2020 - 2022"])
    for nm, ps in runs.items():
        auc = [100 * roc_auc_score(ylab[idx_te], p) for p in ps]
        apr = [100 * average_precision_score(ylab[idx_te], p) for p in ps]
        sv = [100 * roc_auc_score(pd.Series(ylab[idx_te]).groupby(stay[idx_te]).first(),
                                  pd.Series(p).groupby(stay[idx_te]).mean()) for p in ps]
        ex = ([100 * roc_auc_score(ylab[idx_te][ext], p[ext]) for p in ps]
              if ext.sum() > 100 and len(set(ylab[idx_te][ext])) > 1 else [np.nan])
        allrows.append({"결과": tname, "모델": nm, "AUROC": round(np.mean(auc), 1),
                        "AUROC SD": round(np.std(auc), 2), "AUPRC": round(np.mean(apr), 1),
                        "기저%": round(base, 1),
                        "정규화 AUPRC": round(100 * (np.mean(apr) - base) / (100 - base), 1),
                        "stay 단위 AUROC": round(np.mean(sv), 1),
                        "2020-22 AUROC": round(np.mean(ex), 1) if np.isfinite(ex).all() else None,
                        "시드": len(ps)})
        print(f"  {nm:28s} AUROC {np.mean(auc):5.1f}±{np.std(auc):.2f} · AUPRC {np.mean(apr):5.1f}"
              f" (기저 {base:.1f}) · stay {np.mean(sv):5.1f}", flush=True)

T = pd.DataFrame(allrows)
T.to_csv(os.path.join(OUTD, "mortality_results.csv"), index=False, encoding="utf-8-sig")
head("[결과] 결과 교체 — 사망 예측")
print(T.to_string(index=False))
if satrows:
    S_ = pd.DataFrame(satrows)
    S_.to_csv(os.path.join(OUTD, "mortality_axiom_sat.csv"), index=False, encoding="utf-8-sig")
    head("[공리 만족도] test 앵커")
    print(S_.pivot_table(index="공리", columns=["결과", "모델"], values="만족도").to_string())
print(f"\n-> {OUTD}")
print(f"총 {time.time()-t0:.0f}초")
