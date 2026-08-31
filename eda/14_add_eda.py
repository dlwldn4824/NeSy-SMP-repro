# -*- coding: utf-8 -*-
"""추가 EDA 1~5 중 중간 파일만으로 가능한 부분 (1,2,3,4,5a).

  1. 24-72h 고정 outcome: 라벨 재계산 · 새 Positive 비율 · 창 내 판정횟수별 라벨률
  2. 24-72h 관찰 가능성: 창 내 P/N 판정 0회 stay 규모와 그 이유 분해
  3. 첫 24h Positive 제외군(⑤ 대상): P->N 회복 비율/시점, N->P 재발 비율/시점
  4. 전체 first Positive timing: ⑤ 적용 전 집단(①②③)에서 누적 포착률
  5a. cohort 제한 후보: ICU type별 / 연도별 기술 통계 (제한을 적용하지 않고 나열만)

연도별 inputevents 기록률과 SOFA/기계환기 가용성(5b)은 원본 DB가 필요해서
15_db_checks.py 로 분리했다.

필요 파일: _icu_base(.pkl/.parquet), _label_values.parquet, _padis_stay_group_counts.parquet
출력: chk14_*.csv (집계표만, 환자 식별자 없음)

집단 정의는 기존 코드와 동일하게 재현한다 (02_delirium_cohort.py / 09_remaining_eda.py):
  DEN   = age>=18 & los>=1.0                                  (74,829)
  base3 = age>=18 & icu_seq_in_subject==1 & los>=1.0          (51,838; ①②③)
  ⑤ 통과 = base3 & 첫 24h P 0회                               (43,853)
  ⑤ 제외 = base3 & 첫 24h P >=1회                             (7,985)
CAM record 는 itemid 228332, Positive/Negative/UTA 매핑, intime 이후(hr>=0)만.
"""
import os
import sys

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
pd.set_option("display.width", 220)

DATA = os.environ.get("EDA_DATA", "notes/eda")
OUT = os.environ.get("EDA_OUT", DATA)
os.makedirs(OUT, exist_ok=True)
W0, W1 = 24.0, 72.0          # 고정 outcome 창 [24, 72)


def head(t):
    print("\n" + "=" * 78); print(t); print("=" * 78)


def pct(x, d=1):
    return round(100 * float(x), d)


def save(df, name):
    df.to_csv(f"{OUT}/{name}", encoding="utf-8-sig")
    print(f"  -> {name}")


# ============================================================ 로드 (09와 동일)
def load_base():
    pkl, pq = f"{DATA}/_icu_base.pkl", f"{DATA}/_icu_base.parquet"
    if os.path.exists(pkl):
        try:
            return pd.read_pickle(pkl)
        except Exception as e:
            print(f"[주의] {pkl} 못 읽음 ({type(e).__name__}). parquet 시도.")
    if os.path.exists(pq):
        return pd.read_parquet(pq)
    sys.exit(f"_icu_base 를 못 찾음: {pkl} / {pq}")


b = load_base()
b["intime"] = pd.to_datetime(b["intime"])
b["outtime"] = pd.to_datetime(b["outtime"])
b["era"] = b["anchor_year_group"].astype(str).str.replace(" ", "", regex=False)
CU = {"Medical Intensive Care Unit (MICU)": "MICU",
      "Medical/Surgical Intensive Care Unit (MICU/SICU)": "MICU/SICU",
      "Surgical Intensive Care Unit (SICU)": "SICU",
      "Cardiac Vascular Intensive Care Unit (CVICU)": "CVICU",
      "Coronary Care Unit (CCU)": "CCU",
      "Trauma SICU (TSICU)": "TSICU",
      "Neuro Intermediate": "NeuroInt",
      "Neuro Surgical Intensive Care Unit (Neuro SICU)": "NeuroSICU",
      "Neuro Stepdown": "NeuroStep"}
b["cu"] = b["first_careunit"].map(CU).fillna("기타")

DEN = b[(b.age >= 18) & (b.los >= 1.0)].copy()
base3 = b[(b.age >= 18) & (b.icu_seq_in_subject == 1) & (b.los >= 1.0)].copy()
intime = b.set_index("stay_id")["intime"]
print(f"DEN   (age>=18, los>=1d)          : {len(DEN):,} stays")
print(f"base3 (①성인 ②첫stay ③los>=1d)   : {len(base3):,} stays")

v = pd.read_parquet(f"{DATA}/_label_values.parquet")
dl = v[v.itemid == 228332][["stay_id", "charttime", "value"]].copy()
dl["charttime"] = pd.to_datetime(dl["charttime"])
MAP = {"Positive": "P", "Negative": "N", "UTA": "U",
       "Unable to Assess": "U", "Unable to assess": "U"}
dl["v"] = dl["value"].astype(str).str.strip().map(MAP)
dl = dl[dl["v"].notna()]
dl["hr"] = (dl["charttime"] - dl["stay_id"].map(intime)).dt.total_seconds() / 3600
dl = dl[dl.hr >= 0].sort_values(["stay_id", "hr"]).reset_index(drop=True)

