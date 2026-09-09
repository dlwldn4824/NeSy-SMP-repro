# -*- coding: utf-8 -*-
# ============================================================================
# 00_extract.py 가 값으로 뽑지 않은 3개 항목군을 보충 추출한다.
#   MOBILITY · PAIN_NRS · GCS_total
#
# 왜 별도 스크립트인가: 00_extract.py 를 다시 돌리면 _icu_base 등 기존 중간파일을
# 전부 덮어써서, 이미 문서에 실은 수치의 재현성이 흔들린다. 기존 파일은 그대로 두고
# 새 파일 하나(_extra_values.parquet)만 만든다.
# (00_extract.py 의 VALUE_IDS 도 같이 넓혀 두었으니, 다음 전체 재추출부터는 자동 포함된다.)
#
# 앵커 관련 구간만 남긴다: 입실 후 0~264h (240h 캡 + lookback 24h)
# 사용: EDA_DATA=<notes/eda> EDA_SQLITE=<db> python eda/24_extract_mobility_pain_gcs.py
# ============================================================================
import os, sys, time, sqlite3
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ.get("EDA_DATA", "notes/eda")
DB = os.environ.get("EDA_SQLITE", "C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db")
OUTF = os.path.join(DATA, "_extra_values.parquet")
HR_MAX = 264.0                      # 240h 캡 + lookback 24h
CHUNK = 4_000_000

GROUPS = {
    "PAIN_NRS": [223791, 223794, 224409, 229702, 230144],
    "MOBILITY": [229319, 229321, 229633, 229742, 228697, 224057],
    "GCS_total": [220739, 223900, 223901],
}
ITEM2G = {i: g for g, xs in GROUPS.items() for i in xs}
IDS = sorted(ITEM2G)


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


if not os.path.exists(DB):
    sys.exit(f"DB 없음: {DB}")
log(f"DB {os.path.getsize(DB)/1e9:.1f}GB · itemid {len(IDS)}개")

b = pd.read_pickle(f"{DATA}/_icu_base.pkl")
b["intime"] = pd.to_datetime(b["intime"])
if "age" not in b.columns:
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
DEN = b[(b.age >= 18) & (b.los >= 1.0)]
keep = set(DEN.stay_id.astype("int64"))
intime = DEN.set_index("stay_id")["intime"]
log(f"코호트 stay {len(keep):,}")

try:
    con = sqlite3.connect(f"file:{DB}?immutable=1", uri=True)
    con.execute("select 1")
except sqlite3.OperationalError:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.execute("pragma cache_size=-400000")

q = (f"select stay_id, itemid, charttime, value, valuenum from chartevents "
     f"where itemid in ({','.join(map(str, IDS))}) and stay_id is not null")
log("chartevents 스캔 시작 (인덱스 없으면 풀스캔)")

parts, seen, kept = [], 0, 0
t0 = time.time()
for ch in pd.read_sql(q, con, chunksize=CHUNK):
    seen += len(ch)
    ch["stay_id"] = ch["stay_id"].astype("int64")
    ch = ch[ch.stay_id.isin(keep)]
    if len(ch):
        ch["charttime"] = pd.to_datetime(ch["charttime"], errors="coerce")
        ch["hr"] = (ch["charttime"] - ch["stay_id"].map(intime)).dt.total_seconds() / 3600
        ch = ch[(ch.hr >= 0) & (ch.hr <= HR_MAX)]
    if len(ch):
        ch["grp"] = ch["itemid"].map(ITEM2G)
        ch["valuenum"] = pd.to_numeric(ch["valuenum"], errors="coerce").astype("float32")
        ch["hr"] = ch["hr"].astype("float32")
        parts.append(ch[["stay_id", "itemid", "grp", "hr", "value", "valuenum"]])
        kept += len(ch)
    log(f"  스캔 {seen:,} · 보존 {kept:,} · {time.time()-t0:.0f}s")
con.close()

if not parts:
    sys.exit("보존된 행이 없다 — itemid 나 코호트를 확인할 것")
val = pd.concat(parts, ignore_index=True)
del parts
log(f"합계 {len(val):,} 행 · {val.memory_usage(deep=True).sum()/1e6:.0f}MB")

print()
print(val.groupby("grp").agg(
    행수=("hr", "size"), stay수=("stay_id", "nunique"),
    valuenum있음=("valuenum", lambda s: f"{100*s.notna().mean():.1f}%")).to_string())
print("\n항목별 값 예시:")
for g in GROUPS:
    sub = val[val.grp == g]
    if not len(sub):
        continue
    ex = sub["value"].astype(str).value_counts().head(4)
    print(f"  {g}: " + " | ".join(f"{k}({v:,})" for k, v in ex.items()))

val.to_parquet(OUTF, index=False)
log(f"저장 -> {OUTF}  ({os.path.getsize(OUTF)/1e6:.0f}MB)")

cov = val.groupby("grp")["stay_id"].nunique() / len(keep) * 100
print("\n코호트 stay 대비 보유율:")
print(cov.round(1).to_string())
