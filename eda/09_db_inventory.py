# -*- coding: utf-8 -*-
"""전체 MIMIC 데이터 확인: 31개 테이블 전수 인벤토리."""
import sys,sqlite3,time; import pandas as pd
sys.stdout.reconfigure(encoding="utf-8"); pd.set_option("display.width",240)
DB="file:C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db?mode=ro"
con=sqlite3.connect(DB,uri=True); con.execute("pragma cache_size=-400000")
tabs=[r[0] for r in con.execute("select name from sqlite_master where type='table' order by name")]
rows=[]
for t in tabs:
    t0=time.time()
    n=con.execute(f"select count(*) from {t}").fetchone()[0]
    cols=[c[1] for c in con.execute(f"pragma table_info({t})")]
    has=lambda c: c in cols
    d={"table":t,"rows":n,"cols":len(cols),"sec":round(time.time()-t0,1),
       "subject_id":has("subject_id"),"hadm_id":has("hadm_id"),"stay_id":has("stay_id")}
    # ICU stay 연결성
    if has("stay_id") and n>0:
        d["n_stay"]=con.execute(f"select count(distinct stay_id) from {t}").fetchone()[0]
    elif has("hadm_id") and n>0:
        d["n_hadm"]=con.execute(f"select count(distinct hadm_id) from {t}").fetchone()[0]
    rows.append(d)
    print(f"{t:22s} rows={n:>12,}  ({d['sec']}s)",flush=True)
df=pd.DataFrame(rows)
df.to_csv("notes/eda/step1_db_inventory.csv",index=False,encoding="utf-8-sig")
print("\n"+df.to_string(index=False))
