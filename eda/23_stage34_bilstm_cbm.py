# -*- coding: utf-8 -*-
# ============================================================================
# 3단계 BiLSTM · 4단계 CBM — 1·2단계와 동일한 test set 에서 비교
#
#   3    BiLSTM          원시 24h 시계열이 2단계의 요약 피처를 넘나
#   4    CBM             개념 병목(개념 5종)을 거치는 비용
#   4b   CBM + Assessable  라벨 미관찰 앵커(29.0%)를 Assessable 보조라벨로 재활용
#
# 시계열 채널: RASS + 진정제 + (24_ 추출분) GCS 3성분 · mobility 2종 · pain NRS.
#
# 분할: test 는 20_/22_ 와 완전히 동일(환자 단위 30%, seed 42).
#       val 은 train 환자 중 15%p 를 다시 뗀다.
# 사용: EDA_DATA=<notes/eda> python eda/23_stage34_bilstm_cbm.py
# ============================================================================
import os, sys, time
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score, average_precision_score

sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ.get("EDA_DATA", "/content/drive/MyDrive/mimic_eda")
OUT = os.environ.get("EDA_OUT", os.path.join(DATA, "out_split"))
os.makedirs(OUT, exist_ok=True)
SEED, CAM_ITEM, RASS_ITEM = 42, 228332, 228096
W_AHEAD, HR_CAP, NBIN = 24.0, 240.0, 24
DEV = "cuda" if torch.cuda.is_available() else "cpu"
torch.manual_seed(SEED); np.random.seed(SEED)
pd.set_option("display.width", 220)


def head(t):
    print("\n" + "=" * 78); print(t); print("=" * 78, flush=True)


t0 = time.time()
# ================================================================ 앵커·라벨
b = pd.read_pickle(f"{DATA}/_icu_base.pkl")
v = pd.read_parquet(f"{DATA}/_label_values.parquet")
b["intime"] = pd.to_datetime(b["intime"])
if "age" not in b.columns:
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
DEN = b[(b.age >= 18) & (b.los >= 1.0)].copy()
intime = b.set_index("stay_id")["intime"]

MAP = {"Positive": "P", "Negative": "N", "UTA": "U",
       "Unable to Assess": "U", "Unable to assess": "U"}
cam = v[v.itemid == CAM_ITEM][["stay_id", "charttime", "value"]].copy()
cam["charttime"] = pd.to_datetime(cam["charttime"])
cam["v"] = cam["value"].astype(str).str.strip().map(MAP)
cam = cam[cam.v.notna() & cam.stay_id.isin(DEN.stay_id)].copy()
cam["hr"] = (cam["charttime"] - cam["stay_id"].map(intime)).dt.total_seconds() / 3600
cam = cam[(cam.hr >= 0) & (cam.hr <= HR_CAP)].sort_values(["stay_id", "hr"]).reset_index(drop=True)

h = cam["hr"].to_numpy(float)
isC = (cam["v"] != "U").to_numpy(); isP = (cam["v"] == "P").to_numpy()
cumC = np.concatenate([[0], isC.cumsum()]); cumP = np.concatenate([[0], (isC & isP).cumsum()])
cumU = np.concatenate([[0], (~isC).cumsum()])
sids, first, cnt = np.unique(cam["stay_id"].to_numpy(), return_index=True, return_counts=True)
labeled = np.zeros(len(cam), bool); y = np.zeros(len(cam), bool)
for a, n in zip(first, cnt):
    hh = h[a:a + n]; idx = np.arange(n)
    j = np.searchsorted(hh, hh + W_AHEAD, side="right")
    labeled[a:a + n] = (cumC[a + j] - cumC[a + idx + 1]) > 0
    y[a:a + n] = (cumP[a + j] - cumP[a + idx + 1]) > 0
cam["labeled"], cam["y"] = labeled, y

