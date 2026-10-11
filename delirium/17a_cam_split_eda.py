# -*- coding: utf-8 -*-
# ============================================================================
# CAM 평가 단위 split 설계 타당성 EDA
# 코랩 셀 단위로 잘라 쓸 수 있게 구획을 나눠 두었다.
# ============================================================================

# ===================== CELL 1 : 설정 =====================
import os, sys
import numpy as np
import pandas as pd

# 중간 파일이 있는 폴더 (00_extract.py 가 만든 것)
DATA = os.environ.get("EDA_DATA", "/content/drive/MyDrive/mimic_eda")
# 중간 파일이 없을 때만 쓰는 원본 DB 경로
DB_PATH = os.environ.get("EDA_SQLITE", "/content/drive/MyDrive/Datasets-new/MIMIC4-hosp-icu.db")
OUT = os.environ.get("EDA_OUT", os.path.join(DATA, "out_split"))
os.makedirs(OUT, exist_ok=True)

CAM_ITEM = 228332          # Delirium assessment (Positive / Negative / UTA)
LOOKAHEAD = [12.0, 24.0]   # '앞으로 X시간 안에 P가 있나' 대안 타깃용

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
pd.set_option("display.width", 200)


def head(t):
    print("\n" + "=" * 76); print(t); print("=" * 76)


def save(df, name):
    df.to_csv(os.path.join(OUT, name), encoding="utf-8-sig")
    print(f"  -> {name}")


def q(s):
    """median (IQR) 문자열"""
    s = pd.Series(s).dropna()
    if not len(s):
        return "-"
    return f"{s.median():.1f} ({s.quantile(.25):.1f}-{s.quantile(.75):.1f})"


# ===================== CELL 2 : 로드 =====================
def load_base():
    for p, fn in [(f"{DATA}/_icu_base.parquet", pd.read_parquet),
                  (f"{DATA}/_icu_base.pkl", pd.read_pickle)]:
        if os.path.exists(p):
            try:
                return fn(p)
            except Exception as e:
                print(f"[주의] {p} 못 읽음 ({type(e).__name__})")
    return None


def load_from_db():
    """중간 파일이 없을 때: DB 에서 필요한 것만 직접 읽는다."""
    import sqlite3
    if not os.path.exists(DB_PATH):
        sys.exit(f"중간 파일도 DB 도 없음.\n  DATA={DATA}\n  DB_PATH={DB_PATH}")
    print("중간 파일이 없어 DB 에서 직접 읽는다. chartevents 스캔에 시간이 걸린다.")
    uri = f"file:{DB_PATH}?immutable=1"
    try:
        con = sqlite3.connect(uri, uri=True); con.execute("select 1")
    except sqlite3.OperationalError:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.execute("pragma cache_size=-400000")
    b = pd.read_sql("""select i.subject_id, i.hadm_id, i.stay_id, i.first_careunit,
                              i.intime, i.outtime, i.los,
                              p.gender, p.anchor_age, p.anchor_year, p.anchor_year_group,
                              a.hospital_expire_flag
                       from icustays i
                       join patients p on p.subject_id = i.subject_id
                       join admissions a on a.hadm_id = i.hadm_id""", con)
    v = pd.read_sql(f"""select stay_id, charttime, value from chartevents
                        where itemid = {CAM_ITEM} and stay_id is not null""", con)
    v["itemid"] = CAM_ITEM
    return b, v


b = load_base()
if b is not None and os.path.exists(f"{DATA}/_label_values.parquet"):
    v = pd.read_parquet(f"{DATA}/_label_values.parquet")
    v = v[v.itemid == CAM_ITEM][["stay_id", "charttime", "value"]]
    print("중간 파일에서 로드했다.")
else:
    b, v = load_from_db()

# 기본 파생
b["intime"] = pd.to_datetime(b["intime"])
b["outtime"] = pd.to_datetime(b["outtime"])
if "age" not in b.columns:
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
if "icu_seq_in_subject" not in b.columns:
    b = b.sort_values(["subject_id", "intime"])
    b["icu_seq_in_subject"] = b.groupby("subject_id")["intime"].rank(method="first").astype(int)
