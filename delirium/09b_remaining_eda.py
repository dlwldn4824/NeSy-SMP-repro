# -*- coding: utf-8 -*-
"""남은 EDA 항목. 원본 DB 재스캔 없이 중간 파일만으로 돈다.

  항목2  ICU 입실 -> 첫 CAM 까지 시간 + 그 첫 결과 P/N/UTA
  항목4  CAM 시계열 전이 패턴 (P->N, N->P, UTA->P) + 스펙 ⑤(첫 24h Positive 제외) 타당성 검증
  항목5  CAM 평가 간격
  항목1' stay 단위 P/N/UTA 삼분할
  항목7' LOS 구간별 CAM coverage 와 P/N/UTA 구성
  항목8' 시기 / 진료과별 UTA
  항목9  첫 24h 기준 predictor coverage (전체 재원 기준 보유율과 비교)

필요 파일: _icu_base.pkl(또는 .parquet), _label_values.parquet,
          _padis_item_stay_counts.parquet, _step1_sed.parquet
출력: chk2_*.csv ~ chk9_*.csv (전부 집계표. 환자 식별자 없음)
"""
import os, sys
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
pd.set_option("display.width", 220)

DATA = os.environ.get("EDA_DATA", "notes/eda")
OUT = os.environ.get("EDA_OUT", DATA)
os.makedirs(OUT, exist_ok=True)
W = 24.0          # observation window (h). 스펙 ④와 동일
CSV = dict(encoding="utf-8-sig")


def head(t):
    print("\n" + "=" * 78); print(t); print("=" * 78)


def pct(x):
    return round(100 * float(x), 1)


def save(df, name):
    df.to_csv(f"{OUT}/{name}", **CSV)
    print(f"  -> {name}")


# ============================================================ 로드
def load_base():
    """pickle 은 pandas 버전이 다르면 못 읽는다 (로컬에서 만들고 코랩에서 읽는 경우).
    실패하면 parquet 으로 넘어간다."""
    pkl, pq = f"{DATA}/_icu_base.pkl", f"{DATA}/_icu_base.parquet"
    if os.path.exists(pkl):
        try:
            return pd.read_pickle(pkl)
        except Exception as e:
            print(f"[주의] {pkl} 을 못 읽음 ({type(e).__name__}). parquet 으로 시도한다.")
    if os.path.exists(pq):
        return pd.read_parquet(pq)
    sys.exit(f"_icu_base 를 못 찾음: {pkl} / {pq}")


b = load_base()
b["intime"] = pd.to_datetime(b["intime"])
b["era"] = b["anchor_year_group"].astype(str).str.replace(" ", "", regex=False)

CU = {"Medical Intensive Care Unit (MICU)": "MICU",
      "Medical/Surgical Intensive Care Unit (MICU/SICU)": "MICU/SICU",
      "Surgical Intensive Care Unit (SICU)": "SICU",
      "Cardiac Vascular Intensive Care Unit (CVICU)": "CVICU",
      "Coronary Care Unit (CCU)": "CCU",
      "Trauma SICU (TSICU)": "TSICU",
      "Neuro Intermediate": "NeuroInt",
      "Neuro Surgical Intensive Care Unit (Neuro SICU)": "NeuroSICU",
      "Neuro Stepdown": "NeuroStep"}
b["cu"] = b["first_careunit"].map(CU).fillna("기타")

DEN = b[(b.age >= 18) & (b.los >= 1.0)].copy()          # 분모 = adult ICU, LOS>=1d
intime = b.set_index("stay_id")["intime"]
print(f"분모 (adult, ICU LOS>=1d) : {len(DEN):,} stays / {DEN.subject_id.nunique():,} 환자")

v = pd.read_parquet(f"{DATA}/_label_values.parquet")
dl = v[v.itemid == 228332][["stay_id", "charttime", "value"]].copy()
dl["charttime"] = pd.to_datetime(dl["charttime"])

# 값 정규화 (기대값 3개 외에 뭐가 있으면 알려준다)
MAP = {"Positive": "P", "Negative": "N", "UTA": "U",
       "Unable to Assess": "U", "Unable to assess": "U"}
raw = dl["value"].astype(str).str.strip()
dl["v"] = raw.map(MAP)
unmapped = raw[dl["v"].isna()].value_counts()
if len(unmapped):
    print("\n[주의] P/N/UTA 로 매핑 안 된 값:"); print(unmapped.head(10).to_string())
dl = dl[dl["v"].notna()]

