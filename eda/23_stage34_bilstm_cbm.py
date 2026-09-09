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

# ---------------- 25_ 산출물: 동반질환 3종 + 수혈 ----------------
# 공리를 강제하려면 개념이 필요하고, 개념을 예측하려면 입력에도 있어야 한다. 셋 다 붙인다.
_cmb_p = f"{DATA}/_axiom_comorb.parquet"
_trf_p = f"{DATA}/_axiom_transfusion.parquet"
HAS_GAP = os.path.exists(_cmb_p) and os.path.exists(_trf_p)
if HAS_GAP:
    _hadm = DEN.set_index("stay_id")["hadm_id"].astype("int64")
    cam["hadm_id"] = cam["stay_id"].map(_hadm)
    _cmb = pd.read_parquet(_cmb_p).set_index("hadm_id")
    for _w in ["dementia", "trauma", "hypertension"]:
        cam[_w] = cam["hadm_id"].map(_cmb[_w]).fillna(0).astype(np.float32)
    _trf = pd.read_parquet(_trf_p)
    _tb = {k: (np.sort(g["hr"].to_numpy(np.float64)),
               g.sort_values("hr")["is_rbc"].to_numpy(np.float64))
           for k, g in _trf.groupby("stay_id", sort=False)}
    _tr24 = np.zeros(len(cam), np.float32)      # 이전 24h 안 수혈(적혈구)
    _trcum = np.zeros(len(cam), np.float32)     # 앵커까지 누적 수혈 건수
    for a_, n_ in zip(first, cnt):
        g_ = _tb.get(cam["stay_id"].iloc[a_])
        if g_ is None:
            continue
        hs_, rb_ = g_
        hh_ = h[a_:a_ + n_]
        hi_ = np.searchsorted(hs_, hh_, side="right")
        lo_ = np.searchsorted(hs_, hh_ - 24.0, side="left")
        crb = np.concatenate([[0.0], np.cumsum(rb_)])
        _tr24[a_:a_ + n_] = (crb[hi_] - crb[lo_]) > 0
        _trcum[a_:a_ + n_] = hi_
    cam["transfusion24"] = _tr24
    cam["transfusion_cum"] = _trcum
    print(f"공백 공리 입력 — dementia {100*cam.dementia.mean():.1f}% · "
          f"trauma {100*cam.trauma.mean():.1f}% · hypertension {100*cam.hypertension.mean():.1f}% · "
          f"수혈(24h) {100*(_tr24>0).mean():.1f}%")
else:
    print("[!] _axiom_comorb/_axiom_transfusion 없음 — 공리 8개로 진행 (eda/25_ 를 먼저 돌릴 것)")

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
if HAS_GAP:
    SFEAT += ["dementia", "trauma", "hypertension", "transfusion24", "transfusion_cum"]
S = cam[SFEAT].to_numpy(np.float32)

# ---------------- 개념 라벨 ----------------
# 두 벌을 만든다.
#   BIN  : 이진 임계 (v2). 지금까지 쓰던 것.
#   CONT : 연속값 (v3). 같은 임상량을 임계 없이 그대로 개념으로 둔다.
# -10.1 의 병목 비용이 정의의 거칠기 탓인지 가리려면 둘을 같은 폭에서 비교해야 한다.
# 미관측(예: mobility 기록 없음)은 개념 손실에서 마스킹한다 — 중앙값으로 채우면 라벨 잡음이 된다.
#
# 채널(정규화 전 raw X): 0 rass_mean · 1 rass_binmin · 2 rass_obs · 3 benzo · 4 propofol
#   · 5 dexmed · 6/7 gcs_eye · 8/9 gcs_verbal · 10/11 gcs_motor · 12/13 mob_braden
#   · 14/15 mob_jhhlm · 16/17 pain_nrs · 18 pain_attempt
def _agg(vi, mi, how):
    v, m = X[:, :, vi], X[:, :, mi] > 0
    if how == "min":
        o = np.where(m, v, np.inf).min(1)
    else:
        o = np.where(m, v, -np.inf).max(1)
    ok = np.isfinite(o)
    return np.where(ok, o, 0.0).astype(np.float32), ok


_rm = X[:, :, 2] > 0
_rass_min = np.where(_rm, X[:, :, 1], np.inf).min(1)
_rass_ok = np.isfinite(_rass_min)
_rass_min = np.where(_rass_ok, _rass_min, 0.0).astype(np.float32)
_rass_negmean = (np.where(_rm, np.minimum(X[:, :, 0], 0), 0.0).sum(1)
                 / np.maximum(_rm.sum(1), 1)).astype(np.float32)
