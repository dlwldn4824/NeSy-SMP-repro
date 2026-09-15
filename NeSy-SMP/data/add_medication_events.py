"""재현 입력 wide CSV 에 ICU 약물 투여 이벤트를 넣는다 (약물 arm).

원본 preprocess_eventlog 는 `concept:name` 에 'Administration of vasopressor' 같은 투여 이벤트가 있고
`medication` 열에 약 이름이 있다고 전제한다. 우리 build_dataset_gcs.py 는 chartevents·labevents 만 읽어
약물이 입력에 전혀 없었다(long_to_wide.py 가 medication='unknown').

넣는 방법
- inputevents 에서 아래 약물만. 각 입원의 기존 관찰 창 [첫 이벤트 시각, 마지막 이벤트 시각] 과 겹치는 투여를
  시각 max(starttime, 창 시작) 의 이벤트 1행으로 넣는다 (창 시작 전에 시작해 창 안까지 이어진 주입도 포함).
  창 끝 이후 정보는 쓰지 않는다 — 이벤트 시각 ≤ 창 끝.
- concept:name = 'Administration of {vasopressor|inotrope|sedative|opioid}', medication = d_items 라벨.
- 수치 열은 비워 둔다(전처리가 입원 안에서 앞 값으로 채움). 정적 열은 그 입원의 기존 행에서 복사.

사용:
  python data/add_medication_events.py --wide C:/data/mimic-iv-derived/events_6h_wide_s3_como.csv \
      --cohort C:/data/mimic-iv-derived/cohort_sepsis3_paperlike.csv \
      --db C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db \
      --output C:/data/mimic-iv-derived/events_6h_wide_s3_como_med.csv
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

DRUGS = {
    "vasopressor": [221906, 221289, 222315, 221749, 221662],  # norepi, epi, vasopressin, phenylephrine, dopamine
    "inotrope": [221653, 221986],                             # dobutamine, milrinone
    "sedative": [222168, 221668, 225150, 229420, 221385, 221712],  # propofol, midazolam, dexmed×2, lorazepam, ketamine
    "opioid": [221744, 225942, 225154, 221833],              # fentanyl×2, morphine, hydromorphone
}
NUMERIC_KEEP_EMPTY = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wide", type=Path, required=True)
    ap.add_argument("--cohort", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    wide = pd.read_csv(args.wide, low_memory=False)
    wide["time:timestamp"] = pd.to_datetime(wide["time:timestamp"])
    print(f"wide rows={len(wide):,} hadm={wide.hadm_id.nunique():,}")
    win = wide.groupby("hadm_id")["time:timestamp"].agg(ws="min", we="max")

    co = pd.read_csv(args.cohort, usecols=["hadm_id", "stay_id"]).drop_duplicates("hadm_id")
    co = co[co.hadm_id.isin(win.index)]
    item_cls = {i: c for c, ids in DRUGS.items() for i in ids}
    con = sqlite3.connect(args.db)
    labels = pd.read_sql(f"SELECT itemid, label FROM d_items WHERE itemid IN ({','.join(map(str, item_cls))})", con)
    parts = []
    stays = co.stay_id.tolist()
    for i in range(0, len(stays), 2000):
        sid = ",".join(map(str, stays[i:i + 2000]))
        parts.append(pd.read_sql(
            f"SELECT stay_id, itemid, starttime, endtime FROM inputevents "
            f"WHERE itemid IN ({','.join(map(str, item_cls))}) AND stay_id IN ({sid})", con))
    ie = pd.concat(parts, ignore_index=True)
    print(f"inputevents rows (cohort, selected drugs)={len(ie):,}")

    ie = ie.merge(co, on="stay_id").merge(win, left_on="hadm_id", right_index=True)
    ie["starttime"], ie["endtime"] = pd.to_datetime(ie["starttime"]), pd.to_datetime(ie["endtime"])
    ie["endtime"] = ie["endtime"].fillna(ie["starttime"])
    ie = ie[(ie.starttime <= ie.we) & (ie.endtime >= ie.ws)].copy()
    ie["time:timestamp"] = ie[["starttime", "ws"]].max(axis=1)
    ie = ie.merge(labels, on="itemid")
    ie["concept:name"] = "Administration of " + ie.itemid.map(item_cls)
    ie["medication"] = ie["label"]
    ev = ie.drop_duplicates(["hadm_id", "time:timestamp", "concept:name", "medication"])[
        ["hadm_id", "time:timestamp", "concept:name", "medication"]]
    print(f"medication events in windows={len(ev):,} | hadm with any={ev.hadm_id.nunique():,} "
          f"({ev.hadm_id.nunique() / wide.hadm_id.nunique():.1%})")
    print(ev["concept:name"].value_counts().to_string())

    ID_COLS = ("hadm_id", "subject_id", "anchor_age", "hospital_expire_flag")
    wide["hadm_id"] = wide["hadm_id"].astype("int64")
    # 측정 열만 비운다. id·정적 열이 float 으로 읽혀도 측정으로 오인하지 않게 명시적으로 뺀다.
    numeric = [c for c in wide.columns if pd.api.types.is_float_dtype(wide[c]) and c not in ID_COLS]
    static = [c for c in wide.columns if c not in numeric + ["time:timestamp", "concept:name", "medication", "hadm_id"]]
    first = wide.drop_duplicates("hadm_id").set_index("hadm_id")[static]
    new = ev.join(first, on="hadm_id")
    for c in numeric:
        new[c] = float("nan")
    new = new[wide.columns]
    wide["_src"], new["_src"] = 0, 1
    out = pd.concat([wide, new], ignore_index=True)
    out = out.sort_values(["hadm_id", "time:timestamp", "_src"], kind="mergesort").drop(columns="_src")
    per = out.groupby("hadm_id").size()
    print(f"rows/hadm before median {wide.groupby('hadm_id').size().median():.0f} → after median {per.median():.0f} "
          f"p99 {per.quantile(.99):.0f} max {per.max()} | >230 {(per > 230).sum():,}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    assert out["hadm_id"].notna().all() and out["subject_id"].notna().all(), "id 가 빈 행이 생겼다"
    out.to_csv(args.output, index=False)
    print(f"saved {args.output} rows={len(out):,}")


if __name__ == "__main__":
    main()
