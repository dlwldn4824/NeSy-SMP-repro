# -*- coding: utf-8 -*-
"""09_remaining_eda.py 가 읽는 중간 파일 4개를 원본에서 만든다.

  _icu_base.pkl / .parquet             ICU stay 기본 테이블
  _label_values.parquet                섬망평가(228332) + RASS(228096) 원본 기록
  _padis_item_stay_counts.parquet      stay x itemid 기록수 + 첫/마지막 시각
  _padis_stay_group_counts.parquet     stay x 항목군 기록수
  _step1_sed.parquet                   진정제 투여(inputevents)

이 4개가 이미 있으면 이 스크립트는 돌릴 필요가 없다. 바로 09 를 돌리면 된다.
chartevents 는 인덱스가 없어 풀스캔 1회에 60~75초 (로컬 SSD 기준).
"""
import os
import sys
import time

import pandas as pd

# ============================================================================
# ===== 여기만 고치세요 =======================================================
# ============================================================================
# 원본을 어떤 형태로 갖고 있는지: "sqlite" 또는 "csvgz"
SRC_MODE = "sqlite"

# [sqlite 모드] MIMIC4-hosp-icu.db 경로.
#   윈도우는 역슬래시 대신 슬래시로 쓴다 (r"" 를 써도 URI 로 넘길 때 깨진다).
#   경로에 공백이 있으면 폴더째 공백 없는 곳으로 옮기는 편이 안전하다.
SQLITE_PATH = "C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db"

# 구글 드라이브에 마운트해서 쓰는 경우 True 로.
#   드라이브 FUSE 는 SQLite 가 요구하는 파일 잠금을 지원하지 않아
#   "unable to open database file" 이 난다. immutable=1 이면 잠금 없이 읽는다.
SQLITE_IMMUTABLE = False

# [csvgz 모드] physionet 원본 csv.gz 디렉터리 (duckdb 필요)
CSV_HOSP = "/content/mimiciv/hosp"
CSV_ICU = "/content/mimiciv/icu"

# 중간 파일을 저장할 곳. 09_remaining_eda.py 의 DATA 와 같아야 한다.
OUT = "notes/eda"
# ============================================================================
# ===== 여기까지 =============================================================
# ============================================================================

# 환경변수로도 덮어쓸 수 있다 (코랩에서 편하다)
SRC_MODE = os.environ.get("EDA_SRC_MODE", SRC_MODE)
SQLITE_PATH = os.environ.get("EDA_SQLITE", SQLITE_PATH)
CSV_HOSP = os.environ.get("EDA_CSV_HOSP", CSV_HOSP)
CSV_ICU = os.environ.get("EDA_CSV_ICU", CSV_ICU)
OUT = os.environ.get("EDA_DATA", OUT)
SQLITE_IMMUTABLE = os.environ.get("EDA_SQLITE_IMMUTABLE", str(SQLITE_IMMUTABLE)).lower() in ("1", "true")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
os.makedirs(OUT, exist_ok=True)

# ---- itemid 목록 (scan_padis_labels.py / 05_scan_step1.py 와 동일) ----
GROUPS = {
    "RASS":            [228096],
    "RASS_goal":       [228299],
    "CAMICU":          [228300, 228301, 228302, 228303, 228334, 228335, 228336, 228337,
                        229324, 229325, 229326],
    "DELIRIUM_ASSESS": [228332, 228688],
    "PAIN_NRS":        [223791, 223794, 224409, 229702, 230144],
    "CPOT":            [229689, 229690, 229691, 229692, 229694, 229695, 229696, 229697,
                        229698, 229699],
    "MOBILITY":        [229319, 229321, 229633, 229742, 228697, 224057],
    "RESTRAINT":       [227671, 227670, 224063, 227945, 227962, 224856],
    "GCS_total":       [220739, 223900, 223901],
}
ITEM2G = {i: g for g, xs in GROUPS.items() for i in xs}
ALL_IDS = sorted(ITEM2G)
# 값까지 원본 그대로 보관할 항목 (섬망평가 · RASS · CAM-ICU feature)
VALUE_IDS = [228332, 228096, 228300, 228301, 228302, 228303, 228334, 228335, 228336,
             228337, 229324, 229325, 229326]