cam["n_prev"] = cam.groupby("stay_id").cumcount()
pp = np.zeros(len(cam), int); pu = np.zeros(len(cam), int)
for a, n in zip(first, cnt):
    idx = np.arange(n)
    pp[a:a + n] = cumP[a + idx] - cumP[a]
    pu[a:a + n] = cumU[a + idx] - cumU[a]
cam["n_prev_pos"], cam["n_prev_uta"] = pp, pu
cam["uta_frac"] = np.where(cam.n_prev > 0, cam.n_prev_uta / cam.n_prev.clip(lower=1), 0.0)
cam["prev_conf"] = cam["v"].where(cam.v != "U").groupby(cam.stay_id).ffill().shift()
cam.loc[cam.groupby("stay_id").head(1).index, "prev_conf"] = np.nan
cam["prev_conf"] = cam["prev_conf"].fillna("없음")
lc = cam["hr"].where(cam.v != "U").groupby(cam.stay_id).ffill().shift()
cam["since_conf"] = (cam["hr"] - lc).fillna(-1)
cam["since_prev"] = cam.groupby("stay_id")["hr"].diff().fillna(-1)

# ================================================================ 시계열 (24 x C)
r = v[v.itemid == RASS_ITEM][["stay_id", "charttime", "valuenum"]].copy()
r["charttime"] = pd.to_datetime(r["charttime"])
r = r[r.stay_id.isin(DEN.stay_id)].copy()
r["hr"] = (r["charttime"] - r["stay_id"].map(intime)).dt.total_seconds() / 3600
r = r[r.hr >= 0].sort_values(["stay_id", "hr"])
RH, RV = {}, {}
for k, g in r.groupby("stay_id", sort=False):
    RH[k] = g["hr"].to_numpy(float)
    RV[k] = np.nan_to_num(g["valuenum"].to_numpy(float), nan=0.0)

sed = pd.read_parquet(f"{DATA}/_step1_sed.parquet")
sed = sed[sed.stay_id.isin(DEN.stay_id)].copy()
for c in ["starttime", "endtime"]:
    sed[c] = pd.to_datetime(sed[c])
