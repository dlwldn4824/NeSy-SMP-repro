"""Convert long-format dataset_gcs / events_* CSV → wide format expected by preprocess_eventlog."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

CONCEPT_MAP = {
    "HR": "Heart Rate",
    "RR": "Respiratory Rate",
    "TempC": "Temperature Celsius",
    "SBP": "Arterial Blood Pressure systolic",
    "DBP": "Arterial Blood Pressure diastolic",
    "MAP": "Arterial Blood Pressure mean",
    "Hemoglobin": "Hemoglobin",
    "Platelets": "Platelet Count",
    "Creatinine": "Creatinine (serum)",
    "Bilirubin": "Total Bilirubin",
    "Potassium": "Potassium (serum)",
    "Albumin": "Albumin",
    "CRP": "C-Reactive Protein",
    "Glucose": "Glucose",
    "Lactate": "Lactate",
    "Lymphocytes": "Lymphocytes",
    "Neutrophils": "Neutrophils",
    "WBC": "White Blood Cells",
    "ALT": "Alanine Aminotransferase (ALT)",
    "AST": "Asparate Aminotransferase (AST)",
    "GCS": "gcs",
}

NUMERIC_COLS = [
    "Heart Rate",
    "Respiratory Rate",
    "Temperature Celsius",
    "Hemoglobin",
    "Platelet Count",
    "Creatinine (serum)",
    "Total Bilirubin",
    "Potassium (serum)",
    "Albumin",
    "Arterial CO2 Pressure",
    "Arterial Blood Pressure systolic",
    "Arterial Blood Pressure diastolic",
    "Arterial Blood Pressure mean",
    "Daily Weight",
    "Brain Natiuretic Peptide (BNP)",
    "Direct Bilirubin",
    "C-Reactive Protein",
    "Creatinine (whole blood)",
    "Glucose",
    "Lactate",
    "Lymphocytes",
    "Neutrophils",
    "White Blood Cells",
    "Alanine Aminotransferase (ALT)",
    "Asparate Aminotransferase (AST)",
    "gcs",
    "anchor_age",
]

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


def long_to_wide(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df[df["concept:name"] != "Death"].copy()
    df["concept:name"] = df["concept:name"].map(lambda c: CONCEPT_MAP.get(c, c))
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"])

    # age is static on every row
    age = df.groupby("hadm_id")["age"].first() if "age" in df.columns else None

    # pivot numeric measurements
    keep_concepts = set(CONCEPT_MAP.values())
    meas = df[df["concept:name"].isin(keep_concepts)].copy()
    # one value per hadm/time/concept
    meas = meas.sort_values("time:timestamp")
    wide = meas.pivot_table(
        index=["hadm_id", "time:timestamp"],
        columns="concept:name",
        values="value",
        aggfunc="last",
    ).reset_index()

    # concept:name column = last observed concept at that timestamp (categorical event id)
    last_concept = (
        meas.groupby(["hadm_id", "time:timestamp"], as_index=False)
        .tail(1)[["hadm_id", "time:timestamp", "concept:name"]]
        .rename(columns={"concept:name": "event_concept"})
    )
    wide = wide.merge(last_concept, on=["hadm_id", "time:timestamp"], how="left")
    wide = wide.rename(columns={"event_concept": "concept:name"})

    # static fields
    static_cols = ["hospital_expire_flag", "admission_location"]
    static = df.groupby("hadm_id")[static_cols].first().reset_index()
    wide = wide.merge(static, on="hadm_id", how="left")
    if age is not None:
        wide["anchor_age"] = wide["hadm_id"].map(age)
    else:
        wide["anchor_age"] = 0.0

    # fill required columns
    for c in NUMERIC_COLS:
        if c not in wide.columns:
            wide[c] = np.nan
    for c in COMORBIDITIES:
        wide[c] = 0
    wide["admission_type"] = "unknown"
    wide["medication"] = "unknown"
    wide["subject_id"] = wide["hadm_id"].astype(str)
    wide["race"] = "unknown"
    wide["language"] = "unknown"
    wide["last_careunit"] = "unknown"
    wide["marital_status"] = "unknown"
    # ensure a known category exists for legacy print in preprocess
    if wide["concept:name"].isna().all():
        wide["concept:name"] = "Lactate"
    # inject one vasopressor label so legacy get_loc does not crash (optional)
    # (preprocess patched separately)

    wide = wide.sort_values(["hadm_id", "time:timestamp"])
    return wide


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    print(f"Loading {args.input}")
    df = pd.read_csv(args.input, low_memory=False)
    wide = long_to_wide(df)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    wide.to_csv(args.output, index=False)
    print(f"saved {args.output} rows={len(wide):,} hadm={wide['hadm_id'].nunique():,}")
    print("cols", len(wide.columns))


if __name__ == "__main__":
    main()
