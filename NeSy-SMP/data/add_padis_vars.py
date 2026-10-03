# -*- coding: utf-8 -*-
"""안 2 준비 — sepsis 코호트에 PADIS 변수(진정 깊이·진정제·통증·거동·억제대)를 추가한다.

논문 조건 재현 입력(events_{h}h_wide_paper_como.csv)에 **열 5개를 더한** 파일을 만든다.
  RASS            진정 깊이 (chartevents 228096)
  Pain NRS        통증 점수 (223791 223794 224409 229702 230144)
  Mobility level  거동 수준 (229319 229321 229633 229742 228697 224057)
  Restraint       억제대 기록 유무 (227671 227670 224063 227945 227962 224856)
  Sedative rate   진정제 투여 중 여부 (inputevents: benzo/propofol/dexmedetomidine)

원본 전처리는 변수마다 ffill 후 MinMax 하므로, 새 변수는 **자기 측정 시각의 행**으로 추가한다
(기존 행의 값을 덮어쓰지 않는다). 관찰 창은 기존 입원별 [최초, 최종] 타임스탬프로 제한한다.

사용: python NeSy-SMP/data/add_padis_vars.py --leads 6 [--db <sqlite>]
출력: C:\\data\\mimic-iv-derived\\paper_leads\\events_{h}h_wide_paper_como_padis.csv
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
DB = r"C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db"
LEADS = Path(r"C:\data\mimic-iv-derived\paper_leads")
COHORT = Path(r"C:\data\mimic-iv-derived\cohort_sepsis3_paper.csv")
CACHE = Path(r"C:\data\mimic-iv-derived\_cache_padis_vars")

ITEMS = {
    "RASS": [228096],
    "Pain NRS": [223791, 223794, 224409, 229702, 230144],
    "Mobility level": [229319, 229321, 229633, 229742, 228697, 224057],
    "Restraint": [227671, 227670, 224063, 227945, 227962, 224856],
}
SED = {225150: "dexmedetomidine", 229420: "dexmedetomidine", 221385: "lorazepam",
       221668: "midazolam", 222168: "propofol", 221623: "diazepam"}
NEW_COLS = ["RASS", "Pain NRS", "Mobility level", "Restraint", "Sedative"]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def fetch(con, stays):
    """chartevents / inputevents 에서 코호트 stay 의 PADIS 변수를 긁는다."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cp, sp = CACHE / "chart.parquet", CACHE / "sed.parquet"
    if cp.exists() and sp.exists():
        log("캐시 사용")
        return pd.read_parquet(cp), pd.read_parquet(sp)
    ids = sorted({i for v in ITEMS.values() for i in v})
    log(f"chartevents 스캔 (itemid {len(ids)}개) — 인덱스 없으면 풀스캔")
    ch = pd.read_sql(
        f"select stay_id, itemid, charttime, value, valuenum from chartevents "
        f"where itemid in ({','.join(map(str, ids))}) and stay_id is not null", con)
    ch = ch[ch.stay_id.isin(stays)].copy()
    i2g = {i: g for g, v in ITEMS.items() for i in v}
    ch["var"] = ch.itemid.map(i2g)
    log(f"  보존 {len(ch):,}행 · 변수별 {ch.var.value_counts().to_dict()}")
    log("inputevents 스캔 (진정제)")
    sed = pd.read_sql(
        f"select stay_id, starttime, endtime, itemid from inputevents "
        f"where itemid in ({','.join(map(str, SED))}) and stay_id is not null", con)
    sed = sed[sed.stay_id.isin(stays)].copy()
    log(f"  보존 {len(sed):,}행")
    ch.to_parquet(cp, index=False); sed.to_parquet(sp, index=False)
    return ch, sed


