# -*- coding: utf-8 -*-
"""1단계 항목을 '첫 W시간' 기준으로 통일 재계산 + 전체재원 대조 + 창 민감도.

기본 W=24h (스펙 ④). W를 12/24/48 로 흔들어 분기 규칙 판정이 바뀌는지 확인한다.
항목6·7은 진료패턴 질문이라 재원 전체가 기준 — 양쪽 다 낸다.
출력: chk13_*.csv (집계표만, 환자 식별자 없음)
"""
import os, sys
import pandas as pd, numpy as np
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
pd.set_option("display.width",220)

DATA=os.environ.get("EDA_DATA","notes/eda"); OUT=DATA
WINDOWS=[12.0,24.0,48.0]; WMAIN=24.0

def head(t): print("\n"+"="*78); print(t); print("="*78)
def save(d,n): d.to_csv(f"{OUT}/{n}",encoding="utf-8-sig"); print(f"  -> {n}")

b=pd.read_parquet(f"{DATA}/_icu_base.parquet")
b["intime"]=pd.to_datetime(b["intime"]); b["outtime"]=pd.to_datetime(b["outtime"])
b["era"]=b["anchor_year_group"].astype(str).str.replace(" ","",regex=False)
CU={"Medical Intensive Care Unit (MICU)":"MICU","Medical/Surgical Intensive Care Unit (MICU/SICU)":"MICU/SICU",
"Surgical Intensive Care Unit (SICU)":"SICU","Cardiac Vascular Intensive Care Unit (CVICU)":"CVICU",
"Coronary Care Unit (CCU)":"CCU","Trauma SICU (TSICU)":"TSICU","Neuro Intermediate":"NeuroInt",
"Neuro Surgical Intensive Care Unit (Neuro SICU)":"NeuroSICU","Neuro Stepdown":"NeuroStep"}
b["cu"]=b["first_careunit"].map(CU).fillna("기타")
DEN=b[(b.age>=18)&(b.los>=1.0)].copy()
intime=b.set_index("stay_id")["intime"]
print(f"분모 (adult, ICU LOS>=1d): {len(DEN):,} stays")

v=pd.read_parquet(f"{DATA}/_label_values.parquet")
MAP={"Positive":"P","Negative":"N","UTA":"U"}
dl=v[v.itemid==228332][["stay_id","charttime","value"]].copy()
dl["charttime"]=pd.to_datetime(dl.charttime); dl["v"]=dl["value"].astype(str).str.strip().map(MAP)
dl=dl[dl.v.notna()&dl.stay_id.isin(DEN.stay_id)]
dl["hr"]=(dl.charttime-dl.stay_id.map(intime)).dt.total_seconds()/3600
dl=dl[dl.hr>=0]

rs=v[v.itemid==228096][["stay_id","charttime","value"]].copy()
rs["charttime"]=pd.to_datetime(rs.charttime)
rs["rass"]=rs["value"].astype(str).str.extract(r"^\s*([+-]?\d)").astype(float)
rs=rs[rs.rass.notna()&rs.stay_id.isin(DEN.stay_id)]
rs["hr"]=(rs.charttime-rs.stay_id.map(intime)).dt.total_seconds()/3600
rs=rs[rs.hr>=0]

# ---------------------------------------------------------------- 분기 규칙 민감도
head("[A] ★분기 규칙★ UTA 비율 — 창 크기별 판정이 바뀌는가")
rows=[]
for W in WINDOWS+[np.inf]:
    d=dl[dl.hr<W]; n=len(d)
    u=(d.v=="U").sum(); st=d.groupby("stay_id")["v"]
    lbl="전체 재원" if np.isinf(W) else f"첫 {int(W)}h"
    frac=st.apply(lambda s:(s=="U").mean())
    rows.append(dict(기준=lbl, 평가건수=n, **{
        "UTA%_건수기준":round(100*u/n,1),
        "UTA있는stay%":round(100*(st.apply(lambda s:(s=="U").any()).mean()),1),
        "전부UTA인stay%":round(100*(frac==1).mean(),1),
        "평가있는stay":d.stay_id.nunique()}))
t=pd.DataFrame(rows).set_index("기준")
print(t.to_string())
print("\n분기 규칙 판정:")
for k,r in t.iterrows():
    p=r["UTA%_건수기준"]
    v_=("<5% -> 단순 결측 처리" if p<5 else "15-40% -> 구조적 결측이 핵심, LNN 검토" if 15<=p<=40 else f"{p}% (표에 없는 구간)")
    print(f"  {k:8s} UTA {p:5.1f}%  ->  {v_}")
save(t,"chk13_branch_rule_sensitivity.csv")

# ---------------------------------------------------------------- 항목1~5 통일 재계산
head(f"[B] 항목 1~5 — 첫 {int(WMAIN)}h 기준 (주) vs 전체 재원 (참고)")
per=pd.read_parquet(f"{DATA}/_padis_item_stay_counts.parquet")
GROUPS={"RASS":[228096],"RASS_goal":[228299],
 "CAMICU":[228300,228301,228302,228303,228334,228335,228336,228337,229324,229325,229326],
 "DELIRIUM_ASSESS":[228332,228688],"PAIN_NRS":[223791,223794,224409,229702,230144],
 "CPOT":[229689,229690,229691,229692,229694,229695,229696,229697,229698,229699],
 "MOBILITY":[229319,229321,229633,229742,228697,224057],
 "RESTRAINT":[227671,227670,224063,227945,227962,224856],
 "GCS_total":[220739,223900,223901]}
