# -*- coding: utf-8 -*-
"""24-72h 고정 outcome 라벨을 두 버전으로 계산해 비교한다. 판정은 하지 않는다.

  버전 A: 첫 24h CAM Positive 제외 (스펙 ⑤ 적용)   — base3 & obs_P==0
  버전 B: 첫 24h CAM Positive 포함 (⑤ 미적용)      — base3 전체

두 버전 모두: 24-72h 창 내 P/N 판정 >=1 인 stay 만 라벨 부여,
라벨 = 창 내 Positive >=1.

집단 정의는 02_delirium_cohort.py 와 동일:
  base3 = age>=18 & icu_seq_in_subject==1 & los>=1.0
  CAM record = itemid 228332, P/N/UTA 매핑, hr>=0

필요 파일: _icu_base(.pkl/.parquet), _label_values.parquet
출력: chk16_*.csv
"""
import os
import sys

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
pd.set_option("display.width", 220)

DATA = os.environ.get("EDA_DATA", "notes/eda")
OUT = os.environ.get("EDA_OUT", DATA)
os.makedirs(OUT, exist_ok=True)
W0, W1 = 24.0, 72.0


def head(t):
    print("\n" + "=" * 78); print(t); print("=" * 78)


def pct(x, d=1):
    return round(100 * float(x), d)


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


# ---------------- 로드 ----------------
b = load_base()
b["intime"] = pd.to_datetime(b["intime"])
base3 = b[(b.age >= 18) & (b.icu_seq_in_subject == 1) & (b.los >= 1.0)].copy()
intime = b.set_index("stay_id")["intime"]

v = pd.read_parquet(f"{DATA}/_label_values.parquet")
dl = v[v.itemid == 228332][["stay_id", "charttime", "value"]].copy()
dl["charttime"] = pd.to_datetime(dl["charttime"])
MAP = {"Positive": "P", "Negative": "N", "UTA": "U",
       "Unable to Assess": "U", "Unable to assess": "U"}
dl["v"] = dl["value"].astype(str).str.strip().map(MAP)
dl = dl[dl["v"].notna()]
dl["hr"] = (dl["charttime"] - dl["stay_id"].map(intime)).dt.total_seconds() / 3600
dl = dl[dl.hr >= 0]
d3 = dl[dl.stay_id.isin(base3.stay_id)]

obs_pos = set(d3[(d3.hr < W0) & (d3.v == "P")].stay_id)          # 첫 24h P>=1
win = d3[(d3.hr >= W0) & (d3.hr < W1)]
wg = win.groupby(["stay_id", "v"]).size().unstack(fill_value=0) \
        .reindex(columns=["P", "N", "U"], fill_value=0)
wg["judge"] = wg.P + wg.N

print(f"base3 (①②③)            : {len(base3):,} stays")
print(f"첫 24h Positive >=1      : {len(obs_pos):,} stays")


# ---------------- 두 버전 계산 ----------------
def build(name, idx):
    """idx(분모 stay 집합)에 대해 24-72h 라벨 테이블을 만든다."""
    den = base3[base3.stay_id.isin(idx)].set_index("stay_id")
    t = den.join(wg[["P", "N", "U", "judge"]], how="left").fillna(
        {"P": 0, "N": 0, "U": 0, "judge": 0})
    lab = t[t.judge >= 1].copy()
    lab["y"] = (lab.P > 0).astype(int)
    lab["obs_pos"] = lab.index.isin(obs_pos)
    print(f"\n[{name}] 분모 {len(den):,} -> 창 내 판정>=1: {len(lab):,} "
          f"({pct(len(lab)/len(den))}%) -> 라벨 Positive {int(lab.y.sum()):,} "
          f"({pct(lab.y.mean())}%)")
    return den, lab


den_A, lab_A = build("A: 첫 24h P 제외 (⑤ 적용)", set(base3.stay_id) - obs_pos)
den_B, lab_B = build("B: 첫 24h P 포함 (⑤ 미적용)", set(base3.stay_id))


# ---------------- 비교 표 ----------------
head("A vs B 비교")
def summ(name, den, lab):
    r = {"버전": name, "분모": len(den), "판정>=1": len(lab),
         "판정>=1_%": pct(len(lab) / len(den)),
         "라벨P_n": int(lab.y.sum()), "유병률%": pct(lab.y.mean())}
    if "hospital_expire_flag" in lab.columns:
        r["사망%_라벨1"] = pct(lab.loc[lab.y == 1, "hospital_expire_flag"].mean())
        r["사망%_라벨0"] = pct(lab.loc[lab.y == 0, "hospital_expire_flag"].mean())
    r["LOS_med_라벨1"] = round(lab.loc[lab.y == 1, "los"].median(), 2)
    r["LOS_med_라벨0"] = round(lab.loc[lab.y == 0, "los"].median(), 2)
    return r

t = pd.DataFrame([summ("A (⑤ 적용)", den_A, lab_A), summ("B (⑤ 미적용)", den_B, lab_B)])
print(t.to_string(index=False)); save(t, "chk16_ab_compare.csv")


# ---------------- 판정 횟수별 라벨률 (양쪽) ----------------
head("창 내 판정 횟수별 라벨률 — 관찰기회 의존이 버전별로 어떤가")
rows = []
for name, lab in [("A", lab_A), ("B", lab_B)]:
    lab["ab"] = pd.cut(lab.judge, [0, 1, 2, 4, 10000], labels=["1", "2", "3-4", "5+"])
    g = lab.groupby("ab", observed=True)["y"].agg(["size", "mean"])
    for k, r in g.iterrows():
        rows.append({"버전": name, "판정횟수": k, "stays": int(r["size"]),
                     "Positive%": pct(r["mean"])})
    mx = g["mean"].max(); mn = max(g["mean"].min(), 1e-3)
    rows.append({"버전": name, "판정횟수": "최대/최소 비", "Positive%": round(mx / mn, 1)})
t = pd.DataFrame(rows)
print(t.to_string(index=False)); save(t, "chk16_gradient.csv")


# ---------------- B 가 A 에 무엇을 더하는가 ----------------
head("B 에서 추가되는 stay (= 첫 24h P 였고 창 내 판정도 있는 stay)")
add = lab_B[lab_B.obs_pos]
print(f"추가 stay: {len(add):,} (B 판정>=1 의 {pct(len(add)/max(len(lab_B),1))}%)")
rows = [{"항목": "추가 stay 수", "값": len(add)},
        {"항목": "그중 창 내 라벨 Positive %", "값": pct(add.y.mean()) if len(add) else None},
        {"항목": "추가 stay 사망률 %",
         "값": pct(add["hospital_expire_flag"].mean()) if len(add) and
               "hospital_expire_flag" in add.columns else None},
        {"항목": "A 집단 사망률 % (참고)",
         "값": pct(lab_A["hospital_expire_flag"].mean())
               if "hospital_expire_flag" in lab_A.columns else None}]
t = pd.DataFrame(rows)
print(t.to_string(index=False)); save(t, "chk16_b_added.csv")

print("\n※ B 의 라벨 1 은 '신규 발생'과 '첫 24h 부터 지속/재발'이 섞인다.")
print("   위 표의 '추가 stay 라벨 Positive %' 가 그 지속/재발 성분의 크기다.")
print("   어느 버전을 쓸지는 이 숫자들을 보고 결정한다 — 이 스크립트는 판정하지 않는다.")

head("끝. 출력 CSV")
print("\n".join(sorted(f for f in os.listdir(OUT) if f.startswith("chk16") and f.endswith(".csv"))))