_one = np.ones(len(cam), bool)
_nb = X.shape[1]
_benzo_f = X[:, :, 3].mean(1); _prop_f = X[:, :, 4].mean(1); _dex_f = X[:, :, 5].mean(1)
_age = cam["age"].to_numpy(np.float32)
_male = (cam["is_male"].to_numpy() > 0)
_lab = cam["labeled"].to_numpy()
_curP = (cam.v.to_numpy() == "P")
_curU = (cam.v.to_numpy() == "U")
_npv = cam.n_prev.to_numpy(); _pf = cam.n_prev_pos.to_numpy() / np.maximum(_npv, 1)
_uf = cam.n_prev_uta.to_numpy() / np.maximum(_npv, 1)

if NCH > 6:
    _ge, _geo = _agg(6, 7, "min"); _gv, _gvo = _agg(8, 9, "min"); _gm, _gmo = _agg(10, 11, "min")
    _gcs = (_ge + _gv + _gm).astype(np.float32); _gcso = _geo & _gvo & _gmo
    _mb, _mbo = _agg(12, 13, "min")
    _mj, _mjo = _agg(14, 15, "min")
    _mjx, _mjxo = _agg(14, 15, "max")
    _pn, _pno = _agg(16, 17, "max")
    _pa = (X[:, :, 18].max(1) > 0)
else:
    _gcs = _gcso = _mb = _mbo = _mj = _mjo = _mjx = _mjxo = _pn = _pno = _pa = None

# (이름, 값, 마스크, 종류)
BIN_DEF = [("DeepSedation", (_rass_min <= -4), _one, "bin"),
           ("HighSedationIntensity", (_rass_negmean <= -2), _one, "bin"),
           ("BenzoExposure", (_benzo_f > 0), _one, "bin"),
           ("PropofolExposure", (_prop_f > 0), _one, "bin"),
           ("DexmedExposure", (_dex_f > 0), _one, "bin")]
CONT_DEF = [("RASSmin", _rass_min, _rass_ok, "cont"),
            ("RASSnegmean", _rass_negmean, _one, "cont"),
            ("BenzoFrac", _benzo_f, _one, "cont"),
            ("PropofolFrac", _prop_f, _one, "cont"),
            ("DexmedFrac", _dex_f, _one, "cont")]
if NCH > 6:
    BIN_DEF += [("LowGCS", (_gcs <= 8), _gcso, "bin"),
                ("Immobility", (_mb <= 2) | (_mj <= 2), _mbo | _mjo, "bin"),
                ("EarlyMobility", (_mjx >= 4), _mjxo, "bin"),
                ("SeverePain", (_pn >= 4), _pno, "bin"),
                ("PainUnassessable", _pa & ~_pno, _one, "bin")]
    CONT_DEF += [("GCStotal", _gcs, _gcso, "cont"),
                 ("MobBraden", _mb, _mbo, "cont"),
                 ("MobJHHLM", _mjx, _mjxo, "cont"),
                 ("PainNRSmax", _pn, _pno, "cont"),
                 ("PainUnassessable", _pa & ~_pno, _one, "bin")]
_TAIL = [("OlderAge", (_age >= 65), _one, "bin"), ("MaleSex", _male, _one, "bin"),
         ("Assessable", _lab, _one, "bin"), ("CurrentDelirium", _curP, _one, "bin"),
         ("PriorDelirium", (cam.n_prev_pos.to_numpy() > 0), _one, "bin")]
_TAILC = [("Age", _age, _one, "cont"), ("MaleSex", _male, _one, "bin"),
          ("Assessable", _lab, _one, "bin"), ("CurrentDelirium", _curP, _one, "bin"),
          ("CurrentUTA", _curU, _one, "bin"), ("PriorDeliriumFrac", _pf, _one, "cont"),
          ("PriorUTAFrac", _uf, _one, "cont")]
if HAS_GAP:
    _gap = [("Dementia", cam.dementia.to_numpy() > 0, _one, "bin"),
            ("Trauma", cam.trauma.to_numpy() > 0, _one, "bin"),
            ("Hypertension", cam.hypertension.to_numpy() > 0, _one, "bin"),
            ("BloodTransfusion", cam.transfusion24.to_numpy() > 0, _one, "bin")]
    BIN_DEF += _gap
    CONT_DEF += _gap
