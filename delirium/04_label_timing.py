# -*- coding: utf-8 -*-
import sys, pandas as pd, numpy as np
sys.stdout.reconfigure(encoding="utf-8")
OUT="notes/eda"
coh=pd.read_pickle(f"{OUT}/_delirium_cohort.pkl")
b=pd.read_pickle(f"{OUT}/_icu_base.pkl")
v=pd.read_parquet(f"{OUT}/_label_values.parquet")
dl=v[v.itemid==228332][["stay_id","charttime","value"]].copy(); dl["charttime"]=pd.to_datetime(dl.charttime)
intime=b.set_index("stay_id")["intime"]
dl["hr"]=(dl["charttime"]-dl["stay_id"].map(intime)).dt.total_seconds()/3600

print("="*70); print("[G] 라벨의 LOS 교란 — 관찰기회가 라벨을 만든다")
c=coh.copy()
c["fut_assess"]=c.fut_pos+c.fut_neg
c["los_bin"]=pd.cut(c.los,[1,2,3,5,10,1000],labels=["1-2d","2-3d","3-5d","5-10d","10d+"])
t=c.groupby("los_bin",observed=True).agg(n=("delirium","size"),delirium=("delirium","mean"),
   assess_median=("fut_assess","median"),mort=("hospital_expire_flag","mean"))
t["delirium%"]=(100*t["delirium"]).round(1); t["mort%"]=(100*t["mort"]).round(1)
print(t[["n","assess_median","delirium%","mort%"]].to_string())
t.to_csv(f"{OUT}/chk_G_los_confound.csv",encoding="utf-8-sig")

print("\n평가횟수(24h 이후 assessable) 구간별 delirium rate:")
c["ab"]=pd.cut(c.fut_assess,[0,1,2,4,8,16,10000],labels=["1","2","3-4","5-8","9-16","17+"])
t2=c.groupby("ab",observed=True).agg(n=("delirium","size"),delirium=("delirium","mean"),los=("los","median"))
t2["delirium%"]=(100*t2["delirium"]).round(1)
print(t2[["n","delirium%","los"]].to_string())
t2.to_csv(f"{OUT}/chk_G_assess_confound.csv",encoding="utf-8-sig")

print("\n"+"="*70); print("[H] 첫 delirium positive 발생 시점 (코호트 내 delirium=1)")
pos=dl[(dl.value=="Positive")&(dl.hr>=24)]
first=pos.groupby("stay_id")["hr"].min()
f=first.reindex(coh.index[coh.delirium==1]).dropna()
print(f"n={len(f)}  median={f.median():.1f}h  q1={f.quantile(.25):.1f}h  q3={f.quantile(.75):.1f}h")
for hi in [36,48,72,96,168]:
    print(f"  ICU 입실 {hi:3d}h 이내 발생: {100*(f<=hi).mean():5.1f}%  (누적 {int((f<=hi).sum())}명)")
pd.DataFrame({"first_pos_hr":f}).to_csv(f"{OUT}/chk_H_onset.csv",encoding="utf-8-sig")

print("\n"+"="*70); print("[I] observation window 안의 평가 밀도")
print(f"첫 24h 평가 횟수 median={coh.obs_n.median():.0f} (q1={coh.obs_n.quantile(.25):.0f}, q3={coh.obs_n.quantile(.75):.0f})")
print(f"첫 24h에 평가가 0회인 stay: {int((coh.obs_n==0).sum())} ({100*(coh.obs_n==0).mean():.1f}%)")
print(f"첫 24h이 전부 UTA인 stay: {int(((coh.obs_n>0)&(coh.obs_neg==0)&(coh.obs_pos==0)).sum())} "
      f"({100*((coh.obs_n>0)&(coh.obs_neg==0)&(coh.obs_pos==0)).mean():.1f}%)")