SED = {225150: "dexmedetomidine", 229420: "dexmedetomidine", 221385: "lorazepam",
       221668: "midazolam", 222168: "propofol", 221623: "diazepam"}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def build_base(icustays, patients, admissions):
    b = (icustays.merge(patients, on="subject_id", how="inner")
                 .merge(admissions[["hadm_id", "admittime", "dischtime", "deathtime",
                                    "hospital_expire_flag"]], on="hadm_id", how="inner"))
    for c in ["intime", "outtime", "admittime", "dischtime", "dod"]:
        if c in b.columns:
            b[c] = pd.to_datetime(b[c], errors="coerce")
    # anchor_age 는 anchor_year 시점 나이. MIMIC-IV 는 환자별로 날짜가 시프트되어 있다.
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
    b = b.sort_values(["subject_id", "intime"])
    b["icu_seq_in_hadm"] = b.groupby("hadm_id")["intime"].rank(method="first").astype(int)
    b["icu_seq_in_subject"] = b.groupby("subject_id")["intime"].rank(method="first").astype(int)
    if "dod" in b.columns:
        d = (b["dod"] - b["outtime"]).dt.total_seconds() / 86400.0
        b["mort_30d"] = ((d <= 30) & (d >= -1)).astype(int)
        b["mort_1y"] = ((d <= 365) & (d >= -1)).astype(int)
    return b


def run_sqlite():
    import sqlite3
    if not os.path.exists(SQLITE_PATH):
        sys.exit(f"DB 를 못 찾음: {SQLITE_PATH}\n  -> 파일 상단 SQLITE_PATH 를 고치세요.")
    uri = f"file:{SQLITE_PATH}?" + ("immutable=1" if SQLITE_IMMUTABLE else "mode=ro")
    try:
        con = sqlite3.connect(uri, uri=True)
        con.execute("select 1")
    except sqlite3.OperationalError as e:
        sys.exit(f"DB 를 열지 못함: {e}\n"
                 f"  구글 드라이브에 마운트한 파일이면 SQLITE_IMMUTABLE = True 로 바꿔보세요.")
    con.execute("pragma cache_size=-400000")
    con.execute("pragma temp_store=MEMORY")

    log("icustays / patients / admissions")
    icustays = pd.read_sql("select subject_id,hadm_id,stay_id,first_careunit,last_careunit,"
                           "intime,outtime,los from icustays", con)
    patients = pd.read_sql("select subject_id,gender,anchor_age,anchor_year,"
                           "anchor_year_group,dod from patients", con)
    admissions = pd.read_sql("select hadm_id,admittime,dischtime,deathtime,"
                             "hospital_expire_flag from admissions", con)

    ids = ",".join(map(str, ALL_IDS))
    log("chartevents 스캔 1/2 (stay x itemid 집계) — 인덱스 없으면 풀스캔")
    t = time.time()
    cnt = pd.read_sql(f"""select stay_id, itemid, count(*) n,
                                 min(charttime) t0, max(charttime) t1
                          from chartevents
                          where itemid in ({ids}) and stay_id is not null
                          group by stay_id, itemid""", con)
    log(f"  {time.time()-t:.0f}s rows={len(cnt):,}")

    log("chartevents 스캔 2/2 (원본 값)")
    t = time.time()
    val = pd.read_sql(f"""select stay_id, itemid, charttime, value, valuenum
                          from chartevents
                          where itemid in ({','.join(map(str, VALUE_IDS))})
                            and stay_id is not null""", con)
    log(f"  {time.time()-t:.0f}s rows={len(val):,}")

    log("inputevents (진정제)")
    ie = pd.read_sql(f"""select stay_id,itemid,starttime,endtime,amount,amountuom
                         from inputevents
                         where itemid in ({','.join(map(str, SED))})""", con)
    return icustays, patients, admissions, cnt, val, ie


