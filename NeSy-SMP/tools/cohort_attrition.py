"""논문 조건 재현 — 코호트 단계별 인원표 (학습 없음).

MIMIC-IV ICU stay 전체에서 시작해 build_cohort_paper.py 의 각 조건을 순서대로 적용하고,
이어서 관찰 창 생성(make_leadtime_csvs.py)과 원본 전처리의 '이벤트 4개 이하 제외'까지 lead 별로 센다.
각 단계: 남은 ICU stay(=입원) 수 · 사망률 · 이번 단계에서 빠진 수.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
DB = r"C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db"
OUT = Path(r"C:\data\mimic-iv-derived")
CACHE = OUT / "_cache_paper"
DOCS = Path(__file__).resolve().parents[2] / "docs"

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
icu = pd.read_sql("SELECT subject_id, hadm_id, stay_id, intime, los FROM icustays", con)
adm = pd.read_sql("SELECT hadm_id, admittime, hospital_expire_flag FROM admissions", con)
pat = pd.read_sql("SELECT subject_id, anchor_age, anchor_year, anchor_year_group FROM patients", con)
d = icu.merge(adm, on="hadm_id").merge(pat, on="subject_id")
d["admittime"] = pd.to_datetime(d["admittime"])
d["age"] = d.anchor_age + (d.admittime.dt.year - d.anchor_year)
d["year_lb"] = d.anchor_year_group.str[:4].astype(int) + (d.admittime.dt.year - d.anchor_year)
d["n_icu"] = d.groupby("hadm_id").stay_id.transform("size")

soi = pd.read_parquet(CACHE / "suspicion.parquet")
soi_stays = set(soi.loc[soi.stay_id.notna() & (soi.suspected_infection == 1), "stay_id"].astype("int64"))
sofa = pd.read_parquet(CACHE / "sofa.parquet", columns=["stay_id"])
sofa_stays = set(sofa.stay_id.unique())
cohort = pd.read_csv(OUT / "cohort_sepsis3_paper.csv")
s3 = pd.read_parquet(CACHE / "sofa.parquet", columns=["stay_id", "endtime", "sofa_24hours"])
# sepsis3 해당 stay 는 build 로그의 41,296 과 같아야 한다 → 코호트 조건을 모두 뺀 집합으로 다시 구한다
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))
from build_cohort_paper import build_sepsis3  # noqa: E402
sep = build_sepsis3(soi, pd.read_parquet(CACHE / "sofa.parquet"))
sep_stays = set(sep.stay_id.astype("int64"))

rows = []


def step(name, mask, note=""):
    global d
    before = len(d)
    d = d[mask]
    rows.append({"단계": name, "남은 ICU stay": len(d), "빠짐": before - len(d),
                 "사망률%": round(100 * d.hospital_expire_flag.mean(), 1), "근거": note})


rows.append({"단계": "MIMIC-IV ICU stay 전체 (로컬 DB v3.x)", "남은 ICU stay": len(d), "빠짐": 0,
             "사망률%": round(100 * d.hospital_expire_flag.mean(), 1), "근거": "icustays"})
step("ICU 안에서 감염 의심 (항생제 + 배양 72h/24h 규칙)", d.stay_id.isin(soi_stays),
     "mimic-code suspicion_of_infection · antibiotic")
step("시간별 SOFA 계산 가능 (ICU 심박수 기록 있음)", d.stay_id.isin(sofa_stays), "mimic-code icustay_times · sofa")
step("Sepsis-3: 감염 의심 −48h~+24h 안 SOFA ≥ 2", d.stay_id.isin(sep_stays), "논문 §5.1 · mimic-code sepsis3")
step("성인 (≥ 18세)", d.age >= 18, "논문 §5.1")
step("2008–2019 (MIMIC-IV v2.2 기간 근사)", d.year_lb < 2020, "논문 §5.1 v2.2 · 로컬 DB 는 2020–2022 포함")
step("ICU 재원 ≥ 24h", d.los >= 1.0, "논문 제외 (1)")
step("입원 중 ICU 1회", d.n_icu == 1, "논문 제외 (2)")
assert len(d) == len(cohort), (len(d), len(cohort))

lead_rows = []
leads = OUT / "paper_leads"
for h in (6, 12, 24, 48):
    long = pd.read_csv(leads / f"events_{h}h_before_death_gcs.csv", usecols=["hadm_id", "concept:name"])
    win = long.groupby("hadm_id").size()
    wide = pd.read_csv(leads / f"events_{h}h_wide_paper_como.csv", usecols=["hadm_id", "concept:name", "hospital_expire_flag"],
                       low_memory=False)
    wide = wide[~wide["concept:name"].isin(["Urine output", "Death", "Discharge from hospital"])]
    g = wide.groupby("hadm_id")
    sz, mort = g.size(), g.hospital_expire_flag.first()
    keep = sz[sz > 4].index
    lost_window = len(cohort) - long.hadm_id.nunique()
    dead_lost = cohort[~cohort.hadm_id.isin(long.hadm_id)].hospital_expire_flag.mean() if lost_window else np.nan
    lead_rows.append({
        "lead": f"{h}h", "코호트": len(cohort),
        "창에 이벤트 있음": long.hadm_id.nunique(), "창 없어 빠짐": lost_window,
        "빠진 입원 중 사망%": round(100 * dead_lost, 1) if lost_window else None,
        "전처리 후 (이벤트 > 4)": len(keep), "이벤트 ≤ 4 로 빠짐": int((sz <= 4).sum()),
        "최종 사망률%": round(100 * mort[keep].mean(), 1), "최대 시퀀스 길이": int(sz.max()),
    })

t1, t2 = pd.DataFrame(rows), pd.DataFrame(lead_rows)
t1.to_csv(OUT / "cohort_attrition_paper.csv", index=False, encoding="utf-8-sig")
t2.to_csv(OUT / "cohort_attrition_paper_leads.csv", index=False, encoding="utf-8-sig")
print(t1.to_string(index=False)); print(); print(t2.to_string(index=False))
