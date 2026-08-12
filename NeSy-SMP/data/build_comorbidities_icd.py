"""Build comorbidities one-hot from MIMIC diagnoses_icd (ICD proxy).

Paper uses notes NLP (spaCy/medspaCy). Local hosp-icu DB has no note tables and
notes zip is not present, so we map ICD-9/10 codes (+ diagnosis titles) onto the
same 23 comorbidity labels expected by preprocessing.py / models.py.

Output long format compatible with upstream extract_comorbidities.py:
  subject_id,hadm_id,age,comorbidity
and a wide one-hot CSV for easy merge into events_*_wide CSV.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

import pandas as pd

COMORBIDITIES = [
    "acute kidney injury",
    "aids",
    "atrial fibrillation",
    "cad",
    "cancer",
    "cerebrovascular accident",
    "cirrhosis",
    "copd",
    "dementia",
    "diabetes",
    "diabetes mellitus",
    "heart failure",
    "hiv",
    "hypertension",
    "kidney disease",
    "kidney failure",
    "leukemia",
    "lymphoma",
    "metastatic cancer",
    "metastatic disease",
    "peptic ulcer disease",
    "pneumonia",
    "trauma",
]

# (label, icd10 prefixes, icd9 prefixes/codes, title keywords)
RULES: list[tuple[str, list[str], list[str], list[str]]] = [
    ("acute kidney injury", ["N17"], ["584"], ["acute kidney injury", "acute renal failure"]),
    ("kidney failure", ["N18", "N19"], ["585", "586"], ["chronic kidney", "end stage renal", "renal failure"]),
    ("kidney disease", ["N18", "N19", "N28"], ["585", "586", "593"], ["kidney disease", "renal disease", "ckd"]),
    ("aids", ["B20"], ["042"], ["aids", "acquired immune deficiency"]),
    ("hiv", ["B20", "Z21", "B97.35"], ["042", "V08"], ["human immunodeficiency", "hiv"]),
    ("atrial fibrillation", ["I48"], ["4273"], ["atrial fibrillation", "atrial flutter"]),
    ("cad", ["I20", "I21", "I22", "I23", "I24", "I25"], ["410", "411", "412", "413", "414"], ["coronary", "atherosclerotic heart", "cad"]),
    ("heart failure", ["I50"], ["428"], ["heart failure", "congestive heart"]),
    ("hypertension", ["I10", "I11", "I12", "I13", "I15", "I16"], ["401", "402", "403", "404", "405"], ["hypertension", "hypertensive"]),
    ("cirrhosis", ["K74", "K70.3"], ["5712", "5715", "5716"], ["cirrhosis"]),
    ("copd", ["J44"], ["491", "492", "496"], ["copd", "chronic obstructive"]),
    ("dementia", ["F01", "F02", "F03", "G30"], ["290", "2941", "3310"], ["dementia", "alzheimer"]),
    ("diabetes mellitus", ["E10", "E11", "E13"], ["250"], ["diabetes mellitus"]),
    ("diabetes", ["E10", "E11", "E13"], ["250"], ["diabetes"]),
    ("cerebrovascular accident", ["I60", "I61", "I62", "I63", "I64", "I65", "I66", "I67", "I69"], ["430", "431", "432", "433", "434", "435", "436", "437", "438"], ["stroke", "cerebrovascular", "cerebral infarction", "cva"]),
    ("peptic ulcer disease", ["K25", "K26", "K27", "K28"], ["531", "532", "533", "534"], ["peptic ulcer", "gastric ulcer", "duodenal ulcer"]),
    ("pneumonia", ["J12", "J13", "J14", "J15", "J16", "J17", "J18"], ["480", "481", "482", "483", "484", "485", "486"], ["pneumonia"]),
    ("leukemia", ["C91", "C92", "C93", "C94", "C95"], ["204", "205", "206", "207", "208"], ["leukemia"]),
    ("lymphoma", ["C81", "C82", "C83", "C84", "C85", "C86"], ["200", "201", "202"], ["lymphoma"]),
    ("metastatic cancer", ["C77", "C78", "C79"], ["196", "197", "198"], ["secondary malignant", "metastasis", "metastatic"]),
    ("metastatic disease", ["C77", "C78", "C79"], ["196", "197", "198"], ["secondary malignant", "metastasis", "metastatic"]),
    ("cancer", ["C"], ["14", "15", "16", "17", "18", "19", "20", "21"], ["malignant neoplasm", "cancer", "carcinoma"]),
    # trauma: injury chapter only (no bare "fracture" — that hits osteoporosis M81 etc.)
    ("trauma", [], [], ["traumatic injury", "multiple trauma", "traumatic fracture"]),
]


def connect_ro(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=600)


def norm_code(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(code)).upper()


def is_trauma_code(icd_version: int, code: str) -> bool:
    """Acute injury codes only; exclude late effects / personal history / pathologic fx."""
    c = norm_code(code)
    if int(icd_version) == 9:
        if not c.isdigit() or len(c) < 3:
            return False
        stem = int(c[:3])
        # ICD-9 injury 800-904 (exclude 905-909 late effects, 910-959 often superficial/toxic)
        return 800 <= stem <= 904
    # ICD-10: S00-S99, T07, T14, T79; exclude Z87 history, M80 pathologic fracture
    if c.startswith("Z87") or c.startswith("M80") or c.startswith("M81"):
        return False
    if c.startswith("S") and len(c) >= 3:
        try:
            return 0 <= int(c[1:3]) <= 99
        except ValueError:
            return False
    return c.startswith(("T07", "T14", "T79"))


def match_label(icd_version: int, code: str, title: str) -> set[str]:
    c = norm_code(code)
    t = (title or "").lower()
    hit: set[str] = set()

    if is_trauma_code(int(icd_version), code):
        hit.add("trauma")
    # title keywords alone for trauma (avoid bare "fracture")
    if any(k in t for k in ["traumatic injury", "multiple trauma", "traumatic fracture"]):
        if "pathologic" not in t and "osteoporosis" not in t:
            hit.add("trauma")

    for label, p10, p9, kws in RULES:
        if label == "trauma":
            continue
        if any(k in t for k in kws):
            hit.add(label)
            continue
        prefs = p10 if int(icd_version) == 10 else p9
        for p in prefs:
            pn = norm_code(p)
            if c.startswith(pn):
                # avoid overly broad cancer 'C' catching everything: require C00-C97-ish
                if label == "cancer" and int(icd_version) == 10:
                    if c.startswith("C") and len(c) >= 3:
                        try:
                            num = int(c[1:3])
                        except ValueError:
                            continue
                        if 0 <= num <= 96 and not c.startswith(("C77", "C78", "C79")):
                            hit.add(label)
                else:
                    hit.add(label)
                break
    return hit


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--cohort", type=Path, required=True, help="cohort CSV with hadm_id,subject_id,age")
    ap.add_argument("--out-long", type=Path, required=True)
    ap.add_argument("--out-wide", type=Path, required=True)
    args = ap.parse_args()

    cohort = pd.read_csv(args.cohort)
    hadm = set(cohort["hadm_id"].astype(int))
    print(f"cohort hadm={len(hadm):,}")

    con = connect_ro(args.db)
    try:
        dx = pd.read_sql(
            """
            SELECT d.subject_id, d.hadm_id, d.icd_code, d.icd_version,
                   COALESCE(t.long_title, '') AS long_title
            FROM diagnoses_icd d
            LEFT JOIN d_icd_diagnoses t
              ON d.icd_code = t.icd_code AND d.icd_version = t.icd_version
            """,
            con,
        )
    finally:
        con.close()

    dx["hadm_id"] = dx["hadm_id"].astype(int)
    dx = dx[dx["hadm_id"].isin(hadm)].copy()
    print(f"diagnoses rows in cohort: {len(dx):,}")

    rows = []
    for _, r in dx.iterrows():
        labels = match_label(int(r["icd_version"]), r["icd_code"], r["long_title"])
        for lab in labels:
            rows.append(
                {
                    "subject_id": int(r["subject_id"]),
                    "hadm_id": int(r["hadm_id"]),
                    "comorbidity": lab,
                }
            )
    long_df = pd.DataFrame(rows).drop_duplicates()
    # attach age from cohort
    age_col = "age" if "age" in cohort.columns else "anchor_age"
    long_df = long_df.merge(
        cohort[["hadm_id", "subject_id", age_col]].rename(columns={age_col: "age"}),
        on=["hadm_id", "subject_id"],
        how="left",
    )
    args.out_long.parent.mkdir(parents=True, exist_ok=True)
    long_df[["subject_id", "hadm_id", "age", "comorbidity"]].to_csv(args.out_long, index=False)
    print(f"wrote long {args.out_long} rows={len(long_df):,} hadm={long_df['hadm_id'].nunique():,}")

    # wide one-hot for all cohort hadm
    wide = cohort[["subject_id", "hadm_id"]].drop_duplicates().copy()
    for c in COMORBIDITIES:
        wide[c] = 0
    if len(long_df):
        for hadm_id, g in long_df.groupby("hadm_id"):
            labs = set(g["comorbidity"])
            idx = wide.index[wide["hadm_id"] == hadm_id]
            for lab in labs:
                if lab in COMORBIDITIES:
                    wide.loc[idx, lab] = 1
    args.out_wide.parent.mkdir(parents=True, exist_ok=True)
    wide.to_csv(args.out_wide, index=False)
    rates = {c: float(wide[c].mean()) for c in COMORBIDITIES}
    top = sorted(rates.items(), key=lambda x: -x[1])[:8]
    print(f"wrote wide {args.out_wide} n={len(wide):,}")
    print("top prevalence:", ", ".join(f"{k}={v:.1%}" for k, v in top))
    print(f"any comorbidity: {(wide[COMORBIDITIES].sum(axis=1) > 0).mean():.1%}")


if __name__ == "__main__":
    main()