b["era"] = b["anchor_year_group"].astype(str).str.replace(" ", "", regex=False)
CU = {"Medical Intensive Care Unit (MICU)": "MICU",
      "Medical/Surgical Intensive Care Unit (MICU/SICU)": "MICU/SICU",
      "Surgical Intensive Care Unit (SICU)": "SICU",
      "Cardiac Vascular Intensive Care Unit (CVICU)": "CVICU",
      "Coronary Care Unit (CCU)": "CCU", "Trauma SICU (TSICU)": "TSICU",
      "Neuro Intermediate": "NeuroInt",
      "Neuro Surgical Intensive Care Unit (Neuro SICU)": "NeuroSICU",
      "Neuro Stepdown": "NeuroStep"}
b["cu"] = b["first_careunit"].map(CU).fillna("기타")

# 분석 무대: 성인 + ICU 재원 1일 이상 (제한은 CELL 9 에서 따로 본다)
DEN = b[(b.age >= 18) & (b.los >= 1.0)].copy()
intime = b.set_index("stay_id")["intime"]
outtime = b.set_index("stay_id")["outtime"]
print(f"분석 무대: {len(DEN):,} stays / {DEN.subject_id.nunique():,} 환자")

# CAM 기록 정리
MAP = {"Positive": "P", "Negative": "N", "UTA": "U",
       "Unable to Assess": "U", "Unable to assess": "U"}
cam = v.copy()
cam["charttime"] = pd.to_datetime(cam["charttime"])
cam["v"] = cam["value"].astype(str).str.strip().map(MAP)
bad = cam.loc[cam["v"].isna(), "value"].value_counts()
if len(bad):
    print("[주의] P/N/UTA 로 매핑 안 된 값:"); print(bad.head().to_string())
cam = cam[cam["v"].notna() & cam.stay_id.isin(DEN.stay_id)].copy()
cam["hr"] = (cam["charttime"] - cam["stay_id"].map(intime)).dt.total_seconds() / 3600
cam = cam[cam.hr >= 0].sort_values(["stay_id", "hr"]).reset_index(drop=True)
print(f"CAM 기록 {len(cam):,}건 / {cam.stay_id.nunique():,} stays")


# ===================== CELL 3 : 확정 평가 · 전이 테이블 =====================
head("[준비] 확정 CAM(P/N)만 남기고 연속 쌍을 만든다")

cam["is_u"] = (cam["v"] == "U").astype(int)
cam["uta_cum"] = cam.groupby("stay_id")["is_u"].cumsum()

conf = cam[cam.v != "U"].copy()                       # 확정 평가만
conf["idx"] = conf.groupby("stay_id").cumcount()      # stay 내 확정 평가 순번 (0부터)
conf["prev_v"] = conf.groupby("stay_id")["v"].shift()
conf["prev_hr"] = conf.groupby("stay_id")["hr"].shift()
conf["prev_uta_cum"] = conf.groupby("stay_id")["uta_cum"].shift()

print(f"확정 CAM(P/N) {len(conf):,}건 / {conf.stay_id.nunique():,} stays")
print(f"  Positive {int((conf.v == 'P').sum()):,} ({100*(conf.v=='P').mean():.1f}%) / "
      f"Negative {int((conf.v == 'N').sum()):,}")
print(f"UTA 기록 {int(cam.is_u.sum()):,}건은 예측 대상에서 제외 (입력으로는 사용 가능)")

tr = conf[conf.prev_v.notna()].copy()                 # 전이 = 연속한 확정 평가 쌍
tr["trans"] = tr["prev_v"] + "->" + tr["v"]
tr["gap_h"] = tr["hr"] - tr["prev_hr"]
tr["uta_between"] = tr["uta_cum"] - tr["prev_uta_cum"]
print(f"전이(연속 확정 평가 쌍) {len(tr):,}건 / {tr.stay_id.nunique():,} stays")


# ===================== CELL 4 : EDA 1 — stay 당 확정 CAM 횟수 =====================
head("[1] stay 당 확정 CAM(P/N) 평가 횟수")