def value_of(var, s):
    """변수별 수치화. 기록 텍스트는 숫자만 뽑아 쓴다."""
    v = pd.to_numeric(s["valuenum"], errors="coerce")
    if var == "Restraint":
        return pd.Series(1.0, index=s.index)                       # 기록 자체가 '적용 중'
    if var == "Mobility level":
        txt = s["value"].astype(str).str.extract(r"(\d+)")[0]
        return v.fillna(pd.to_numeric(txt, errors="coerce"))
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leads", default="6")
    ap.add_argument("--db", default=DB)
    a = ap.parse_args()
    t0 = time.time()
    coh = pd.read_csv(COHORT)
    stays = set(coh.stay_id.astype("int64"))
    h2s = coh.groupby("hadm_id").stay_id.apply(list).to_dict()
    log(f"코호트 입원 {len(h2s):,} · stay {len(stays):,}")
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    ch, sed = fetch(con, stays)
    con.close()
    ch["charttime"] = pd.to_datetime(ch["charttime"])
    s2h = coh.set_index("stay_id").hadm_id.to_dict()
    ch["hadm_id"] = ch.stay_id.map(s2h)
    for c in ("starttime", "endtime"):
        sed[c] = pd.to_datetime(sed[c])
    sed["hadm_id"] = sed.stay_id.map(s2h)

    for lead in [int(x) for x in a.leads.split(",")]:
        src = LEADS / f"events_{lead}h_wide_paper_como.csv"
        dst = LEADS / f"events_{lead}h_wide_paper_como_padis.csv"
        log(f"== {lead}h  {src.name}")
        w = pd.read_csv(src, low_memory=False)
        w["time:timestamp"] = pd.to_datetime(w["time:timestamp"])
        win = w.groupby("hadm_id")["time:timestamp"].agg(["min", "max"])
        stat_cols = [c for c in ("hospital_expire_flag", "anchor_age", "admission_type",
                                 "admission_location") if c in w.columns]
        stat = w.groupby("hadm_id")[stat_cols].first()
        rows = []
        # ---- chartevents 계열
        for var in ITEMS:
            d = ch[ch["var"] == var][["hadm_id", "charttime", "value", "valuenum"]].copy()
            d["v"] = value_of(var, d)
            d = d.dropna(subset=["v"])
            d = d.join(win, on="hadm_id")
            d = d[(d.charttime >= d["min"]) & (d.charttime <= d["max"])]
            if d.empty:
                log(f"  {var}: 창 안 기록 없음")
                continue
            r = pd.DataFrame({"hadm_id": d.hadm_id, "time:timestamp": d.charttime,
                              "concept:name": var, var: d.v.astype(float)})
            rows.append(r)
            log(f"  {var}: {len(r):,}행 · 입원 {r.hadm_id.nunique():,}")
        # ---- 진정제: 창 안에서 투여 구간이 겹치면 시작·종료 시각에 1/0 기록
        s = sed.join(win, on="hadm_id")
        s = s[(s.endtime >= s["min"]) & (s.starttime <= s["max"])]
        if not s.empty:
            on = pd.DataFrame({"hadm_id": s.hadm_id,
                               "time:timestamp": s.starttime.clip(lower=s["min"]),
                               "concept:name": "Sedative", "Sedative": 1.0})
            off = pd.DataFrame({"hadm_id": s.hadm_id,
                                "time:timestamp": s.endtime.clip(upper=s["max"]),
                                "concept:name": "Sedative", "Sedative": 0.0})
            rows += [on, off]
            log(f"  Sedative: {len(on)+len(off):,}행 · 입원 {on.hadm_id.nunique():,}")
        add = pd.concat(rows, ignore_index=True)
        for c in stat_cols:                      # 첫 행이 결측이면 label/static 이 깨진다
            add[c] = add.hadm_id.map(stat[c])
        for c in NEW_COLS:
            if c not in add.columns:
                add[c] = np.nan
            if c not in w.columns:
                w[c] = np.nan
        out = pd.concat([w, add[[c for c in add.columns if c in w.columns]]], ignore_index=True)
        out = out.sort_values(["hadm_id", "time:timestamp"], kind="stable")
        out.to_csv(dst, index=False)
        log(f"  -> {dst.name}  {len(w):,} + {len(add):,} = {len(out):,}행 "
            f"· 입원 {out.hadm_id.nunique():,}")
        cov = {c: round(100 * out.groupby('hadm_id')[c].apply(lambda x: x.notna().any()).mean(), 1)
               for c in NEW_COLS}
        log(f"  변수별 입원 보유율%: {cov}")
    log(f"총 {time.time()-t0:.0f}초")


if __name__ == "__main__":
    main()
