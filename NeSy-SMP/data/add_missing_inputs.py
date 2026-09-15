"""재현 입력 wide CSV 에서 비어 있던 입력을 MIMIC-IV 에서 채운다 (최대 근접 arm 용).

원본 preprocess_eventlog 가 쓰는 변수 중 우리 build_dataset_gcs.py 가 추출하지 않아 전부 0 이던 것:
  Arterial CO2 Pressure       labevents 50818  pCO2 (Blood Gas — 동맥/정맥 구분 없음)
  Direct Bilirubin            labevents 50883
  Brain Natiuretic Peptide    labevents 50963  NTproBNP (원본이 BNP 인지 NT-proBNP 인지 불명)
  Creatinine (whole blood)    labevents 52024
  Daily Weight                chartevents 224639
  admission_type              admissions.admission_type (전부 'unknown' 이었음)

넣는 방법 (add_medication_events.py 와 같은 원칙)
- 각 입원의 기존 관찰 창 [첫 행 시각, 마지막 행 시각] 안의 측정만 쓴다 — 창 끝 이후 정보 없음.
- 같은 입원·같은 시각의 행이 이미 있으면 그 행의 해당 열에 값을 넣고(long_to_wide 가 시각별로 한 행으로 합치는 것과 같게),
  없으면 concept:name = 그 변수 이름인 새 행을 만든다. 정적 열은 그 입원의 기존 행에서 복사.

DB 에 인덱스가 없어 표마다 전체 스캔 1회 (DB 파일은 건드리지 않음).
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

import pandas as pd

LAB = {50818: "Arterial CO2 Pressure", 50883: "Direct Bilirubin", 50963: "Brain Natiuretic Peptide (BNP)",
       52024: "Creatinine (whole blood)"}
CHART = {224639: "Daily Weight"}


def ro(db):
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wide", type=Path, required=True)
    ap.add_argument("--cohort", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None, help="추출 결과 캐시 CSV (있으면 DB 스캔 생략)")
    args = ap.parse_args()
    t0 = time.time()

    wide = pd.read_csv(args.wide, low_memory=False)
    wide["time:timestamp"] = pd.to_datetime(wide["time:timestamp"])
    win = wide.groupby("hadm_id")["time:timestamp"].agg(ws="min", we="max")
    co = pd.read_csv(args.cohort, usecols=["hadm_id", "stay_id"]).drop_duplicates("hadm_id")
    co = co[co.hadm_id.isin(win.index)]
    print(f"wide rows={len(wide):,} hadm={len(win):,}", flush=True)

    if args.cache and args.cache.exists():
        ev = pd.read_csv(args.cache, parse_dates=["time:timestamp"])
        print(f"cache {args.cache} rows={len(ev):,}")
    else:
        con = ro(args.db)
        lab = pd.read_sql(f"SELECT hadm_id, itemid, charttime, valuenum FROM labevents "
                          f"WHERE itemid IN ({','.join(map(str, LAB))}) AND valuenum IS NOT NULL", con)
        print(f"labevents scan {time.time() - t0:.0f}s rows={len(lab):,}", flush=True)
        lab = lab[lab.hadm_id.isin(win.index)]
        lab["concept:name"] = lab.itemid.map(LAB)
        ch = pd.read_sql(f"SELECT stay_id, itemid, charttime, valuenum FROM chartevents "
                         f"WHERE itemid IN ({','.join(map(str, CHART))}) AND valuenum IS NOT NULL", con)
        print(f"chartevents scan {time.time() - t0:.0f}s rows={len(ch):,}", flush=True)
        ch = ch.merge(co, on="stay_id")
        ch["concept:name"] = ch.itemid.map(CHART)
        ev = pd.concat([lab[["hadm_id", "charttime", "concept:name", "valuenum"]],
                        ch[["hadm_id", "charttime", "concept:name", "valuenum"]]], ignore_index=True)
        ev = ev.rename(columns={"charttime": "time:timestamp", "valuenum": "value"})
        ev["time:timestamp"] = pd.to_datetime(ev["time:timestamp"])
        if args.cache:
            ev.to_csv(args.cache, index=False)
    adm = pd.read_sql("SELECT hadm_id, admission_type FROM admissions", ro(args.db))

    ev = ev.merge(win, left_on="hadm_id", right_index=True)
    ev = ev[(ev["time:timestamp"] >= ev.ws) & (ev["time:timestamp"] <= ev.we)]
    ev = ev.sort_values("time:timestamp", kind="mergesort").drop_duplicates(
        ["hadm_id", "time:timestamp", "concept:name"], keep="last")
    print("in-window measurements:", ev["concept:name"].value_counts().to_dict())
    cover = ev.groupby("concept:name").hadm_id.nunique() / len(win)
    print("hadm coverage:", {k: f"{v:.1%}" for k, v in cover.items()})

    # 같은 시각 행이 있으면 그 행에 값, 없으면 새 행
    piv = ev.pivot_table(index=["hadm_id", "time:timestamp"], columns="concept:name", values="value", aggfunc="last")
    key = wide.set_index(["hadm_id", "time:timestamp"]).index
    hit = piv.index.isin(key)
    wide = wide.set_index(["hadm_id", "time:timestamp"])
    for c in piv.columns:
        vals = piv.loc[hit, c].dropna()
        wide.loc[vals.index, c] = vals.values
    wide = wide.reset_index()
    print(f"merged into existing rows: {hit.sum():,} timestamps", flush=True)

    new_ev = ev.set_index(["hadm_id", "time:timestamp"]).loc[~ev.set_index(["hadm_id", "time:timestamp"]).index.isin(key)]
    new_ev = new_ev.reset_index()
    new = new_ev.pivot_table(index=["hadm_id", "time:timestamp"], columns="concept:name", values="value",
                             aggfunc="last").reset_index()
    last_c = new_ev.groupby(["hadm_id", "time:timestamp"])["concept:name"].last().rename("concept:name").reset_index()
    new = new.merge(last_c, on=["hadm_id", "time:timestamp"])
    numeric = [c for c in wide.columns if pd.api.types.is_float_dtype(wide[c]) and c != "anchor_age"]
    static = [c for c in wide.columns if c not in numeric + ["time:timestamp", "concept:name", "hadm_id"]]
    new = new.join(wide.drop_duplicates("hadm_id").set_index("hadm_id")[static], on="hadm_id")
    for c in wide.columns:
        if c not in new.columns:
            new[c] = float("nan")
    new = new[wide.columns]
    wide["_src"], new["_src"] = 0, 1
    out = pd.concat([wide, new], ignore_index=True)
    out = out.sort_values(["hadm_id", "time:timestamp", "_src"], kind="mergesort").drop(columns="_src")

    out = out.drop(columns="admission_type").merge(adm, on="hadm_id", how="left")
    out["admission_type"] = out["admission_type"].fillna("unknown")
    out["hadm_id"] = out["hadm_id"].astype("int64")   # set_index/reset_index 를 거치며 float 이 된다
    print("admission_type:", out.drop_duplicates("hadm_id").admission_type.value_counts().to_dict())
    per = out.groupby("hadm_id").size()
    print(f"new rows {len(new):,} | rows/hadm median {per.median():.0f} p99 {per.quantile(.99):.0f} max {per.max()}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    print(f"saved {args.output} rows={len(out):,} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
