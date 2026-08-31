# -*- coding: utf-8 -*-
"""부분수행 지적 대응: (a) 전체 MIMIC 분모 (b) 항목5 도구별 보유율 정식화"""
import sys; import pandas as pd, numpy as np
sys.stdout.reconfigure(encoding="utf-8"); pd.set_option("display.width",220)
OUT="notes/eda"
b=pd.read_pickle(f"{OUT}/_icu_base.pkl"); b["era"]=b["anchor_year_group"].str.replace(" ","",regex=False)
per=pd.read_parquet(f"{OUT}/_padis_stay_group_counts.parquet")

print("="*74); print("[보완A] 분모를 좁힌 것이 결과를 바꾸는가 — 필터 없는 전체로 재계산")
defs={"전체 ICU stay (필터 없음)":b,
      "adult (age>=18)":b[b.age>=18],
      "adult + LOS>=1d (기존 보고 분모)":b[(b.age>=18)&(b.los>=1.0)]}
rows=[]
for name,x in defs.items():
    j=x.merge(per,left_on="stay_id",right_index=True,how="left").fillna(0)
    rows.append(dict(분모=name, stays=len(j), 환자=j.subject_id.nunique(),
        RASS=round(100*(j.RASS>0).mean(),1),
        섬망평가=round(100*(j.DELIRIUM_ASSESS>0).mean(),1),
        PainNRS=round(100*(j.PAIN_NRS>0).mean(),1),
        CPOT=round(100*(j.CPOT>0).mean(),1),
        Mobility=round(100*(j.MOBILITY>0).mean(),1)))
t=pd.DataFrame(rows); print(t.to_string(index=False))
t.to_csv(f"{OUT}/step1_A_denominator.csv",index=False,encoding="utf-8-sig")
print("[RASS 보유율] 전체 {:.1f}% vs adult+LOS>=1d {:.1f}%".format(rows[0]["RASS"], rows[2]["RASS"]))
print("  짧은 stay는 평가를 받기 전에 나가므로. 보고 시 분모를 반드시 명시해야 함.")

print("\n"+"="*74); print("[보완B] 항목5 정식화 — 통증 도구별 stay 보유율 (분모: adult+LOS>=1d)")
DEN=b[(b.age>=18)&(b.los>=1.0)]; den=DEN.groupby("era").size()
j=DEN.merge(per,left_on="stay_id",right_index=True,how="left").fillna(0)
t=j.groupby("era").apply(lambda x: pd.Series({
    "stays":len(x),
    "NRS (Pain Level)%":round(100*(x.PAIN_NRS>0).mean(),1),
    "CPOT%":round(100*(x.CPOT>0).mean(),1),
    "BPS%":0.0}),include_groups=False)
t.loc["전체"]=[len(j),round(100*(j.PAIN_NRS>0).mean(),1),round(100*(j.CPOT>0).mean(),1),0.0]
print(t.to_string())
t.to_csv(f"{OUT}/step1_5_tool_coverage.csv",encoding="utf-8-sig")
print("\nBPS = 0.0% : MIMIC-IV d_items 에 Behavioral Pain Scale 항목 자체가 없음 (검색 결과 0건)")
print("\nstay당 측정 횟수 median (보유 stay 한정):")
for g in ["PAIN_NRS","CPOT"]:
    s=j[j[g]>0][g]; print(f"  {g:9s} n_stay={len(s):6d}  median={s.median():5.0f}  q3={s.quantile(.75):6.0f}")
