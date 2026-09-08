# -*- coding: utf-8 -*-
# ============================================================================
# split 설계 확정용 계산 — SPLIT_DESIGN.md 후속
#   [1] 실제 환자 한 명의 CAM 시계열을 X -> y 로 쪼갠 예시
#   [2] split 후 표본 수: transition 4종 + 고정 24h 타깃, 각각 건수/stay/환자
#   [3] 입력 lookback 커버리지 (RASS / 진정제 / CAM 이력) + 미확보 항목
#   [4] trajectory 별 환자 수 (P->N->P 모수가 되나)
# 사용: EDA_DATA=<notes/eda> python eda/19_split_spec.py
# ============================================================================
import os, sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ.get("EDA_DATA", "/content/drive/MyDrive/mimic_eda")
OUT = os.environ.get("EDA_OUT", os.path.join(DATA, "out_split"))
os.makedirs(OUT, exist_ok=True)

CAM_ITEM, RASS_ITEM = 228332, 228096
W_AHEAD = 24.0                      # 타깃 창
HR_CAP = 240.0                      # 입실 후 10일까지
LOOKBACK = [6.0, 12.0, 24.0]        # 입력 lookback 후보
pd.set_option("display.width", 220)


def head(t):
    print("\n" + "=" * 78); print(t); print("=" * 78)


def save(df, name):
    df.to_csv(os.path.join(OUT, name), encoding="utf-8-sig")
    print(f"  -> {name}")


# ---------------------------------------------------------------- 로드
b = pd.read_pickle(f"{DATA}/_icu_base.pkl")
v = pd.read_parquet(f"{DATA}/_label_values.parquet")
b["intime"] = pd.to_datetime(b["intime"])
if "age" not in b.columns:
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
DEN = b[(b.age >= 18) & (b.los >= 1.0)].copy()
intime = b.set_index("stay_id")["intime"]
stay2subj = DEN.set_index("stay_id")["subject_id"]

MAP = {"Positive": "P", "Negative": "N", "UTA": "U",
       "Unable to Assess": "U", "Unable to assess": "U"}
cam = v[v.itemid == CAM_ITEM][["stay_id", "charttime", "value"]].copy()
cam["charttime"] = pd.to_datetime(cam["charttime"])
cam["v"] = cam["value"].astype(str).str.strip().map(MAP)
cam = cam[cam.v.notna() & cam.stay_id.isin(DEN.stay_id)].copy()
cam["hr"] = (cam["charttime"] - cam["stay_id"].map(intime)).dt.total_seconds() / 3600
cam = cam[(cam.hr >= 0) & (cam.hr <= HR_CAP)].sort_values(["stay_id", "hr"]).reset_index(drop=True)
cam["subject_id"] = cam["stay_id"].map(stay2subj)
print(f"CAM 앵커 후보 {len(cam):,}건 / {cam.stay_id.nunique():,} stay / "
      f"{cam.subject_id.nunique():,} 환자  (입실 {HR_CAP:.0f}h 이내)")

# ---- 고정 24h 타깃 (앵커 이후 24h 안에 확정 P 가 있나) ----
h = cam["hr"].to_numpy(float)
isC = (cam["v"] != "U").to_numpy()
isP = (cam["v"] == "P").to_numpy()
cumC = np.concatenate([[0], isC.cumsum()])
cumP = np.concatenate([[0], (isC & isP).cumsum()])
uniq, first, cnt = np.unique(cam["stay_id"].to_numpy(), return_index=True, return_counts=True)
labeled = np.zeros(len(cam), bool); y = np.zeros(len(cam), bool)
for a, n in zip(first, cnt):
    hh = h[a:a + n]; idx = np.arange(n)
    j = np.searchsorted(hh, hh + W_AHEAD, side="right")
    labeled[a:a + n] = (cumC[a + j] - cumC[a + idx + 1]) > 0
    y[a:a + n] = (cumP[a + j] - cumP[a + idx + 1]) > 0
cam["labeled"], cam["y"] = labeled, y


# ================================================================= [1] 예시
head("[1] 한 환자의 CAM 시계열을 X -> y 로 쪼갠 예시")

