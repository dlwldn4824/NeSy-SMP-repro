# -*- coding: utf-8 -*-
# ============================================================================
# 무학습 baseline — 모델이 넘어야 할 바닥
#   B0  직전 확정 상태를 그대로 이월 (prev==P -> 1)
#   B1  직전 확정 상태 3수준을 순위로 (없음 < N < P) -> AUROC/AUPRC
#   B2  B1 + 현재 앵커 상태 (6칸 룩업, 각 칸의 학습셋 Positive 율)
# 전부 앵커=N / P / U 계층별로 따로 낸다.
# 분할은 환자 단위 70/30 (여기서는 baseline 이므로 val 불필요).
# 사용: EDA_DATA=<notes/eda> python eda/20_baseline_carryforward.py
# ============================================================================
import os, sys
import numpy as np
import pandas as pd
from sklearn.metrics import (roc_auc_score, average_precision_score,
                             f1_score, precision_score, recall_score,
                             accuracy_score)

sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ.get("EDA_DATA", "/content/drive/MyDrive/mimic_eda")
OUT = os.environ.get("EDA_OUT", os.path.join(DATA, "out_split"))
os.makedirs(OUT, exist_ok=True)
SEED = 42
CAM_ITEM, W_AHEAD, HR_CAP = 228332, 24.0, 240.0
pd.set_option("display.width", 220)


def head(t):
    print("\n" + "=" * 78); print(t); print("=" * 78)


# ---------------------------------------------------------------- instance 생성
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
cam["subject_id"] = cam["stay_id"].map(DEN.set_index("stay_id")["subject_id"])

h = cam["hr"].to_numpy(float)
isC = (cam["v"] != "U").to_numpy(); isP = (cam["v"] == "P").to_numpy()
cumC = np.concatenate([[0], isC.cumsum()]); cumP = np.concatenate([[0], (isC & isP).cumsum()])
_, first, cnt = np.unique(cam["stay_id"].to_numpy(), return_index=True, return_counts=True)
labeled = np.zeros(len(cam), bool); y = np.zeros(len(cam), bool)
for a, n in zip(first, cnt):
    hh = h[a:a + n]; idx = np.arange(n)
    j = np.searchsorted(hh, hh + W_AHEAD, side="right")
    labeled[a:a + n] = (cumC[a + j] - cumC[a + idx + 1]) > 0
    y[a:a + n] = (cumP[a + j] - cumP[a + idx + 1]) > 0
cam["labeled"], cam["y"] = labeled, y

cam["prev_conf"] = cam["v"].where(cam.v != "U").groupby(cam.stay_id).ffill().shift()
cam.loc[cam.groupby("stay_id").head(1).index, "prev_conf"] = np.nan
d = cam[cam.labeled].copy()
d["prev_conf"] = d["prev_conf"].fillna("없음")
print(f"instance {len(d):,} · 환자 {d.subject_id.nunique():,} · Positive {100*d.y.mean():.1f}%")

# ---------------------------------------------------------------- 환자 단위 분할
rng = np.random.default_rng(SEED)
pats = d.subject_id.unique()
rng.shuffle(pats)
n_tr = int(len(pats) * 0.70)
tr_pat = set(pats[:n_tr])
d["split"] = np.where(d.subject_id.isin(tr_pat), "train", "test")
tr, te = d[d.split == "train"], d[d.split == "test"]
print(f"train {len(tr):,} instance / {tr.subject_id.nunique():,}명 · "
      f"test {len(te):,} / {te.subject_id.nunique():,}명")
assert not (set(tr.subject_id) & set(te.subject_id)), "환자 누수"

# ---------------------------------------------------------------- 점수
RANK = {"없음": 0.5, "N": 0.0, "P": 1.0}          # B1
lut = tr.groupby(["prev_conf", "v"])["y"].mean()   # B2 — train 에서만 추정
te = te.copy()
te["b0"] = (te.prev_conf == "P").astype(int)
te["b1"] = te.prev_conf.map(RANK)
te["b2"] = [lut.get((p, a), tr.y.mean()) for p, a in zip(te.prev_conf, te.v)]


def report(sub, name):
    if len(sub) < 50 or sub.y.nunique() < 2:
        return None
    yt = sub.y.astype(int).to_numpy()
    r = {"계층": name, "n": len(sub), "Positive%": round(100 * yt.mean(), 1)}
    # B0 = 이진 예측
    r["B0 Acc"] = round(100 * accuracy_score(yt, sub.b0), 1)
    r["B0 Prec"] = round(100 * precision_score(yt, sub.b0, zero_division=0), 1)
    r["B0 Rec"] = round(100 * recall_score(yt, sub.b0, zero_division=0), 1)
    r["B0 F1(bin)"] = round(100 * f1_score(yt, sub.b0, zero_division=0), 1)
    r["B0 F1(macro)"] = round(100 * f1_score(yt, sub.b0, average="macro", zero_division=0), 1)
    # B1 / B2 = 점수
    for k in ["b1", "b2"]:
        r[f"{k.upper()} AUROC"] = round(100 * roc_auc_score(yt, sub[k]), 1)
        r[f"{k.upper()} AUPRC"] = round(100 * average_precision_score(yt, sub[k]), 1)
    return r


head("[1] 무학습 baseline — test set (환자 단위 30%)")
rows = [report(te, "전체")]
for a in ["N", "P", "U"]:
    rows.append(report(te[te.v == a], f"앵커={a}"))
t = pd.DataFrame([r for r in rows if r]).set_index("계층")
print(t.to_string())
t.to_csv(os.path.join(OUT, "base_carryforward.csv"), encoding="utf-8-sig")
print("  -> base_carryforward.csv")

head("[2] B2 룩업표 — train 에서 추정한 각 칸의 Positive 율")
print((100 * lut.unstack()).round(1).to_string())

head("[3] 모델이 넘어야 하는 선")
n_row = t.loc["앵커=N"]
print(f"주 지표 계층 (앵커=N, 신규 발생, 기저 {n_row['Positive%']}%)")
print(f"  B1 AUROC {n_row['B1 AUROC']}  ·  B2 AUROC {n_row['B2 AUROC']}  ·  B2 AUPRC {n_row['B2 AUPRC']}")
print(f"전체")
print(f"  B0 F1(binary) {t.loc['전체','B0 F1(bin)']}  ·  B0 F1(macro) {t.loc['전체','B0 F1(macro)']}"
      f"  ·  B2 AUROC {t.loc['전체','B2 AUROC']}")
print("\n※ B2 는 변수 2개(직전 확정상태 × 현재 앵커)짜리 룩업표다. 학습이 없다.")
print("  모델이 이걸 못 넘으면 시계열·논리층이 아무 값도 못 더한 것이다.")
