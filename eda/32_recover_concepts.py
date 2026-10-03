# -*- coding: utf-8 -*-
# ============================================================================
# 2순위 (추출) — KG 공리로 못 쓰던 개념을 MIMIC 에서 회수한다
#
#   억제대 PhysicalRestraint · 기계환기 MechanicalVentilation ·
#   오피오이드 OpioidUse · 멜라토닌 Melatonin
#
#   추출 트리플의 절반 이상이 "주어 미매핑"으로 공리가 못 됐다 (docs/OUTCOME_SWITCH_2026-10-03.md §3).
#   이 네 개를 붙이면 KG 범위 비교가 공리 수 차이에 끌려가지 않는다.
#
# 출력: notes/eda/_axiom_padis2_events.parquet  (stay_id, hr, var)  — 앵커 창 판정은 33_ 에서
# 사용: EDA_DATA=notes/eda python eda/32_recover_concepts.py
# ============================================================================
from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ.get("EDA_DATA", "notes/eda")
DB = os.environ.get("MIMIC_DB", r"C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db")
OUTP = Path(DATA) / "_axiom_padis2_events.parquet"

RESTRAINT = [227671, 227670, 224063, 227945, 227962, 224856]
VENT = [223849, 223848, 220339, 224684, 224685, 224686, 224696]      # 환기 설정·모드
OPIOID_LIKE = ["%fentanyl%", "%morphine%", "%hydromorphone%", "%remifentanil%"]
MELATONIN_LIKE = ["%melatonin%", "%ramelteon%"]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def main():
    t0 = time.time()
    b = pd.read_pickle(f"{DATA}/_icu_base.pkl")
    b["intime"] = pd.to_datetime(b["intime"])
    if "age" not in b.columns:
        b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
    den = b[(b.age >= 18) & (b.los >= 1.0)]
    stays = set(den.stay_id)
    intime = den.set_index("stay_id")["intime"]
    log(f"대상 stay {len(stays):,}")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    parts = []
    for var, ids in [("Restraint", RESTRAINT), ("MechVent", VENT)]:
        log(f"chartevents {var} (itemid {len(ids)}개)")
        d = pd.read_sql(f"select stay_id, charttime from chartevents "
                        f"where itemid in ({','.join(map(str, ids))}) and stay_id is not null", con)
        d = d[d.stay_id.isin(stays)].copy()
        d["hr"] = (pd.to_datetime(d.charttime) - d.stay_id.map(intime)).dt.total_seconds() / 3600
        d = d[(d.hr >= -1) & (d.hr <= 480)]
        d["var"] = var
        parts.append(d[["stay_id", "hr", "var"]])
        log(f"  {len(d):,}행 · stay {d.stay_id.nunique():,}")

    # 오피오이드 — d_items 에서 라벨로 찾아 inputevents
    ql = " or ".join(["lower(label) like ?"] * len(OPIOID_LIKE))
    it = pd.read_sql(f"select itemid, label from d_items where {ql}", con, params=OPIOID_LIKE)
    log(f"오피오이드 itemid {len(it)}개: {it.label.head(8).tolist()}")
    if len(it):
        ids = ",".join(map(str, it.itemid.tolist()))
        d = pd.read_sql(f"select stay_id, starttime from inputevents "
                        f"where itemid in ({ids}) and stay_id is not null", con)
        d = d[d.stay_id.isin(stays)].copy()
        d["hr"] = (pd.to_datetime(d.starttime) - d.stay_id.map(intime)).dt.total_seconds() / 3600
        d = d[(d.hr >= -1) & (d.hr <= 480)]
        d["var"] = "Opioid"
        parts.append(d[["stay_id", "hr", "var"]])
        log(f"  {len(d):,}행 · stay {d.stay_id.nunique():,}")

    # 멜라토닌 — 처방 테이블 (hosp). stay 가 없으므로 hadm 으로 받아 stay 로 되돌린다
    h2s = den[["hadm_id", "stay_id"]]
    ql = " or ".join(["lower(drug) like ?"] * len(MELATONIN_LIKE))
    d = pd.read_sql(f"select hadm_id, starttime, drug from prescriptions where {ql}",
                    con, params=MELATONIN_LIKE)
    log(f"멜라토닌 처방 {len(d):,}행 · 약물명 {d.drug.str.lower().value_counts().head(5).to_dict()}")
    if len(d):
        d = d.merge(h2s, on="hadm_id")
        d["hr"] = (pd.to_datetime(d.starttime) - d.stay_id.map(intime)).dt.total_seconds() / 3600
        d = d[(d.hr >= -1) & (d.hr <= 480)]
        d["var"] = "Melatonin"
        parts.append(d[["stay_id", "hr", "var"]])
        log(f"  창 안 {len(d):,}행 · stay {d.stay_id.nunique():,}")
    con.close()

    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(OUTP, index=False)
    log(f"-> {OUTP}  {len(out):,}행")
    log(f"변수별 stay 보유율%: "
        f"{ {v: round(100*g.stay_id.nunique()/len(stays),1) for v,g in out.groupby('var')} }")
    log(f"총 {time.time()-t0:.0f}초")


if __name__ == "__main__":
    main()