dl = dl[dl.stay_id.isin(DEN.stay_id)].copy()
dl["hr"] = (dl["charttime"] - dl["stay_id"].map(intime)).dt.total_seconds() / 3600
n_before = (dl.hr < 0).sum()
if n_before:
    print(f"[주의] intime 이전 기록 {n_before:,}건 제외")
dl = dl[dl.hr >= 0].sort_values(["stay_id", "charttime"]).reset_index(drop=True)
print(f"섬망평가 기록 {len(dl):,}건 / {dl.stay_id.nunique():,} stays")

# RASS (첫 평가 시점 진정 깊이 확인용)
rs = v[v.itemid == 228096][["stay_id", "charttime", "value"]].copy()
rs["charttime"] = pd.to_datetime(rs["charttime"])
rs["rass"] = rs["value"].astype(str).str.extract(r"^\s*([+-]?\d)").astype(float)
rs = rs[["stay_id", "charttime", "rass"]].dropna()

RASS_BINS = [-5.5, -3.5, -2.5, -0.5, 4.5]
RASS_LAB = ["RASS -5~-4", "RASS -3", "RASS -2~-1", "RASS 0~+4"]


# ============================================================ 항목 2
head("[항목2] ICU 입실 -> 첫 CAM 까지 시간 + 첫 결과")
first = dl.drop_duplicates("stay_id", keep="first").set_index("stay_id")

cov = len(first) / len(DEN)
print(f"CAM 기록이 1회 이상 있는 stay : {pct(cov)}%  ({len(first):,} / {len(DEN):,})")
print(f"첫 CAM 까지 시간  median {first.hr.median():.1f}h  "
      f"(q1 {first.hr.quantile(.25):.1f} / q3 {first.hr.quantile(.75):.1f})")

rows = []
for h in [2, 4, 6, 12, 24, 48]:
    rows.append({"기준": f"{h}h 이내 첫 CAM", "stay%_of_CAM보유": pct((first.hr <= h).mean()),
                 "stay%_of_전체": pct((first.hr <= h).sum() / len(DEN))})
t = pd.DataFrame(rows)
print("\n" + t.to_string(index=False)); save(t, "chk2_first_cam_timing.csv")

vc = first["v"].value_counts()
t = pd.DataFrame({"n": vc, "비율%": (100 * vc / len(first)).round(1),
                  "첫CAM시각_median_h": first.groupby("v").hr.median().round(1),
                  "첫CAM시각_q3_h": first.groupby("v").hr.quantile(.75).round(1)})
t.index.name = "첫 CAM 결과"
print("\n첫 CAM 결과 분포:"); print(t.to_string()); save(t, "chk2_first_cam_result.csv")

# 첫 CAM 이 UTA 인 stay 는 그 시각에 얼마나 진정되어 있었나
m = first.reset_index()[["stay_id", "charttime", "v"]].merge(rs, on=["stay_id", "charttime"], how="left")
print(f"\n첫 CAM 과 같은 charttime 에 RASS 가 붙은 비율: {pct(m.rass.notna().mean())}%")
ct = pd.crosstab(m["v"], pd.cut(m["rass"], RASS_BINS, labels=RASS_LAB), normalize="index").mul(100).round(1)
print(ct.to_string()); save(ct, "chk2_first_cam_rass.csv")


# ============================================================ 항목 5 (간격)
head("[항목5] CAM 평가 간격")
dl["gap"] = dl.groupby("stay_id")["hr"].diff()
g = dl["gap"].dropna()
print(f"연속 평가 간격  median {g.median():.1f}h  (q1 {g.quantile(.25):.1f} / q3 {g.quantile(.75):.1f})")
rows = [{"구간": lbl, "비율%": pct(msk.mean())} for lbl, msk in [
    ("<= 4h", g <= 4), ("4~8h", (g > 4) & (g <= 8)), ("8~12h", (g > 8) & (g <= 12)),
    ("12~24h", (g > 12) & (g <= 24)), ("> 24h", g > 24)]]
t = pd.DataFrame(rows)
print(t.to_string(index=False))
per_stay = dl.groupby("stay_id")["gap"].median().dropna()
print(f"\nstay별 median 간격의 median : {per_stay.median():.1f}h  "
      f"(간격 median 이 12h 넘는 stay {pct((per_stay > 12).mean())}%)")
w1 = dl[dl.hr < W]["gap"].dropna(); w2 = dl[dl.hr >= W]["gap"].dropna()
print(f"첫 24h 안 간격 median {w1.median():.1f}h  /  24h 이후 간격 median {w2.median():.1f}h")
t2 = pd.DataFrame([{"구간": "전체", "median_h": round(g.median(), 1), "n": len(g)},
                   {"구간": "첫24h", "median_h": round(w1.median(), 1), "n": len(w1)},
                   {"구간": "24h이후", "median_h": round(w2.median(), 1), "n": len(w2)}])