n_conf = conf.groupby("stay_id").size()
n_conf = n_conf.reindex(DEN.stay_id).fillna(0).astype(int)   # CAM 없는 stay 는 0
bins = pd.cut(n_conf, [-1, 0, 1, 2, 3, 1e9], labels=["0회", "1회", "2회", "3회", "4회 이상"])
t = bins.value_counts().reindex(["0회", "1회", "2회", "3회", "4회 이상"]).to_frame("stays")
t["비율%"] = (100 * t.stays / len(DEN)).round(1)
print(t.to_string())
print(f"\n확정 CAM 횟수  median (IQR) : {q(n_conf)}")
nz = n_conf[n_conf > 0]
print(f"CAM 보유 stay 만  median (IQR) : {q(nz)}")
print(f"확정 평가가 2회 이상인 stay (전이 생성 가능): "
      f"{int((n_conf >= 2).sum()):,} ({100*(n_conf>=2).mean():.1f}%)")

pat = conf.merge(DEN[["stay_id", "subject_id"]], on="stay_id").groupby("subject_id").size()
print(f"\n환자 단위: 확정 CAM 보유 환자 {len(pat):,}명, 환자당 median (IQR) {q(pat)}")
save(t, "split1_n_assess.csv")


# ===================== CELL 5 : EDA 2 — transition 분포 =====================
head("[2] 확정 CAM 사이의 transition 분포")

order = ["N->N", "N->P", "P->N", "P->P"]
t = pd.DataFrame({
    "transition 수": tr.groupby("trans").size().reindex(order).fillna(0).astype(int),
    "stay 수": tr.groupby("trans")["stay_id"].nunique().reindex(order).fillna(0).astype(int),
})
t["transition%"] = (100 * t["transition 수"] / len(tr)).round(1)
print(t.to_string())
print(f"\n다음이 Positive 일 비율 — 이전 N: {100*(tr[tr.prev_v=='N'].v=='P').mean():.1f}%"
      f" / 이전 P: {100*(tr[tr.prev_v=='P'].v=='P').mean():.1f}%")
print(f"전체 transition 중 타깃이 Positive: {100*(tr.v=='P').mean():.1f}%  (클래스 균형)")
save(t, "split2_transitions.csv")

# UTA 를 사이에 낀 전이가 얼마나 되나 (입력에서 UTA 를 살릴 근거)
t2 = tr.groupby("trans")["uta_between"].apply(lambda s: pd.Series({
    "UTA 낀 비율%": round(100 * (s > 0).mean(), 1),
    "낀 UTA 수 median": s[s > 0].median() if (s > 0).any() else 0,
})).unstack().reindex(order)
print("\n두 확정 평가 사이에 UTA 가 끼어 있었나:")
print(t2.to_string()); save(t2, "split2_uta_between.csv")


# ===================== CELL 6 : EDA 3 — transition 별 시간 간격 =====================
head("[3] transition 별 시간 간격 (예측 지평)")

rows = []
for k in order:
    s = tr.loc[tr.trans == k, "gap_h"]
    rows.append({"transition": k, "n": len(s), "median_h": round(s.median(), 1),
                 "IQR": f"{s.quantile(.25):.1f}-{s.quantile(.75):.1f}",
                 "<=12h%": round(100 * (s <= 12).mean(), 1),
                 "<=24h%": round(100 * (s <= 24).mean(), 1),
                 ">48h%": round(100 * (s > 48).mean(), 1)})
t = pd.DataFrame(rows).set_index("transition")
print(t.to_string())
g = tr["gap_h"]
print(f"\n전체: median {g.median():.1f}h, IQR {g.quantile(.25):.1f}-{g.quantile(.75):.1f}, "
      f"24h 초과 {100*(g>24).mean():.1f}%")
print("※ 간격이 넓게 퍼져 있으면 '다음 평가 결과' 예측은 환자마다 예측 지평이 달라진다.")
save(t, "split3_gap.csv")

# 대안 타깃: '앞으로 X시간 안에 Positive 가 있나'
head("[3-b] 대안 타깃 — 각 확정 평가 시점에서 앞으로 X시간 안에 Positive 가 있나")
# stay 블록 안에서 searchsorted + 누적합으로 O(n) 계산 (58만 건에서도 몇 초)
_c = conf.sort_values(["stay_id", "hr"]).reset_index(drop=True)
_h = _c["hr"].to_numpy(dtype=float)
_isP = (_c["v"].to_numpy() == "P").astype(np.int64)
_cumP = np.concatenate([[0], _isP.cumsum()])
_uniq, _first, _cnt = np.unique(_c["stay_id"].to_numpy(), return_index=True, return_counts=True)

