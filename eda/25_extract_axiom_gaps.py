# -*- coding: utf-8 -*-
# ============================================================================
# 강제하지 못하고 있던 PADIS 공리 4개의 입력을 뽑는다.
#   BloodTransfusion (strong)  <- inputevents · Blood Products/Colloids
#   Dementia (strong) · Trauma (strong) · Hypertension (moderate)  <- diagnoses_icd
#
# 동반질환 매핑은 NeSy-SMP/data/build_comorbidities_icd.py 의 match_label 을 그대로 쓴다
# (내가 ICD 규칙을 새로 지어내지 않는다).
#
# ⚠️ ICD 진단은 **퇴원 시점에 부여**되고 hadm 단위라 앵커 시점 정보가 아니다.
#    치매·고혈압 같은 만성질환은 무리가 없지만, 엄밀히는 앵커 이후 정보가 섞일 수 있다.
#    원 논문도 동반질환을 정적 피처로 쓰므로 재현 관점에서는 일관되지만 한계로 기록한다.
#    수혈은 시각이 있어 lookback 창 안으로 제한한다 — 이쪽은 누수가 없다.
#
# 사용: EDA_DATA=<notes/eda> EDA_SQLITE=<db> python eda/25_extract_axiom_gaps.py
# ============================================================================
import os, sys, time, sqlite3
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "NeSy-SMP", "data"))
from build_comorbidities_icd import match_label          # noqa: E402

DATA = os.environ.get("EDA_DATA", "notes/eda")
DB = os.environ.get("EDA_SQLITE", "C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db")
HR_MAX = 264.0
# d_items category = 'Blood Products/Colloids' + 미사용 표기지만 데이터가 있는 것들
BLOOD_RBC = [225168, 226368, 227070, 220996, 221013, 226370]      # 적혈구 계열
BLOOD_ANY = BLOOD_RBC + [220970, 225170, 226369, 227071, 220971]  # + FFP·혈소판


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


b = pd.read_pickle(f"{DATA}/_icu_base.pkl")
b["intime"] = pd.to_datetime(b["intime"])
if "age" not in b.columns:
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
DEN = b[(b.age >= 18) & (b.los >= 1.0)].copy()
stays = set(DEN.stay_id.astype("int64"))
hadms = set(DEN.hadm_id.astype("int64"))
intime = DEN.set_index("stay_id")["intime"]
log(f"코호트 stay {len(stays):,} · hadm {len(hadms):,}")

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=600)
con.execute("pragma cache_size=-400000")

# ---------------------------------------------------------------- 1. 동반질환
log("diagnoses_icd 조회")
dx = pd.read_sql("""select d.hadm_id, d.icd_code, d.icd_version, t.long_title
                    from diagnoses_icd d
                    left join d_icd_diagnoses t
                      on t.icd_code = d.icd_code and t.icd_version = d.icd_version""", con)
dx["hadm_id"] = dx["hadm_id"].astype("int64")
dx = dx[dx.hadm_id.isin(hadms)]
log(f"  진단 {len(dx):,}행 / hadm {dx.hadm_id.nunique():,}")

WANT = ["dementia", "trauma", "hypertension"]
hit = {w: set() for w in WANT}
for h_, c_, v_, t_ in zip(dx.hadm_id.to_numpy(), dx.icd_code.to_numpy(),
                          dx.icd_version.to_numpy(), dx.long_title.to_numpy()):
    for lab in match_label(v_, c_, t_):
        if lab in hit:
            hit[lab].add(h_)
com = pd.DataFrame({"hadm_id": sorted(hadms)})
for w in WANT:
    com[w] = com.hadm_id.isin(hit[w]).astype("int8")
print()
print("동반질환 유병률 (hadm 기준):")
print((100 * com[WANT].mean()).round(1).to_string())
print(f"(참고: sepsis 코호트 값 — dementia 5.2% · trauma 9.6% · hypertension 70.9%)")

# ---------------------------------------------------------------- 2. 수혈
log("inputevents 조회 (혈액제제)")
ids = ",".join(map(str, BLOOD_ANY))
tr = pd.read_sql(f"""select stay_id, itemid, starttime from inputevents
                     where itemid in ({ids}) and stay_id is not null""", con)
con.close()
tr["stay_id"] = tr["stay_id"].astype("int64")
tr = tr[tr.stay_id.isin(stays)].copy()
tr["starttime"] = pd.to_datetime(tr["starttime"], errors="coerce")
tr["hr"] = (tr["starttime"] - tr["stay_id"].map(intime)).dt.total_seconds() / 3600
tr = tr[(tr.hr >= 0) & (tr.hr <= HR_MAX)].copy()
tr["is_rbc"] = tr.itemid.isin(BLOOD_RBC).astype("int8")
tr["hr"] = tr["hr"].astype("float32")
print()
print(f"수혈 기록 {len(tr):,}건 / stay {tr.stay_id.nunique():,} "
      f"({100*tr.stay_id.nunique()/len(stays):.1f}%)")
print(f"  적혈구 계열만: {int(tr.is_rbc.sum()):,}건 / stay {tr[tr.is_rbc==1].stay_id.nunique():,} "
      f"({100*tr[tr.is_rbc==1].stay_id.nunique()/len(stays):.1f}%)")
print("\n제제별:")
print(tr.groupby("itemid").agg(건수=("hr", "size"), stay=("stay_id", "nunique")).to_string())

com.to_parquet(f"{DATA}/_axiom_comorb.parquet", index=False)
tr[["stay_id", "hr", "is_rbc"]].to_parquet(f"{DATA}/_axiom_transfusion.parquet", index=False)
log(f"저장 -> _axiom_comorb.parquet · _axiom_transfusion.parquet")
