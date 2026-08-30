# -*- coding: utf-8 -*-
"""1단계 항목 5,6,7 용 스캔."""
import sys,sqlite3,time; import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
DB="file:C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db?mode=ro"
con=sqlite3.connect(DB,uri=True); con.execute("pragma cache_size=-400000")

# 5) 통증 평가 도구 + 7) 조기 이동
PAIN_METHOD=[223795,229687,229688,229705,229689,229690,229706]
MOBIL=[229319,229321,229633,229742,228697]
ids=PAIN_METHOD+MOBIL
t=time.time()
ce=pd.read_sql(f"""select stay_id,itemid,charttime,value from chartevents
 where itemid in ({','.join(map(str,ids))}) and stay_id is not null""",con)
print(f"chartevents scan {time.time()-t:.0f}s rows={len(ce)}")
ce.to_parquet("notes/eda/_step1_chart.parquet")

# 6) 진정제 (inputevents)
SED={225150:"dexmedetomidine",229420:"dexmedetomidine",221385:"lorazepam",
     221668:"midazolam",222168:"propofol",221623:"diazepam"}
t=time.time()
ie=pd.read_sql(f"""select stay_id,itemid,starttime,endtime,amount,amountuom
 from inputevents where itemid in ({','.join(map(str,SED))})""",con)
print(f"inputevents scan {time.time()-t:.0f}s rows={len(ie)}")
ie["drug"]=ie["itemid"].map(SED)
ie.to_parquet("notes/eda/_step1_sed.parquet")
print(ie.groupby("drug").size().to_string())
