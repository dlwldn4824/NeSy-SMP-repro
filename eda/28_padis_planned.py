# -*- coding: utf-8 -*-
# ============================================================================
# PADIS 섬망 — 계획(MODELING_ONEPAGER §2·§3)의 남은 항목
#
#   A  5r  LTN 검수본      docs/KG_RULE_REVIEW.md 권고대로 고친 공리로 5단계 재실행 (최종 승인 전 · 잠정)
#   B  6   LNN            가중 Łukasiewicz 함축 뉴런의 경계 추론. '전부 UTA' 앵커를 구간 진리값 [0,1] 로 학습에 넣는다
#   C  4b' Assessable 재실험  미관찰 앵커를 넣되 라벨 배치를 줄이지 않고(균형 배치) Assessable 손실만 따로 가중
#   D  평가 프로토콜 미완    연도 외부검증(2011-16 학습 → 2017-19 · 2020-22 평가) · calibration ·
#                          ICU 유형·era 하위군 · 정규화 AUPRC · stay 가중 AUPRC
#
# 데이터 준비는 eda/23_stage34_bilstm_cbm.py 의 앞부분(학습 직전까지)을 그대로 실행해 재사용한다.
# 23_ 파일은 고치지 않는다 — 기존 1~5단계 수치의 재현성을 지키기 위해.
#
# 사용: EDA_DATA=<notes/eda> python eda/28_padis_planned.py      (PADIS28_QUICK=1 이면 점검용 축소 실행)
# ============================================================================
import os, sys, time
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
_p23 = os.path.join(HERE, "23_stage34_bilstm_cbm.py")
_src = open(_p23, encoding="utf-8").read()
_cut = _src.index("\nAX_SAT = {}\n")
globals()["__file__"] = _p23
exec(compile(_src[:_cut], "23_stage34_bilstm_cbm.py (데이터 준비)", "exec"), globals())
__file__ = os.path.join(HERE, "28_padis_planned.py")
assert HAS_GAP, "eda/25_ 산출물이 필요하다"

QUICK = os.environ.get("PADIS28_QUICK") == "1"
SEEDS = [42] if QUICK else [42, 7, 2024]
EPOCHS = 2 if QUICK else 10
OUT28 = os.path.join(OUT, "stage28_quick" if QUICK else "stage28")
os.makedirs(OUT28, exist_ok=True)
T28 = time.time()

y_all = cam.y.to_numpy().astype(int)
v_all = cam.v.to_numpy()
stay_all = cam.stay_id.to_numpy()

# ---------------- '전부 UTA' 앵커와 지연 라벨 ----------------
# 전부 UTA = 라벨 미관찰이지만 (t, t+24h] 에 CAM 기록은 있다(모두 UTA). 계획 §2: LNN 의 대상.
# 지연 라벨 = (t+24h, t+72h] 의 확정 CAM — 전부 UTA 앵커 예측을 사후에 대략 점검하는 대리 지표.
_nany = np.zeros(len(cam), int); _dconf = np.zeros(len(cam), int); _dpos = np.zeros(len(cam), int)
for a, n in zip(first, cnt):
    hh = h[a:a + n]; idx = np.arange(n)
    j24 = np.searchsorted(hh, hh + 24.0, side="right")
    j72 = np.searchsorted(hh, hh + 72.0, side="right")
    _nany[a:a + n] = j24 - idx - 1
    _dconf[a:a + n] = cumC[a + j72] - cumC[a + j24]
    _dpos[a:a + n] = cumP[a + j72] - cumP[a + j24]
ALLUTA = (~L) & (_nany > 0)
print(f"전부 UTA 앵커 {int(ALLUTA.sum()):,} (전체 {len(cam):,} 의 {100*ALLUTA.mean():.1f}%) · "
      f"그중 72h 안 확정 기록 있음 {100*(_dconf[ALLUTA] > 0).mean():.1f}%", flush=True)