d3 = dl[dl.stay_id.isin(base3.stay_id)]
obs = d3[d3.hr < W0]                                   # 첫 24h
prev_pos = obs[obs.v == "P"].stay_id.unique()          # ⑤ 제외 대상
pass5 = base3[~base3.stay_id.isin(prev_pos)]           # ⑤ 통과
print(f"⑤ 제외 대상 (첫 24h P>=1)          : {len(prev_pos):,} stays")
print(f"⑤ 통과                             : {len(pass5):,} stays")


# ============================================================ 1. 24-72h 고정 outcome
head(f"[1] {int(W0)}-{int(W1)}h 고정 outcome 라벨")
win = d3[(d3.hr >= W0) & (d3.hr < W1)]
wg = win[win.stay_id.isin(pass5.stay_id)].groupby(["stay_id", "v"]).size() \
        .unstack(fill_value=0).reindex(columns=["P", "N", "U"], fill_value=0)
wg["judge"] = wg.P + wg.N                              # 창 내 P/N 판정 횟수
lab = wg[wg.judge >= 1].copy()
lab["y"] = (lab.P > 0).astype(int)

rows = [
    {"단계": "⑤ 통과", "stays": len(pass5)},
    {"단계": f"{int(W0)}-{int(W1)}h 판정(P/N) >=1 (새 ⑥)", "stays": len(lab),
     "직전대비%": pct(len(lab) / len(pass5))},
    {"단계": "새 라벨 Positive", "stays": int(lab.y.sum()),
     "직전대비%": pct(lab.y.mean())},
]
t = pd.DataFrame(rows)
print(t.to_string(index=False))
print(f"\n새 라벨 유병률: {pct(lab.y.mean())}%   (기존 '24h 이후 언제든' 라벨: 22.5%)")
save(t, "chk14_1_label2472.csv")

lab["ab"] = pd.cut(lab.judge, [0, 1, 2, 4, 10000], labels=["1", "2", "3-4", "5+"])
g = lab.groupby("ab", observed=True).agg(stays=("y", "size"), pos=("y", "mean"))
g["Positive%"] = (100 * g.pos).round(1)
print("\n창 내 판정 횟수별 새 라벨률 (기존 라벨은 1회 5.1% vs 17회+ 76.3%, 26배):")
print(g[["stays", "Positive%"]].to_string())
mx, mn = g["Positive%"].max(), g["Positive%"].min()
print(f"최대/최소 비 = {mx / max(mn, 0.1):.1f}배")
save(g[["stays", "Positive%"]], "chk14_1_assess_gradient.csv")


# ============================================================ 2. 24-72h 관찰 가능성
head(f"[2] {int(W0)}-{int(W1)}h 창에서 outcome 을 관찰 못 하는 stay")
p5 = pass5.set_index("stay_id")
p5["judge"] = wg["judge"].reindex(p5.index).fillna(0)
p5["win_n"] = (wg.P + wg.N + wg.U).reindex(p5.index).fillna(0)   # UTA 포함 창 내 기록수
p5["icu_hr"] = (p5["outtime"] - p5["intime"]).dt.total_seconds() / 3600
if "deathtime" in p5.columns:
    p5["death_hr"] = (pd.to_datetime(p5["deathtime"]) - p5["intime"]).dt.total_seconds() / 3600
else:
    p5["death_hr"] = np.nan
    print("[주의] _icu_base 에 deathtime 없음 -> 사망 시점 분해 생략")

no_j = p5[p5.judge == 0].copy()
print(f"창 내 P/N 판정 0회: {len(no_j):,} stays ({pct(len(no_j) / len(p5))}% of ⑤ 통과)")

# 상호배타 분해: 사망 -> 퇴실 -> 재원중이지만 전부 UTA -> 재원중이고 기록 자체 없음
reason = np.where(no_j.death_hr < W1, f"{int(W1)}h 이전 사망",
         np.where(no_j.icu_hr < W1, f"{int(W1)}h 이전 ICU 퇴실",
         np.where(no_j.win_n > 0, "재원 중 · 창 내 전부 UTA",
                  "재원 중 · 창 내 기록 없음")))
t = pd.Series(reason).value_counts().to_frame("stays")
t["%of판정0회"] = (100 * t.stays / len(no_j)).round(1)
t["%of⑤통과"] = (100 * t.stays / len(p5)).round(1)
print(t.to_string())
save(t, "chk14_2_observability.csv")


# ============================================================ 3. ⑤ 제외군 회복/재발
head("[3] 첫 24h Positive 제외군: P->N 회복, N->P 재발")
dp = d3[d3.stay_id.isin(prev_pos)].copy()
firstP = dp[(dp.v == "P") & (dp.hr < W0)].groupby("stay_id")["hr"].min()
dp["fp"] = dp["stay_id"].map(firstP)

