# -*- coding: utf-8 -*-
"""추가 EDA 5b — 원본 DB가 필요한 확인 3가지. 결론 없이 가용성만 보고한다.

  (a) 연도별 inputevents 기록 보유 stay 비율 (투약 변수 사용 가능 시기 판단 재료)
  (b) mechanical ventilation 가용성: procedureevents 의 인공호흡 itemid 존재/규모
  (c) SOFA 가용성: SOFA 테이블 유무 + 구성요소가 있는 테이블/itemid 존재 여부

빠른 쿼리만 쓴다 (chartevents/labevents 풀스캔 없음).
필요: MIMIC4-hosp-icu.db + _icu_base(.pkl/.parquet)
출력: chk15_*.csv
"""
import os
import sqlite3
import sys

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
pd.set_option("display.width", 220)

# ===== 여기만 고치세요 =====
DB_PATH = "C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db"
DATA = "notes/eda"          # _icu_base 위치. 출력도 여기에.
# =========================
DB_PATH = os.environ.get("EDA_SQLITE", DB_PATH)
DATA = os.environ.get("EDA_DATA", DATA)
OUT = os.environ.get("EDA_OUT", DATA)
os.makedirs(OUT, exist_ok=True)

if not os.path.exists(DB_PATH):
    sys.exit(f"DB 를 못 찾음: {DB_PATH}  -> 상단 DB_PATH 를 고치세요.")
con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
TABLES = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}


def has(t):
    return t in TABLES


def head(t):
    print("\n" + "=" * 78); print(t); print("=" * 78)


def save(df, name):
    df.to_csv(f"{OUT}/{name}", encoding="utf-8-sig")
    print(f"  -> {name}")


def load_base():
    pkl, pq = f"{DATA}/_icu_base.pkl", f"{DATA}/_icu_base.parquet"
    if os.path.exists(pkl):
        try:
            return pd.read_pickle(pkl)
        except Exception:
            pass
    if os.path.exists(pq):
        return pd.read_parquet(pq)
    sys.exit(f"_icu_base 를 못 찾음: {pkl} / {pq}")


b = load_base()
b["era"] = b["anchor_year_group"].astype(str).str.replace(" ", "", regex=False)
DEN = b[(b.age >= 18) & (b.los >= 1.0)][["stay_id", "era"]].copy()
print(f"DEN (age>=18, los>=1d): {len(DEN):,} stays")

# ============================================================ (a) inputevents 기록률
head("[a] 연도별 inputevents 기록 보유 stay 비율")
if has("inputevents"):
    ie = pd.read_sql("select distinct stay_id from inputevents", con)
    DEN["has_ie"] = DEN.stay_id.isin(ie.stay_id)
    t = DEN.groupby("era").agg(stays=("stay_id", "size"), has_ie=("has_ie", "mean"))
    t["inputevents보유stay%"] = (100 * t.has_ie).round(1)
    print(t[["stays", "inputevents보유stay%"]].to_string())
    save(t[["stays", "inputevents보유stay%"]], "chk15_a_inputevents_era.csv")
else:
    print("inputevents 테이블 없음")

# ============================================================ (b) mechanical ventilation
head("[b] mechanical ventilation 가용성")
VENT_PROC = {225792: "Invasive Ventilation", 225794: "Non-invasive Ventilation"}
rows = []
if has("procedureevents"):
    q = f"""select itemid, count(*) n, count(distinct stay_id) stays
            from procedureevents where itemid in ({','.join(map(str, VENT_PROC))})
            group by itemid"""
    r = pd.read_sql(q, con)
    for _, x in r.iterrows():
        rows.append({"소스": "procedureevents", "itemid": int(x.itemid),
                     "label": VENT_PROC[int(x.itemid)], "records": int(x.n),
                     "stays": int(x.stays),
                     "DEN보유stay%": round(100 * x.stays / len(DEN), 1)})
    if r.empty:
        rows.append({"소스": "procedureevents", "label": "인공호흡 itemid 기록 0건"})
else:
    rows.append({"소스": "procedureevents", "label": "테이블 없음"})
if has("d_items"):
    di = pd.read_sql("select itemid,label,linksto from d_items "
                     "where lower(label) like '%ventilat%'", con)
    print(f"d_items 에서 'ventilat' 포함 항목 {len(di)}개 (참고, 상위 10):")
    print(di.head(10).to_string(index=False))
else:
    print("d_items 테이블 없음")
t = pd.DataFrame(rows)
print("\n" + t.to_string(index=False))
save(t, "chk15_b_ventilation.csv")

# ============================================================ (c) SOFA
head("[c] SOFA 가용성")
sofa_tabs = [t_ for t_ in TABLES if "sofa" in t_.lower()]
print(f"이름에 'sofa' 가 들어간 테이블: {sofa_tabs if sofa_tabs else '없음 (MIMIC-IV 원본에는 SOFA 파생 테이블이 없음)'}")

# 구성요소별로 어느 테이블이 필요한지 + 그 테이블이 이 DB에 있는지
COMP = [
    ("호흡 (PaO2/FiO2)", "labevents + chartevents", None),
    ("응고 (혈소판)", "labevents", None),
    ("간 (빌리루빈)", "labevents", None),
    ("심혈관 (MAP/승압제)", "chartevents + inputevents", None),
    ("신경 (GCS)", "chartevents", "기존 스캔에서 보유율 100% 확인됨"),
    ("신장 (크레아티닌/소변량)", "labevents + outputevents", None),
]
rows = []
for name, need, note in COMP:
    tabs = [x.strip() for x in need.split("+")]
    ok = all(has(x) for x in tabs)
    rows.append({"구성요소": name, "필요 테이블": need,
                 "테이블 존재": "O" if ok else "X", "비고": note or ""})
t = pd.DataFrame(rows)
print(t.to_string(index=False))

# 승압제는 inputevents 라 싸게 규모까지 확인 가능
VASO = {221906: "norepinephrine", 221289: "epinephrine", 221662: "dopamine",
        221653: "dobutamine", 222315: "vasopressin"}
if has("inputevents"):
    r = pd.read_sql(f"""select itemid, count(distinct stay_id) stays from inputevents
                        where itemid in ({','.join(map(str, VASO))}) group by itemid""", con)
    r["drug"] = r.itemid.map(VASO)
    r["DEN보유stay%"] = (100 * r.stays / len(DEN)).round(1)
    print("\n승압제 (inputevents, 심혈관 SOFA 재료):")
    print(r[["drug", "stays", "DEN보유stay%"]].to_string(index=False))
print("\n※ labevents 항목별 실제 보유율은 풀스캔이 필요해 여기서는 테이블 존재까지만 확인.")
print("   SOFA 를 쓰기로 결정되면 별도 스캔 스크립트로 확인할 것.")
save(t, "chk15_c_sofa.csv")

head("끝. 출력 CSV")
print("\n".join(sorted(f for f in os.listdir(OUT) if f.startswith("chk15") and f.endswith(".csv"))))
