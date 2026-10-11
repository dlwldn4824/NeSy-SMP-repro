# -*- coding: utf-8 -*-
"""항목7 보완: '조기' 이동 — 시점과 도달 수준."""
import sys,re; import pandas as pd, numpy as np
sys.stdout.reconfigure(encoding="utf-8"); pd.set_option("display.width",240)
OUT="notes/eda"
b=pd.read_pickle(f"{OUT}/_icu_base.pkl"); b["era"]=b["anchor_year_group"].str.replace(" ","",regex=False)
ce=pd.read_parquet(f"{OUT}/_step1_chart.parquet")
DEN=b[(b.age>=18)&(b.los>=1.0)]
mb=ce[ce.itemid.isin([229319,229321])].copy()          # JH-HLM (순서형)
mb=mb[mb.stay_id.isin(DEN.stay_id)]
mb["charttime"]=pd.to_datetime(mb.charttime)
mb["hr"]=(mb.charttime-mb.stay_id.map(DEN.set_index("stay_id")["intime"])).dt.total_seconds()/3600
mb["lvl"]=mb["value"].str.extract(r"^(\d)").astype(float)   # 1..8
mb=mb[mb.hr.notna()&mb.lvl.notna()]

# JH-HLM 보유 stay 로 분모 한정 (2017+ 100%)
have=set(mb.stay_id.unique())
D=DEN[DEN.stay_id.isin(have)]
print(f"JH-HLM 보유 stay = {len(D):,} / {len(DEN):,} ({100*len(D)/len(DEN):.1f}%)\n")

print("="*74); print("[항목7-1] 첫 이동 기록까지 걸린 시간 (ICU 입실 기준)")
f=mb.groupby("stay_id")["hr"].min()
print(f"median={f.median():.1f}h  q1={f.quantile(.25):.1f}h  q3={f.quantile(.75):.1f}h")
for h in [6,12,24,48]: print(f"  {h:3d}h 이내 첫 기록: {100*(f<=h).mean():5.1f}%")

print("\n"+"="*74); print("[항목7-2] '조기 가동' 도달 — 수준 3+ (침상 밖 활동) 최초 시각")
# 1 Bedrest, 2a/2b/2c 침상내, 3 Sit at edge, 4 Chair, 5 Stand, 6/7 Walk
oob=mb[mb.lvl>=3].groupby("stay_id")["hr"].min()
oob=oob.reindex(D.stay_id.values)
for h in [24,48,72]:
    print(f"  ICU 입실 {h:3d}h 이내 수준3+ 도달: {100*(oob<=h).mean():5.1f}%")
print(f"  ICU 재원 중 한 번도 수준3+ 도달 못함: {100*oob.isna().mean():5.1f}%")
print(f"  도달한 stay의 도달시각 median: {oob.median():.1f}h")

print("\n"+"="*74); print("[항목7-3] stay 최고 도달 수준 분포")
mx=mb.groupby("stay_id")["lvl"].max().reindex(D.stay_id.values)
lab={1:"1 Bedrest",2:"2 침상내(ROM/turning)",3:"3 침상 걸터앉기",4:"4 의자 이동",
     5:"5 기립",6:"6 10보 보행",7:"7 25ft 보행",8:"8 이상"}
t=mx.value_counts().sort_index()
for k,v in t.items(): print(f"  {lab.get(int(k),k):22s} {v:7,}  ({100*v/len(mx):5.1f}%)")

print("\n"+"="*74); print("[항목7-4] 시기별 조기가동(48h내 수준3+) 비율")
D2=D.copy(); D2["oob48"]=(oob.values<=48)
print((100*D2.groupby("era")["oob48"].mean()).round(1).to_string())

print("\n"+"="*74); print("[항목7-5] 섬망과의 관계")
coh=pd.read_pickle(f"{OUT}/_delirium_cohort.pkl")
c=coh.join(pd.DataFrame({"oob_hr":oob}),how="left")
c["early48"]=(c.oob_hr<=48)
sub=c[c.oob_hr.notna()|c.index.isin(have)]
print(f"delirium cohort 중 JH-HLM 보유: {c.index.isin(have).sum():,}")
x=c[c.index.isin(have)]
print(f"  48h내 수준3+ 도달군 섬망률   : {100*x.loc[x.early48,'delirium'].mean():.1f}%  (n={int(x.early48.sum()):,})")
print(f"  미도달군 섬망률              : {100*x.loc[~x.early48,'delirium'].mean():.1f}%  (n={int((~x.early48).sum()):,})")
print("\n※ 교란 미보정. 중증도가 낮아야 일찍 걷는다 (confounding by indication).")
pd.DataFrame({"first_mob_hr":f}).describe().to_csv(f"{OUT}/step1_7_early_mobility.csv",encoding="utf-8-sig")