aftN = dp[(dp.v == "N") & (dp.hr > dp.fp)]
firstN = aftN.groupby("stay_id")["hr"].min()
dtN = (firstN - firstP.reindex(firstN.index)).dropna()
print(f"제외군 {len(prev_pos):,}명 중 첫 P 이후 N 관찰(회복): "
      f"{len(firstN):,} ({pct(len(firstN) / len(prev_pos))}%)")
print(f"  첫 P -> 첫 N 시간: median {dtN.median():.1f}h (q1 {dtN.quantile(.25):.1f} / q3 {dtN.quantile(.75):.1f})")
rows = [{"이벤트": "P->N 회복", "n": len(firstN), "%": pct(len(firstN) / len(prev_pos)),
         "dt_median_h": round(dtN.median(), 1)}]
for h in [24, 48, 72]:
    rows.append({"이벤트": f"  회복이 첫 P 후 {h}h 이내", "n": int((dtN <= h).sum()),
                 "%": pct((dtN <= h).sum() / len(prev_pos))})

dp2 = dp[dp.stay_id.isin(firstN.index)].copy()
dp2["fn"] = dp2["stay_id"].map(firstN)
reP = dp2[(dp2.v == "P") & (dp2.hr > dp2.fn)]
firstReP = reP.groupby("stay_id")["hr"].min()
dtR = (firstReP - firstN.reindex(firstReP.index)).dropna()
print(f"\n회복자 {len(firstN):,}명 중 N 이후 다시 P(재발): "
      f"{len(firstReP):,} ({pct(len(firstReP) / len(firstN))}%)")
print(f"  첫 N -> 재발 P 시간: median {dtR.median():.1f}h (q1 {dtR.quantile(.25):.1f} / q3 {dtR.quantile(.75):.1f})")
rows.append({"이벤트": "N->P 재발 (회복자 대비)", "n": len(firstReP),
             "%": pct(len(firstReP) / len(firstN)), "dt_median_h": round(dtR.median(), 1)})
for h in [24, 48, 72]:
    rows.append({"이벤트": f"  재발이 첫 N 후 {h}h 이내", "n": int((dtR <= h).sum()),
                 "%": pct((dtR <= h).sum() / len(firstN))})
save(pd.DataFrame(rows), "chk14_3_relapse.csv")


# ============================================================ 4. 전체 first Positive timing
head("[4] first Positive 누적 포착률 — ⑤ 적용 전 집단(base3) 전체")
allP = d3[d3.v == "P"].groupby("stay_id")["hr"].min()
print(f"base3 {len(base3):,} 중 P 가 1회 이상: {len(allP):,} ({pct(len(allP) / len(base3))}%)")
rows = []
for h in [24, 48, 72, 96, 168]:
    c = int((allP <= h).sum())
    rows.append({"입실 후": f"{h}h 이내 첫 P", "stays": c,
                 "%of_P있는stay": pct(c / len(allP)), "%of_base3": pct(c / len(base3))})
t = pd.DataFrame(rows)
print(t.to_string(index=False))
print("※ 기존 EDA #3(median 52.5h)은 코호트 내 delirium=1(24h 이후 첫 P) 조건부 분포 — 별개 값이다.")
save(t, "chk14_4_first_pos_all.csv")


# ============================================================ 5a. cohort 제한 후보 (기술 통계만)
head("[5a] cohort 제한 후보 확인 — 제한 적용 없이 나열")
cnt = dl.groupby(["stay_id", "v"]).size().unstack(fill_value=0) \
        .reindex(columns=["P", "N", "U"], fill_value=0)
D = DEN.set_index("stay_id")
D = D.join(cnt, how="left").fillna({"P": 0, "N": 0, "U": 0})
D["rec"] = D.P + D.N + D.U

t = D.groupby("cu").apply(lambda x: pd.Series({
    "stays": len(x),
    "P경험stay%": pct((x.P > 0).mean()),
    "UTA기록%": pct(x.U.sum() / max(x.rec.sum(), 1)),
    "CAM기록stay%": pct((x.rec > 0).mean())}), include_groups=False) \
     .sort_values("stays", ascending=False)
print("[ICU type 별] (DEN 기준)"); print(t.to_string())
save(t, "chk14_5_cu.csv")

t = D.groupby("era").apply(lambda x: pd.Series({
    "stays": len(x),
    "CAM기록stay%": pct((x.rec > 0).mean()),
    "P경험stay%": pct((x.P > 0).mean()),
    "UTA기록%": pct(x.U.sum() / max(x.rec.sum(), 1))}), include_groups=False)
print("\n[연도(anchor_year_group) 별] (DEN 기준)"); print(t.to_string())
print("※ 연도별 inputevents 기록률과 SOFA/기계환기 가용성은 15_db_checks.py (DB 필요)")
save(t, "chk14_5_era_cam.csv")

head("끝. 출력 CSV")
print("\n".join(sorted(f for f in os.listdir(OUT) if f.startswith("chk14") and f.endswith(".csv"))))
