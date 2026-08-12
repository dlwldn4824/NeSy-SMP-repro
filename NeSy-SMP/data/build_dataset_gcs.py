"""Build cohort + dataset_gcs_v1.csv from local MIMIC4-hosp-icu.db.

Resumable: intermediate CSVs under --out-dir/_cache.
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

import pandas as pd

CHART_ITEMS = {
    "HR": [220045],
    "SBP": [220050, 220179],
    "DBP": [220051, 220180],
    "MAP": [220052, 220181, 225312],
    "RR": [220210, 224690],
    "TempC": [223762],
    "TempF": [223761],
    "GCS_Eye": [220739],
    "GCS_Verbal": [223900],
    "GCS_Motor": [223901],
}
LAB_ITEMS = {
    "Lactate": [50813],
    "Creatinine": [50912],
    "Hemoglobin": [51222],
    "Platelets": [51265],
    "Bilirubin": [50885],
    "Potassium": [50971],
    "Albumin": [50862],
    "CRP": [50889],
    "Glucose": [50931, 50809],
    "WBC": [51301],
    "ALT": [50861],
    "AST": [50878],
    "Lymphocytes": [51244],
    "Neutrophils": [51256],
}


def connect_ro(db: Path, timeout: int = 600) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=timeout)


def load_or_query(conn_factory, path: Path, sql: str, desc: str) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        df = pd.read_csv(path)
        print(f"[SKIP] {desc}: {path.name} ({len(df):,} rows)")
        return df
    print(f"[RUN ] {desc} ...")
    t0 = time.time()
    conn = conn_factory()
    try:
        df = pd.read_sql(sql, conn)
    finally:
        conn.close()
    df.to_csv(path, index=False)
    print(f"[DONE] {desc}: {len(df):,} rows → {path} ({time.time() - t0:.0f}s)")
    return df


def build_cohort(db: Path, out_dir: Path, cache: Path) -> pd.DataFrame:
    cohort_path = out_dir / "cohort_sepsis_v1.csv"
    if cohort_path.exists() and cohort_path.stat().st_size > 0:
        cohort = pd.read_csv(cohort_path)
        print(f"[SKIP] cohort: {len(cohort):,} rows")
        return cohort

    factory = lambda: connect_ro(db)
    icu_one = load_or_query(
        factory,
        cache / "icu_one.csv",
        """
        WITH icu_ranked AS (
          SELECT subject_id, hadm_id, stay_id, intime, outtime, los,
                 COUNT(*) OVER (PARTITION BY hadm_id) AS n_icu
          FROM icustays
        )
        SELECT subject_id, hadm_id, stay_id, intime, outtime, los
        FROM icu_ranked
        WHERE n_icu = 1 AND los >= 1.0
        """,
        "ICU single-stay >=24h",
    )
    sepsis_hadm = load_or_query(
        factory,
        cache / "sepsis_hadm.csv",
        """
        SELECT DISTINCT hadm_id
        FROM diagnoses_icd
        WHERE
          (icd_version = 10 AND (
            icd_code LIKE 'A40%' OR icd_code LIKE 'A41%' OR icd_code LIKE 'R652%'
          ))
          OR (icd_version = 9 AND icd_code IN ('99591', '99592', '78552'))
        """,
        "sepsis ICD hadm_id",
    )
    patients_min = load_or_query(
        factory,
        cache / "patients_min.csv",
        "SELECT subject_id, gender, anchor_age FROM patients",
        "patients min",
    )
    admissions_min = load_or_query(
        factory,
        cache / "admissions_min.csv",
        """
        SELECT hadm_id, subject_id, admittime, dischtime, deathtime,
               admission_location, hospital_expire_flag
        FROM admissions
        """,
        "admissions min",
    )

    cohort = (
        icu_one.merge(sepsis_hadm, on="hadm_id", how="inner")
        .merge(patients_min, on="subject_id", how="inner")
        .merge(admissions_min.drop(columns=["subject_id"], errors="ignore"), on="hadm_id", how="inner")
    )
    cohort = cohort[cohort["anchor_age"] >= 18].copy()
    cohort = cohort.rename(
        columns={
            "anchor_age": "age",
            "intime": "icu_intime",
            "outtime": "icu_outtime",
            "los": "icu_los_days",
        }
    )
    keep = [
        "subject_id",
        "hadm_id",
        "stay_id",
        "gender",
        "age",
        "admittime",
        "dischtime",
        "deathtime",
        "admission_location",
        "hospital_expire_flag",
        "icu_intime",
        "icu_outtime",
        "icu_los_days",
    ]
    cohort = cohort[[c for c in keep if c in cohort.columns]]
    cohort.to_csv(cohort_path, index=False)
    mort = float(cohort["hospital_expire_flag"].mean()) if len(cohort) else float("nan")
    print(f"[DONE] cohort n={len(cohort):,} mortality={mort:.1%} → {cohort_path}")
    return cohort


def extract_batches(
    db: Path,
    cohort: pd.DataFrame,
    evt: Path,
    batch_size: int,
) -> None:
    chart_id_to_name = {i: n for n, ids in CHART_ITEMS.items() for i in ids}
    lab_id_to_name = {i: n for n, ids in LAB_ITEMS.items() for i in ids}
    all_chart_ids = sorted(chart_id_to_name)
    all_lab_ids = sorted(lab_id_to_name)
    stay_ids = cohort["stay_id"].astype(int).unique().tolist()
    hadm_ids = cohort["hadm_id"].astype(int).unique().tolist()

    chart_ids_csv = ",".join(map(str, all_chart_ids))
    n_chart = (len(stay_ids) + batch_size - 1) // batch_size
    print(f"chart batches: {n_chart}")
    for b in range(n_chart):
        out = evt / f"chart_batch_{b:04d}.csv"
        if out.exists() and out.stat().st_size > 0:
            print(f"[SKIP] {out.name}")
            continue
        batch = stay_ids[b * batch_size : (b + 1) * batch_size]
        ids = ",".join(map(str, batch))
        sql = f"""
          SELECT stay_id, subject_id, hadm_id, itemid, charttime, valuenum
          FROM chartevents
          WHERE stay_id IN ({ids})
            AND itemid IN ({chart_ids_csv})
            AND valuenum IS NOT NULL
        """
        t0 = time.time()
        conn = connect_ro(db)
        try:
            df = pd.read_sql(sql, conn)
        finally:
            conn.close()
        df.to_csv(out, index=False)
        print(f"[DONE] {out.name}: {len(df):,} rows ({time.time() - t0:.0f}s) [{b+1}/{n_chart}]")

    lab_ids_csv = ",".join(map(str, all_lab_ids))
    n_lab = (len(hadm_ids) + batch_size - 1) // batch_size
    print(f"lab batches: {n_lab}")
    for b in range(n_lab):
        out = evt / f"lab_batch_{b:04d}.csv"
        if out.exists() and out.stat().st_size > 0:
            print(f"[SKIP] {out.name}")
            continue
        batch = hadm_ids[b * batch_size : (b + 1) * batch_size]
        ids = ",".join(map(str, batch))
        sql = f"""
          SELECT subject_id, hadm_id, itemid, charttime, valuenum
          FROM labevents
          WHERE hadm_id IN ({ids})
            AND itemid IN ({lab_ids_csv})
            AND valuenum IS NOT NULL
        """
        t0 = time.time()
        conn = connect_ro(db)
        try:
            df = pd.read_sql(sql, conn)
        finally:
            conn.close()
        df.to_csv(out, index=False)
        print(f"[DONE] {out.name}: {len(df):,} rows ({time.time() - t0:.0f}s) [{b+1}/{n_lab}]")


def merge_events(cohort: pd.DataFrame, evt: Path, out_path: Path) -> pd.DataFrame:
    chart_id_to_name = {i: n for n, ids in CHART_ITEMS.items() for i in ids}
    lab_id_to_name = {i: n for n, ids in LAB_ITEMS.items() for i in ids}

    def load_batches(prefix: str) -> pd.DataFrame:
        files = sorted(evt.glob(f"{prefix}_batch_*.csv"))
        if not files:
            raise FileNotFoundError(f"no {prefix} batches in {evt}")
        return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)

    chart = load_batches("chart")
    lab = load_batches("lab")
    print(f"raw chart {len(chart):,} lab {len(lab):,}")

    chart["concept:name"] = chart["itemid"].map(chart_id_to_name)
    lab["concept:name"] = lab["itemid"].map(lab_id_to_name)

    mask_f = chart["concept:name"] == "TempF"
    chart.loc[mask_f, "valuenum"] = (chart.loc[mask_f, "valuenum"] - 32) * 5 / 9
    chart.loc[mask_f, "concept:name"] = "TempC"

    gcs_parts = chart[chart["concept:name"].isin(["GCS_Eye", "GCS_Verbal", "GCS_Motor"])].copy()
    if len(gcs_parts):
        gcs_parts["time_bin"] = pd.to_datetime(gcs_parts["charttime"]).dt.floor("h")
        gcs = (
            gcs_parts.pivot_table(
                index=["stay_id", "subject_id", "hadm_id", "time_bin"],
                columns="concept:name",
                values="valuenum",
                aggfunc="last",
            )
            .reset_index()
        )
        need = ["GCS_Eye", "GCS_Verbal", "GCS_Motor"]
        if all(c in gcs.columns for c in need):
            gcs["valuenum"] = gcs[need].sum(axis=1)
            gcs["concept:name"] = "GCS"
            gcs["charttime"] = gcs["time_bin"]
            gcs = gcs[["stay_id", "subject_id", "hadm_id", "charttime", "valuenum", "concept:name"]]
        else:
            gcs = pd.DataFrame()
    else:
        gcs = pd.DataFrame()

    chart = chart[~chart["concept:name"].isin(["GCS_Eye", "GCS_Verbal", "GCS_Motor", "TempF"])]
    lab = lab.merge(cohort[["hadm_id", "stay_id"]], on="hadm_id", how="inner")

    parts = [
        chart[["subject_id", "hadm_id", "stay_id", "charttime", "concept:name", "valuenum"]],
        lab[["subject_id", "hadm_id", "stay_id", "charttime", "concept:name", "valuenum"]],
    ]
    if len(gcs):
        parts.append(gcs[["subject_id", "hadm_id", "stay_id", "charttime", "concept:name", "valuenum"]])
    events = pd.concat(parts, ignore_index=True)

    events = events.merge(
        cohort[
            [
                "hadm_id",
                "hospital_expire_flag",
                "deathtime",
                "icu_intime",
                "icu_outtime",
                "age",
                "admission_location",
            ]
        ],
        on="hadm_id",
        how="left",
    )
    events = events.rename(columns={"charttime": "time:timestamp", "valuenum": "value"})
    events["time:timestamp"] = pd.to_datetime(events["time:timestamp"])
    events["icu_intime"] = pd.to_datetime(events["icu_intime"])
    events["icu_outtime"] = pd.to_datetime(events["icu_outtime"])
    events = events[
        (events["time:timestamp"] >= events["icu_intime"])
        & (events["time:timestamp"] <= events["icu_outtime"])
    ]

    dead = cohort[cohort["hospital_expire_flag"] == 1].copy()
    dead["deathtime"] = pd.to_datetime(dead["deathtime"])
    death_rows = dead.dropna(subset=["deathtime"])[
        ["subject_id", "hadm_id", "stay_id", "deathtime", "hospital_expire_flag", "age", "admission_location"]
    ].copy()
    death_rows["time:timestamp"] = death_rows["deathtime"]
    death_rows["concept:name"] = "Death"
    death_rows["value"] = 1.0
    events = pd.concat([events, death_rows[events.columns.intersection(death_rows.columns)]], ignore_index=True)
    events = events.sort_values(["hadm_id", "time:timestamp"])

    events.to_csv(out_path, index=False)
    print(f"[DONE] saved {out_path}")
    print(f"rows={len(events):,} hadm={events['hadm_id'].nunique():,}")
    print(events["concept:name"].value_counts().head(20).to_string())
    return events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--skip-extract", action="store_true", help="Only merge existing batches")
    parser.add_argument(
        "--cohort",
        type=Path,
        default=None,
        help="Optional prebuilt cohort CSV (e.g. cohort_sepsis3_paperlike.csv). Skips ICD build.",
    )
    parser.add_argument(
        "--dataset-name",
        type=str,
        default="dataset_gcs_v1.csv",
        help="Output dataset filename under --out-dir",
    )
    parser.add_argument(
        "--cache-name",
        type=str,
        default="_cache",
        help="Cache folder name under --out-dir (use separate cache per cohort)",
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise FileNotFoundError(args.db)

    out_dir = args.out_dir
    cache = out_dir / args.cache_name
    evt = cache / "events_batches"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    evt.mkdir(parents=True, exist_ok=True)

    dataset_path = out_dir / args.dataset_name
    if dataset_path.exists() and dataset_path.stat().st_size > 0:
        print(f"[SKIP] dataset already exists: {dataset_path} ({dataset_path.stat().st_size / 1e9:.2f} GB)")
        return

    if args.cohort is not None:
        if not args.cohort.exists():
            raise FileNotFoundError(args.cohort)
        cohort = pd.read_csv(args.cohort)
        print(f"[LOAD] cohort {args.cohort} n={len(cohort):,} mort={cohort['hospital_expire_flag'].mean():.1%}")
    else:
        cohort = build_cohort(args.db, out_dir, cache)
    if not args.skip_extract:
        extract_batches(args.db, cohort, evt, args.batch_size)
    merge_events(cohort, evt, dataset_path)


if __name__ == "__main__":
    main()
