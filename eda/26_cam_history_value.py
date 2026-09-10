# -*- coding: utf-8 -*-
# ============================================================================
# 누적 CAM 이력이 무슨 정보를 주는가
#
# 2단계 ablation 에서 '이력' 블록이 단일 최대 기여(+11.4 AUPRC)였는데
# 그 안을 쪼갠 적이 없다. 두 가지로 본다.
#   (가) 예측 기여  — 상태만(직전확정×현재앵커) 위에 변수를 하나씩 더해 본다
#   (나) 무슨 정보  — 앵커=N 계층에서 변수값별 실제 Positive 율
#
# 주 지표는 앵커=N 계층 AUPRC (기저 12.0%). 분할·seed 는 22_ 와 동일.
# 사용: EDA_DATA=<notes/eda> python eda/26_cam_history_value.py
# ============================================================================
import os, sys, time
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score
from xgboost import XGBClassifier

sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ.get("EDA_DATA", "notes/eda")
OUT = os.environ.get("EDA_OUT", os.path.join(DATA, "out_split"))
os.makedirs(OUT, exist_ok=True)
SEED, CAM_ITEM = 42, 228332
W_AHEAD, HR_CAP = 24.0, 240.0
pd.set_option("display.width", 220)


def head(t):
    print("\n" + "=" * 78); print(t); print("=" * 78, flush=True)


t0 = time.time()
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

cam["n_prev"] = cam.groupby("stay_id").cumcount()
pp = np.zeros(len(cam), int); pu = np.zeros(len(cam), int)
for a, n in zip(first, cnt):
    idx = np.arange(n)
    pp[a:a + n] = cumP[a + idx] - cumP[a]
    pu[a:a + n] = cumU[a + idx] - cumU[a]
cam["n_prev_pos"], cam["n_prev_uta"] = pp, pu
cam["uta_frac"] = np.where(cam.n_prev > 0, cam.n_prev_uta / cam.n_prev.clip(lower=1), 0.0)
cam["pos_frac"] = np.where(cam.n_prev > 0, cam.n_prev_pos / cam.n_prev.clip(lower=1), 0.0)
cam["prev_conf"] = cam["v"].where(cam.v != "U").groupby(cam.stay_id).ffill().shift()
cam.loc[cam.groupby("stay_id").head(1).index, "prev_conf"] = np.nan
cam["prev_conf"] = cam["prev_conf"].fillna("없음")
lc = cam["hr"].where(cam.v != "U").groupby(cam.stay_id).ffill().shift()
cam["since_conf"] = (cam["hr"] - lc).fillna(-1)
cam["since_prev"] = cam.groupby("stay_id")["hr"].diff().fillna(-1)
cam["subject_id"] = cam["stay_id"].map(DEN.set_index("stay_id")["subject_id"])
for a_ in ["N", "P", "U"]:
    cam[f"anchor_{a_}"] = (cam.v == a_).astype(float)
for a_, nm in [("N", "prev_N"), ("P", "prev_P"), ("없음", "prev_none")]:
    cam[nm] = (cam.prev_conf == a_).astype(float)

d = cam[cam.labeled].copy()
rng = np.random.default_rng(SEED)
pats = d.subject_id.unique(); rng.shuffle(pats)
tr_pat = set(pats[:int(len(pats) * 0.70)])
d["split"] = np.where(d.subject_id.isin(tr_pat), "train", "test")
tr, te = d[d.split == "train"], d[d.split == "test"]
teN = te[te.v == "N"]
print(f"train {len(tr):,} · test {len(te):,} (앵커=N {len(teN):,}) · {time.time()-t0:.0f}s")

STATE = ["anchor_N", "anchor_P", "anchor_U", "prev_N", "prev_P", "prev_none"]
HIST = {
    "hr (입실 후 경과시간)": ["hr"],
    "n_prev (누적 평가 횟수)": ["n_prev"],
    "n_prev_pos (누적 P 횟수)": ["n_prev_pos"],
    "pos_frac (누적 P 비율)": ["pos_frac"],
    "n_prev_uta (누적 UTA 횟수)": ["n_prev_uta"],
    "uta_frac (누적 UTA 비율)": ["uta_frac"],
    "since_conf (직전 확정평가 경과)": ["since_conf"],
    "since_prev (직전 기록 경과)": ["since_prev"],
}
ALL_H = [c for cs in HIST.values() for c in cs]


