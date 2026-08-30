# -*- coding: utf-8 -*-
"""One pass over chartevents for PADIS-relevant itemids -> per-stay coverage."""
import sqlite3, time, sys
import pandas as pd

DB = "file:C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db?mode=ro"
OUT = "notes/eda"

GROUPS = {
    "RASS":        [228096],                       # Richmond-RAS Scale
    "RASS_goal":   [228299],
    "CAMICU":      [228300, 228301, 228302, 228303, 228334, 228335, 228336, 228337, 229324, 229325, 229326],
    "DELIRIUM_ASSESS": [228332, 228688],
    "PAIN_NRS":    [223791, 223794, 224409, 229702, 230144],
    "CPOT":        [229689, 229690, 229691, 229692, 229694, 229695, 229696, 229697, 229698, 229699],
    "MOBILITY":    [229319, 229321, 229633, 229742, 228697, 224057],
    "RESTRAINT":   [227671, 227670, 224063, 227945, 227962, 224856],
    "GCS_total":   [220739, 223900, 223901],
}
ITEM2G = {i: g for g, xs in GROUPS.items() for i in xs}
ids = sorted(ITEM2G)

con = sqlite3.connect(DB, uri=True)
con.execute("pragma cache_size=-400000")
con.execute("pragma temp_store=MEMORY")

t0 = time.time()
q = f"""select stay_id, itemid, count(*) n, min(charttime) t0, max(charttime) t1
        from chartevents where itemid in ({','.join(map(str, ids))}) and stay_id is not null
        group by stay_id, itemid"""
print("scanning chartevents ...", file=sys.stderr, flush=True)
df = pd.read_sql(q, con)
print(f"scan done in {time.time()-t0:.0f}s, rows={len(df)}", file=sys.stderr, flush=True)
df["grp"] = df["itemid"].map(ITEM2G)
df.to_parquet(f"{OUT}/_padis_item_stay_counts.parquet")

per = df.groupby(["stay_id", "grp"])["n"].sum().unstack(fill_value=0)
per.to_parquet(f"{OUT}/_padis_stay_group_counts.parquet")
print("wrote per-stay group counts", per.shape, file=sys.stderr, flush=True)