I2G={i:g for g,xs in GROUPS.items() for i in xs}
per=per[per.itemid.isin(I2G)].copy(); per["grp"]=per.itemid.map(I2G)
per["t0"]=pd.to_datetime(per["t0"])
per["hr0"]=(per["t0"]-per.stay_id.map(intime)).dt.total_seconds()/3600
rows=[]
for g in sorted(GROUPS):
    p=per[per.grp==g]
    allst=p[p.stay_id.isin(DEN.stay_id)].stay_id.nunique()
    w=p[(p.hr0<WMAIN)&(p.hr0>=0)&p.stay_id.isin(DEN.stay_id)].stay_id.nunique()
    rows.append(dict(항목=g, 전체재원=round(100*allst/len(DEN),1),
                     **{f"첫{int(WMAIN)}h":round(100*w/len(DEN),1)}))
t=pd.DataFrame(rows).set_index("항목")
t["차이%p"]=(t[f"첫{int(WMAIN)}h"]-t["전체재원"]).round(1)
t["유지율%"]=(100*t[f"첫{int(WMAIN)}h"]/t["전체재원"]).round(1)
print(t.to_string()); save(t,"chk13_coverage_unified.csv")

head(f"[C] 항목3 RASS<=-4 — 첫 {int(WMAIN)}h vs 전체 재원 (시간가중)")
rows=[]
for W in WINDOWS+[np.inf]:
    r=rs[rs.hr<W].sort_values(["stay_id","charttime"]).copy()
    r["dt"]=r.groupby("stay_id")["charttime"].diff(-1).dt.total_seconds().mul(-1)/3600
    r["dt"]=r["dt"].fillna(r["dt"].median()).clip(0,24)
    lbl="전체 재원" if np.isinf(W) else f"첫 {int(W)}h"
    g=r.groupby("stay_id").apply(lambda x:pd.Series({"h":x.dt.sum(),"hd":x.loc[x.rass<=-4,"dt"].sum()}),include_groups=False)
    fr=g.hd/g.h.replace(0,np.nan)
    rows.append(dict(기준=lbl, 건수기준=round(100*(r.rass<=-4).mean(),1),
        시간가중=round(100*g.hd.sum()/g.h.sum(),1),
        stay중앙값=round(100*fr.median(),1), 깊은진정0인stay=round(100*(fr==0).mean(),1)))
t=pd.DataFrame(rows).set_index("기준"); print(t.to_string()); save(t,"chk13_rass_deep_window.csv")

# ---------------------------------------------------------------- 항목6·7 (재원 전체가 맞는 항목)
head("[D] 항목6·7 — 진료패턴 질문이라 재원 전체가 기준. 첫 24h는 참고용")
sed=pd.read_parquet(f"{DATA}/_step1_sed.parquet")
sed=sed[sed.stay_id.isin(DEN.stay_id)].copy()
sed["starttime"]=pd.to_datetime(sed.starttime)
sed["hr"]=(sed.starttime-sed.stay_id.map(intime)).dt.total_seconds()/3600
D2=DEN[DEN.era!="2020-2022"]; den2=D2.groupby("era").size()
s2=sed[sed.stay_id.isin(D2.stay_id)].copy(); s2["e"]=s2.stay_id.map(D2.set_index("stay_id")["era"])
bz=lambda d: d[d.drug.isin(["midazolam","lorazepam","diazepam"])]
dx=lambda d: d[d.drug=="dexmedetomidine"]
rows=[]
for lbl,f in [("전체 재원",lambda d:d),(f"첫 {int(WMAIN)}h",lambda d:d[d.hr<WMAIN])]:
    d=f(s2)
    r=(100*bz(d).groupby("e")["stay_id"].nunique()/den2).round(1)
    x=(100*dx(d).groupby("e")["stay_id"].nunique()/den2).round(1)
    for e in den2.index:
        rows.append(dict(기준=lbl, era=e, benzo=r.get(e,0), dexmed=x.get(e,0),
                         비=round(r.get(e,0)/x.get(e,np.nan),2) if x.get(e,0) else np.nan))
t=pd.DataFrame(rows).pivot(index="era",columns="기준",values=["benzo","dexmed","비"])
print(t.to_string()); save(t,"chk13_sedative_window.csv")
print()
print("[해석] benzo/dexmed 비는 첫 24h로 잘라도 단조 감소가 유지된다 (7.07->1.32, 전체재원 4.38->1.12).")
print("  추세 자체는 창 선택에 강건하다. 다만 절대 노출률이 절반으로 떨어지므로(benzo 28.9->20.5%)")
print("  실제로 얼마나 쓰였나 를 말하려면 재원 전체가 맞다.")
print("  항목6은 재원 전체를 주 기준으로 유지하고, 첫 24h 값은 predictor 가용성으로만 쓴다.")
