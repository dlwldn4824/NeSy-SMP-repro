# -*- coding: utf-8 -*-
"""항목6 심화: 노출률 + 투여기간 + 누적용량 + 지속주입 여부."""
import sys; import pandas as pd, numpy as np
sys.stdout.reconfigure(encoding="utf-8"); pd.set_option("display.width",240)
OUT="notes/eda"
b=pd.read_pickle(f"{OUT}/_icu_base.pkl"); b["era"]=b["anchor_year_group"].str.replace(" ","",regex=False)
DEN=b[(b.age>=18)&(b.los>=1.0)]
# 투약 데이터 결손으로 2020-2022 제외
DEN=DEN[DEN.era!="2020-2022"]
den=DEN.groupby("era").size()
sed=pd.read_parquet(f"{OUT}/_step1_sed.parquet")
sed=sed[sed.stay_id.isin(DEN.stay_id)].copy()
sed["starttime"]=pd.to_datetime(sed.starttime); sed["endtime"]=pd.to_datetime(sed.endtime)
sed["hrs"]=(sed.endtime-sed.starttime).dt.total_seconds()/3600
sed["e"]=sed.stay_id.map(DEN.set_index("stay_id")["era"])
print("분모: adult + LOS>=1d, 2020-2022 제외 =",f"{len(DEN):,} stays\n")

print("="*74); print("[항목6-1] 노출률 (%)  — 해당 약을 1회 이상 받은 stay")
expo=sed.groupby(["e","drug"])["stay_id"].nunique().unstack(fill_value=0)
print((100*expo.div(den,axis=0)).round(1).to_string())

print("\n"+"="*74); print("[항목6-2] 투여기간 median (시간) — 노출된 stay 한정, stay별 총합")
dur=sed.groupby(["stay_id","drug"])["hrs"].sum().reset_index()
dur["e"]=dur.stay_id.map(DEN.set_index("stay_id")["era"])
print(dur.pivot_table(index="e",columns="drug",values="hrs",aggfunc="median").round(1).to_string())

print("\n"+"="*74); print("[항목6-3] 누적용량 median — 노출된 stay 한정 (단위는 약별 상이)")
amt=sed.groupby(["stay_id","drug"]).agg(amount=("amount","sum")).reset_index()
amt["e"]=amt.stay_id.map(DEN.set_index("stay_id")["era"])
print(amt.pivot_table(index="e",columns="drug",values="amount",aggfunc="median").round(1).to_string())
print("단위:", sed.groupby("drug")["amountuom"].agg(lambda s:s.mode().iat[0] if len(s) else "?").to_dict())

print("\n"+"="*74); print("[항목6-4] 지속주입(>=6h 연속) 비율 — PADIS는 지속주입 최소화를 권고")
cont=sed[sed.hrs>=6].groupby(["e","drug"])["stay_id"].nunique().unstack(fill_value=0)
print((100*cont.div(den,axis=0)).round(1).to_string())

print("\n"+"="*74); print("[항목6-5] benzo vs dexmed — PADIS 핵심 축")
bz=sed[sed.drug.isin(["midazolam","lorazepam","diazepam"])]
dx=sed[sed.drug=="dexmedetomidine"]
t=pd.DataFrame({
 "benzo 노출%":(100*bz.groupby("e")["stay_id"].nunique()/den).round(1),
 "dexmed 노출%":(100*dx.groupby("e")["stay_id"].nunique()/den).round(1),
 "benzo 지속주입%":(100*bz[bz.hrs>=6].groupby("e")["stay_id"].nunique()/den).round(1),
 "dexmed 지속주입%":(100*dx[dx.hrs>=6].groupby("e")["stay_id"].nunique()/den).round(1),
})
t["benzo/dexmed 노출비"]=(t["benzo 노출%"]/t["dexmed 노출%"]).round(2)
print(t.to_string()); t.to_csv(f"{OUT}/step1_6_detail.csv",encoding="utf-8-sig")

print("\n"+"="*74); print("[항목6-6] 섬망과의 관계 (delirium cohort 내)")
coh=pd.read_pickle(f"{OUT}/_delirium_cohort.pkl")
ex=sed.groupby(["stay_id","drug"]).size().unstack(fill_value=0).gt(0)
c=coh.join(ex,how="left")
for _d in ex.columns: c[_d]=c[_d].fillna(False).astype(bool)
r=[]
for d in ["midazolam","lorazepam","propofol","dexmedetomidine"]:
    if d in c: r.append(dict(drug=d, 노출stay=int(c[d].sum()),
        delirium_노출=round(100*c.loc[c[d],"delirium"].mean(),1),
        delirium_비노출=round(100*c.loc[~c[d],"delirium"].mean(),1)))
rr=pd.DataFrame(r); rr["차이%p"]=(rr.delirium_노출-rr.delirium_비노출).round(1)
print(rr.to_string(index=False)); rr.to_csv(f"{OUT}/step1_6_delirium_assoc.csv",index=False,encoding="utf-8-sig")
print("\n※ 교란 미보정 단순 대조. confounding by indication (중증도) 보정 안 됨.")
