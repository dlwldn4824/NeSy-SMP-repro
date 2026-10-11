# -*- coding: utf-8 -*-
"""PADIS candidate labels per ICU stay + prevalence by cohort."""
import re
import pandas as pd

v = pd.read_parquet("notes/eda/_label_values.parquet")
b = pd.read_pickle("notes/eda/_icu_base.pkl")
b["era"] = b["anchor_year_group"].str.replace(" ", "", regex=False)

# --- delirium (itemid 228332: Negative / Positive / UTA) ---
dl = v[v.itemid == 228332].copy()
g = dl.groupby("stay_id")["value"].agg(
    n_assess="size",
    n_pos=lambda s: (s == "Positive").sum(),
    n_neg=lambda s: (s == "Negative").sum(),
    n_uta=lambda s: (s == "UTA").sum(),
)
g["delirium_ever"] = (g.n_pos > 0).astype(int)
g["assessable"] = ((g.n_pos + g.n_neg) > 0).astype(int)   # 한 번이라도 판정된 stay
g["uta_frac"] = g.n_uta / g.n_assess

# --- RASS (itemid 228096) -> leading signed integer ---
rs = v[v.itemid == 228096].copy()
rs["rass"] = rs["value"].str.extract(r"^\s*([+-]?\d)").astype(float)
r = rs.groupby("stay_id")["rass"].agg(n_rass="size", rass_min="min", rass_max="max", rass_median="median")
r["deep_sedation_ever"] = (r.rass_min <= -3).astype(int)   # PADIS: over-sedation
r["agitation_ever"] = (r.rass_max >= 2).astype(int)

lab = g.join(r, how="outer")
lab.to_parquet("notes/eda/stay_labels_padis.parquet")

d = b.merge(lab, left_on="stay_id", right_index=True, how="left")
MIX = ["Medical Intensive Care Unit (MICU)", "Medical/Surgical Intensive Care Unit (MICU/SICU)"]
adult = d[(d.age >= 18) & (d.los >= 1.0)]

def row(x, name):
    a = x[x.assessable == 1]
    return dict(
        cohort=name, stays=len(x),
        delirium_assessed_pct=round(100 * (x.assessable == 1).mean(), 1),
        delirium_pos_pct_of_assessed=round(100 * a.delirium_ever.mean(), 1) if len(a) else None,
        delirium_pos_pct_of_all=round(100 * (x.delirium_ever == 1).mean(), 1),
        deep_sedation_pct=round(100 * (x.deep_sedation_ever == 1).mean(), 1),
        agitation_pct=round(100 * (x.agitation_ever == 1).mean(), 1),
        hosp_mort_pct=round(100 * x.hospital_expire_flag.mean(), 1),
    )

rows = [row(adult, "C3 all adult ICU LOS>=1d")]
for era in ["2008-2010", "2011-2013", "2014-2016", "2017-2019", "2020-2022"]:
    rows.append(row(adult[adult.era == era], f"  all ICU / {era}"))
c2 = adult[adult.first_careunit.isin(MIX) & adult.era.isin(["2014-2016", "2017-2019"]) & (adult.icu_seq_in_hadm == 1)]
c1 = adult[(adult.first_careunit == MIX[0]) & adult.era.isin(["2014-2016", "2017-2019"]) & (adult.icu_seq_in_hadm == 1)]
rows.append(row(c1, "C1 MICU 2014-2019"))
rows.append(row(c2, "C2 MICU+MICU/SICU 2014-2019"))
out = pd.DataFrame(rows)
out.to_csv("notes/eda/label_prevalence.csv", index=False, encoding="utf-8-sig")
print(out.to_string(index=False))

print("\n== C2: 라벨 상호관계 ==")
a = c2[c2.assessable == 1]
print(f"assessable stays: {len(a)} / {len(c2)}")
print(pd.crosstab(a.delirium_ever, a.hospital_expire_flag, normalize="index").round(3).to_string())
print("\ndelirium_ever x deep_sedation_ever (row%):")
print(pd.crosstab(a.delirium_ever, a.deep_sedation_ever, normalize="index").round(3).to_string())
print("\nICU LOS median by delirium_ever:", a.groupby("delirium_ever")["los"].median().round(2).to_dict())
print("age median by delirium_ever:", a.groupby("delirium_ever")["age"].median().to_dict())