def run_csvgz():
    ce = os.path.join(CSV_ICU, "chartevents.csv.gz")
    if not os.path.exists(ce):
        sys.exit(f"chartevents 를 못 찾음: {ce}\n  -> 파일 상단 CSV_ICU 를 고치세요.")
    try:
        import duckdb
    except ImportError:
        sys.exit("csvgz 모드는 duckdb 가 필요하다:  pip install duckdb\n"
                 "  (.db 파일을 갖고 있다면 SRC_MODE = \"sqlite\" 로 바꾸면 duckdb 없이 된다)")
    con = duckdb.connect()
    con.execute("pragma threads=4")
    con.execute("pragma memory_limit='6GB'")     # 필터 결과가 수천만 행이라 메모리에 다 못 얹는다
    if os.path.isdir("/content"):
        os.makedirs("/content/duckdb_tmp", exist_ok=True)
        con.execute("pragma temp_directory='/content/duckdb_tmp'")

    def rd(path, cols):
        return con.execute(f"select {cols} from read_csv_auto('{path}', compression='gzip')").df()

    log("icustays / patients / admissions")
    icustays = rd(os.path.join(CSV_ICU, "icustays.csv.gz"),
                  "subject_id,hadm_id,stay_id,first_careunit,last_careunit,intime,outtime,los")
    patients = rd(os.path.join(CSV_HOSP, "patients.csv.gz"),
                  "subject_id,gender,anchor_age,anchor_year,anchor_year_group,dod")
    admissions = rd(os.path.join(CSV_HOSP, "admissions.csv.gz"),
                    "hadm_id,admittime,dischtime,deathtime,hospital_expire_flag")

    ids = ",".join(map(str, ALL_IDS))
    tmp = os.path.join(OUT, "_ce_filtered.parquet")
    log("chartevents 1회 스캔 -> parquet 으로 흘려보냄 (메모리에 안 얹는다)")
    t = time.time()
    con.execute(f"""copy (select stay_id, itemid, charttime, value, valuenum
                          from read_csv_auto('{ce}', compression='gzip')
                          where itemid in ({ids}) and stay_id is not null)
                    to '{tmp}' (format parquet)""")
    log(f"  {time.time()-t:.0f}s -> {tmp}")
    cnt = con.execute(f"""select stay_id, itemid, count(*) n,
                                 min(charttime) t0, max(charttime) t1
                          from read_parquet('{tmp}') group by stay_id, itemid""").df()
    val = con.execute(f"""select stay_id,itemid,charttime,value,valuenum
                          from read_parquet('{tmp}')
                          where itemid in ({','.join(map(str, VALUE_IDS))})""").df()
    log(f"  집계 {len(cnt):,} rows / 값 {len(val):,} rows")

    log("inputevents (진정제)")
    ie = con.execute(f"""select stay_id,itemid,starttime,endtime,amount,amountuom
                         from read_csv_auto(
                             '{os.path.join(CSV_ICU, "inputevents.csv.gz")}', compression='gzip')
                         where itemid in ({','.join(map(str, SED))})""").df()
    return icustays, patients, admissions, cnt, val, ie


if SRC_MODE == "sqlite":
    icustays, patients, admissions, cnt, val, ie = run_sqlite()
elif SRC_MODE == "csvgz":
    icustays, patients, admissions, cnt, val, ie = run_csvgz()
else:
    sys.exit(f"SRC_MODE 는 sqlite 또는 csvgz 여야 한다: {SRC_MODE}")

b = build_base(icustays, patients, admissions)
b.to_pickle(f"{OUT}/_icu_base.pkl")
b.to_parquet(f"{OUT}/_icu_base.parquet")     # pickle 은 pandas 버전이 다르면 못 읽는다
log(f"_icu_base  {len(b):,} stays")

cnt["grp"] = cnt["itemid"].map(ITEM2G)
cnt.to_parquet(f"{OUT}/_padis_item_stay_counts.parquet")
cnt.groupby(["stay_id", "grp"])["n"].sum().unstack(fill_value=0) \
   .to_parquet(f"{OUT}/_padis_stay_group_counts.parquet")
log(f"_padis_item_stay_counts  {len(cnt):,} rows")

val.to_parquet(f"{OUT}/_label_values.parquet")
log(f"_label_values  {len(val):,} rows")

ie["drug"] = ie["itemid"].map(SED)
ie.to_parquet(f"{OUT}/_step1_sed.parquet")
log(f"_step1_sed  {len(ie):,} rows")
log(f"완료. 출력 -> {OUT}/  이제 09_remaining_eda.py 를 돌리면 된다.")
