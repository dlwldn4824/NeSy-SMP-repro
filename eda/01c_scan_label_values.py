# -*- coding: utf-8 -*-
"""Pull raw values for delirium/RASS items (one chartevents pass) -> label prevalence."""
import sqlite3, time, sys
import pandas as pd
DB="file:C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db?mode=ro"
IDS=[228332,228096,228300,228301,228302,228303,228334,228335,228336,228337,229324,229325,229326]
con=sqlite3.connect(DB,uri=True); con.execute("pragma cache_size=-400000")
t0=time.time()
df=pd.read_sql(f"""select stay_id,itemid,charttime,value,valuenum from chartevents
                   where itemid in ({','.join(map(str,IDS))}) and stay_id is not null""",con)
print(f"scan {time.time()-t0:.0f}s rows={len(df)}",file=sys.stderr,flush=True)
df.to_parquet("notes/eda/_label_values.parquet")
