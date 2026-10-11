# -*- coding: utf-8 -*-
"""1단계 데이터 확인 7개 항목."""
import sys; import pandas as pd, numpy as np
sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width",220)
OUT="notes/eda"
b=pd.read_pickle(f"{OUT}/_icu_base.pkl"); b["era"]=b["anchor_year_group"].str.replace(" ","",regex=False)
v=pd.read_parquet(f"{OUT}/_label_values.parquet")
per=pd.read_parquet(f"{OUT}/_padis_stay_group_counts.parquet")

DEN=b[(b.age>=18)&(b.los>=1.0)]          # 분모: adult ICU stay, LOS>=1d
print(f"분모 = adult ICU stay, LOS>=1d : {len(DEN):,} stays / {DEN.subject_id.nunique():,} 환자\n")

# ---------- 1) RASS 기록된 stay 비율 / 2) CAM-ICU 기록된 stay 비율 ----------
j=DEN.merge(per,left_on="stay_id",right_index=True,how="left").fillna(0)
print("="*72); print("[항목1·2] RASS / CAM-ICU 기록 보유 stay 비율")
t=j.groupby("era").apply(lambda x: pd.Series({
    "stays":len(x),
    "RASS%":round(100*(x.RASS>0).mean(),1),
    "Delirium평가%":round(100*(x.DELIRIUM_ASSESS>0).mean(),1),
    "CAMICU항목%":round(100*(x.CAMICU>0).mean(),1)}),include_groups=False)
t.loc["전체"]=[len(j),round(100*(j.RASS>0).mean(),1),round(100*(j.DELIRIUM_ASSESS>0).mean(),1),
               round(100*(j.CAMICU>0).mean(),1)]
print(t.to_string()); t.to_csv(f"{OUT}/step1_12_coverage.csv",encoding="utf-8-sig")

# ---------- 3) RASS <= -4 시간 비율 ----------
print("\n"+"="*72); print("[항목3] RASS ≤ −4 (CAM-ICU 평가 불가) 시간 비율")
rs=v[v.itemid==228096][["stay_id","charttime","value"]].copy()
rs["charttime"]=pd.to_datetime(rs.charttime)
rs["rass"]=rs["value"].str.extract(r"^\s*([+-]?\d)").astype(float)
rs=rs[rs.stay_id.isin(DEN.stay_id)].sort_values(["stay_id","charttime"])
# 각 측정이 다음 측정까지 유효하다고 보고 시간가중 (마지막은 중앙 간격으로 대체)
rs["dt"]=rs.groupby("stay_id")["charttime"].diff(-1).dt.total_seconds().mul(-1)/3600
med=rs["dt"].median()
rs["dt"]=rs["dt"].fillna(med).clip(0,24)
g=rs.groupby("stay_id").apply(lambda x: pd.Series({
    "hrs":x.dt.sum(),"hrs_deep":x.loc[x.rass<=-4,"dt"].sum()}),include_groups=False)
g["frac"]=g.hrs_deep/g.hrs.replace(0,np.nan)
print(f"측정 건수 기준  RASS≤−4 비율 : {100*(rs.rass<=-4).mean():.1f}%")
print(f"시간가중 기준  RASS≤−4 비율 : {100*g.hrs_deep.sum()/g.hrs.sum():.1f}%  (중앙 측정간격 {med:.1f}h)")
print(f"stay 단위 중앙값             : {100*g.frac.median():.1f}%   (q3={100*g.frac.quantile(.75):.1f}%)")
print(f"RASS≤−4 시간이 0인 stay      : {100*(g.frac==0).mean():.1f}%")
print(f"RASS≤−4 시간이 50% 넘는 stay : {100*(g.frac>0.5).mean():.1f}%")
g.to_parquet(f"{OUT}/step1_3_rass_deep.parquet")

# ---------- 4) CAM-ICU UTA 비율  ★분기 규칙★ ----------
print("\n"+"="*72); print("[항목4] CAM-ICU 'Unable to Assess' 비율  ★분기 규칙 트리거★")
dl=v[v.itemid==228332][["stay_id","charttime","value"]].copy()
dl=dl[dl.stay_id.isin(DEN.stay_id)]
vc=dl["value"].value_counts(); tot=len(dl)
print(f"전체 섬망평가 {tot:,}건")
for k in ["Negative","Positive","UTA"]:
    print(f"  {k:9s} {vc.get(k,0):>9,}  ({100*vc.get(k,0)/tot:5.1f}%)")
sg=dl.groupby("stay_id")["value"]
st=pd.DataFrame({"n":sg.size(),"uta":sg.apply(lambda s:(s=="UTA").sum())})
st["frac"]=st.uta/st.n
print(f"\nstay 단위:")
print(f"  UTA가 1건이라도 있는 stay      : {100*(st.uta>0).mean():.1f}%")
print(f"  stay별 UTA 비율 중앙값          : {100*st.frac.median():.1f}%")
print(f"  UTA가 평가의 50% 넘는 stay      : {100*(st.frac>0.5).mean():.1f}%")
print(f"  전부 UTA인 stay                 : {100*(st.frac==1).mean():.1f}%")
uta_pct=100*vc.get("UTA",0)/tot
print(f"\n>>> 측정 건수 기준 UTA = {uta_pct:.1f}%")
band = "<5% → 단순 결측 처리" if uta_pct<5 else ("15–40% → 구조적 결측이 논문 핵심, LNN 검토" if 15<=uta_pct<=40 else "5–15% 구간 (표에 없음)")
print(f">>> 분기 규칙: {band}")
st.to_parquet(f"{OUT}/step1_4_uta.parquet")