rows = []
for W in LOOKAHEAD:
    any_l, pos_l = [], []
    for a, n in zip(_first, _cnt):
        hh = _h[a:a + n]
        idx = np.arange(n)
        j = np.searchsorted(hh, hh + W, side="right")       # 창 끝 위치
        any_l.append(j > idx + 1)                            # 창 안에 다음 확정평가가 있나
        pos_l.append((_cumP[a + j] - _cumP[a + idx + 1]) > 0)
    has_any = np.concatenate(any_l); has_pos = np.concatenate(pos_l)
    rows.append({"창": f"앞으로 {int(W)}h",
                 "평가 시점 수": len(has_any),
                 "창 안에 확정평가 있음%": round(100 * has_any.mean(), 1),
                 "그중 Positive 있음%": round(100 * has_pos[has_any].mean(), 1)})
t = pd.DataFrame(rows).set_index("창")
print(t.to_string())
print("※ 이 방식이면 예측 지평이 모든 instance 에서 같아진다.")
save(t, "split3b_lookahead.csv")


# ===================== CELL 7 : EDA 4 — prediction instance 수와 집중도 =====================
head("[4] stay 당 prediction instance 수")

inst_a = conf.groupby("stay_id").size()          # 정의 A: 모든 확정 평가가 타깃
inst_b = (inst_a - 1).clip(lower=0)              # 정의 B: 이전 확정 평가가 있어야 타깃
inst_b = inst_b[inst_b > 0]
print(f"정의 A (모든 확정 평가가 타깃)      : instance {int(inst_a.sum()):,}개 / stay {len(inst_a):,}")
print(f"정의 B (이전 확정 평가가 있을 때만) : instance {int(inst_b.sum()):,}개 / stay {len(inst_b):,}")
print(f"\nstay 당 instance 수 (정의 B) median (IQR): {q(inst_b)}")

s = inst_b.sort_values(ascending=False)
cum = s.cumsum() / s.sum()
rows = []
for p in [0.01, 0.05, 0.10, 0.25]:
    k = max(int(len(s) * p), 1)
    rows.append({"상위": f"{int(p*100)}% stay", "stay 수": k,
                 "이 stay 들이 차지하는 instance%": round(100 * cum.iloc[k - 1], 1)})
t = pd.DataFrame(rows).set_index("상위")
print("\n집중도 — 일부 장기 재원 stay 가 데이터를 지배하는가:")
print(t.to_string())
print(f"instance 가 가장 많은 stay: {int(s.iloc[0])}개")
save(t, "split4_concentration.csv")

t2 = pd.cut(inst_b, [0, 1, 2, 5, 10, 20, 1e9],
            labels=["1", "2", "3-5", "6-10", "11-20", "21+"]).value_counts().sort_index().to_frame("stays")
t2["비율%"] = (100 * t2.stays / len(inst_b)).round(1)
print("\nstay 당 instance 수 분포 (정의 B):"); print(t2.to_string())
save(t2, "split4_instance_dist.csv")

# 예측 시점이 재원 기간 중 어디에 분포하나
t3 = pd.cut(tr["hr"], [0, 24, 48, 72, 120, 240, 1e9],
            labels=["0-24h", "24-48h", "48-72h", "72-120h", "120-240h", "240h+"]) \
       .value_counts().sort_index().to_frame("instances")
t3["비율%"] = (100 * t3.instances / len(tr)).round(1)
t3["Positive%"] = tr.groupby(pd.cut(tr["hr"], [0, 24, 48, 72, 120, 240, 1e9],
                             labels=t3.index.tolist()), observed=True)["v"] \
                    .apply(lambda s: round(100 * (s == "P").mean(), 1))
print("\n예측 시점의 입실 후 경과시간 분포:"); print(t3.to_string())
save(t3, "split4_time_dist.csv")


# ===================== CELL 8 : EDA 5 — P->N->P 모수 =====================
head("[5] P->N->P (회복 후 재발) 모수")