save(pd.concat([t.assign(표="간격분포"), t2.assign(표="구간별")], ignore_index=True),
     "chk5_cam_interval.csv")


# ============================================================ 항목 1'
head("[항목1'] stay 단위 P/N/UTA 삼분할")
cntv = dl.groupby(["stay_id", "v"]).size().unstack(fill_value=0).reindex(columns=["P", "N", "U"], fill_value=0)
has = cntv > 0
t = pd.DataFrame({"stay%": [pct(has.P.mean()), pct(has.N.mean()), pct(has.U.mean())]},
                 index=["Positive 1회 이상", "Negative 1회 이상", "UTA 1회 이상"])
print(t.to_string())

def pat(r):
    if r.P and not r.U:  return "P 있음 (UTA 없음)"
    if r.P and r.U:      return "P 있음 + UTA 섞임"
    if r.N and not r.U:  return "N 만"
    if r.N and r.U:      return "N + UTA (P 없음)"
    return "전부 UTA"
p = has.apply(pat, axis=1).value_counts()
t2 = pd.DataFrame({"stays": p, "비율%": (100 * p / len(has)).round(1)})
print("\nstay 유형:"); print(t2.to_string())
uf = (cntv.U / cntv.sum(axis=1))
print(f"\nstay별 UTA 비율  median {pct(uf.median())}%  q3 {pct(uf.quantile(.75))}%")
out1 = pd.concat([
    pd.DataFrame({"지표": t.index, "값": t["stay%"].values, "단위": "stay%"}),
    pd.DataFrame({"지표": t2.index, "값": t2["비율%"].values, "단위": "stay%"}),
    pd.DataFrame({"지표": ["UTA비율 median", "UTA비율 q3"],
                  "값": [pct(uf.median()), pct(uf.quantile(.75))], "단위": "%"}),
], ignore_index=True)
save(out1.set_index("지표"), "chk1_stay_level_pnu.csv")


# ============================================================ 항목 4
head("[항목4] CAM 전이 패턴")
dl["prev"] = dl.groupby("stay_id")["v"].shift()
tr = pd.crosstab(dl["prev"], dl["v"])
tr = tr.reindex(index=["P", "N", "U"], columns=["P", "N", "U"], fill_value=0)
print("전이 건수 (행=이전, 열=다음):"); print(tr.to_string())
trp = tr.div(tr.sum(axis=1), axis=0).mul(100).round(1)
print("\n행 정규화 % — '이전이 X일 때 다음이 Y일 확률':"); print(trp.to_string())
save(trp, "chk4_transition_matrix.csv")

# 첫 Positive 이후에 Negative 로 돌아오는가
fp = dl[dl.v == "P"].groupby("stay_id")["hr"].min()
d2 = dl[dl.stay_id.isin(fp.index)].copy()
d2["fp"] = d2["stay_id"].map(fp)
after = d2[d2.hr > d2.fp]
recov = after[after.v == "N"].stay_id.nunique()
print(f"\nPositive 가 1회 이상인 stay {len(fp):,}개 중")
print(f"  첫 P 이후 Negative 가 나온 stay : {recov:,} ({pct(recov/len(fp))}%)")
print(f"  첫 P 이후 기록이 아예 없는 stay : {pct(1 - after.stay_id.nunique()/len(fp))}%")
blk = (dl["v"] != dl["prev"]).cumsum()
runs = dl.assign(blk=blk).groupby(["stay_id", "blk"])["v"].first()
pruns = runs[runs == "P"].groupby("stay_id").size()
t = pruns.value_counts().sort_index().head(6)
t = pd.DataFrame({"stays": t, "비율%": (100 * t / len(fp)).round(1)})
t.index.name = "연속 Positive 구간(에피소드) 개수"
print("\n" + t.to_string()); save(t, "chk4_positive_episodes.csv")

# --- 스펙 ⑤ 검증: 첫 24h 에 Positive 라서 제외되는 사람들은 그 뒤에 어떻게 되나
head("[항목4-b] 스펙 ⑤ '첫 24h Positive 제외' 가 타당한가")
base3 = b[(b.age >= 18) & (b.icu_seq_in_subject == 1) & (b.los >= 1.0)]
d3 = dl[dl.stay_id.isin(base3.stay_id)]
obs = d3[d3.hr < W]; fut = d3[d3.hr >= W]
prev_pos = obs[obs.v == "P"].stay_id.unique()
print(f"③ 통과 {len(base3):,} stays 중 첫 24h Positive(=⑤ 제외 대상) : {len(prev_pos):,}")