BIN_DEF += _TAIL
CONT_DEF += _TAILC


def _pack(defs):
    names = [d[0] for d in defs]
    arr = np.stack([np.asarray(d[1], dtype=np.float32) for d in defs], 1)
    msk = np.stack([np.asarray(d[2], dtype=np.float32) for d in defs], 1)
    typ = [d[3] for d in defs]
    # 연속 개념은 train 통계로 표준화한다 (MSE 스케일 통일)
    return names, arr, msk, typ


CONCEPTS, CARR, CMASK, CTYPE = _pack(BIN_DEF)
CONCEPTS_C, CARR_C, CMASK_C, CTYPE_C = _pack(CONT_DEF)
V1 = ["DeepSedation", "BenzoExposure", "Assessable", "CurrentDelirium", "PriorDelirium"]
CONCEPT_SETS = {"5 (v1)": [CONCEPTS.index(x) for x in V1]}
print(f"개념 세트 — 이진 {len(CONCEPTS)}개 / 연속 {len(CONCEPTS_C)}개"
      f" (연속 중 cont {sum(t=='cont' for t in CTYPE_C)}개)")

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
# 연속 개념은 train 통계로 표준화
_trm = (in_tr & L)
_cs = CARR_C.copy()
_cmu = np.zeros(_cs.shape[1], np.float32); _csd = np.ones(_cs.shape[1], np.float32)
for i, t_ in enumerate(CTYPE_C):
    if t_ == "cont":
        w = _trm & (CMASK_C[:, i] > 0)
        mu_, sd_ = _cs[w, i].mean(), _cs[w, i].std() + 1e-6
        _cmu[i], _csd[i] = mu_, sd_
        _cs[:, i] = (_cs[:, i] - mu_) / sd_
Ct = torch.from_numpy(CARR)
Mt = torch.from_numpy(CMASK)
CtC = torch.from_numpy(_cs)
MtC = torch.from_numpy(CMASK_C)
TYPE_B = torch.tensor([t == "bin" for t in CTYPE])
TYPE_C = torch.tensor([t == "bin" for t in CTYPE_C])
Lt = torch.from_numpy(L.astype(np.float32))


# ================================================================ PADIS 공리 (5단계)
# NeSy-SMP/pipeline/horn_to_ltn.py 가 컴파일한 19개 중 **데이터가 있는 8개**만 강제한다.
# BloodTransfusion · PhysicalRestraint · Dementia · Trauma · Hypertension · Melatonin ·
# OpioidExposure · MechanicalVentilation 은 미매핑이고, HighMortality 는 우리 출력이 아니다.
#
# 연속 개념 위에서 술어의 진리값이 필요하다 — 임계 기반 membership 으로 둔다.
# 이건 원 논문의 weak anchoring(stratified_main.py 519-537)이 있던 자리와 같다.
CI = {n: i for i, n in enumerate(CONCEPTS_C)}
TAU = 0.35          # membership 의 부드러움 (표준화 좌표)


def _zthr(name, raw):
    i = CI[name]
    return float((raw - _cmu[i]) / _csd[i])


# (이름, 개념, 방향(+1: 임계 이상이 참), 임계z, head, head 부정, GRADE)
GRADE_W = {"strong": 1.0, "moderate": 0.6, "low": 0.3, "cohort": 0.3, "derived": 0.5,
           "inconclusive": 0.2}
AXIOMS = [
    ("Benzo→Delirium", "BenzoFrac", +1, _zthr("BenzoFrac", 1e-6), "Delirium", False, "strong"),
    ("DeepSedation→Delirium", "RASSmin", -1, _zthr("RASSmin", -4.0), "Delirium", False, "low"),
    ("SedationIntensity→Delirium", "RASSnegmean", -1, _zthr("RASSnegmean", -2.0),
     "Delirium", False, "cohort"),
    ("SeverePain→Delirium", "PainNRSmax", +1, _zthr("PainNRSmax", 4.0), "Delirium", False,
     "inconclusive"),
    ("OlderAge→Delirium", "Age", +1, _zthr("Age", 65.0), "Delirium", False, "strong"),
    ("Dexmed→¬Delirium", "DexmedFrac", +1, _zthr("DexmedFrac", 1e-6), "Delirium", True, "moderate"),
    ("EarlyMobility→¬Delirium", "MobJHHLM", +1, _zthr("MobJHHLM", 4.0), "Delirium", True, "low"),
    ("DeepSedation→¬Assessable", "RASSmin", -1, _zthr("RASSmin", -4.0), "Assessable", True,
     "derived"),
]
if HAS_GAP:
    # eda/25_ 로 회수한 4개. 전부 양의 방향이라 균형이 5:3 -> 9:3 으로 기운다 (collapse 주의)
    AXIOMS += [
        ("BloodTransfusion→Delirium", "BloodTransfusion", +1, 0.5, "Delirium", False, "strong"),
        ("Dementia→Delirium", "Dementia", +1, 0.5, "Delirium", False, "strong"),
        ("Trauma→Delirium", "Trauma", +1, 0.5, "Delirium", False, "strong"),
        ("Hypertension→Delirium", "Hypertension", +1, 0.5, "Delirium", False, "moderate"),
    ]
