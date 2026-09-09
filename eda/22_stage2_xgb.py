# -*- coding: utf-8 -*-
# ============================================================================
# 2단계 — XGBoost (요약 피처만). 1단계 lookup baseline 을 넘는지 본다.
#
# ⚠️ mobility / pain / GCS 는 아직 값이 없다 (00_extract.py VALUE_IDS).
#    따라서 이 결과는 "가능한 피처의 부분집합"이고, 재추출 후 다시 돌려야 한다.
#
# 분할·seed 는 20_baseline_carryforward.py 와 동일 (환자 단위 70/30, seed 42)
# 사용: EDA_DATA=<notes/eda> python eda/22_stage2_xgb.py
# ============================================================================
import os, sys, time
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score
from xgboost import XGBClassifier

sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ.get("EDA_DATA", "/content/drive/MyDrive/mimic_eda")
OUT = os.environ.get("EDA_OUT", os.path.join(DATA, "out_split"))
os.makedirs(OUT, exist_ok=True)
SEED, CAM_ITEM, RASS_ITEM = 42, 228332, 228096
W_AHEAD, HR_CAP = 24.0, 240.0
pd.set_option("display.width", 220)


def head(t):
    print("\n" + "=" * 78); print(t); print("=" * 78)


t0 = time.time()
# ---------------------------------------------------------------- 앵커 + 라벨
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
_, first, cnt = np.unique(cam["stay_id"].to_numpy(), return_index=True, return_counts=True)
labeled = np.zeros(len(cam), bool); y = np.zeros(len(cam), bool)
for a, n in zip(first, cnt):
    hh = h[a:a + n]; idx = np.arange(n)
    j = np.searchsorted(hh, hh + W_AHEAD, side="right")
    labeled[a:a + n] = (cumC[a + j] - cumC[a + idx + 1]) > 0
    y[a:a + n] = (cumP[a + j] - cumP[a + idx + 1]) > 0
cam["labeled"], cam["y"] = labeled, y

# ---------------------------------------------------------------- 누적 피처
cam["n_prev"] = cam.groupby("stay_id").cumcount()
pos_in_stay = np.zeros(len(cam), int)   # 앵커 이전 P 횟수
uta_in_stay = np.zeros(len(cam), int)
for a, n in zip(first, cnt):
    idx = np.arange(n)
    pos_in_stay[a:a + n] = cumP[a + idx] - cumP[a]
    uta_in_stay[a:a + n] = cumU[a + idx] - cumU[a]
cam["n_prev_pos"], cam["n_prev_uta"] = pos_in_stay, uta_in_stay
cam["uta_frac"] = np.where(cam.n_prev > 0, cam.n_prev_uta / cam.n_prev.clip(lower=1), np.nan)
cam["prev_conf"] = cam["v"].where(cam.v != "U").groupby(cam.stay_id).ffill().shift()
cam.loc[cam.groupby("stay_id").head(1).index, "prev_conf"] = np.nan
cam["prev_conf"] = cam["prev_conf"].fillna("없음")
# 직전 확정 평가로부터 경과시간
last_conf_hr = cam["hr"].where(cam.v != "U").groupby(cam.stay_id).ffill().shift()
cam["since_conf"] = cam["hr"] - last_conf_hr
cam["since_prev"] = cam.groupby("stay_id")["hr"].diff()

# ---------------------------------------------------------------- RASS
r = v[v.itemid == RASS_ITEM][["stay_id", "charttime", "valuenum"]].copy()
r["charttime"] = pd.to_datetime(r["charttime"])
r = r[r.stay_id.isin(DEN.stay_id)].copy()
r["hr"] = (r["charttime"] - r["stay_id"].map(intime)).dt.total_seconds() / 3600
r = r[r.hr >= 0].sort_values(["stay_id", "hr"])
rh = {k: g["hr"].to_numpy(float) for k, g in r.groupby("stay_id", sort=False)}
rv = {k: g["valuenum"].to_numpy(float) for k, g in r.groupby("stay_id", sort=False)}

cols = ["rass_last", "rass_min24", "rass_mean24", "rass_max24", "rass_n24", "rass_negmean24"]
F = {c: np.full(len(cam), np.nan) for c in cols}
for a, n in zip(first, cnt):
    sid = cam["stay_id"].iloc[a]
    arr = rh.get(sid)
    if arr is None:
        continue
    vals = rv[sid]; hh = h[a:a + n]
    hi = np.searchsorted(arr, hh, side="right")
    lo = np.searchsorted(arr, hh - 24.0, side="left")
    for k in range(n):
        seg = vals[lo[k]:hi[k]]
        seg = seg[~np.isnan(seg)]
        if seg.size:
            F["rass_last"][a + k] = seg[-1]
            F["rass_min24"][a + k] = seg.min()
            F["rass_max24"][a + k] = seg.max()
            F["rass_mean24"][a + k] = seg.mean()
            F["rass_negmean24"][a + k] = np.minimum(seg, 0).mean()
        F["rass_n24"][a + k] = hi[k] - lo[k]