# ================================================================ A. 검수본 공리
# docs/KG_RULE_REVIEW.md 권고 반영:
#   R-15 SeverePain 보류 → 제외 · X-01 SedationIntensity → R-12 와 통합(제외)
#   R-07 Trauma strong → moderate · R-12 DeepSedation 등급 표기 low → cohort(가중 동일)
#   R-17 EarlyMobility 발생 예측에서는 가중 축소(low 의 절반)
#   R-16 Dexmed 절대 효과 → '벤조 대비' 비교형 제약
GW = dict(GRADE_W, low_half=GRADE_W["low"] / 2)
AX_REV = [
    ("Benzo→Delirium", "BenzoFrac", +1, _zthr("BenzoFrac", 1e-6), "Delirium", False, "strong"),
    ("DeepSedation→Delirium", "RASSmin", -1, _zthr("RASSmin", -4.0), "Delirium", False, "cohort"),
    ("OlderAge→Delirium", "Age", +1, _zthr("Age", 65.0), "Delirium", False, "strong"),
    ("EarlyMobility→¬Delirium", "MobJHHLM", +1, _zthr("MobJHHLM", 4.0), "Delirium", True, "low_half"),
    ("DeepSedation→CurrentUTA", "RASSmin", -1, _zthr("RASSmin", -4.0), "CurrentUTA", False, "derived"),
    ("BloodTransfusion→Delirium", "BloodTransfusion", +1, 0.5, "Delirium", False, "strong"),
    ("Dementia→Delirium", "Dementia", +1, 0.5, "Delirium", False, "strong"),
    ("Trauma→Delirium", "Trauma", +1, 0.5, "Delirium", False, "moderate"),
    ("Hypertension→Delirium", "Hypertension", +1, 0.5, "Delirium", False, "moderate"),
]
PAIR_REV = [("Dexmed≤Benzo (진정제 비교)", "DexmedFrac", "BenzoFrac", "moderate")]
REV_NAMES = [a[0] for a in AX_REV] + [p[0] for p in PAIR_REV]


def memb(c, cn, sgn, thr):
    z = c[:, CI[cn]]
    return torch.sigmoid(z) if CTYPE_C[CI[cn]] == "bin" else torch.sigmoid(sgn * (z - thr) / TAU)


def sat_rev(c, p, per_axiom=False):
    sats, ws = [], []
    for nm, cn, sgn, thr, hd, neg, gr in AX_REV:
        a_ = memb(c, cn, sgn, thr)
        b_ = p if hd == "Delirium" else torch.sigmoid(c[:, CI[hd]])
        if neg:
            b_ = 1.0 - b_
        s_ = 1.0 - a_ + a_ * b_
        sats.append(1.0 - torch.sqrt(torch.clamp(((1.0 - s_) ** 2).mean(), min=1e-9)))
        ws.append(GW[gr])
    for nm, cd, cb, gr in PAIR_REV:
        ad, ab = memb(c, cd, +1, _zthr(cd, 1e-6)), memb(c, cb, +1, _zthr(cb, 1e-6))
        wd, wb = ad * (1 - ab), ab * (1 - ad)          # 덱스만 / 벤조만
        md = (wd * p).sum() / wd.sum().clamp(min=1e-6)
        mb = (wb * p).sum() / wb.sum().clamp(min=1e-6)
        sats.append(1.0 - torch.relu(md - mb))
        ws.append(GW[gr])
    st_ = torch.stack(sats)
    if per_axiom:
        return st_
    w_ = torch.tensor(ws, device=st_.device)
    return (st_ * w_).sum() / w_.sum()


# ================================================================ B. LNN (6단계)
# LNN(Riegel et al., 2020)의 가중 Łukasiewicz 함축  a→b = clamp(w_a(1−a) + w_b·b)  (β=1, w ≥ 1)
# 규칙 k 를 진리 하한 τ_k(=GRADE 가중) 로 단언하면 하향 추론으로 머리의 경계가 나온다:
#     b ≥ (τ_k − w_a(1−a)) / w_b          (머리가 ¬Delirium 이면 Delirium 의 상한)
# - 규칙 가중치 w 는 **실제 라벨과의 모순**으로만 학습한다(데이터가 규칙을 약하게 만든다).
# - 모델 예측은 규칙 경계(고정) 밖에 있을 때만 벌점을 받는다.
# - '전부 UTA' 앵커는 라벨 구간 [0,1] — 과제 손실 없이 경계 손실에만 참여한다.
# IBM lnn 라이브러리가 아니라 위 식을 torch 로 직접 구현한 것이다.
AX_LNN = [(a[0], a[1], a[2], a[3], a[5], a[6]) for a in AX_REV if a[4] == "Delirium"]