f = fut[fut.stay_id.isin(prev_pos)]
fut_first = f.drop_duplicates("stay_id", keep="first").set_index("stay_id")["v"]
n_norec = len(prev_pos) - f.stay_id.nunique()
vc = fut_first.value_counts()
rows = [{"24h 이후 첫 판정": k, "stays": int(vc.get(k, 0)),
         "비율%": pct(vc.get(k, 0)/len(prev_pos))} for k in ["P", "N", "U"]]
rows.append({"24h 이후 첫 판정": "기록 없음", "stays": int(n_norec),
             "비율%": pct(n_norec/len(prev_pos))})
t = pd.DataFrame(rows); print("\n" + t.to_string(index=False))

anyN = f[f.v == "N"].stay_id.nunique()
allP = f.groupby("stay_id")["v"].apply(lambda s: set(s) == {"P"}).sum()
print(f"\n24h 이후 Negative 가 1회라도 나온 stay : {anyN:,} ({pct(anyN/len(prev_pos))}% of 제외 대상)")
print(f"24h 이후 전부 Positive 인 stay        : {allP:,} ({pct(allP/len(prev_pos))}%)")
print("\n※ Negative 로 돌아온 비율이 높으면 '첫 24h Positive = prevalent delirium 이므로 영구 제외'")
print("   라는 스펙 ⑤의 전제가 약해진다. 그 사람들은 회복 후 재발을 예측할 수 있는 대상이다.")
save(t, "chk4_spec5_prevalent_followup.csv")

# UTA 다음에 무엇이 오나 (UTA 를 결측으로 지울 수 있는지)
nxt = dl[dl.prev == "U"]["v"].value_counts(normalize=True).mul(100).round(1)
print(f"\nUTA 다음 판정: " + " / ".join(f"{k} {nxt.get(k,0)}%" for k in ["P", "N", "U"]))


# ============================================================ 항목 7'
head("[항목7'] LOS 구간별 CAM coverage / 구성")
DEN["los_bin"] = pd.cut(
    DEN.los,
    [1, 2, 3, 5, 10, 1e9],
    labels=["1-2d", "2-3d", "3-5d", "5-10d", "10d+"],
    include_lowest=True,
)
lb = DEN.set_index("stay_id")["los_bin"]
dl["los_bin"] = dl["stay_id"].map(lb)
rec = dl.groupby("los_bin", observed=True)["v"].value_counts(normalize=True).unstack().mul(100).round(1)
stay_any = has.join(lb.rename("los_bin"), how="left").groupby("los_bin", observed=True).mean().mul(100).round(1)
covr = DEN.assign(hascam=DEN.stay_id.isin(dl.stay_id)).groupby("los_bin", observed=True).agg(
    stays=("stay_id", "size"), CAM보유stay=("hascam", "mean"))
covr["CAM보유stay%"] = (100 * covr["CAM보유stay"]).round(1)
t = covr[["stays", "CAM보유stay%"]].join(rec.add_prefix("기록%_")).join(stay_any.add_prefix("stay%_"))
print(t.to_string()); save(t, "chk7_los_coverage.csv")


# ============================================================ 항목 8'
head("[항목8'] 시기 / 진료과별 P/N/UTA")
for key, name in [("era", "시기"), ("cu", "진료과")]:
    k = DEN.set_index("stay_id")[key]
    dl[key] = dl["stay_id"].map(k)
    rec = dl.groupby(key, observed=True)["v"].value_counts(normalize=True).unstack().mul(100).round(1)
    sa = has.join(k, how="left").groupby(key, observed=True).mean().mul(100).round(1)
    allu = (cntv.U == cntv.sum(axis=1)).to_frame("all_UTA").join(k, how="left") \
             .groupby(key, observed=True)["all_UTA"].mean().mul(100).round(1)
    t = rec.add_prefix("기록%_").join(sa.add_prefix("stay%_")).join(allu.rename("전부UTA인stay%"))
    print(f"\n[{name}]"); print(t.to_string()); save(t, f"chk8_{key}_pnu.csv")