# (a) 연속한 확정 평가 3개가 정확히 P,N,P
conf["v2"] = conf.groupby("stay_id")["v"].shift(2)
strict = conf[(conf.v == "P") & (conf.prev_v == "N") & (conf.v2 == "P")]
# (b) 순서만 만족 (P ... N ... P), 중간에 다른 평가가 끼어도 됨
fP = conf[conf.v == "P"].groupby("stay_id")["hr"].min()
tmp = conf[conf.v == "N"].copy(); tmp["fp"] = tmp["stay_id"].map(fP)
fN = tmp[tmp.hr > tmp.fp].groupby("stay_id")["hr"].min()
tmp2 = conf[conf.v == "P"].copy(); tmp2["fn"] = tmp2["stay_id"].map(fN)
fP2 = tmp2[tmp2.hr > tmp2.fn].groupby("stay_id")["hr"].min()

n_all = len(DEN); n_pos = conf[conf.v == "P"].stay_id.nunique()
rows = [
    {"정의": "연속 3개가 P,N,P (엄격)", "stay 수": strict.stay_id.nunique()},
    {"정의": "순서만 P...N...P (느슨)", "stay 수": len(fP2)},
]
for r in rows:
    r["전체 stay 대비%"] = round(100 * r["stay 수"] / n_all, 1)
    r["Positive 경험 stay 대비%"] = round(100 * r["stay 수"] / max(n_pos, 1), 1)
t = pd.DataFrame(rows).set_index("정의")
print(f"Positive 를 겪은 stay: {n_pos:,} / 전체 {n_all:,}")
print(t.to_string())

dt = (fP2 - fN.reindex(fP2.index)).dropna()
print(f"\n회복(N) -> 재발(P) 까지 시간: median (IQR) {q(dt)}h")
for h in [12, 24, 48]:
    print(f"  {h}h 이내 재발: {100*(dt<=h).mean():.1f}%")
save(t, "split5_pnp.csv")

print("\n※ split 설계에서는 P->N->P 를 따로 코호트로 뽑을 필요가 없다.")
print("   '이전 이력에 P 와 N 이 모두 있는 예측 시점'으로 자동 포함된다.")


# ===================== CELL 9 : 코호트 제한별 규모 =====================
head("[6] 코호트 제한을 걸면 표본이 어떻게 줄어드나 (제한을 확정하지 않고 나열만)")

MICU = ["MICU", "MICU/SICU"]
ERA = ["2011-2013", "2014-2016", "2017-2019"]
defs = {
    "성인 + LOS>=1d": DEN,
    "  + 환자당 첫 stay": DEN[DEN.icu_seq_in_subject == 1],
    "  + 2011-2019": DEN[DEN.era.isin(ERA)],
    "  + 첫 stay + 2011-2019": DEN[(DEN.icu_seq_in_subject == 1) & DEN.era.isin(ERA)],
    "  + 첫 stay + 2011-2019 + MICU계열": DEN[(DEN.icu_seq_in_subject == 1)
                                            & DEN.era.isin(ERA) & DEN.cu.isin(MICU)],
}
rows = []
for name, d in defs.items():
    tt = tr[tr.stay_id.isin(d.stay_id)]
    rows.append({"코호트": name, "stays": len(d), "환자": d.subject_id.nunique(),
                 "transition(instance)": len(tt),
                 "instance 있는 stay": tt.stay_id.nunique(),
                 "N->P": int((tt.trans == "N->P").sum()),
                 "타깃 Positive%": round(100 * (tt.v == "P").mean(), 1) if len(tt) else None})
t = pd.DataFrame(rows).set_index("코호트")
print(t.to_string()); save(t, "split6_cohort_sizes.csv")


# ===================== CELL 10 : 환자 단위 분할 점검 =====================
head("[7] 환자 단위 train/val/test 분할이 실제로 필요한가")

m = tr.merge(DEN[["stay_id", "subject_id"]], on="stay_id")
per_pat = m.groupby("subject_id").size()
print(f"instance 를 가진 환자 {len(per_pat):,}명, 환자당 instance median (IQR) {q(per_pat)}")
print(f"instance 가 2개 이상인 환자: {100*(per_pat>=2).mean():.1f}%  "
      f"-> 기록 단위로 나누면 같은 환자가 train/test 양쪽에 들어간다")
multi = DEN.groupby("subject_id").size()
print(f"stay 를 2개 이상 가진 환자: {int((multi>1).sum()):,}명 "
      f"({100*(multi>1).mean():.1f}%) -> 환자 단위 분할이 stay 단위보다 안전")

head("끝. 저장된 CSV")
print("\n".join(sorted(f for f in os.listdir(OUT) if f.endswith(".csv"))))
