# -*- coding: utf-8 -*-
# ============================================================================
# 라벨 미관찰(창 안에 확정 CAM 없음) 원인 분리 — SPLIT_SPEC.md §3 의 28.3% 를 쪼갠다
# 원인: 전부 UTA / 사망 / ICU 퇴실 / 240h 캡 / 순수 미평가
# 이게 무작위 탈락이 아니라는 것을 보이는 표이고, LNN 구간 제약의 대상 정의가 된다.
# 사용: EDA_DATA=<notes/eda> python eda/21_censoring_reasons.py
# ============================================================================
import os, sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ.get("EDA_DATA", "/content/drive/MyDrive/mimic_eda")
OUT = os.environ.get("EDA_OUT", os.path.join(DATA, "out_split"))
os.makedirs(OUT, exist_ok=True)
CAM_ITEM, W_AHEAD, HR_CAP = 228332, 24.0, 240.0
pd.set_option("display.width", 220)


def head(t):
    print("\n" + "=" * 78); print(t); print("=" * 78)


b = pd.read_pickle(f"{DATA}/_icu_base.pkl")
v = pd.read_parquet(f"{DATA}/_label_values.parquet")
for c in ["intime", "outtime", "deathtime"]:
    if c in b.columns:
        b[c] = pd.to_datetime(b[c], errors="coerce")
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
isC = (cam["v"] != "U").to_numpy()
cumC = np.concatenate([[0], isC.cumsum()])
cumALL = np.arange(len(cam) + 1)
_, first, cnt = np.unique(cam["stay_id"].to_numpy(), return_index=True, return_counts=True)
n_conf_win = np.zeros(len(cam), int)     # 창 안 확정 CAM 수
n_any_win = np.zeros(len(cam), int)      # 창 안 CAM 기록 수 (UTA 포함)
for a, n in zip(first, cnt):
    hh = h[a:a + n]; idx = np.arange(n)
    j = np.searchsorted(hh, hh + W_AHEAD, side="right")
    n_conf_win[a:a + n] = cumC[a + j] - cumC[a + idx + 1]
    n_any_win[a:a + n] = cumALL[a + j] - cumALL[a + idx + 1]
cam["n_conf_win"], cam["n_any_win"] = n_conf_win, n_any_win
cam["labeled"] = cam.n_conf_win > 0

# 창 끝 시각 대비 퇴실/사망
out_hr = ((DEN.set_index("stay_id")["outtime"] - DEN.set_index("stay_id")["intime"])
          .dt.total_seconds() / 3600)
cam["out_hr"] = cam["stay_id"].map(out_hr)
if "deathtime" in DEN.columns:
    d_hr = ((DEN.set_index("stay_id")["deathtime"] - DEN.set_index("stay_id")["intime"])
            .dt.total_seconds() / 3600)
    cam["death_hr"] = cam["stay_id"].map(d_hr)
else:
    cam["death_hr"] = np.nan
cam["win_end"] = cam["hr"] + W_AHEAD

miss = cam[~cam.labeled].copy()
print(f"전체 앵커 {len(cam):,} · 라벨 생성 {int(cam.labeled.sum()):,} "
      f"({100*cam.labeled.mean():.1f}%) · 미관찰 {len(miss):,} ({100*(~cam.labeled).mean():.1f}%)")


def classify(r_any, r_death, r_out, r_end):
    if r_any > 0:
        return "전부 UTA (창에 평가는 있었다)"
    if pd.notna(r_death) and r_death <= r_end:
        return "사망"
    if pd.notna(r_out) and r_out <= r_end:
        return "ICU 퇴실"
    if r_end > HR_CAP:
        return "240h 캡에 잘림"
    return "재원 중인데 미평가"


miss["원인"] = [classify(a, d, o, e) for a, d, o, e
               in zip(miss.n_any_win, miss.death_hr, miss.out_hr, miss.win_end)]

head("[1] 라벨 미관찰 원인 분리")
order = ["전부 UTA (창에 평가는 있었다)", "ICU 퇴실", "재원 중인데 미평가", "240h 캡에 잘림", "사망"]
t = miss["원인"].value_counts().reindex(order).fillna(0).astype(int).to_frame("instance")
t["미관찰 중 %"] = (100 * t.instance / len(miss)).round(1)
t["전체 앵커 대비 %"] = (100 * t.instance / len(cam)).round(1)
t["stay"] = miss.groupby("원인")["stay_id"].nunique().reindex(order).fillna(0).astype(int)
print(t.to_string())
t.to_csv(os.path.join(OUT, "cens1_reasons.csv"), encoding="utf-8-sig")
print("  -> cens1_reasons.csv")

head("[2] 앵커 상태별 원인 (UTA 앵커가 왜 41%밖에 라벨이 안 붙나)")
ct = pd.crosstab(miss["v"], miss["원인"], normalize="index").reindex(columns=order) * 100
ct = ct.round(1)
ct.insert(0, "미관찰 n", miss.groupby("v").size())
print(ct.to_string())
ct.to_csv(os.path.join(OUT, "cens2_by_anchor.csv"), encoding="utf-8-sig")
print("  -> cens2_by_anchor.csv")

head("[3] 무작위 탈락인가 — 탈락군 vs 라벨군의 사망률")
lab = cam[cam.labeled]
hef = DEN.set_index("stay_id")["hospital_expire_flag"]
for nm, sub in [("라벨 생성됨", lab), ("미관찰 전체", miss)]:
    print(f"{nm:18s} stay {sub.stay_id.nunique():6,} · 병원 사망률 "
          f"{100*hef.reindex(sub.stay_id.unique()).mean():.1f}%")
for r in order:
    s = miss[miss.원인 == r]
    if len(s):
        print(f"  └ {r:22s} stay {s.stay_id.nunique():6,} · 사망률 "
              f"{100*hef.reindex(s.stay_id.unique()).mean():.1f}%")

print("\n※ '전부 UTA' 는 LNN 구간 제약의 실제 대상이다 — 평가는 했는데 결과가 확정이 아닌 창.")
print("  'ICU 퇴실' 은 경쟁위험이고 구간 문제가 아니다. 둘을 섞으면 안 된다.")
