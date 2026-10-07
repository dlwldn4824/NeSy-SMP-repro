# -*- coding: utf-8 -*-
"""ICU cohort candidates (knowledge-free). Small tables only: icustays/patients/admissions/services."""
import sqlite3, json, sys
import pandas as pd

DB = "file:C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db?mode=ro"
OUT = "notes/eda"

con = sqlite3.connect(DB, uri=True)

base = pd.read_sql("""
select i.subject_id, i.hadm_id, i.stay_id, i.first_careunit, i.last_careunit,
       i.intime, i.outtime, i.los,
       p.gender, p.anchor_age, p.anchor_year, p.anchor_year_group, p.dod,
       a.admittime, a.dischtime, a.deathtime, a.admission_type, a.admission_location,
       a.discharge_location, a.insurance, a.race, a.hospital_expire_flag
from icustays i
join patients p on p.subject_id = i.subject_id
join admissions a on a.hadm_id = i.hadm_id
""", con)

# age at ICU intime: anchor_age is age at anchor_year; MIMIC-IV dates shifted per patient
base["intime"] = pd.to_datetime(base["intime"])
base["outtime"] = pd.to_datetime(base["outtime"])
base["admittime"] = pd.to_datetime(base["admittime"])
base["dischtime"] = pd.to_datetime(base["dischtime"])
base["dod"] = pd.to_datetime(base["dod"])
base["age"] = base["anchor_age"] + (base["intime"].dt.year - base["anchor_year"])

# order of ICU stays within a hospital admission / within a patient
base = base.sort_values(["subject_id", "intime"])
base["icu_seq_in_hadm"] = base.groupby("hadm_id")["intime"].rank(method="first").astype(int)
base["icu_seq_in_subject"] = base.groupby("subject_id")["intime"].rank(method="first").astype(int)

# 30-day mortality from ICU discharge
base["days_to_death_from_icu_out"] = (base["dod"] - base["outtime"]).dt.total_seconds()/86400.0
base["mort_30d"] = ((base["days_to_death_from_icu_out"] <= 30) & (base["days_to_death_from_icu_out"] >= -1)).astype(int)
base["mort_1y"] = ((base["days_to_death_from_icu_out"] <= 365) & (base["days_to_death_from_icu_out"] >= -1)).astype(int)
base["los_hosp"] = (base["dischtime"] - base["admittime"]).dt.total_seconds()/86400.0

base.to_pickle(f"{OUT}/_icu_base.pkl")

MICU = ["Medical Intensive Care Unit (MICU)"]
MICU_MIX = ["Medical Intensive Care Unit (MICU)", "Medical/Surgical Intensive Care Unit (MICU/SICU)"]
ERA = ["2014 - 2016", "2017 - 2019"]
eras_present = sorted(base["anchor_year_group"].unique())
print("anchor_year_group values:", eras_present, file=sys.stderr)

def norm_era(s):
    return s.replace(" ", "")

base["era"] = base["anchor_year_group"].map(norm_era)
ERA_N = [norm_era(e) for e in ERA]

def cohort(df, careunits=None, era=None, min_los=1.0, adult=True, first_only=None):
    m = pd.Series(True, index=df.index)
    if careunits is not None:
        m &= df["first_careunit"].isin(careunits)
    if era is not None:
        m &= df["era"].isin(era)
    if min_los is not None:
        m &= df["los"] >= min_los
    if adult:
        m &= df["age"] >= 18
    d = df[m]
    if first_only == "hadm":
        d = d[d["icu_seq_in_hadm"] == 1]
    elif first_only == "subject":
        d = d[d["icu_seq_in_subject"] == 1]
    return d

DEFS = {
    "C1_MICU_2014_2019":      dict(careunits=MICU,     era=ERA_N),
    "C2_MICU+MICUSICU_2014_2019": dict(careunits=MICU_MIX, era=ERA_N),
    "C3_allICU_allera":       dict(careunits=None,     era=None),
    "C1b_MICU_allera":        dict(careunits=MICU,     era=None),
    "C2b_MICU+MICUSICU_allera": dict(careunits=MICU_MIX, era=None),
}