# ============================================================ 항목 9
head("[항목9] 첫 24h 기준 predictor coverage")
# ①~⑦ 코호트를 여기서 다시 만든다 (_delirium_cohort.pkl 의존 제거)
agg = d3.groupby(["stay_id", "v"]).size().unstack(fill_value=0)
o = obs.groupby(["stay_id", "v"]).size().unstack(fill_value=0).reindex(columns=["P", "N", "U"], fill_value=0)
fu = fut.groupby(["stay_id", "v"]).size().unstack(fill_value=0).reindex(columns=["P", "N", "U"], fill_value=0)
c = base3.set_index("stay_id").join(o.add_prefix("obs_")).join(fu.add_prefix("fut_")).fillna(0)
coh = c[(c.obs_P == 0) & ((c.fut_P + c.fut_N) >= 1)].copy()
coh["delirium"] = (coh.fut_P > 0).astype(int)
print(f"코호트 재현: {len(coh):,} stays / delirium {pct(coh.delirium.mean())}%  "
      f"(참고: 기존 EDA 23,939 / 22.5%)")

PC = f"{DATA}/_padis_item_stay_counts.parquet"
if not os.path.exists(PC):
    print(f"[건너뜀] {PC} 가 없어 항목9 를 계산할 수 없다. 00_extract.py 로 만들 것.")
    sys.exit(0)
cnt = pd.read_parquet(PC)
if "grp" not in cnt.columns:                      # 예전 파일 호환
    G = {"RASS": [228096], "DELIRIUM_ASSESS": [228332, 228688],
         "PAIN_NRS": [223791, 223794, 224409, 229702, 230144],
         "CPOT": [229689, 229690, 229691, 229692, 229694, 229695, 229696, 229697, 229698, 229699],
         "MOBILITY": [229319, 229321, 229633, 229742, 228697, 224057],
         "RESTRAINT": [227671, 227670, 224063, 227945, 227962, 224856],
         "GCS_total": [220739, 223900, 223901]}
    cnt["grp"] = cnt["itemid"].map({i: g for g, xs in G.items() for i in xs})
    cnt = cnt[cnt.grp.notna()]
cnt["t0"] = pd.to_datetime(cnt["t0"])
cnt["hr0"] = (cnt["t0"] - cnt["stay_id"].map(intime)).dt.total_seconds() / 3600
firstg = cnt.groupby(["stay_id", "grp"])["hr0"].min().unstack()

def cover(idx, label):
    f = firstg.reindex(idx)
    ever = f.notna().mean().mul(100).round(1)
    in24 = (f <= W).mean().mul(100).round(1)          # NaN 은 False
    return pd.DataFrame({f"{label}_전체재원%": ever, f"{label}_첫24h%": in24})

t = cover(DEN.stay_id, "DEN").join(cover(coh.index, "코호트"))
t.index.name = "predictor"
print("\n'전체 재원 중 1회라도' vs '첫 24h 안에 첫 기록':")
print(t.to_string()); save(t, "chk9_coverage_first24h.csv")

# 진정제 첫 24h 노출
SEDF = f"{DATA}/_step1_sed.parquet"
if not os.path.exists(SEDF):
    print(f"[건너뜀] {SEDF} 없음 — 진정제 부분 생략")
    sys.exit(0)
sed = pd.read_parquet(SEDF)
sed["starttime"] = pd.to_datetime(sed["starttime"])
sed["hr"] = (sed["starttime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
# DEN 비율의 분자와 분모를 동일한 성인·ICU LOS>=1일 집단으로 맞춘다.
sed_den = sed[sed.stay_id.isin(DEN.stay_id)].copy()
rows = []
for drug, s in sed_den.groupby("drug"):
    ever = s.stay_id.nunique()
    e24 = s[(s.hr >= 0) & (s.hr < W)].stay_id.nunique()
    c24 = s[(s.hr >= 0) & (s.hr < W) & s.stay_id.isin(coh.index)].stay_id.nunique()
    rows.append({"drug": drug, "DEN_전체재원%": pct(ever/len(DEN)),
                 "DEN_첫24h%": pct(e24/len(DEN)), "코호트_첫24h%": pct(c24/len(coh))})
t = pd.DataFrame(rows).sort_values("DEN_첫24h%", ascending=False)
print("\n진정제 노출:"); print(t.to_string(index=False)); save(t, "chk9_sedative_first24h.csv")
print("\n※ '전체 재원' 과 '첫 24h' 가 크게 벌어지는 변수는 예측 입력으로 못 쓴다.")
print("   (기존 커버리지 표는 전부 '전체 재원 중 1회라도' 기준이었다)")

head("끝. 출력 CSV")
print("\n".join(sorted(f for f in os.listdir(OUT) if f.startswith("chk") and f.endswith(".csv"))))