for c in cols:
    cam[c] = F[c]
cam["deep_sed24"] = (cam.rass_min24 <= -4).astype(float)

# ---------------------------------------------------------------- 진정제
sed = pd.read_parquet(f"{DATA}/_step1_sed.parquet")
sed = sed[sed.stay_id.isin(DEN.stay_id)].copy()
for c in ["starttime", "endtime"]:
    sed[c] = pd.to_datetime(sed[c])
sed["s"] = (sed["starttime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
sed["e"] = (sed["endtime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
BENZO = {"lorazepam", "midazolam", "diazepam"}
sed["cls"] = np.where(sed.drug.isin(BENZO), "benzo", sed.drug)
sed_by = {k: (g["s"].to_numpy(float), g["e"].to_numpy(float), g["cls"].to_numpy())
          for k, g in sed.groupby("stay_id", sort=False)}
CLS = ["benzo", "propofol", "dexmedetomidine"]
S = {f"sed_{c}": np.zeros(len(cam)) for c in CLS}
S["sed_benzo_cum"] = np.zeros(len(cam))
for a, n in zip(first, cnt):
    g = sed_by.get(cam["stay_id"].iloc[a])
    if g is None:
        continue
    s_, e_, cl = g; hh = h[a:a + n]
    ov = (s_[None, :] < hh[:, None]) & (e_[None, :] > hh[:, None] - 24.0)
    before = s_[None, :] < hh[:, None]
    for c in CLS:
        S[f"sed_{c}"][a:a + n] = (ov & (cl == c)[None, :]).any(1)
    S["sed_benzo_cum"][a:a + n] = (before & (cl == "benzo")[None, :]).sum(1)
for k, arr in S.items():
    cam[k] = arr

# ---------------------------------------------------------------- 정적
st = DEN.set_index("stay_id")
cam["subject_id"] = cam["stay_id"].map(st["subject_id"])
cam["age"] = cam["stay_id"].map(st["age"])
cam["los"] = cam["stay_id"].map(st["los"])
cam["is_male"] = (cam["stay_id"].map(st["gender"]) == "M").astype(float)
cam["cu"] = cam["stay_id"].map(st["first_careunit"]).astype("category").cat.codes
cam["era"] = cam["stay_id"].map(st["anchor_year_group"]).astype("category").cat.codes

d = cam[cam.labeled].copy()
print(f"instance {len(d):,} · 환자 {d.subject_id.nunique():,} · Positive {100*d.y.mean():.1f}% "
      f"· 피처 준비 {time.time()-t0:.0f}s")

# ---------------------------------------------------------------- 분할 (20_ 과 동일)
rng = np.random.default_rng(SEED)
pats = d.subject_id.unique(); rng.shuffle(pats)
tr_pat = set(pats[:int(len(pats) * 0.70)])
d["split"] = np.where(d.subject_id.isin(tr_pat), "train", "test")

FEATS = (["hr", "n_prev", "n_prev_pos", "n_prev_uta", "uta_frac", "since_conf", "since_prev"]
         + cols + ["deep_sed24"] + [f"sed_{c}" for c in CLS] + ["sed_benzo_cum"]
         + ["age", "los", "is_male", "cu", "era"]
         + ["anchor_N", "anchor_P", "anchor_U", "prev_N", "prev_P", "prev_none"])
for a in ["N", "P", "U"]:
    d[f"anchor_{a}"] = (d.v == a).astype(float)
for a, nm in [("N", "prev_N"), ("P", "prev_P"), ("없음", "prev_none")]:
    d[nm] = (d.prev_conf == a).astype(float)

tr, te = d[d.split == "train"], d[d.split == "test"]
print(f"train {len(tr):,} / {tr.subject_id.nunique():,}명 · test {len(te):,} / {te.subject_id.nunique():,}명")
assert not (set(tr.subject_id) & set(te.subject_id))

head("[1] 2단계 XGBoost 학습")
clf = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8, eval_metric="aucpr",
                    random_state=SEED, n_jobs=-1, tree_method="hist")
clf.fit(tr[FEATS], tr.y.astype(int))
te = te.copy()
te["p"] = clf.predict_proba(te[FEATS])[:, 1]
# 1단계 B2 룩업 (동일 분할에서 재계산)
lut = tr.groupby(["prev_conf", "v"])["y"].mean()
te["b2"] = [lut.get((p_, a_), tr.y.mean()) for p_, a_ in zip(te.prev_conf, te.v)]
print(f"학습 완료 {time.time()-t0:.0f}s")

head("[2] 계층별 — 1단계(B2 lookup) vs 2단계(XGB)")
rows = []
for nm, sub in [("전체", te)] + [(f"앵커={a}", te[te.v == a]) for a in ["N", "P", "U"]]:
    yt = sub.y.astype(int).to_numpy()
    if yt.min() == yt.max():
        continue
    r_ = {"계층": nm, "n": len(sub), "기저%": round(100 * yt.mean(), 1),
          "B2 AUROC": round(100 * roc_auc_score(yt, sub.b2), 1),
          "XGB AUROC": round(100 * roc_auc_score(yt, sub.p), 1),
          "B2 AUPRC": round(100 * average_precision_score(yt, sub.b2), 1),
          "XGB AUPRC": round(100 * average_precision_score(yt, sub.p), 1)}
    r_["ΔAUROC"] = round(r_["XGB AUROC"] - r_["B2 AUROC"], 1)
    r_["ΔAUPRC"] = round(r_["XGB AUPRC"] - r_["B2 AUPRC"], 1)
    rows.append(r_)
t = pd.DataFrame(rows).set_index("계층")
print(t.to_string())
t.to_csv(os.path.join(OUT, "stage2_xgb.csv"), encoding="utf-8-sig")
print("  -> stage2_xgb.csv")

head("[3] 피처 중요도 상위 15")
imp = (pd.Series(clf.feature_importances_, index=FEATS)
       .sort_values(ascending=False).head(15) * 100).round(1)
print(imp.to_string())

head("[4] 피처군 ablation — 이득이 어디서 오나 (주 지표 = 앵커=N)")
G_STATE = ["anchor_N", "anchor_P", "anchor_U", "prev_N", "prev_P", "prev_none"]
G_HIST = ["hr", "n_prev", "n_prev_pos", "n_prev_uta", "uta_frac", "since_conf", "since_prev"]
G_RASS = cols + ["deep_sed24"]
G_MED = [f"sed_{c}" for c in CLS] + ["sed_benzo_cum"]
G_STATIC = ["age", "los", "is_male", "cu", "era"]
steps = [("A 상태만", G_STATE),
         ("B +이력", G_STATE + G_HIST),
         ("C +RASS", G_STATE + G_HIST + G_RASS),
         ("D +진정제", G_STATE + G_HIST + G_RASS + G_MED),
         ("E +정적 (full)", FEATS)]
teN = te[te.v == "N"]; ytN = teN.y.astype(int).to_numpy()
yt_all = te.y.astype(int).to_numpy()
rows = []
for nm, fs in steps:
    m = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.05,
                      subsample=0.8, colsample_bytree=0.8, eval_metric="aucpr",
                      random_state=SEED, n_jobs=-1, tree_method="hist")
    m.fit(tr[fs], tr.y.astype(int))
    pN = m.predict_proba(teN[fs])[:, 1]
    pA = m.predict_proba(te[fs])[:, 1]
    rows.append({"피처군": nm, "n_feat": len(fs),
                 "N AUPRC": round(100 * average_precision_score(ytN, pN), 1),
                 "N AUROC": round(100 * roc_auc_score(ytN, pN), 1),
                 "전체 AUPRC": round(100 * average_precision_score(yt_all, pA), 1)})
ab = pd.DataFrame(rows).set_index("피처군")
ab["N AUPRC 증분"] = ab["N AUPRC"].diff().round(1)
print(ab.to_string())
ab.to_csv(os.path.join(OUT, "stage2_ablation.csv"), encoding="utf-8-sig")
print("  -> stage2_ablation.csv")

head("[5] 판정")
n = t.loc["앵커=N"]
print(f"주 지표 (앵커=N AUPRC): {n['B2 AUPRC']} -> {n['XGB AUPRC']}  (Δ{n['ΔAUPRC']:+})")
print(f"        (앵커=N AUROC): {n['B2 AUROC']} -> {n['XGB AUROC']}  (Δ{n['ΔAUROC']:+})")
gain_hist = ab.loc["B +이력", "N AUPRC"] - ab.loc["A 상태만", "N AUPRC"]
gain_rass = ab.loc["C +RASS", "N AUPRC"] - ab.loc["B +이력", "N AUPRC"]
print(f"\n이득 분해 — 이력 +{gain_hist:.1f} · RASS +{gain_rass:.1f} "
      f"· 진정제 {ab.loc['D +진정제','N AUPRC']-ab.loc['C +RASS','N AUPRC']:+.1f} "
      f"· 정적 {ab.loc['E +정적 (full)','N AUPRC']-ab.loc['D +진정제','N AUPRC']:+.1f}")
print("→ RASS 증분이 작으면 3단계(BiLSTM)로 원시 시계열을 넣을 근거가 약하다.")
print("\n⚠️ mobility / pain / GCS 미포함 상태의 수치다. 재추출 후 다시 돌려야 한다.")