AX_W = torch.tensor([GRADE_W[a[6]] for a in AXIOMS], dtype=torch.float32)
AX_W = AX_W / AX_W.sum()
print(f"공리 {len(AXIOMS)}개 강제 (컴파일 19개 중 데이터 있는 것) · "
      f"양의 방향 {sum(1 for a in AXIOMS if not a[5])} · 음의 방향 {sum(1 for a in AXIOMS if a[5])}")


def axiom_sat(c, p_del, per_axiom=False):
    """공리별 만족도. 함축은 Reichenbach(1-a+ab), 전칭은 pMeanError(p=2)."""
    sats = []
    for nm, cn, sgn, thr, head, neg, _g in AXIOMS:
        z = c[:, CI[cn]]
        # 이진 개념은 헤드가 이미 확률을 내므로 sigmoid 만, 연속 개념은 임계 membership
        a = (torch.sigmoid(z) if CTYPE_C[CI[cn]] == "bin"
             else torch.sigmoid(sgn * (z - thr) / TAU))
        b = p_del if head == "Delirium" else torch.sigmoid(c[:, CI["Assessable"]])
        if neg:
            b = 1.0 - b
        sat = 1.0 - a + a * b                      # a -> b
        agg = 1.0 - torch.sqrt(torch.clamp(((1.0 - sat) ** 2).mean(), min=1e-9))
        sats.append(agg)
    st = torch.stack(sats)
    return st if per_axiom else (st * AX_W.to(st.device)).sum()