class LNNRules(nn.Module):
    def __init__(self, rules):
        super().__init__()
        self.rules = rules
        # w ≥ 1 은 매 step 뒤 사영(clamp)으로 지킨다. softplus 재매개화는 w≈1 근처에서 기울기가 거의 0이라 안 배웠다.
        self.w_a = nn.Parameter(torch.ones(len(rules)))
        self.w_b = nn.Parameter(torch.ones(len(rules)))
        self.register_buffer("tau", torch.tensor([GW[r[5]] for r in rules], dtype=torch.float32))
        self.register_buffer("neg", torch.tensor([r[4] for r in rules]))

    def weights(self):
        return self.w_a, self.w_b

    @torch.no_grad()
    def project(self, w_max=10.0):
        self.w_a.clamp_(1.0, w_max); self.w_b.clamp_(1.0, w_max)

    def bounds(self, c):
        wa, wb = self.weights()
        A = torch.stack([memb(c, r[1], r[2], r[3]) for r in self.rules], 1)
        lb = ((self.tau - wa * (1.0 - A)) / wb).clamp(0.0, 1.0)
        zero = torch.zeros_like(lb)
        lower = torch.where(self.neg, zero, lb).max(1).values
        upper = 1.0 - torch.where(self.neg, lb, zero).max(1).values
        return lower, upper


# ================================================================ 학습
def _pred(m, idx):
    ps, cs = [], []
    with torch.no_grad():
        for i in range(0, len(idx), 8192):
            j = idx[i:i + 8192]
            lg, c = m(Xt[j].to(DEV), St[j].to(DEV), Zt[j].to(DEV))
            ps.append(torch.sigmoid(lg).cpu()); cs.append(c.cpu())
    if not ps:
        return np.zeros(0), torch.zeros((0, CtC.shape[1]))
    return torch.cat(ps).numpy(), torch.cat(cs)


