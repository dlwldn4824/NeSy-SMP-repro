# -*- coding: utf-8 -*-
# 17_cam_split_eda.py 보충: (1) UTA 앵커 포함 규모  (2) 고정 24h 타깃 계층별  (3) 240h 캡  (4) 환자단위 분할 규모
import os, sys, numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ["EDA_DATA"]
CAM_ITEM, W = 228332, 24.0

b = pd.read_pickle(f"{DATA}/_icu_base.pkl")
v = pd.read_parquet(f"{DATA}/_label_values.parquet")
v = v[v.itemid == CAM_ITEM][["stay_id","charttime","value"]]
b["intime"] = pd.to_datetime(b["intime"])
if "age" not in b.columns:
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
DEN = b[(b.age>=18)&(b.los>=1.0)].copy()
intime = b.set_index("stay_id")["intime"]

MAP = {"Positive":"P","Negative":"N","UTA":"U","Unable to Assess":"U","Unable to assess":"U"}
cam = v.copy()
cam["charttime"] = pd.to_datetime(cam["charttime"])
cam["v"] = cam["value"].astype(str).str.strip().map(MAP)
cam = cam[cam.v.notna() & cam.stay_id.isin(DEN.stay_id)].copy()
cam["hr"] = (cam["charttime"] - cam["stay_id"].map(intime)).dt.total_seconds()/3600
cam = cam[cam.hr>=0].sort_values(["stay_id","hr"]).reset_index(drop=True)

# 앵커 = 모든 CAM 기록(UTA 포함). 타깃 = 앞으로 24h 안의 확정(P/N) 중 P 가 있나
h   = cam["hr"].to_numpy(float)
isC = (cam["v"]!="U").to_numpy()          # 확정 여부
isP = (cam["v"]=="P").to_numpy()
cumC = np.concatenate([[0], isC.cumsum()])
cumP = np.concatenate([[0], (isC&isP).cumsum()])
uniq, first, cnt = np.unique(cam["stay_id"].to_numpy(), return_index=True, return_counts=True)
has_any = np.zeros(len(cam), bool); has_pos = np.zeros(len(cam), bool)
for a, n in zip(first, cnt):
    hh = h[a:a+n]; idx = np.arange(n)
    j = np.searchsorted(hh, hh+W, side="right")
    has_any[a:a+n] = (cumC[a+j]-cumC[a+idx+1]) > 0
    has_pos[a:a+n] = (cumP[a+j]-cumP[a+idx+1]) > 0
cam["labeled"], cam["y"] = has_any, has_pos

def block(title, d):
    print("\n"+"="*72); print(title); print("="*72)
    t = d.groupby("v").agg(앵커수=("y","size"), 라벨생성=("labeled","sum"))
    t["라벨생성%"] = (100*t.라벨생성/t.앵커수).round(1)
    lab = d[d.labeled]
    t["y=1"] = lab.groupby("v")["y"].sum()
    t["Positive%"] = (100*lab.groupby("v")["y"].mean()).round(1)
    t["stay수"] = lab.groupby("v")["stay_id"].nunique()
    print(t.reindex(["N","P","U"]).to_string())
    print(f"합계: 앵커 {len(d):,} · 라벨생성 {int(d.labeled.sum()):,} "
          f"({100*d.labeled.mean():.1f}%) · Positive {100*lab.y.mean():.1f}%")
    return lab

lab_all = block("[A] 고정 24h 타깃 — 앵커 상태별 (전체 재원기간)", cam)
lab_cap = block("[B] 같은 조건 + 입실 240h 이내로 캡", cam[cam.hr<=240])

print("\n"+"="*72); print("[C] UTA 앵커를 넣으면 얼마나 늘어나나"); print("="*72)
c_only = lab_cap[lab_cap.v!="U"]; u_only = lab_cap[lab_cap.v=="U"]
print(f"확정(P/N) 앵커만        : {len(c_only):,} instance / {c_only.stay_id.nunique():,} stay")
print(f"UTA 앵커 추가           : +{len(u_only):,} ({100*len(u_only)/len(c_only):.1f}% 증가)")
print(f"UTA 앵커만 가진 stay    : {len(set(u_only.stay_id)-set(c_only.stay_id)):,} stay (새로 살아남음)")

print("\n"+"="*72); print("[D] 환자 단위 분할 규모 (B안 = 240h 캡, UTA 앵커 포함)"); print("="*72)
m = lab_cap.merge(DEN[["stay_id","subject_id"]], on="stay_id")
per_pat = m.groupby("subject_id").agg(inst=("y","size"), pos=("y","sum"))
print(f"환자 {len(per_pat):,}명 · instance {len(m):,}개")
print(f"환자당 instance median (IQR): {per_pat.inst.median():.0f} "
      f"({per_pat.inst.quantile(.25):.0f}-{per_pat.inst.quantile(.75):.0f})")
print(f"Positive 를 한 번이라도 겪은 환자: {100*(per_pat.pos>0).mean():.1f}%")
s = per_pat.inst.sort_values(ascending=False); cum = s.cumsum()/s.sum()
for p in [0.01,0.05,0.10]:
    k = max(int(len(s)*p),1)
    print(f"  상위 {int(p*100)}% 환자({k:,}명)가 instance 의 {100*cum.iloc[k-1]:.1f}% 차지")
for r in [0.70,0.15,0.15]:
    print(f"  {int(r*100)}% 분할 시 환자 ~{int(len(per_pat)*r):,}명 / instance ~{int(len(m)*r):,}개")

print("\n"+"="*72); print("[E] stay 당 instance 상한(cap)을 걸면"); print("="*72)
n_by_stay = lab_cap.groupby("stay_id").size()
for cap in [5,10,20,40,None]:
    tot = int(np.minimum(n_by_stay, cap).sum()) if cap else int(n_by_stay.sum())
    print(f"  cap={str(cap):>4} : instance {tot:,} · 영향받는 stay "
          f"{int((n_by_stay>cap).sum()) if cap else 0:,}")
