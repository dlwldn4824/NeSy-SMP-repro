# -*- coding: utf-8 -*-
"""§3 '특히 확인할 부분' 항목별 EDA."""
import sys, pandas as pd, numpy as np
sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 200)
OUT="notes/eda"
coh=pd.read_pickle(f"{OUT}/_delirium_cohort.pkl")
base3=pd.read_pickle(f"{OUT}/_base3.pkl")
b=pd.read_pickle(f"{OUT}/_icu_base.pkl"); b["era"]=b["anchor_year_group"].str.replace(" ","",regex=False)
v=pd.read_parquet(f"{OUT}/_label_values.parquet")

SH={"Medical Intensive Care Unit (MICU)":"MICU","Medical/Surgical Intensive Care Unit (MICU/SICU)":"MICU/SICU",
"Surgical Intensive Care Unit (SICU)":"SICU","Cardiac Vascular Intensive Care Unit (CVICU)":"CVICU",
"Coronary Care Unit (CCU)":"CCU","Trauma SICU (TSICU)":"TSICU","Neuro Intermediate":"NeuroInt",
"Neuro Surgical Intensive Care Unit (Neuro SICU)":"NeuroSICU","Neuro Stepdown":"NeuroStep"}
for df in (coh,base3): df["cu"]=df["first_careunit"].map(SH).fillna("기타")

print("="*70); print("[A] 진료과별 분포 · delirium rate · 코호트 진입률")
a=base3.groupby("cu").agg(step3=("subject_id","size"))
c=coh.groupby("cu").agg(final=("subject_id","size"),delirium=("delirium","mean"),
                        mort=("hospital_expire_flag","mean"),los=("los","median"),age=("age","median"))
t=a.join(c).fillna(0)
t["진입률%"]=(100*t["final"]/t["step3"]).round(1)
t["delirium%"]=(100*t["delirium"]).round(1); t["mort%"]=(100*t["mort"]).round(1)
t=t[["step3","final","진입률%","delirium%","mort%","los","age"]].sort_values("final",ascending=False)
print(t.to_string()); t.to_csv(f"{OUT}/chk_A_careunit.csv",encoding="utf-8-sig")

print("\n"+"="*70); print("[B] 시기(anchor_year_group)별")
t=base3.groupby("era").agg(step3=("subject_id","size")).join(
  coh.groupby("era").agg(final=("subject_id","size"),delirium=("delirium","mean"),mort=("hospital_expire_flag","mean")))
t["진입률%"]=(100*t["final"]/t["step3"]).round(1); t["delirium%"]=(100*t["delirium"]).round(1)
t["mort%"]=(100*t["mort"]).round(1)
print(t[["step3","final","진입률%","delirium%","mort%"]].to_string()); t.to_csv(f"{OUT}/chk_B_era.csv",encoding="utf-8-sig")

print("\n"+"="*70); print("[C] UTA — 무엇이 UTA를 만드나 (RASS 동시각 매칭)")
dl=v[v.itemid==228332][["stay_id","charttime","value"]].copy(); dl["charttime"]=pd.to_datetime(dl.charttime)
rs=v[v.itemid==228096][["stay_id","charttime","value"]].copy(); rs["charttime"]=pd.to_datetime(rs.charttime)
rs["rass"]=rs["value"].str.extract(r"^\s*([+-]?\d)").astype(float)
m=dl.merge(rs[["stay_id","charttime","rass"]],on=["stay_id","charttime"],how="left")
print(f"같은 charttime에 RASS가 붙은 비율: {100*m.rass.notna().mean():.1f}%")
ct=pd.crosstab(m["value"],pd.cut(m["rass"],[-5.5,-3.5,-2.5,-0.5,4.5],
     labels=["RASS -5~-4 (깊은진정)","RASS -3","RASS -2~-1","RASS 0~+4"]),normalize="index")
print((100*ct).round(1).to_string()); ct.to_csv(f"{OUT}/chk_C_uta_rass.csv",encoding="utf-8-sig")
print("\nUTA 중 RASS<=-4 비율: %.1f%%"%(100*((m.value=="UTA")&(m.rass<=-4)).sum()/max((m.value=="UTA").sum(),1)))

print("\n"+"="*70); print("[D] ⑥에서 탈락하는 집단의 성격 (선택편향)")
t=base3.copy()
t["grp"]=np.where(t.obs_pos>0,"⑤ prevalent",np.where((t.fut_pos+t.fut_neg)>=1,"included",
        np.where(t.fut_uta>0,"⑥ UTA-only","⑥ 기록없음")))
g=t.groupby("grp").agg(stays=("subject_id","size"),mort=("hospital_expire_flag","mean"),
    los_median=("los","median"),age=("age","median"),vent_proxy=("obs_uta","mean"))
g["mort%"]=(100*g["mort"]).round(1); g["비중%"]=(100*g["stays"]/len(t)).round(1)
print(g[["stays","비중%","mort%","los_median","age"]].to_string())
print("\n⑥ UTA-only 를 delirium=1 로 넣으면:", end=" ")
alt=t[(t.obs_pos==0)&(((t.fut_pos+t.fut_neg)>=1)|(t.fut_uta>0))].copy()
alt["lab"]=np.where(alt.fut_pos>0,1,np.where((alt.fut_pos+alt.fut_neg)>=1,0,1))
print(f"n={len(alt)}, delirium={100*alt.lab.mean():.1f}%, 사망률={100*alt.hospital_expire_flag.mean():.1f}%")
g.to_csv(f"{OUT}/chk_D_dropbias.csv",encoding="utf-8-sig")

print("\n"+"="*70); print("[E] ② 환자당 첫 stay 로 버려지는 것")
allb=b[(b.age>=18)&(b.los>=1.0)]
n=allb.groupby("subject_id").size()
print(f"LOS>=1d stay가 2개 이상인 환자: {(n>1).sum()} ({100*(n>1).mean():.1f}%), 버려지는 stay {len(allb)-n.size}")
first=allb[allb.icu_seq_in_subject==1]; later=allb[allb.icu_seq_in_subject>1]
print(f"첫 stay 사망률 {100*first.hospital_expire_flag.mean():.1f}% vs 재입실 stay 사망률 {100*later.hospital_expire_flag.mean():.1f}%")

print("\n"+"="*70); print("[F] 최종 코호트 요약")
print(f"n={len(coh)} 환자={coh.subject_id.nunique()} delirium={100*coh.delirium.mean():.1f}% "
      f"사망={100*coh.hospital_expire_flag.mean():.1f}% LOS median={coh.los.median():.2f} age median={coh.age.median():.0f} "
      f"여성={100*(coh.gender=='F').mean():.1f}%")
print("\nlabel 별 대조:")
print(coh.groupby("delirium").agg(n=("subject_id","size"),mort=("hospital_expire_flag","mean"),
      los=("los","median"),age=("age","median"),obs_n=("obs_n","median"),fut_n=("fut_n","median")).round(3).to_string())