def run28(name, seed, tr, va, te, cbm=True, w_concept=1.0, axioms=None, w_axiom=0.0,
          w_lnn=0.0, lnn_uta=False, unlab=None, w_assess=1.0, extra=None, epochs=None, bs=2048):
    epochs = epochs or EPOCHS
    torch.manual_seed(seed); np.random.seed(seed)
    m = Net(NCH, len(SFEAT), cbm=cbm, nconcept=CtC.shape[1], backbone="bilstm", nz=Z.shape[1]).to(DEV)
    m.type_bin.copy_(TYPE_C.to(DEV))
    rules = LNNRules(AX_LNN).to(DEV) if w_lnn > 0 else None
    params = list(m.parameters()) + (list(rules.parameters()) if rules is not None else [])
    opt = torch.optim.Adam(params, lr=1e-3)
    bce = nn.BCEWithLogitsLoss(reduction="none")
    tb_ = TYPE_C.to(DEV)
    iA = CI["Assessable"]
    idx_l = np.where(tr & L)[0]
    if QUICK:
        idx_l = np.random.permutation(idx_l)[:30000]
    idx_u = np.where(tr & ~L)[0]
    idx_uta = np.where(tr & ALLUTA)[0]
    if unlab == "naive":                     # 기존 4b: 미관찰을 같은 배치에 섞는다
        idx_l = np.concatenate([idx_l, idx_u])
    idx_va = np.where(va & L)[0]
    vN = v_all[idx_va] == "N"; yv = y_all[idx_va]
    best, best_state, bad = -1.0, None, 0
    for ep in range(epochs):
        m.train()
        perm = np.random.permutation(idx_l)
        for bi in range(0, len(perm), bs):
            j = perm[bi:bi + bs]
            logit, c = m(Xt[j].to(DEV), St[j].to(DEV), Zt[j].to(DEV))
            yb, lb = Yt[j].to(DEV), Lt[j].to(DEV)
            loss = (bce(logit, yb) * lb).sum() / lb.sum().clamp(min=1)
            if w_concept > 0:
                cb, mb_ = CtC[j].to(DEV), MtC[j].to(DEV)
                lc_ = torch.where(tb_.unsqueeze(0), bce(c, cb), (c - cb) ** 2)
                loss = loss + w_concept * (lc_ * mb_).sum() / mb_.sum().clamp(min=1)
            p = torch.sigmoid(logit)
            if w_axiom > 0:
                sat = axiom_sat(c, p) if axioms == "orig" else sat_rev(c, p)
                loss = loss + w_axiom * (1.0 - sat)
            if unlab == "balanced" and len(idx_u):
                ju = np.random.choice(idx_u, min(bs // 4, len(idx_u)), replace=False)
                _, cu = m(Xt[ju].to(DEV), St[ju].to(DEV), Zt[ju].to(DEV))
                loss = loss + w_assess * bce(cu[:, iA], torch.zeros(len(ju), device=DEV)).mean()
            if rules is not None:
                lo_, up_ = rules.bounds(c.detach())
                k_ = lb > 0
                l_rule = (torch.relu(lo_[k_] - yb[k_]) + torch.relu(yb[k_] - up_[k_])).mean() if k_.any() \
                    else torch.zeros((), device=DEV)
                l_model = (torch.relu(lo_.detach() - p) + torch.relu(p - up_.detach())).mean()
                if lnn_uta and len(idx_uta):
                    jt = np.random.choice(idx_uta, min(bs // 4, len(idx_uta)), replace=False)
                    lgt, ct = m(Xt[jt].to(DEV), St[jt].to(DEV), Zt[jt].to(DEV))
                    lo_t, up_t = rules.bounds(ct.detach())
                    pt_ = torch.sigmoid(lgt)
                    l_model = l_model + (torch.relu(lo_t.detach() - pt_) + torch.relu(pt_ - up_t.detach())).mean()
                loss = loss + w_lnn * l_model + l_rule
            opt.zero_grad(); loss.backward(); opt.step()
            if rules is not None:
                rules.project()
        m.eval()
        pv, _ = _pred(m, idx_va)
        ap = average_precision_score(yv[vN], pv[vN])
        print(f"    {name} s{seed} ep{ep+1} valN_AUPRC={100*ap:.1f}", flush=True)
        if ap > best:
            best, bad = ap, 0
            best_state = {k: t_.detach().clone() for k, t_ in m.state_dict().items()}
            rule_state = {k: t_.detach().clone() for k, t_ in rules.state_dict().items()} if rules is not None else None
        else:
            bad += 1
            if bad >= 2:
                break
    m.load_state_dict(best_state); m.eval()
    if rules is not None:
        rules.load_state_dict(rule_state)
    idx_te = np.where(te & L)[0]
    pt, ct = _pred(m, idx_te)
    out = {"idx": idx_te, "p": pt}
    with torch.no_grad():
        out["sat_rev"] = sat_rev(ct, torch.from_numpy(pt), per_axiom=True).numpy()
        out["sat_orig"] = axiom_sat(ct, torch.from_numpy(pt), per_axiom=True).numpy()
    for k, msk in (extra or {}).items():
        ie = np.where(msk)[0]
        out[k] = (ie, _pred(m, ie)[0])
    if rules is not None:
        wa, wb = rules.weights()
        lo_, up_ = rules.bounds(ct.to(DEV))
        out["lnn"] = {"w_a": wa.detach().cpu().numpy(), "w_b": wb.detach().cpu().numpy(),
                      "lower_mean": float(lo_.mean()), "upper_mean": float(up_.mean()),
                      "p_below_lower%": float(100 * (torch.from_numpy(pt).to(DEV) < lo_ - 1e-6).float().mean()),
                      "p_above_upper%": float(100 * (torch.from_numpy(pt).to(DEV) > up_ + 1e-6).float().mean())}
    return out


def run_xgb(tr, te):
    from xgboost import XGBClassifier
    i_tr, i_te = np.where(tr & L)[0], np.where(te & L)[0]
    x = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.05, subsample=0.8,
                      colsample_bytree=0.8, eval_metric="aucpr", random_state=SEED, n_jobs=-1, tree_method="hist")
    x.fit(Z[i_tr], y_all[i_tr])
    return {"idx": i_te, "p": x.predict_proba(Z[i_te])[:, 1]}


# ================================================================ 지표
def strat_metrics(idx, p):
    r = {}
    for st_ in ["N", "P", "U", "전체"]:
        sel = np.ones(len(idx), bool) if st_ == "전체" else (v_all[idx] == st_)
        yy, pp = y_all[idx][sel], p[sel]
        if len(np.unique(yy)) < 2:
            continue
        base = yy.mean()
        ap = average_precision_score(yy, pp)
        r[f"{st_}_AUPRC"] = 100 * ap
        r[f"{st_}_AUROC"] = 100 * roc_auc_score(yy, pp)
        r[f"{st_}_normAUPRC"] = 100 * (ap - base) / (1 - base)
    selN = v_all[idx] == "N"
    s_ = stay_all[idx][selN]
    w_ = 1.0 / pd.Series(s_).map(pd.Series(s_).value_counts()).to_numpy()
    r["N_AUPRC_stayweighted"] = 100 * average_precision_score(y_all[idx][selN], p[selN], sample_weight=w_)
    return r


def calib(yy, pp):
    pc = np.clip(pp, 1e-6, 1 - 1e-6)
    lg = np.log(pc / (1 - pc))
    lr = LogisticRegression(C=1e6).fit(lg[:, None], yy)
    bins = np.minimum((pc * 10).astype(int), 9)
    ece = sum(abs(pc[bins == k].mean() - yy[bins == k].mean()) * (bins == k).mean() for k in range(10) if (bins == k).any())
    return {"Brier": brier_score_loss(yy, pc), "ECE10": 100 * ece, "slope": float(lr.coef_[0, 0]),
            "intercept": float(lr.intercept_[0]), "mean_p%": 100 * pc.mean(), "base%": 100 * yy.mean()}


def summarize(rows, key_cols):
    df = pd.DataFrame(rows)
    num = [c for c in df.columns if c not in key_cols + ["seed"]]
    g = df.groupby(key_cols, sort=False)[num]
    return g.mean().round(2).join(g.std(ddof=0).round(2), rsuffix="_sd").join(g.size().rename("n_seed"))


# ================================================================ 실행 — 주 분할 (23_ 와 같은 test)
head("[A·B·C] 주 분할 — 23_ 와 동일한 test · 시드 " + str(SEEDS))
EXTRA_MAIN = {"uta_te": in_te & ALLUTA}
VARIANTS = [
    ("3 BiLSTM", dict(cbm=False, w_concept=0.0)),
    ("4c CBM 연속", dict()),
    ("5 LTN 원본12 w.2", dict(axioms="orig", w_axiom=0.2)),
    ("5r LTN 검수본 w.2", dict(axioms="rev", w_axiom=0.2)),
    ("5r LTN 검수본 w.5", dict(axioms="rev", w_axiom=0.5)),
    ("6 LNN 검수본 라벨만 w.5", dict(w_lnn=0.5, lnn_uta=False)),
    ("6 LNN 검수본 +전부UTA w.5", dict(w_lnn=0.5, lnn_uta=True)),
    ("4b 미관찰 섞기(기존)", dict(unlab="naive")),
    ("4b' 균형배치 Assessable w1", dict(unlab="balanced", w_assess=1.0)),
    ("4b' 균형배치 Assessable w.3", dict(unlab="balanced", w_assess=0.3)),
]
rows, sat_rows, lnn_rows, uta_rows = [], [], [], []
keep = {}
xg = run_xgb(in_tr, in_te)
keep["2z XGB(같은 Z)"] = xg
rows.append({"모델": "2z XGB(같은 Z)", "seed": SEED, **strat_metrics(xg["idx"], xg["p"])})
for nm, kw in VARIANTS:
    for sd_ in SEEDS:
        o = run28(nm, sd_, in_tr, in_val, in_te, extra=EXTRA_MAIN, **kw)
        rows.append({"모델": nm, "seed": sd_, **strat_metrics(o["idx"], o["p"])})
        sat_rows.append({"모델": nm, "seed": sd_, **dict(zip(REV_NAMES, o["sat_rev"]))})
        ie, pe = o["uta_te"]
        dl = _dconf[ie] > 0
        if dl.sum() and len(np.unique(_dpos[ie][dl] > 0)) > 1:
            uta_rows.append({"모델": nm, "seed": sd_, "n(72h 확정)": int(dl.sum()),
                             "지연양성%": 100 * (_dpos[ie][dl] > 0).mean(),
                             "AUROC(지연라벨)": 100 * roc_auc_score(_dpos[ie][dl] > 0, pe[dl]),
                             "AUPRC(지연라벨)": 100 * average_precision_score(_dpos[ie][dl] > 0, pe[dl]),
                             "평균예측%": 100 * pe.mean()})
        if "lnn" in o:
            ln = o["lnn"]
            lnn_rows.append({"모델": nm, "seed": sd_, "하한 평균": ln["lower_mean"], "상한 평균": ln["upper_mean"],
                             "하한 아래%": ln["p_below_lower%"], "상한 위%": ln["p_above_upper%"],
                             **{f"w_a {r[0]}": ln["w_a"][i] for i, r in enumerate(AX_LNN)},
                             **{f"w_b {r[0]}": ln["w_b"][i] for i, r in enumerate(AX_LNN)}})
        if sd_ == SEEDS[0]:
            keep[nm] = o
    print(f"  [{time.time()-T28:.0f}s] {nm} 끝", flush=True)

main = summarize(rows, ["모델"])
main.to_csv(os.path.join(OUT28, "main_metrics.csv"), encoding="utf-8-sig")
print(main[[c for c in main.columns if c in ("N_AUPRC", "N_AUPRC_sd", "N_AUROC", "N_normAUPRC",
                                              "N_AUPRC_stayweighted", "P_AUROC", "전체_AUROC", "n_seed")]].to_string())
summarize(sat_rows, ["모델"]).to_csv(os.path.join(OUT28, "axiom_sat_rev.csv"), encoding="utf-8-sig")
if uta_rows:
    ut = summarize(uta_rows, ["모델"]); ut.to_csv(os.path.join(OUT28, "alluta_delayed_label.csv"), encoding="utf-8-sig")
    print("\n[전부 UTA test 앵커 — 72h 지연 라벨 대리 점검]"); print(ut.to_string())
if lnn_rows:
    lt_ = summarize(lnn_rows, ["모델"]).T; lt_.to_csv(os.path.join(OUT28, "lnn_weights_bounds.csv"), encoding="utf-8-sig")
    print("\n[LNN 규칙 가중치·경계]"); print(lt_.to_string())

# 검수본 비교형 제약의 데이터 일치도 (모델 무관)
_teL = np.where(in_te & L)[0]
_dex = CARR_C[_teL, CI["DexmedFrac"]] > 0; _bz = CARR_C[_teL, CI["BenzoFrac"]] > 0
_pd = pd.DataFrame([{"비교": "덱스만 vs 벤조만", "n 덱스만": int((_dex & ~_bz).sum()), "n 벤조만": int((_bz & ~_dex).sum()),
                     "섬망% 덱스만": 100 * y_all[_teL][_dex & ~_bz].mean(), "섬망% 벤조만": 100 * y_all[_teL][_bz & ~_dex].mean()}])
_pd.to_csv(os.path.join(OUT28, "pair_constraint_data.csv"), encoding="utf-8-sig", index=False)
print("\n[검수본 비교형 제약 — 실제 라벨]"); print(_pd.round(1).to_string(index=False))

# ================================================================ D-1 calibration · D-2 하위군 (시드 42 예측)
head("[D] calibration · ICU 유형 · era 하위군 (주 분할, 첫 시드)")
_cu_raw = cam.stay_id.map(st["first_careunit"]).to_numpy()
_cu = np.array([("Neuro" if isinstance(x, str) and "Neuro" in x else
                 {"Medical Intensive Care Unit (MICU)": "MICU", "Medical/Surgical Intensive Care Unit (MICU/SICU)": "MICU/SICU",
                  "Cardiac Vascular Intensive Care Unit (CVICU)": "CVICU", "Surgical Intensive Care Unit (SICU)": "SICU",
                  "Coronary Care Unit (CCU)": "CCU", "Trauma SICU (TSICU)": "TSICU"}.get(x, "기타")) for x in _cu_raw])
_era = cam.stay_id.map(st["anchor_year_group"]).astype(str).to_numpy()
cal_rows, sub_rows, rel_rows = [], [], []
for nm, o in keep.items():
    idx, p = o["idx"], o["p"]
    for st_ in ["N", "전체"]:
        sel = np.ones(len(idx), bool) if st_ == "전체" else (v_all[idx] == st_)
        cal_rows.append({"모델": nm, "계층": st_, **calib(y_all[idx][sel], p[sel])})
        if st_ == "N":
            b_ = np.minimum((np.clip(p[sel], 0, 1 - 1e-9) * 10).astype(int), 9)
            for k in range(10):
                if (b_ == k).any():
                    rel_rows.append({"모델": nm, "bin": f"{k/10:.1f}-{(k+1)/10:.1f}", "n": int((b_ == k).sum()),
                                     "예측%": 100 * p[sel][b_ == k].mean(), "관측%": 100 * y_all[idx][sel][b_ == k].mean()})
    selN = v_all[idx] == "N"
    for gname, garr in [("ICU", _cu), ("era", _era)]:
        for gv in sorted(np.unique(garr[idx])):
            s_ = selN & (garr[idx] == gv)
            yy = y_all[idx][s_]
            if s_.sum() < 200 or len(np.unique(yy)) < 2:
                continue
            sub_rows.append({"모델": nm, "구분": gname, "값": gv, "n(N앵커)": int(s_.sum()), "기저%": 100 * yy.mean(),
                             "N_AUPRC": 100 * average_precision_score(yy, p[s_]),
                             "N_AUROC": 100 * roc_auc_score(yy, p[s_])})
cal = pd.DataFrame(cal_rows).round(3); cal.to_csv(os.path.join(OUT28, "calibration.csv"), encoding="utf-8-sig", index=False)
pd.DataFrame(rel_rows).round(2).to_csv(os.path.join(OUT28, "reliability_N.csv"), encoding="utf-8-sig", index=False)
sub = pd.DataFrame(sub_rows).round(2); sub.to_csv(os.path.join(OUT28, "subgroups.csv"), encoding="utf-8-sig", index=False)
print(cal[cal["계층"] == "N"].to_string(index=False))

# ================================================================ D-3 연도 외부검증
head("[D] 연도 외부검증 — 2011-2016 학습 · 2017-2019 / 2020-2022 평가 (환자 단위, era 는 환자별 고정)")
_subj = cam.subject_id.to_numpy()
_trainera = np.isin(_era, ["2011 - 2013", "2014 - 2016"])
_pats = np.array(sorted(np.unique(_subj[_trainera & L])))
_rng = np.random.default_rng(SEED); _rng.shuffle(_pats)
_vp = set(_pats[:int(0.15 * len(_pats))])
e_va = _trainera & np.isin(_subj, list(_vp))
e_tr = _trainera & ~e_va
e_te = _era == "2017 - 2019"
e_te2 = _era == "2020 - 2022"
print(f"학습 {int((e_tr&L).sum()):,} · val {int((e_va&L).sum()):,} · 평가 2017-19 {int((e_te&L).sum()):,} · "
      f"2020-22 {int((e_te2&L).sum()):,} (라벨 기준)", flush=True)
ext_rows = []
xg = run_xgb(e_tr, e_te); ext_rows.append({"모델": "2z XGB(같은 Z)", "평가": "2017-19", "seed": SEED, **strat_metrics(xg["idx"], xg["p"])})
xg2 = run_xgb(e_tr, e_te2); ext_rows.append({"모델": "2z XGB(같은 Z)", "평가": "2020-22", "seed": SEED, **strat_metrics(xg2["idx"], xg2["p"])})
EXT_VARIANTS = [v for v in VARIANTS if v[0] in ("3 BiLSTM", "4c CBM 연속", "5 LTN 원본12 w.2", "5r LTN 검수본 w.2",
                                                  "6 LNN 검수본 +전부UTA w.5")]
for nm, kw in EXT_VARIANTS:
    for sd_ in SEEDS:
        o = run28(nm, sd_, e_tr, e_va, e_te, extra={"te2": e_te2 & L}, **kw)
        ext_rows.append({"모델": nm, "평가": "2017-19", "seed": sd_, **strat_metrics(o["idx"], o["p"])})
        i2, p2 = o["te2"]
        ext_rows.append({"모델": nm, "평가": "2020-22", "seed": sd_, **strat_metrics(i2, p2)})
    print(f"  [{time.time()-T28:.0f}s] 외부검증 {nm} 끝", flush=True)
ext = summarize(ext_rows, ["모델", "평가"])
ext.to_csv(os.path.join(OUT28, "external_era.csv"), encoding="utf-8-sig")
print(ext[[c for c in ext.columns if c in ("N_AUPRC", "N_AUPRC_sd", "N_AUROC", "N_normAUPRC", "전체_AUROC", "n_seed")]].to_string())

print(f"\n총 {time.time()-T28:.0f}s (데이터 준비 제외) -> {OUT28}")
print("주의: 표준화 통계는 23_ 의 주 분할 train 에서 낸 것을 외부검증에도 그대로 쓴다(평균·표준편차만 공유).")