# ================================================================ 모델
class Net(nn.Module):
    """backbone='bilstm' 은 시계열 텐서를, 'mlp' 는 요약 벡터 Z 를 받는다."""

    def __init__(self, nch, nstat, hid=64, cbm=False, nconcept=15,
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
        self.register_buffer('type_bin', torch.ones(nconcept, dtype=torch.bool))
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
        if not self.cbm:
            return self.out(h_).squeeze(1), c
        # 병목: 이진 개념은 sigmoid, 연속 개념은 예측값 그대로 통과
        tb = self.type_bin.to(c.device)
        z_ = torch.where(tb, torch.sigmoid(c), c)
        return self.out(z_).squeeze(1), c


def run(name, cbm, use_unlabeled, w_concept, epochs=10, bs=2048, backbone="bilstm",
        seed=SEED, quiet=False, cidx=None, cset="bin", w_axiom=0.0):
    torch.manual_seed(seed)
    np.random.seed(seed)
    _C, _M, _T = (Ct, Mt, TYPE_B) if cset == "bin" else (CtC, MtC, TYPE_C)
    cidx = list(range(_C.shape[1])) if cidx is None else cidx
    Csub, Msub, Tsub = _C[:, cidx], _M[:, cidx], _T[cidx]
    m = Net(NCH, len(SFEAT), cbm=cbm, nconcept=len(cidx),
            backbone=backbone, nz=Z.shape[1]).to(DEV)
    m.type_bin.copy_(Tsub.to(DEV))
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
            yb, cb, lb = Yt[j].to(DEV), Csub[j].to(DEV), Lt[j].to(DEV)
            mb_ = Msub[j].to(DEV); tb_ = Tsub.to(DEV)
            zb = Zt[j].to(DEV)
            logit, c = m(xb, sb, zb)
            ltask = (bce(logit, yb) * lb).sum() / lb.sum().clamp(min=1)
            if w_concept > 0:
                lb_ = torch.where(tb_.unsqueeze(0), bce(c, cb), (c - cb) ** 2)
                lcon = (lb_ * mb_).sum() / mb_.sum().clamp(min=1)
            else:
                lcon = torch.zeros((), device=DEV)
            loss = ltask + w_concept * lcon
            if w_axiom > 0:
                loss = loss + w_axiom * (1.0 - axiom_sat(c, torch.sigmoid(logit)))
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
    if cset == "cont" and not quiet and w_concept > 0:
        with torch.no_grad():
            _sat = []
            for i in range(0, len(idx_te), 8192):
                j = idx_te[i:i + 8192]
                _lg, _c = m(Xt[j].to(DEV), St[j].to(DEV), Zt[j].to(DEV))
                _sat.append(axiom_sat(_c, torch.sigmoid(_lg), per_axiom=True).cpu().numpy())
            AX_SAT[name] = np.mean(_sat, 0)
    with torch.no_grad():
        pt = []
        for i in range(0, len(idx_te), 8192):
            j = idx_te[i:i + 8192]
            pt.append(torch.sigmoid(
                m(Xt[j].to(DEV), St[j].to(DEV), Zt[j].to(DEV))[0]).cpu().numpy())
        pt = np.concatenate(pt)
    return idx_te, pt


AX_SAT = {}
head(f"[학습] device={DEV}")
res = {}
_I5 = CONCEPT_SETS["5 (v1)"]
res["3 BiLSTM"] = run("3 BiLSTM", cbm=False, use_unlabeled=False, w_concept=0.0)
res["4 CBM-5"] = run("4 CBM-5", cbm=True, use_unlabeled=False, w_concept=1.0, cidx=_I5)
res[f"4x CBM-{len(CONCEPTS)} 이진"] = run("4x 이진", cbm=True, use_unlabeled=False, w_concept=1.0)
res[f"4c CBM-{len(CONCEPTS_C)} 연속"] = run("4c 연속", cbm=True, use_unlabeled=False,
                                            w_concept=1.0, cset="cont")
res[f"4f free-{len(CONCEPTS_C)}"] = run("4f free", cbm=True, use_unlabeled=False,
                                        w_concept=0.0, cset="cont")
res["5 LTN (w_K=0.2)"] = run("5 LTN", cbm=True, use_unlabeled=False, w_concept=1.0,
                             cset="cont", w_axiom=0.2)
res["5 LTN (w_K=0.5)"] = run("5 LTN .5", cbm=True, use_unlabeled=False, w_concept=1.0,
                             cset="cont", w_axiom=0.5)

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
ta = pd.DataFrame(rows).set_index("계층")
print("\nAUROC")
print(ta.to_string())
ta.to_csv(os.path.join(OUT, "stage34_auroc.csv"), encoding="utf-8-sig")

# AUPRC 의 무작위 예측 값은 곧 그 계층의 기저율이다. 계층끼리 원값으로 비교하면
# 기저 78% 인 앵커=P 가 저절로 높아 보인다. 기저 대비로 정규화해서 같이 본다.
head("[기저 보정] 계층끼리 비교하려면 AUPRC 를 기저 대비로")
_rows = []
for _st in ["전체", "앵커=N", "앵커=P", "앵커=U"]:
    if _st not in t.index:
        continue
    _sel = np.ones(len(idx_te), bool) if _st == "전체" else (vte == _st[-1])
    _b = 100 * yte[_sel].mean()
    _r = {"계층": _st, "기저%": round(_b, 1)}
    for _c in t.columns:
        if _c != "n":
            _r[_c] = round(100 * (t.loc[_st, _c] - _b) / (100 - _b), 1)
    _rows.append(_r)
tn = pd.DataFrame(_rows).set_index("계층")
print("정규화 AUPRC = (AUPRC − 기저) / (100 − 기저) · 0=무작위 · 100=완전")
print(tn.to_string())
tn.to_csv(os.path.join(OUT, "stage34_auprc_norm.csv"), encoding="utf-8-sig")

head("[시드 3개] 앵커=N AUPRC — backbone 결론을 단일 시드로 내리지 않는다")
SEEDS = [42, 7, 2024]
VARIANTS = [
    ("3  BiLSTM", dict(cbm=False, use_unlabeled=False, w_concept=0.0)),
    ("4  CBM-5", dict(cbm=True, use_unlabeled=False, w_concept=1.0, cidx=_I5)),
    (f"4x 이진-{len(CONCEPTS)}", dict(cbm=True, use_unlabeled=False, w_concept=1.0)),
    (f"4c 연속-{len(CONCEPTS_C)}", dict(cbm=True, use_unlabeled=False, w_concept=1.0, cset="cont")),
    (f"4f free-{len(CONCEPTS_C)}", dict(cbm=True, use_unlabeled=False, w_concept=0.0, cset="cont")),
    ("5  LTN w_K=0.2", dict(cbm=True, use_unlabeled=False, w_concept=1.0,
                           cset="cont", w_axiom=0.2)),
    ("5  LTN w_K=0.5", dict(cbm=True, use_unlabeled=False, w_concept=1.0,
                           cset="cont", w_axiom=0.5)),
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
_b = sv.loc[f"4x 이진-{len(CONCEPTS)}", "평균"]
_cc = sv.loc[f"4c 연속-{len(CONCEPTS_C)}", "평균"]
_f = sv.loc[f"4f free-{len(CONCEPTS_C)}", "평균"]
_n = sv.loc["3  BiLSTM", "평균"]
print(f"\n연속 - 이진               {_cc-_b:+.1f}   <- 정의를 다듬어 줄어드나")
print(f"연속 개념의 남은 비용      {_cc-_f:+.1f}   (같은 폭 자유 병목 대비)")
print(f"자유 병목 자체의 비용      {_f-_n:+.1f}")
print("\n연속-이진 차이가 SD 보다 작으면 '정의가 거칠어서'는 기각된다.")
_l2 = sv.loc["5  LTN w_K=0.2", "평균"]; _l5 = sv.loc["5  LTN w_K=0.5", "평균"]
print(f"\n5단계 LTN - 4단계 CBM : w_K=0.2 {_l2-_cc:+.1f} · w_K=0.5 {_l5-_cc:+.1f}")

if AX_SAT:
    head("[공리 만족도] test set · 1.0 = 완전 만족")
    _sat = pd.DataFrame(AX_SAT, index=[a[0] for a in AXIOMS]).round(3)
    # 만족도는 전건 유병률에 좌우된다. A->B 를 Reichenbach 로 재면
    #   독립일 때조차 sat = 1 - P(A)(1-P(B)) 이므로, 유병률이 높으면 기계적으로 낮게 나온다.
    #   보정 기준을 같이 실어야 공리끼리 비교할 수 있다.
    _teL = np.where(in_te & L)[0]
    _pB = float(cam.y.to_numpy()[_teL].mean())
    _pAss = float(cam.labeled.to_numpy()[_teL].mean())
    _prev, _ref = [], []
    for _nm, _cn, _sg, _th, _hd, _ng, _g in AXIOMS:
        _i = CI[_cn]
        if CTYPE_C[_i] == "bin":
            _a = float((CARR_C[_teL, _i] > 0.5).mean())
        else:
            _a = float((np.sign(_sg) * (_cs[_teL, _i] - _th) > 0).mean())
        _b = (_pB if _hd == "Delirium" else _pAss)
        if _ng:
            _b = 1.0 - _b
        _prev.append(_a); _ref.append(1.0 - _a * (1.0 - _b))
    _sat.insert(0, "전건 유병률", np.round(_prev, 3))
    _sat.insert(1, "독립 기준", np.round(_ref, 3))
    _c0 = [c for c in _sat.columns if c.startswith("4c")]
    if _c0:
        _sat["기준 대비"] = (_sat[_c0[0]] - _sat["독립 기준"]).round(3)
    _sat["GRADE"] = [a[6] for a in AXIOMS]
    _sat["가중치"] = AX_W.numpy().round(3)
    _sat = _sat.sort_values("기준 대비") if "기준 대비" in _sat else _sat
    print(_sat.to_string())
    print("\n※ '기준 대비' 가 크게 음수인 것이 데이터가 실제로 저항하는 규칙이다.")
    print("  유병률이 높으면 만족도는 저절로 낮아지므로 원값끼리 비교하면 안 된다.")
    _sat.to_csv(os.path.join(OUT, "stage5_axiom_sat.csv"), encoding="utf-8-sig")
    print("  -> stage5_axiom_sat.csv")

head("[판정] 앵커=N AUPRC (단일 시드)")
n = t.loc["앵커=N"]
for k in t.columns:
    if k != "n":
        print(f"  {k:22s} {n[k]}")

print(f"\n총 {time.time()-t0:.0f}s")
print("\n" + ("mobility/pain/GCS 포함본이다 — 3단계 판정은 확정이다."
                if NCH > 6 else "[!] mobility/pain/GCS 미포함 — 하한이다."))