# P->N->P 가 있고 앵커가 8~14개인 stay 하나를 고른다 (설명용으로 적당한 길이)
conf_seq = cam[cam.v != "U"].groupby("stay_id")["v"].apply(lambda s: "".join(s))
n_anc = cam.groupby("stay_id").size()
cands = [s for s, seq in conf_seq.items()
         if "PNP" in seq and 8 <= n_anc.get(s, 0) <= 14
         and cam.loc[cam.stay_id == s, "v"].eq("U").any()]
ex = cands[len(cands) // 2] if cands else n_anc.idxmax()
d = cam[cam.stay_id == ex].copy()
print(f"stay_id={ex} · subject_id={int(d.subject_id.iloc[0])} · 앵커 {len(d)}개 "
      f"(확정 {int((d.v!='U').sum())} / UTA {int(d.v.eq('U').sum())})\n")
d["입실후"] = d["hr"].round(1)
d["X(관찰)"] = ["0h ~ " + f"{x:.1f}h" for x in d["hr"]]
d["y(24h내P)"] = np.where(~d.labeled, "제외(창내 확정평가 없음)", np.where(d.y, "1", "0"))
print(d[["입실후", "v", "X(관찰)", "y(24h내P)"]]
      .rename(columns={"v": "CAM"}).to_string(index=False))
print(f"\n-> 이 stay 하나에서 instance {int(d.labeled.sum())}개 "
      f"(앵커 {len(d)}개 중 {int((~d.labeled).sum())}개는 라벨 없음)")
save(d[["hr", "v", "labeled", "y"]].set_index("hr"), "split_example_stay.csv")


# ================================================================= [2] 표본 수
head("[2-a] transition 4종 (연속한 확정 P/N 쌍) — 건수 / stay / 환자")

conf = cam[cam.v != "U"].copy()
conf["prev_v"] = conf.groupby("stay_id")["v"].shift()
conf["prev_hr"] = conf.groupby("stay_id")["hr"].shift()
tr = conf[conf.prev_v.notna()].copy()
tr["trans"] = tr["prev_v"] + "->" + tr["v"]
order = ["N->N", "N->P", "P->N", "P->P"]
t = pd.DataFrame({
    "건수": tr.groupby("trans").size(),
    "stay": tr.groupby("trans")["stay_id"].nunique(),
    "환자": tr.groupby("trans")["subject_id"].nunique(),
}).reindex(order)
t["건수%"] = (100 * t["건수"] / len(tr)).round(1)
t["간격 median_h"] = (tr["hr"] - tr["prev_hr"]).groupby(tr["trans"]).median().round(1).reindex(order)
print(t.to_string())
print(f"\n합계 {len(tr):,}건 / {tr.stay_id.nunique():,} stay / {tr.subject_id.nunique():,} 환자")
print(f"★ N->P (신규 발생) {int(t.loc['N->P','건수']):,}건 · "
      f"{int(t.loc['N->P','환자']):,}명 — 주 지표 계층")
save(t, "spec2_transition_counts.csv")

head("[2-b] 고정 24h 타깃 — 앵커 상태별 건수 / stay / 환자")
lab = cam[cam.labeled]
t2 = pd.DataFrame({
    "앵커": cam.groupby("v").size(),
    "라벨생성": lab.groupby("v").size(),
    "y=1": lab.groupby("v")["y"].sum(),
    "stay": lab.groupby("v")["stay_id"].nunique(),
    "환자": lab.groupby("v")["subject_id"].nunique(),
}).reindex(["N", "P", "U"])
t2["라벨생성%"] = (100 * t2["라벨생성"] / t2["앵커"]).round(1)
t2["Positive%"] = (100 * t2["y=1"] / t2["라벨생성"]).round(1)
print(t2[["앵커", "라벨생성", "라벨생성%", "y=1", "Positive%", "stay", "환자"]].to_string())
print(f"\n합계 instance {int(cam.labeled.sum()):,} / "
      f"{lab.stay_id.nunique():,} stay / {lab.subject_id.nunique():,} 환자 · "
      f"Positive {100*lab.y.mean():.1f}%")
save(t2, "spec2_anchor_counts.csv")

head("[2-c] 이전 확정상태 x 현재 앵커 — 두 정의를 겹쳐 본다")
cam["prev_conf"] = cam["v"].where(cam.v != "U").groupby(cam.stay_id).ffill().shift()
cam.loc[cam.groupby("stay_id").head(1).index, "prev_conf"] = np.nan
lab2 = cam[cam.labeled]
ct = pd.crosstab(lab2["prev_conf"].fillna("(없음)"), lab2["v"], values=lab2["y"],
                 aggfunc=["size", "mean"])
ct = pd.concat([ct["size"].add_prefix("n_"),
                (100 * ct["mean"]).round(1).add_prefix("P%_")], axis=1)
print(ct.to_string())
save(ct, "spec2_prev_by_anchor.csv")


# ================================================================= [3] 입력
head("[3] 입력 lookback 커버리지 — 앵커 시점 이전 구간에 뭐가 있나")

# RASS
r = v[v.itemid == RASS_ITEM][["stay_id", "charttime", "valuenum"]].copy()
r["charttime"] = pd.to_datetime(r["charttime"])
r = r[r.stay_id.isin(DEN.stay_id)].copy()
r["hr"] = (r["charttime"] - r["stay_id"].map(intime)).dt.total_seconds() / 3600
r = r[r.hr >= 0].sort_values(["stay_id", "hr"])
rh = {k: g["hr"].to_numpy(float) for k, g in r.groupby("stay_id", sort=False)}
rv = {k: g["valuenum"].to_numpy(float) for k, g in r.groupby("stay_id", sort=False)}

n_rass = {w: np.zeros(len(cam), int) for w in LOOKBACK}
deep = np.zeros(len(cam), bool)          # lookback 24h 안에 RASS <= -4 가 있나
for a, n in zip(first, cnt):
    sid = cam["stay_id"].iloc[a]
    hh = h[a:a + n]
    arr = rh.get(sid)
    if arr is None:
        continue
    hi = np.searchsorted(arr, hh, side="right")
    for w in LOOKBACK:
        n_rass[w][a:a + n] = hi - np.searchsorted(arr, hh - w, side="left")
    lo24 = np.searchsorted(arr, hh - 24.0, side="left")
    vals = rv[sid]
    for k in range(n):
        seg = vals[lo24[k]:hi[k]]
        deep[a + k] = bool(seg.size and np.nanmin(seg) <= -4)

# 진정제
sed = pd.read_parquet(f"{DATA}/_step1_sed.parquet")
sed = sed[sed.stay_id.isin(DEN.stay_id)].copy()
for c in ["starttime", "endtime"]:
    sed[c] = pd.to_datetime(sed[c])
sed["s"] = (sed["starttime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
sed["e"] = (sed["endtime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
BENZO = {"lorazepam", "midazolam", "diazepam"}
sed["cls"] = np.where(sed.drug.isin(BENZO), "benzo", sed.drug)
sed_by = {k: (g["s"].to_numpy(float), g["e"].to_numpy(float), g["cls"].to_numpy())
          for k, g in sed.groupby("stay_id", sort=False)}

any_sed = np.zeros(len(cam), bool); any_benzo = np.zeros(len(cam), bool)
for a, n in zip(first, cnt):
    sid = cam["stay_id"].iloc[a]
    g = sed_by.get(sid)
    if g is None:
        continue
    s, e, cl = g
    hh = h[a:a + n]
    ov = (s[None, :] < hh[:, None]) & (e[None, :] > hh[:, None] - 24.0)
    any_sed[a:a + n] = ov.any(1)
    any_benzo[a:a + n] = (ov & (cl == "benzo")[None, :]).any(1)

# CAM 이력
n_prev_cam = cam.groupby("stay_id").cumcount().to_numpy()

m = cam[cam.labeled].copy()
sel = cam.labeled
rows = []
for w in LOOKBACK:
    rows.append({"입력": f"RASS (이전 {int(w)}h)",
                 "instance 커버%": round(100 * (n_rass[w][sel] > 0).mean(), 1),
                 "median 측정수": float(np.median(n_rass[w][sel]))})
rows += [
    {"입력": "RASS<=-4 (이전 24h)", "instance 커버%": round(100 * deep[sel].mean(), 1), "median 측정수": np.nan},
    {"입력": "진정제 주입 (이전 24h)", "instance 커버%": round(100 * any_sed[sel].mean(), 1), "median 측정수": np.nan},
    {"입력": "  그중 benzo", "instance 커버%": round(100 * any_benzo[sel].mean(), 1), "median 측정수": np.nan},
    {"입력": "이전 CAM 기록 >=1", "instance 커버%": round(100 * (n_prev_cam[sel] > 0).mean(), 1),
     "median 측정수": float(np.median(n_prev_cam[sel]))},
]
t3 = pd.DataFrame(rows).set_index("입력")
print(t3.to_string())
save(t3, "spec3_lookback_coverage.csv")

head("[3-b] 로컬 중간파일에 값이 없는 입력 (stay 단위 보유율만 확인 가능)")
try:
    pc = pd.read_parquet(f"{DATA}/_padis_item_stay_counts.parquet")
    pc = pc[pc.stay_id.isin(set(m.stay_id))]
    gcol = "grp" if "grp" in pc.columns else pc.columns[-1]
    t4 = (pc.groupby(gcol)["stay_id"].nunique() / m.stay_id.nunique() * 100).round(1) \
           .sort_values(ascending=False).to_frame("instance 보유 stay 중 %")
    print(t4.to_string())
    save(t4, "spec3_stay_level_availability.csv")
except Exception as e:
    print("  못 읽음:", e)
print("\n※ MOBILITY / PAIN / GCS 는 _label_values.parquet 에 값이 없다 (00_extract.py VALUE_IDS).")
print("   앵커별 lookback 을 계산하려면 00_extract.py 의 VALUE_IDS 를 넓혀 다시 뽑아야 한다.")


# ================================================================= [4] B안
head("[4] trajectory 별 환자 수 — B안(P->N->P)의 모수가 되나")

seq = cam[cam.v != "U"].groupby("stay_id")["v"].apply(lambda s: "".join(s))
# 연속 중복 압축: NNPPN -> NPN  (RE2 는 역참조를 못 쓴다 — 파이썬으로 압축)
from itertools import groupby
comp = pd.Series([ "".join(k for k, _ in groupby(s)) for s in seq ],
                 index=seq.index, dtype=object)
sub = pd.Series(seq.index.map(stay2subj), index=seq.index)

def pat_stats(mask, name):
    st = set(seq.index[mask])
    return {"패턴": name, "stay": len(st), "환자": sub[list(st)].nunique()}

rows = [
    pat_stats(comp.str.len() == 1, "변화 없음 (N만 또는 P만)"),
    pat_stats(comp == "N", "  N 만"),
    pat_stats(comp == "P", "  P 만"),
    pat_stats(comp.str.contains("NP"), "N->P 있음 (신규 발생)"),
    pat_stats(comp.str.contains("PN"), "P->N 있음 (회복)"),
    pat_stats(comp.str.contains("PNP"), "★ P->N->P 있음 (재발)"),
    pat_stats(comp.str.contains("PNPN"), "  P->N->P->N"),
    pat_stats(comp.str.contains("PNPNP"), "  P->N->P->N->P"),
]
t5 = pd.DataFrame(rows).set_index("패턴")
t5["전체 환자 대비%"] = (100 * t5["환자"] / cam.subject_id.nunique()).round(1)
print(f"확정 CAM 보유: {len(seq):,} stay / {sub.nunique():,} 환자\n")
print(t5.to_string())
save(t5, "spec4_trajectory_counts.csv")

print("\n압축 패턴 상위 12개:")
t6 = comp.value_counts().head(12).to_frame("stay")
t6["환자"] = [sub[list(seq.index[comp == p])].nunique() for p in t6.index]
t6["비율%"] = (100 * t6.stay / len(comp)).round(1)
print(t6.to_string())
save(t6, "spec4_top_patterns.csv")

# P->N->P 를 instance 로 보면
pnp_stays = set(seq.index[comp.str.contains("PNP")])
mm = m[m.stay_id.isin(pnp_stays)]
print(f"\nP->N->P stay 를 평가 단위로 풀면: instance {len(mm):,}개 "
      f"({100*len(mm)/len(m):.1f}%) · Positive {100*mm.y.mean():.1f}%")
print("-> 별도 코호트로 뽑지 않아도 A안 안에 이만큼 들어 있다.")

head("끝. 저장된 CSV")
print("\n".join(sorted(f for f in os.listdir(OUT) if f.startswith("spec") or f.startswith("split_example"))))
