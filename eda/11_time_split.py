# -*- coding: utf-8 -*-
"""분기 규칙 대체 경로: eICU 포기 시 'MIMIC-IV 시간 분할' 실현 가능성."""
import sys; import pandas as pd, numpy as np
sys.stdout.reconfigure(encoding="utf-8"); pd.set_option("display.width",240)
OUT="notes/eda"
b=pd.read_pickle(f"{OUT}/_icu_base.pkl"); b["era"]=b["anchor_year_group"].str.replace(" ","",regex=False)
coh=pd.read_pickle(f"{OUT}/_delirium_cohort.pkl")
per=pd.read_parquet(f"{OUT}/_padis_stay_group_counts.parquet")

print("="*74)
print("페이지가 제안한 분할: 2008–2014 / 2015–2019")
print("anchor_year_group 구간: 2008-2010 | 2011-2013 | 2014-2016 | 2017-2019 | 2020-2022")
print("→ 2014-2016 구간이 제안된 경계(2014/2015)를 가로지른다. 그 분할은 만들 수 없다.")
print("→ 실현 가능한 최근접 분할: 2008-2013 / 2014-2019\n")

SPLITS={"제안(불가) 2008-2014 / 2015-2019":None,
        "실현가능 A: 2008-2013 / 2014-2019":(["2008-2010","2011-2013"],["2014-2016","2017-2019"]),
        "실현가능 B: 2011-2013 / 2014-2019":(["2011-2013"],["2014-2016","2017-2019"])}
for name,sp in SPLITS.items():
    if sp is None: print(f"[{name}] → 산출 불가\n"); continue
    early,late=sp
    print(f"[{name}]")
    for lbl,eras in [("early",early),("late",late)]:
        x=coh[coh.era.isin(eras)]
        j=b[(b.age>=18)&(b.los>=1.0)&(b.era.isin(eras))].merge(per,left_on="stay_id",right_index=True,how="left").fillna(0)
        print(f"  {lbl:5s} {'+'.join(eras):22s} 코호트 {len(x):6,} stay | delirium {100*x.delirium.mean():4.1f}% "
              f"| 사망 {100*x.hospital_expire_flag.mean():4.1f}% | RASS보유 {100*(j.RASS>0).mean():5.1f}% "
              f"| 섬망평가보유 {100*(j.DELIRIUM_ASSESS>0).mean():5.1f}%")
    print()

print("="*74); print("[판정] 시간 분할을 외부검증 축으로 쓸 수 있는가")
e=coh[coh.era.isin(["2008-2010","2011-2013"])]; l=coh[coh.era.isin(["2014-2016","2017-2019"])]
print(f"A안 early n={len(e):,} / late n={len(l):,}  (비율 {len(e)/len(l):.2f})")
print(f"  early 섬망평가 보유율이 낮아 early 코호트가 구조적으로 편향됨:")
for eras,lbl in [(["2008-2010","2011-2013"],"early"),(["2014-2016","2017-2019"],"late")]:
    j=b[(b.age>=18)&(b.los>=1.0)&(b.era.isin(eras))].merge(per,left_on="stay_id",right_index=True,how="left").fillna(0)
    ent=len(coh[coh.era.isin(eras)])/len(j)
    print(f"    {lbl:5s} 코호트 진입률 {100*ent:4.1f}%  (섬망평가 보유 {100*(j.DELIRIUM_ASSESS>0).mean():.1f}%)")
print("\nB안(2011-2013 vs 2014-2019)은 양쪽 다 섬망평가 보유 86%+ 라 진입률 차이가 작다.")
