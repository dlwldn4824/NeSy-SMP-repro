# -*- coding: utf-8 -*-
import sys; import pandas as pd, numpy as np
sys.stdout.reconfigure(encoding="utf-8"); pd.set_option("display.width",220)
OUT="notes/eda"
b=pd.read_pickle(f"{OUT}/_icu_base.pkl"); b["era"]=b["anchor_year_group"].str.replace(" ","",regex=False)
DEN=b[(b.age>=18)&(b.los>=1.0)]
ce=pd.read_parquet(f"{OUT}/_step1_chart.parquet")
sed=pd.read_parquet(f"{OUT}/_step1_sed.parquet")
era=DEN.set_index("stay_id")["era"]

print("="*72); print("[항목5] 통증 평가 도구 사용 분포")
PM=[223795,229687]   # Pain Assessment Method
pm=ce[ce.itemid.isin(PM)].copy()
pm=pm[pm.stay_id.isin(DEN.stay_id)]
print(f"'Pain Assessment Method' 기록 {len(pm):,}건 / 보유 stay {100*pm.stay_id.nunique()/len(DEN):.1f}%\n")
print("값 분포(건수 기준):")
vc=pm["value"].value_counts()
print((100*vc/len(pm)).round(1).head(10).to_string())
pm["e"]=pm.stay_id.map(era)
ct=pd.crosstab(pm["e"],pm["value"],normalize="index").mul(100).round(1)
print("\n시기별 도구 사용 비율(%):"); print(ct.to_string())
ct.to_csv(f"{OUT}/step1_5_pain_tool.csv",encoding="utf-8-sig")
# stay 단위 보유율
for name,ids in [("CPOT 계열",[229689,229690]),("Pain Level(NRS)",[223791])]:
    pass
print(f"\n※ BPS(Behavioral Pain Scale)는 MIMIC-IV d_items에 존재하지 않음 → PADIS 3대 도구 중 BPS는 매핑 불가")

print("\n"+"="*72); print("[항목6] 진정제별 노출 — 시기별 추이")
sed=sed[sed.stay_id.isin(DEN.stay_id)].copy()
sed["e"]=sed.stay_id.map(era)
expo=sed.groupby(["e","drug"])["stay_id"].nunique().unstack(fill_value=0)
den=DEN.groupby("era").size()
pct=(100*expo.div(den,axis=0)).round(1)
pct["stays"]=den
print("시기별 '해당 진정제 1회 이상 투여된 stay 비율(%)':")
print(pct.to_string()); pct.to_csv(f"{OUT}/step1_6_sedative.csv",encoding="utf-8-sig")
print("\n전체 기간 노출률(%):")
print((100*sed.groupby('drug')['stay_id'].nunique()/len(DEN)).round(1).to_string())
print("\n※ PADIS 2018/2025 = benzodiazepine 회피, dexmedetomidine 선호")
bz=sed[sed.drug.isin(["midazolam","lorazepam","diazepam"])].groupby("e")["stay_id"].nunique()
dx=sed[sed.drug=="dexmedetomidine"].groupby("e")["stay_id"].nunique()
cmp=pd.DataFrame({"benzo%":(100*bz/den).round(1),"dexmed%":(100*dx/den).round(1)})
cmp["benzo/dexmed 비"]=(bz/dx).round(2)
print(cmp.to_string()); cmp.to_csv(f"{OUT}/step1_6_benzo_vs_dex.csv",encoding="utf-8-sig")

print("\n"+"="*72); print("[항목7] 조기 이동(mobilization) 이벤트 존재 여부")
MOB={229319:"Activity/Mobility (JH-HLM)",229321:"Activity/Mobility (JH-HLM)_2",
     229633:"Basic Mobility (AM-PAC)",229742:"RN Daily Mobility Goal",228697:"Mobilization Plan"}
mb=ce[ce.itemid.isin(MOB)].copy(); mb=mb[mb.stay_id.isin(DEN.stay_id)]
mb["nm"]=mb.itemid.map(MOB); mb["e"]=mb.stay_id.map(era)
cov=mb.groupby(["e","nm"])["stay_id"].nunique().unstack(fill_value=0)
print("시기별 보유 stay 비율(%):"); print((100*cov.div(den,axis=0)).round(1).to_string())
(100*cov.div(den,axis=0)).round(1).to_csv(f"{OUT}/step1_7_mobility.csv",encoding="utf-8-sig")
print(f"\n어떤 mobility 항목이든 보유한 stay: {100*mb.stay_id.nunique()/len(DEN):.1f}%")
print(f"stay당 기록 횟수 median: {mb.groupby('stay_id').size().median():.0f}")
print("\nJH-HLM 값 분포 상위:")
print(mb[mb.itemid.isin([229319,229321])]["value"].value_counts().head(9).to_string())