def q(s, p):
    return float(s.quantile(p)) if len(s) else float("nan")

rows = []
for name, kw in DEFS.items():
    for scope, fo in [("all_stays", None), ("first_stay_per_hadm", "hadm"), ("first_stay_per_patient", "subject")]:
        d = cohort(base, **kw, first_only=fo)
        rows.append(dict(
            cohort=name, scope=scope,
            stays=len(d), hadm=d["hadm_id"].nunique(), patients=d["subject_id"].nunique(),
            mort_hosp_pct=round(100*d["hospital_expire_flag"].mean(), 2) if len(d) else None,
            mort_30d_pct=round(100*d["mort_30d"].mean(), 2) if len(d) else None,
            mort_1y_pct=round(100*d["mort_1y"].mean(), 2) if len(d) else None,
            age_median=round(q(d["age"], .5), 1), age_q1=round(q(d["age"], .25), 1), age_q3=round(q(d["age"], .75), 1),
            female_pct=round(100*(d["gender"] == "F").mean(), 2) if len(d) else None,
            icu_los_median=round(q(d["los"], .5), 2), icu_los_q1=round(q(d["los"], .25), 2), icu_los_q3=round(q(d["los"], .75), 2),
            hosp_los_median=round(q(d["los_hosp"], .5), 2),
            emergency_pct=round(100*d["admission_type"].str.contains("EMER|URGENT", case=False, na=False).mean(), 2) if len(d) else None,
        ))

summary = pd.DataFrame(rows)
summary.to_csv(f"{OUT}/cohort_candidates.csv", index=False, encoding="utf-8-sig")
print(summary.to_string(index=False))

# attrition table for C2 (the recommended one), step by step
steps = []
d = base.copy(); steps.append(("0. all ICU stays", len(d), d["subject_id"].nunique()))
d = d[d["age"] >= 18]; steps.append(("1. adult (age>=18)", len(d), d["subject_id"].nunique()))
d = d[d["los"] >= 1.0]; steps.append(("2. ICU LOS >= 1 day", len(d), d["subject_id"].nunique()))
d = d[d["first_careunit"].isin(MICU_MIX)]; steps.append(("3. first_careunit in {MICU, MICU/SICU}", len(d), d["subject_id"].nunique()))
d = d[d["era"].isin(ERA_N)]; steps.append(("4. anchor_year_group in 2014-2019", len(d), d["subject_id"].nunique()))
d = d[d["icu_seq_in_hadm"] == 1]; steps.append(("5. first ICU stay of the admission", len(d), d["subject_id"].nunique()))
att = pd.DataFrame(steps, columns=["step", "stays", "patients"])
att["kept_pct_of_prev"] = (att["stays"]/att["stays"].shift(1)*100).round(1)
att.to_csv(f"{OUT}/cohort_attrition_C2.csv", index=False, encoding="utf-8-sig")
print(); print(att.to_string(index=False))

# careunit x era cross-tab on adult+LOS>=1d
d = base[(base["age"] >= 18) & (base["los"] >= 1.0)]
ct = pd.crosstab(d["first_careunit"], d["era"])
ct["TOTAL"] = ct.sum(axis=1)
ct = ct.sort_values("TOTAL", ascending=False)
ct.to_csv(f"{OUT}/careunit_by_era.csv", encoding="utf-8-sig")
print(); print(ct.to_string())

# service mix for C2 final
final = cohort(base, careunits=MICU_MIX, era=ERA_N, first_only="hadm")
final[["subject_id","hadm_id","stay_id","intime","outtime","los","age","gender",
       "first_careunit","era","hospital_expire_flag","mort_30d","mort_1y"]].to_csv(
    f"{OUT}/cohort_C2_stays.csv", index=False, encoding="utf-8-sig")
print(f"\nC2 final stays written: {len(final)}")