sed["s"] = (sed["starttime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
sed["e"] = (sed["endtime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
BENZO = {"lorazepam", "midazolam", "diazepam"}
sed["cls"] = np.where(sed.drug.isin(BENZO), "benzo", sed.drug)
CLS = ["benzo", "propofol", "dexmedetomidine"]
SED = {k: (g["s"].to_numpy(float), g["e"].to_numpy(float), g["cls"].to_numpy())
       for k, g in sed.groupby("stay_id", sort=False)}

# 채널: RASS mean · RASS min · 관측있음 · benzo · propofol · dexmed
NCH = 6
X = np.zeros((len(cam), NBIN, NCH), dtype=np.float32)
edges = np.linspace(-24.0, 0.0, NBIN + 1)          # 앵커 기준 상대시간
centers = (edges[:-1] + edges[1:]) / 2
for a, n in zip(first, cnt):
    sid = cam["stay_id"].iloc[a]
    hh = h[a:a + n]
    arr = RH.get(sid)
    if arr is not None:
        vals = RV[sid]
        csum = np.concatenate([[0.0], np.cumsum(vals)])
        cmin = vals  # min 은 구간별로 직접
        bnd = np.searchsorted(arr, hh[:, None] + edges[None, :], side="left")  # (n, NBIN+1)
        lo, hi = bnd[:, :-1], bnd[:, 1:]
        k_ = hi - lo
        sm = csum[hi] - csum[lo]
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(k_ > 0, sm / np.maximum(k_, 1), 0.0)
        X[a:a + n, :, 0] = mean
        X[a:a + n, :, 2] = (k_ > 0)
        # min: 구간이 있는 칸만 루프 (대부분 0~2개)
        for i in range(n):
            for jb in range(NBIN):
                if k_[i, jb] > 0:
                    X[a + i, jb, 1] = cmin[lo[i, jb]:hi[i, jb]].min()
    g = SED.get(sid)
    if g is not None:
        s_, e_, cl = g
        ct = hh[:, None, None] + centers[None, :, None]        # (n, NBIN, 1)
        cov = (s_[None, None, :] <= ct) & (e_[None, None, :] > ct)
        for ci, c in enumerate(CLS):
            X[a:a + n, :, 3 + ci] = (cov & (cl == c)[None, None, :]).any(2)
# ---- mobility / pain / GCS 채널 붙이기 ----
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _extra_features import build_extra_channels

EX, EXNAMES = build_extra_channels(DATA, cam["stay_id"].to_numpy(), h, first, cnt, nbin=NBIN)
EX_START = X.shape[2]
if EX is None:
    print("[!] _extra_values.parquet 없음 — RASS+진정제 채널만 쓴다")
else:
    EX_START = X.shape[2]
    X = np.concatenate([X, EX], axis=2)
    NCH = X.shape[2]
    del EX
    print(f"채널 확장 -> {NCH} ({', '.join(EXNAMES)})")

print(f"시계열 텐서 {X.shape} · {X.nbytes/1e6:.0f}MB · {time.time()-t0:.0f}s", flush=True)

# ================================================================ 정적/이력 벡터
st = DEN.set_index("stay_id")
cam["subject_id"] = cam["stay_id"].map(st["subject_id"])
cam["age"] = cam["stay_id"].map(st["age"])
cam["los"] = cam["stay_id"].map(st["los"])
cam["is_male"] = (cam["stay_id"].map(st["gender"]) == "M").astype(float)
cam["cu"] = cam["stay_id"].map(st["first_careunit"]).astype("category").cat.codes
cam["era"] = cam["stay_id"].map(st["anchor_year_group"]).astype("category").cat.codes
for a_ in ["N", "P", "U"]:
    cam[f"anchor_{a_}"] = (cam.v == a_).astype(float)
for a_, nm in [("N", "prev_N"), ("P", "prev_P"), ("없음", "prev_none")]:
    cam[nm] = (cam.prev_conf == a_).astype(float)
SFEAT = ["hr", "n_prev", "n_prev_pos", "n_prev_uta", "uta_frac", "since_conf", "since_prev",
         "age", "los", "is_male", "cu", "era",
         "anchor_N", "anchor_P", "anchor_U", "prev_N", "prev_P", "prev_none"]
S = cam[SFEAT].to_numpy(np.float32)

# ---------------- 개념 라벨 (SPLIT_SPEC §16 의 predicate 중 지금 만들 수 있는 것) ----------------
# ⚠️ 처음엔 DeepSedation + Assessable 둘만 뒀는데, 그러면 예측을 지배하는 CAM 상태가
#    병목 어디에도 실리지 않아 CBM 이 baseline 밑으로 떨어진다. 그건 CBM 의 성질이 아니라
#    개념 집합을 잘못 고른 것이다. 관측 가능한 상태 개념을 넣어 다시 잡는다.
#    Mobility / Pain 은 값이 없어 아직 못 넣는다 (6개 중 4개 + 파생 1개).
rmin24 = X[:, :, 1].copy()
rmin24[X[:, :, 2] == 0] = 0.0
c_deep = (rmin24.min(1) <= -4).astype(np.float32)                 # DeepSedation
c_benzo = (X[:, :, 3].max(1) > 0).astype(np.float32)              # BenzodiazepineExposure
c_assess = cam["labeled"].to_numpy().astype(np.float32)           # Assessable (미래 — 보조)
c_cur = (cam.v.to_numpy() == "P").astype(np.float32)              # CurrentDelirium (앵커 시점)
c_prior = (cam.n_prev_pos.to_numpy() > 0).astype(np.float32)      # PriorDelirium (이력)
CONCEPTS = ["DeepSedation", "BenzoExposure", "Assessable", "CurrentDelirium", "PriorDelirium"]
CARR = np.stack([c_deep, c_benzo, c_assess, c_cur, c_prior], 1).astype(np.float32)
print("개념 기저 — " + " · ".join(
    f"{n} {100*CARR[:, i].mean():.1f}%" for i, n in enumerate(CONCEPTS)))

# ================================================================ 분할 (test 는 20_/22_ 와 동일)
lab_idx = np.where(cam.labeled.to_numpy())[0]
d_lab = cam.iloc[lab_idx]
rng = np.random.default_rng(SEED)
pats = d_lab.subject_id.unique(); rng.shuffle(pats)
tr_pat_all = set(pats[:int(len(pats) * 0.70)])
rng2 = np.random.default_rng(SEED + 1)
tr_list = np.array(sorted(tr_pat_all)); rng2.shuffle(tr_list)
val_pat = set(tr_list[:int(len(tr_list) * 0.20)])
tr_pat = tr_pat_all - val_pat

subj = cam["subject_id"].to_numpy()
in_tr = np.isin(subj, list(tr_pat)); in_val = np.isin(subj, list(val_pat))
in_te = ~np.isin(subj, list(tr_pat_all))
L = cam.labeled.to_numpy()
print(f"train {int((in_tr&L).sum()):,} · val {int((in_val&L).sum()):,} · test {int((in_te&L).sum()):,} (라벨 기준)")

# ---------------- 요약 벡터 Z — MLP/CBM/XGB 가 공유하는 입력 ----------------
# X(시계열)에서 그대로 파생한다. BiLSTM 과 입력 정보량이 같아야 backbone 비교가 성립한다.
def _summ(v, m):
    cnt = m.sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(cnt > 0, (v * m).sum(1) / np.maximum(cnt, 1), np.nan)
    vmin = np.where(m, v, np.inf).min(1); vmin[~np.isfinite(vmin)] = np.nan
    vmax = np.where(m, v, -np.inf).max(1); vmax[~np.isfinite(vmax)] = np.nan
    nb = m.shape[1]
    li = nb - 1 - np.argmax(m[:, ::-1], axis=1)
    last = np.where(cnt > 0, v[np.arange(len(v)), np.maximum(li, 0)], np.nan)
    return [mean, vmin, vmax, last, cnt.astype(np.float32)]


zc, zn = [], []
_m = X[:, :, 2] > 0
zc += _summ(X[:, :, 0], _m); zn += [f"rass_{k}" for k in ["mean", "min", "max", "last", "n"]]
_bmin = np.where(_m, X[:, :, 1], np.inf).min(1); _bmin[~np.isfinite(_bmin)] = np.nan
zc.append(_bmin); zn.append("rass_binmin")
zc.append((_bmin <= -4).astype(np.float32)); zn.append("deep_sed24")
for ci, c in enumerate(CLS):
    zc.append(X[:, :, 3 + ci].max(1)); zn.append(f"sed_{c}")
if EX_START < X.shape[2]:
    from _extra_features import summarize as _sm
    _z, _n = _sm(X[:, :, EX_START:], EXNAMES)
    zc += [_z[:, i] for i in range(_z.shape[1])]; zn += _n
Z = np.concatenate([S, np.stack(zc, 1).astype(np.float32)], 1)
ZCOLS = SFEAT + zn
# 결측은 train 중앙값으로 채운다 (관측 수 _n 피처가 결측 여부를 이미 담고 있다)
_med = np.nanmedian(Z[in_tr & L], axis=0)
_med = np.where(np.isfinite(_med), _med, 0.0)
Z = np.where(np.isfinite(Z), Z, _med[None, :]).astype(np.float32)
zmu, zsd = Z[in_tr & L].mean(0), Z[in_tr & L].std(0) + 1e-6
Z = (Z - zmu) / zsd
Zt = torch.from_numpy(Z)
print(f"요약 벡터 Z {Z.shape} ({len(ZCOLS)} 피처)")

mu, sd = S[in_tr & L].mean(0), S[in_tr & L].std(0) + 1e-6
S = (S - mu) / sd
xm = X[in_tr & L].reshape(-1, NCH).mean(0)
xs = X[in_tr & L].reshape(-1, NCH).std(0) + 1e-6
X = (X - xm) / xs

Xt = torch.from_numpy(X); St = torch.from_numpy(S)
Yt = torch.from_numpy(cam.y.to_numpy().astype(np.float32))
Ct = torch.from_numpy(CARR)
Lt = torch.from_numpy(L.astype(np.float32))


# ================================================================ 모델
class Net(nn.Module):
    """backbone='bilstm' 은 시계열 텐서를, 'mlp' 는 요약 벡터 Z 를 받는다."""

    def __init__(self, nch, nstat, hid=64, cbm=False, nconcept=len(CONCEPTS),
                 backbone="bilstm", nz=0):
        super().__init__()
        self.cbm, self.backbone = cbm, backbone
        if backbone == "bilstm":
            self.lstm = nn.LSTM(nch, hid, batch_first=True, bidirectional=True)
            self.att = nn.Linear(hid * 2, 1)
            self.stat = nn.Sequential(nn.Linear(nstat, hid), nn.ReLU())
            enc_in = hid * 3
        else:
            self.mlp = nn.Sequential(
                nn.Linear(nz, hid * 4), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(hid * 4, hid * 2), nn.ReLU(), nn.Dropout(0.1))
            enc_in = hid * 2
        self.enc = nn.Sequential(nn.Linear(enc_in, hid), nn.ReLU(), nn.Dropout(0.1))
        self.concept = nn.Linear(hid, nconcept)
        # CBM: 개념값만 통과시킨다 (병목). 비CBM: 표현 전체를 쓴다.
        self.out = nn.Linear(nconcept if cbm else hid, 1)

    def forward(self, x, s, z=None):
        if self.backbone == "bilstm":
            o, _ = self.lstm(x)
            w = torch.softmax(self.att(o), 1)
            h_ = torch.cat([(o * w).sum(1), self.stat(s)], 1)
        else:
            h_ = self.mlp(z)
        h_ = self.enc(h_)
        c = self.concept(h_)
        return self.out(torch.sigmoid(c) if self.cbm else h_).squeeze(1), c


def run(name, cbm, use_unlabeled, w_concept, epochs=10, bs=2048, backbone="bilstm",
        seed=SEED, quiet=False):
    torch.manual_seed(seed)
    np.random.seed(seed)
    m = Net(NCH, len(SFEAT), cbm=cbm, backbone=backbone, nz=Z.shape[1]).to(DEV)
    opt = torch.optim.Adam(m.parameters(), lr=1e-3)
    bce = nn.BCEWithLogitsLoss(reduction="none")
    tr_mask = in_tr if use_unlabeled else (in_tr & L)
    idx_tr = np.where(tr_mask)[0]
    idx_va = np.where(in_val & L)[0]
    idx_te = np.where(in_te & L)[0]
    best, best_state, bad = -1, None, 0
    for ep in range(epochs):
        m.train()
        perm = np.random.permutation(idx_tr)
        tot = 0.0
        for i in range(0, len(perm), bs):
            j = perm[i:i + bs]
            xb, sb = Xt[j].to(DEV), St[j].to(DEV)
            yb, cb, lb = Yt[j].to(DEV), Ct[j].to(DEV), Lt[j].to(DEV)
            zb = Zt[j].to(DEV)
            logit, c = m(xb, sb, zb)
            ltask = (bce(logit, yb) * lb).sum() / lb.sum().clamp(min=1)
            lcon = bce(c, cb).mean()
            loss = ltask + w_concept * lcon
            opt.zero_grad(); loss.backward(); opt.step()
            tot += float(loss.detach()) * len(j)
        m.eval()
        with torch.no_grad():
            pv = []
            for i in range(0, len(idx_va), 8192):
                j = idx_va[i:i + 8192]
                pv.append(torch.sigmoid(
                    m(Xt[j].to(DEV), St[j].to(DEV), Zt[j].to(DEV))[0]).cpu().numpy())
            pv = np.concatenate(pv)
        yv = cam.y.to_numpy()[idx_va].astype(int)
        vN = cam.v.to_numpy()[idx_va] == "N"
        ap = average_precision_score(yv[vN], pv[vN])       # 주 지표로 조기종료
        if not quiet:
            print(f"  {name} ep{ep+1} loss={tot/len(perm):.4f} valN_AUPRC={100*ap:.1f}", flush=True)
        if ap > best:
            best, best_state, bad = ap, {k: t.detach().clone() for k, t in m.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 2:
                if not quiet:
                    print("  early stop")
                break
    m.load_state_dict(best_state); m.eval()
    with torch.no_grad():
        pt = []
        for i in range(0, len(idx_te), 8192):
            j = idx_te[i:i + 8192]
            pt.append(torch.sigmoid(
                m(Xt[j].to(DEV), St[j].to(DEV), Zt[j].to(DEV))[0]).cpu().numpy())
        pt = np.concatenate(pt)
    return idx_te, pt


head(f"[학습] device={DEV}")
res = {}
res["3 BiLSTM"] = run("3 BiLSTM", cbm=False, use_unlabeled=False, w_concept=0.0)
res["3m MLP"] = run("3m MLP", cbm=False, use_unlabeled=False, w_concept=0.0, backbone="mlp")
res["4 CBM(LSTM)"] = run("4 CBM(LSTM)", cbm=True, use_unlabeled=False, w_concept=1.0)
res["4m CBM(MLP)"] = run("4m CBM(MLP)", cbm=True, use_unlabeled=False, w_concept=1.0, backbone="mlp")
res["4bm CBM(MLP)+Assess"] = run("4bm CBM(MLP)+Assess", cbm=True, use_unlabeled=True,
                                 w_concept=1.0, backbone="mlp")

# 같은 Z 위의 XGBoost — backbone 비교의 상한 기준
from xgboost import XGBClassifier
_xi_tr, _xi_te = np.where(in_tr & L)[0], np.where(in_te & L)[0]
_x = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.05, subsample=0.8,
                   colsample_bytree=0.8, eval_metric="aucpr", random_state=SEED,
                   n_jobs=-1, tree_method="hist")
_x.fit(Z[_xi_tr], cam.y.to_numpy()[_xi_tr].astype(int))
res["2z XGB(같은 Z)"] = (_xi_te, _x.predict_proba(Z[_xi_te])[:, 1])

head("[결과] 1~4단계 — 동일 test set")
prev = pd.read_csv(os.path.join(OUT, "stage2_xgb.csv"))
prev = prev.set_index(prev.columns[0])
idx_te = res["3 BiLSTM"][0]
vte = cam.v.to_numpy()[idx_te]; yte = cam.y.to_numpy()[idx_te].astype(int)
rows = []
for strat in ["전체", "앵커=N", "앵커=P", "앵커=U"]:
    sel = np.ones(len(idx_te), bool) if strat == "전체" else (vte == strat[-1])
    r_ = {"계층": strat, "n": int(sel.sum()),
          "1 lookup": prev.loc[strat, "B2 AUPRC"], "2 XGB": prev.loc[strat, "XGB AUPRC"]}
    for nm, (_, p) in res.items():
        r_[nm] = round(100 * average_precision_score(yte[sel], p[sel]), 1)
    rows.append(r_)
t = pd.DataFrame(rows).set_index("계층")
print("AUPRC")
print(t.to_string())
t.to_csv(os.path.join(OUT, "stage34.csv"), encoding="utf-8-sig")

rows = []
for strat in ["전체", "앵커=N", "앵커=P", "앵커=U"]:
    sel = np.ones(len(idx_te), bool) if strat == "전체" else (vte == strat[-1])
    r_ = {"계층": strat, "1 lookup": prev.loc[strat, "B2 AUROC"], "2 XGB": prev.loc[strat, "XGB AUROC"]}
    for nm, (_, p) in res.items():
        r_[nm] = round(100 * roc_auc_score(yte[sel], p[sel]), 1)
    rows.append(r_)
print("\nAUROC")
print(pd.DataFrame(rows).set_index("계층").to_string())

head("[시드 3개] 앵커=N AUPRC — backbone 결론을 단일 시드로 내리지 않는다")
SEEDS = [42, 7, 2024]
VARIANTS = [
    ("3  BiLSTM", dict(cbm=False, use_unlabeled=False, w_concept=0.0, backbone="bilstm")),
    ("3m MLP", dict(cbm=False, use_unlabeled=False, w_concept=0.0, backbone="mlp")),
    ("4  CBM(LSTM)", dict(cbm=True, use_unlabeled=False, w_concept=1.0, backbone="bilstm")),
    ("4m CBM(MLP)", dict(cbm=True, use_unlabeled=False, w_concept=1.0, backbone="mlp")),
]
_teN = cam.v.to_numpy()[res["3 BiLSTM"][0]] == "N"
_ytN = cam.y.to_numpy()[res["3 BiLSTM"][0]].astype(int)[_teN]
rows = []
for nm, kw in VARIANTS:
    vals = []
    for sd_ in SEEDS:
        _, pp = run(nm, seed=sd_, quiet=True, **kw)
        vals.append(100 * average_precision_score(_ytN, pp[_teN]))
    rows.append({"모델": nm, "평균": round(float(np.mean(vals)), 1),
                 "표준편차": round(float(np.std(vals)), 1),
                 "최소": round(min(vals), 1), "최대": round(max(vals), 1),
                 "시드별": " / ".join(f"{v:.1f}" for v in vals)})
    print(f"  {nm:14s} {rows[-1]['평균']:5.1f} ± {rows[-1]['표준편차']:.1f}   ({rows[-1]['시드별']})",
          flush=True)
sv = pd.DataFrame(rows).set_index("모델")
sv.to_csv(os.path.join(OUT, "stage34_seeds.csv"), encoding="utf-8-sig")
print("  -> stage34_seeds.csv")
d_bb = sv.loc["3m MLP", "평균"] - sv.loc["3  BiLSTM", "평균"]
d_cbm = sv.loc["4m CBM(MLP)", "평균"] - sv.loc["4  CBM(LSTM)", "평균"]
print(f"\nbackbone 교체 (개념층 없이) {d_bb:+.1f}  ·  (CBM) {d_cbm:+.1f}")
print("표준편차보다 작으면 차이라고 말할 수 없다.")

head("[판정] 앵커=N AUPRC")
n = t.loc["앵커=N"]
print(f"  1 lookup        {n['1 lookup']}")
print(f"  2 XGB(원 피처)   {n['2 XGB']}")
print(f"  2z XGB(같은 Z)   {n['2z XGB(같은 Z)']}   ← backbone 비교의 상한")
print(f"  3  BiLSTM        {n['3 BiLSTM']}")
print(f"  3m MLP           {n['3m MLP']}")
print(f"  4  CBM(LSTM)     {n['4 CBM(LSTM)']}")
print(f"  4m CBM(MLP)      {n['4m CBM(MLP)']}")
print(f"  4bm +Assessable  {n['4bm CBM(MLP)+Assess']}")
print(f"\nbackbone 교체 효과 (개념층 없이) : MLP - BiLSTM = {n['3m MLP']-n['3 BiLSTM']:+.1f}")
print(f"backbone 교체 효과 (CBM)         : {n['4m CBM(MLP)']-n['4 CBM(LSTM)']:+.1f}")
print(f"MLP 가 같은 입력의 XGB 에 못 미치는 폭 : {n['3m MLP']-n['2z XGB(같은 Z)']:+.1f}")
print(f"개념 병목 비용 (MLP backbone)     : {n['4m CBM(MLP)']-n['3m MLP']:+.1f}")
print(f"Assessable 재활용                : {n['4bm CBM(MLP)+Assess']-n['4m CBM(MLP)']:+.1f}")
print(f"\n총 {time.time()-t0:.0f}s")
print("\n" + ("mobility/pain/GCS 포함본이다 — 3단계 판정은 확정이다."
                if NCH > 6 else "[!] mobility/pain/GCS 미포함 — 하한이다."))