def fit(feats):
    m = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.05, subsample=0.8,
                      colsample_bytree=0.8, eval_metric="aucpr", random_state=SEED,
                      n_jobs=-1, tree_method="hist")
    m.fit(tr[feats], tr.y.astype(int))
    p = m.predict_proba(teN[feats])[:, 1]
    yt = teN.y.astype(int).to_numpy()
    return (100 * average_precision_score(yt, p), 100 * roc_auc_score(yt, p))


head("[1] 상태만(직전확정 × 현재앵커) 위에 하나씩 더하면 — 앵커=N")
base_ap, base_auc = fit(STATE)
full_ap, full_auc = fit(STATE + ALL_H)
print(f"  상태만        AUPRC {base_ap:.1f} · AUROC {base_auc:.1f}")
print(f"  +이력 전체    AUPRC {full_ap:.1f} · AUROC {full_auc:.1f}   (Δ{full_ap-base_ap:+.1f})\n")
rows = []
for nm, cs in HIST.items():
    ap, auc = fit(STATE + cs)
    rows.append({"추가 변수": nm, "AUPRC": round(ap, 1), "단독 Δ": round(ap - base_ap, 1),
                 "AUROC": round(auc, 1)})
t1 = pd.DataFrame(rows).set_index("추가 변수").sort_values("단독 Δ", ascending=False)
print(t1.to_string())

head("[2] 이력 전체에서 하나씩 빼면 (고유 기여) — 앵커=N")
rows = []
for nm, cs in HIST.items():
    rest = [c for c in ALL_H if c not in cs]
    ap, _ = fit(STATE + rest)
    rows.append({"뺀 변수": nm, "AUPRC": round(ap, 1), "빠진 만큼": round(full_ap - ap, 1)})
t2 = pd.DataFrame(rows).set_index("뺀 변수").sort_values("빠진 만큼", ascending=False)
print(t2.to_string())
print("\n'단독 Δ'는 크고 '빠진 만큼'은 작으면 → 다른 변수와 정보가 겹친다는 뜻이다.")
t1.join(t2["빠진 만큼"]).to_csv(os.path.join(OUT, "hist_ablation.csv"), encoding="utf-8-sig")

head("[3] 무슨 정보인가 — 앵커=N 계층에서 변수값별 실제 Positive 율 (기저 12.0%)")


def show(col, bins, labels, title):
    s = teN.copy()
    s["bin"] = pd.cut(s[col], bins, labels=labels)
    t = s.groupby("bin", observed=True).agg(n=("y", "size"), Positive=("y", "mean"))
    t["Positive%"] = (100 * t.Positive).round(1)
    t["비중%"] = (100 * t.n / len(s)).round(1)
    print(f"\n{title}")
    print(t[["n", "비중%", "Positive%"]].to_string())
    return t


show("n_prev_pos", [-1, 0, 1, 2, 4, 1e9], ["0회", "1회", "2회", "3-4회", "5회+"],
     "누적 P 횟수 — '지금 N 이지만 전에 P 였던 적이 몇 번인가'")
show("pos_frac", [-0.01, 0.0, 0.2, 0.5, 1.01], ["0%", "~20%", "20-50%", "50%+"],
     "누적 P 비율")
show("uta_frac", [-0.01, 0.0, 0.2, 0.5, 1.01], ["0%", "~20%", "20-50%", "50%+"],
     "누적 UTA 비율 — 평가 불가 이력")
show("n_prev", [-1, 1, 3, 7, 15, 1e9], ["0-1회", "2-3회", "4-7회", "8-15회", "16회+"],
     "누적 평가 횟수 — 관찰 강도")
show("since_conf", [-2, 0, 6, 12, 24, 1e9], ["없음", "~6h", "6-12h", "12-24h", "24h+"],
     "직전 확정평가로부터 경과")
show("hr", [-1, 24, 48, 72, 120, 240], ["0-24h", "24-48h", "48-72h", "72-120h", "120-240h"],
     "입실 후 경과시간")

head("[4] 직전 상태만으로는 못 보는 것 — 직전=N 인 앵커=N 만 (기저 8.9%)")
s = teN[teN.prev_conf == "N"].copy()
s["bin"] = pd.cut(s.n_prev_pos, [-1, 0, 1, 2, 1e9], labels=["0회", "1회", "2회", "3회+"])
t = s.groupby("bin", observed=True).agg(n=("y", "size"), Positive=("y", "mean"))
t["Positive%"] = (100 * t.Positive).round(1)
print("직전도 N, 지금도 N — 그런데 과거 P 이력이 있으면?")
print(t[["n", "Positive%"]].to_string())
print(f"\n총 {time.time()-t0:.0f}s")
