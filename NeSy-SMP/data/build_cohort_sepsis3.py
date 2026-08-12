"""Build MIMIC-IV Sepsis-3??style cohort from local SQLite (no BigQuery).

Paper §5.1 / review protocol (approx. PhysioNet mimiciv_derived.sepsis3):
  - age >= 18
  - single ICU stay per admission, ICU LOS >= 24h
  - suspected infection: culture + antibiotic in the classic time windows
  - SOFA >= 2 around the suspected-infection time (simplified 6-component score)
  - sanity target: n ??19,328, mortality ??18%

Outputs:
  --out-dir/cohort_sepsis3.csv
  --out-dir/_cache_s3/*.csv intermediate tables (resumable)
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Common systemic antibiotics (substring match on prescriptions.drug)
ABX_PATTERNS = [
    "vancomycin",
    "ceftriaxone",
    "cefepime",
    "piperacillin",
    "zosyn",
    "meropenem",
    "imipenem",
    "ertapenem",
    "ciprofloxacin",
    "levofloxacin",
    "moxifloxacin",
    "azithromycin",
    "metronidazole",
    "linezolid",
    "daptomycin",
    "gentamicin",
    "tobramycin",
    "amikacin",
    "ampicillin",
    "amoxicillin",
    "nafcillin",
    "oxacillin",
    "cefazolin",
    "cefuroxime",
    "ceftazidime",
    "aztreonam",
    "clindamycin",
    "trimethoprim",
    "sulfamethoxazole",
    "bactrim",
    "fluconazole",
    "caspofungin",
    "micafungin",
    "amphotericin",
    "doxycycline",
    "tigecycline",
    "colistin",
    "polymyxin",
]

LAB_ITEMIDS = {
    "platelets": [51265],
    "bilirubin": [50885],
    "creatinine": [50912],
    "pao2": [50821],  # PO2 (Arterial)
}
CHART_ITEMIDS = {
    "gcs_eye": [220739],
    "gcs_verbal": [223900],
    "gcs_motor": [223901],
    "sbp": [220050, 220179],
    "map": [220052, 220181, 225312],
    "spo2": [220277],
    "fio2": [223835, 226754, 227010, 227009],
    "resp_rate": [220210, 224690],
}
# Vasopressors in inputevents (norepi, epi, dopa, dobutamine, vasopressin, phenylephrine)
VASO_ITEMIDS = [
    221906,  # Norepinephrine
    221289,  # Epinephrine
    221662,  # Dopamine
    221653,  # Dobutamine
    222315,  # Vasopressin
    221749,  # Phenylephrine
]


def connect_ro(db: Path, timeout: int = 600) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=timeout)


def load_or_query(factory, path: Path, sql: str, desc: str, params=None) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        df = pd.read_csv(path)
        print(f"[SKIP] {desc}: {path.name} ({len(df):,} rows)")
        return df
    print(f"[RUN ] {desc} ...")
    t0 = time.time()
    conn = factory()
    try:
        df = pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"[DONE] {desc}: {len(df):,} rows ({time.time() - t0:.0f}s)")
    return df


def sofa_resp(pao2: float | None, fio2: float | None, spo2: float | None) -> int:
    """Approximate respiratory SOFA. Prefer PaO2/FiO2; else SpO2/FiO2 proxy."""
    fio2_frac = None
    if fio2 is not None and not np.isnan(fio2):
        fio2_frac = fio2 / 100.0 if fio2 > 1.5 else fio2
        fio2_frac = max(fio2_frac, 0.21)
    if pao2 is not None and not np.isnan(pao2) and fio2_frac:
        pf = pao2 / fio2_frac
        if pf < 100:
            return 4
        if pf < 200:
            return 3
        if pf < 300:
            return 2
        if pf < 400:
            return 1
        return 0
    if spo2 is not None and not np.isnan(spo2) and fio2_frac:
        sf = spo2 / fio2_frac
        # Rough SF thresholds mapped to SOFA-like bins
        if sf < 89:
            return 4
        if sf < 148:
            return 3
        if sf < 221:
            return 2
        if sf < 302:
            return 1
        return 0
    return 0


def sofa_coag(plt: float | None) -> int:
    if plt is None or np.isnan(plt):
        return 0
    if plt < 20:
        return 4
    if plt < 50:
        return 3
    if plt < 100:
        return 2
    if plt < 150:
        return 1
    return 0


def sofa_liver(bili: float | None) -> int:
    if bili is None or np.isnan(bili):
        return 0
    if bili >= 12.0:
        return 4
    if bili >= 6.0:
        return 3
    if bili >= 2.0:
        return 2
    if bili >= 1.2:
        return 1
    return 0


def sofa_cns(gcs: float | None) -> int:
    if gcs is None or np.isnan(gcs):
        return 0
    if gcs < 6:
        return 4
    if gcs < 10:
        return 3
    if gcs < 13:
        return 2
    if gcs < 15:
        return 1
    return 0


def sofa_renal(crea: float | None) -> int:
    if crea is None or np.isnan(crea):
        return 0
    if crea >= 5.0:
        return 4
    if crea >= 3.5:
        return 3
    if crea >= 2.0:
        return 2
    if crea >= 1.2:
        return 1
    return 0


def sofa_cv(map_v: float | None, sbp: float | None, on_vaso: bool) -> int:
    if on_vaso:
        return 3  # simplified: any vaso ??at least 3
    m = map_v
    if (m is None or np.isnan(m)) and sbp is not None and not np.isnan(sbp):
        m = sbp * 0.7  # crude MAP proxy if only SBP
    if m is None or np.isnan(m):
        return 0
    if m < 70:
        return 1
    return 0


def build_base_icu(factory, cache: Path) -> pd.DataFrame:
    return load_or_query(
        factory,
        cache / "icu_one_adult.csv",
        """
        WITH icu_ranked AS (
          SELECT i.subject_id, i.hadm_id, i.stay_id, i.intime, i.outtime, i.los,
                 p.gender, p.anchor_age,
                 a.admittime, a.dischtime, a.deathtime, a.admission_location,
                 a.hospital_expire_flag,
                 COUNT(*) OVER (PARTITION BY i.hadm_id) AS n_icu
          FROM icustays i
          JOIN patients p ON i.subject_id = p.subject_id
          JOIN admissions a ON i.hadm_id = a.hadm_id
        )
        SELECT *
        FROM icu_ranked
        WHERE n_icu = 1 AND los >= 1.0 AND anchor_age >= 18
        """,
        "ICU single-stay >=24h age>=18",
    )


def build_cultures(factory, cache: Path, hadm_ids: list[int]) -> pd.DataFrame:
    path = cache / "cultures.csv"
    if path.exists() and path.stat().st_size > 0:
        return load_or_query(factory, path, "SELECT 1", "cultures (cached)")
    # Query all cultures with charttime; filter to cohort hadm in pandas (SQL IN list too large)
    df = load_or_query(
        factory,
        cache / "cultures_all.csv",
        """
        SELECT subject_id, hadm_id,
               COALESCE(charttime, chartdate) AS culture_time
        FROM microbiologyevents
        WHERE hadm_id IS NOT NULL
          AND (charttime IS NOT NULL OR chartdate IS NOT NULL)
        """,
        "all microbiology cultures",
    )
    df["culture_time"] = pd.to_datetime(df["culture_time"], errors="coerce")
    df = df.dropna(subset=["culture_time", "hadm_id"])
    hadm_set = set(hadm_ids)
    df = df[df["hadm_id"].isin(hadm_set)].copy()
    # earliest culture per hadm
    df = df.sort_values("culture_time").groupby("hadm_id", as_index=False).first()
    df.to_csv(path, index=False)
    print(f"[DONE] cultures (cohort): {len(df):,}")
    return df


def build_antibiotics(factory, cache: Path, hadm_ids: list[int]) -> pd.DataFrame:
    path = cache / "antibiotics.csv"
    if path.exists() and path.stat().st_size > 0:
        df = pd.read_csv(path)
        print(f"[SKIP] antibiotics: {path.name} ({len(df):,} rows)")
        return df
    # Pull prescriptions with likely abx via SQL OR of LIKEs (chunked patterns)
    like_clauses = " OR ".join([f"lower(drug) LIKE '%{p}%'" for p in ABX_PATTERNS])
    df = load_or_query(
        factory,
        cache / "antibiotics_all.csv",
        f"""
        SELECT subject_id, hadm_id, starttime AS abx_time, drug
        FROM prescriptions
        WHERE hadm_id IS NOT NULL AND starttime IS NOT NULL
          AND ({like_clauses})
        """,
        "antibiotic prescriptions",
    )
    df["abx_time"] = pd.to_datetime(df["abx_time"], errors="coerce")
    df = df.dropna(subset=["abx_time", "hadm_id"])
    hadm_set = set(hadm_ids)
    df = df[df["hadm_id"].isin(hadm_set)].copy()
    df = df.sort_values("abx_time").groupby("hadm_id", as_index=False).first()
    df.to_csv(path, index=False)
    print(f"[DONE] antibiotics (cohort): {len(df):,}")
    return df


def suspected_infection(cultures: pd.DataFrame, abx: pd.DataFrame) -> pd.DataFrame:
    """Classic windows: culture then abx<=72h, or abx then culture<=24h."""
    m = cultures.merge(abx[["hadm_id", "abx_time"]], on="hadm_id", how="inner")
    delta_h = (m["abx_time"] - m["culture_time"]).dt.total_seconds() / 3600.0
    # culture first: abx within 72h after culture (delta in [0,72])
    # abx first: culture within 24h after abx (delta in [-24,0])
    ok = ((delta_h >= 0) & (delta_h <= 72)) | ((delta_h < 0) & (delta_h >= -24))
    m = m.loc[ok].copy()
    # suspected infection time = earlier of culture/abx (onset proxy)
    m["suspected_infection_time"] = m[["culture_time", "abx_time"]].min(axis=1)
    return m[["hadm_id", "subject_id", "culture_time", "abx_time", "suspected_infection_time"]]


def fetch_labs_for_stays(
    factory, cache: Path, stays: pd.DataFrame, window_hours: float = 48.0
) -> pd.DataFrame:
    path = cache / "sofa_labs.csv"
    if path.exists() and path.stat().st_size > 0:
        df = pd.read_csv(path)
        print(f"[SKIP] sofa labs: {len(df):,}")
        return df
    itemids = sorted({i for ids in LAB_ITEMIDS.values() for i in ids})
    id_list = ",".join(str(i) for i in itemids)
    raw = load_or_query(
        factory,
        cache / "sofa_labs_raw.csv",
        f"""
        SELECT hadm_id, itemid, charttime, valuenum
        FROM labevents
        WHERE valuenum IS NOT NULL AND itemid IN ({id_list})
        """,
        "SOFA labevents (all matching itemids)",
    )
    raw["charttime"] = pd.to_datetime(raw["charttime"], errors="coerce")
    stays = stays.copy()
    stays["suspected_infection_time"] = pd.to_datetime(stays["suspected_infection_time"])
    stays["win_start"] = stays["suspected_infection_time"] - pd.Timedelta(hours=24)
    stays["win_end"] = stays["suspected_infection_time"] + pd.Timedelta(hours=window_hours)
    raw = raw.merge(
        stays[["hadm_id", "win_start", "win_end"]], on="hadm_id", how="inner"
    )
    raw = raw[
        (raw["charttime"] >= raw["win_start"]) & (raw["charttime"] <= raw["win_end"])
    ]
    raw.to_csv(path, index=False)
    print(f"[DONE] sofa labs windowed: {len(raw):,}")
    return raw


def fetch_charts_for_stays(
    factory, cache: Path, stays: pd.DataFrame, window_hours: float = 48.0
) -> pd.DataFrame:
    path = cache / "sofa_charts.csv"
    if path.exists() and path.stat().st_size > 0:
        df = pd.read_csv(path)
        print(f"[SKIP] sofa charts: {len(df):,}")
        return df
    itemids = sorted({i for ids in CHART_ITEMIDS.values() for i in ids})
    id_list = ",".join(str(i) for i in itemids)
    # chartevents is huge ??filter by stay_id list in batches
    stay_ids = stays["stay_id"].astype(int).unique().tolist()
    parts = []
    batch = 800
    conn = factory()
    try:
        for i in range(0, len(stay_ids), batch):
            chunk = stay_ids[i : i + batch]
            ids = ",".join(str(s) for s in chunk)
            t0 = time.time()
            q = f"""
            SELECT stay_id, itemid, charttime, valuenum
            FROM chartevents
            WHERE valuenum IS NOT NULL
              AND itemid IN ({id_list})
              AND stay_id IN ({ids})
            """
            part = pd.read_sql(q, conn)
            parts.append(part)
            print(
                f"  chart batch {i // batch + 1}/{(len(stay_ids) + batch - 1) // batch} "
                f"rows={len(part):,} ({time.time() - t0:.0f}s)"
            )
    finally:
        conn.close()
    raw = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    raw["charttime"] = pd.to_datetime(raw["charttime"], errors="coerce")
    stays = stays.copy()
    stays["suspected_infection_time"] = pd.to_datetime(stays["suspected_infection_time"])
    stays["win_start"] = stays["suspected_infection_time"] - pd.Timedelta(hours=24)
    stays["win_end"] = stays["suspected_infection_time"] + pd.Timedelta(hours=window_hours)
    raw = raw.merge(
        stays[["stay_id", "hadm_id", "win_start", "win_end"]], on="stay_id", how="inner"
    )
    raw = raw[
        (raw["charttime"] >= raw["win_start"]) & (raw["charttime"] <= raw["win_end"])
    ]
    raw.to_csv(path, index=False)
    print(f"[DONE] sofa charts windowed: {len(raw):,}")
    return raw


def fetch_vaso(factory, cache: Path, stays: pd.DataFrame) -> pd.DataFrame:
    path = cache / "vaso_flags.csv"
    if path.exists() and path.stat().st_size > 0:
        df = pd.read_csv(path)
        print(f"[SKIP] vaso: {len(df):,}")
        return df
    ids = ",".join(str(i) for i in VASO_ITEMIDS)
    stay_ids = stays["stay_id"].astype(int).unique().tolist()
    parts = []
    batch = 1000
    conn = factory()
    try:
        for i in range(0, len(stay_ids), batch):
            chunk = stay_ids[i : i + batch]
            sid = ",".join(str(s) for s in chunk)
            q = f"""
            SELECT DISTINCT stay_id
            FROM inputevents
            WHERE itemid IN ({ids}) AND stay_id IN ({sid})
            """
            parts.append(pd.read_sql(q, conn))
    finally:
        conn.close()
    vaso = pd.concat(parts, ignore_index=True).drop_duplicates() if parts else pd.DataFrame(columns=["stay_id"])
    vaso["on_vaso"] = 1
    vaso.to_csv(path, index=False)
    print(f"[DONE] vaso stays: {len(vaso):,}")
    return vaso


def worst(series: pd.Series, how: str) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return float("nan")
    return float(s.min() if how == "min" else s.max())


def compute_sofa(
    stays: pd.DataFrame, labs: pd.DataFrame, charts: pd.DataFrame, vaso: pd.DataFrame
) -> pd.DataFrame:
    lab_map = {}
    for name, ids in LAB_ITEMIDS.items():
        lab_map.update({i: name for i in ids})
    chart_map = {}
    for name, ids in CHART_ITEMIDS.items():
        chart_map.update({i: name for i in ids})

    if len(labs):
        labs = labs.copy()
        labs["feat"] = labs["itemid"].map(lab_map)
    if len(charts):
        charts = charts.copy()
        charts["feat"] = charts["itemid"].map(chart_map)

    vaso_set = set(vaso["stay_id"].astype(int)) if len(vaso) else set()
    rows = []
    for _, st in stays.iterrows():
        hid = int(st["hadm_id"])
        sid = int(st["stay_id"])
        lab_g = labs[labs["hadm_id"] == hid] if len(labs) else labs
        ch_g = charts[charts["stay_id"] == sid] if len(charts) else charts

        plt = worst(lab_g.loc[lab_g["feat"] == "platelets", "valuenum"], "min") if len(lab_g) else float("nan")
        bili = worst(lab_g.loc[lab_g["feat"] == "bilirubin", "valuenum"], "max") if len(lab_g) else float("nan")
        crea = worst(lab_g.loc[lab_g["feat"] == "creatinine", "valuenum"], "max") if len(lab_g) else float("nan")
        pao2 = worst(lab_g.loc[lab_g["feat"] == "pao2", "valuenum"], "min") if len(lab_g) else float("nan")

        if len(ch_g):
            eye = worst(ch_g.loc[ch_g["feat"] == "gcs_eye", "valuenum"], "min")
            ver = worst(ch_g.loc[ch_g["feat"] == "gcs_verbal", "valuenum"], "min")
            mot = worst(ch_g.loc[ch_g["feat"] == "gcs_motor", "valuenum"], "min")
            gcs = eye + ver + mot if not any(np.isnan(x) for x in [eye, ver, mot]) else float("nan")
            map_v = worst(ch_g.loc[ch_g["feat"] == "map", "valuenum"], "min")
            sbp = worst(ch_g.loc[ch_g["feat"] == "sbp", "valuenum"], "min")
            spo2 = worst(ch_g.loc[ch_g["feat"] == "spo2", "valuenum"], "min")
            fio2 = worst(ch_g.loc[ch_g["feat"] == "fio2", "valuenum"], "max")
        else:
            gcs = map_v = sbp = spo2 = fio2 = float("nan")

        on_vaso = sid in vaso_set
        scores = {
            "sofa_resp": sofa_resp(pao2, fio2, spo2),
            "sofa_coag": sofa_coag(plt),
            "sofa_liver": sofa_liver(bili),
            "sofa_cns": sofa_cns(gcs),
            "sofa_renal": sofa_renal(crea),
            "sofa_cv": sofa_cv(map_v, sbp, on_vaso),
        }
        total = int(sum(scores.values()))
        rows.append({"hadm_id": hid, "stay_id": sid, "sofa": total, **scores})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--sofa-min", type=int, default=2)
    args = ap.parse_args()

    out = args.out_dir
    cache = out / "_cache_s3"
    out.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    factory = lambda: connect_ro(args.db)

    cohort_path = out / "cohort_sepsis3.csv"
    if cohort_path.exists() and cohort_path.stat().st_size > 0:
        c = pd.read_csv(cohort_path)
        mort = float(c["hospital_expire_flag"].mean())
        print(f"[SKIP] existing cohort n={len(c):,} mort={mort:.1%} ??{cohort_path}")
        return

    base = build_base_icu(factory, cache)
    print(f"base ICU adult single-stay: {len(base):,} mort={base['hospital_expire_flag'].mean():.1%}")

    cultures = build_cultures(factory, cache, base["hadm_id"].astype(int).tolist())
    abx = build_antibiotics(factory, cache, base["hadm_id"].astype(int).tolist())
    soi = suspected_infection(cultures, abx)
    print(f"suspected infection (culture+abx windows): {len(soi):,}")

    stays = base.merge(soi, on=["hadm_id", "subject_id"], how="inner")
    print(f"ICU ??suspected infection: {len(stays):,}")

    labs = fetch_labs_for_stays(factory, cache, stays)
    charts = fetch_charts_for_stays(factory, cache, stays)
    vaso = fetch_vaso(factory, cache, stays)

    sofa_path = cache / "sofa_scores.csv"
    if sofa_path.exists() and sofa_path.stat().st_size > 0:
        sofa = pd.read_csv(sofa_path)
        print(f"[SKIP] sofa scores: {len(sofa):,}")
    else:
        print("[RUN ] computing SOFA ...")
        t0 = time.time()
        sofa = compute_sofa(stays, labs, charts, vaso)
        sofa.to_csv(sofa_path, index=False)
        print(f"[DONE] sofa scores: {len(sofa):,} ({time.time() - t0:.0f}s)")

    cohort = stays.merge(sofa[["hadm_id", "sofa"]], on="hadm_id", how="left")
    cohort["sofa"] = cohort["sofa"].fillna(0).astype(int)
    before = len(cohort)
    cohort = cohort[cohort["sofa"] >= args.sofa_min].copy()
    print(f"SOFA>={args.sofa_min}: {len(cohort):,} / {before:,}")

    cohort = cohort.rename(columns={"anchor_age": "age", "intime": "icu_intime", "outtime": "icu_outtime", "los": "icu_los_days"})
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
        "suspected_infection_time",
        "sofa",
    ]
    cohort = cohort[[c for c in keep if c in cohort.columns]]
    cohort.to_csv(cohort_path, index=False)
    mort = float(cohort["hospital_expire_flag"].mean()) if len(cohort) else float("nan")
    print(f"[DONE] cohort_sepsis3 n={len(cohort):,} mortality={mort:.1%} -> {cohort_path}")
    print("Paper sanity: n~19,328 / mort~18%")


if __name__ == "__main__":
    main()
