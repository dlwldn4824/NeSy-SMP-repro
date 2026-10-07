"""NeSy-SMP 원본 공리 조건 × 0 채우기 점검 (논문 조건 재현 6h 입력).

원본 코드의 판정 (stratified_main.py 519-540, preprocessing.py):
  - 입원 안에서 앞 값 채움 → 남은 빈칸(첫 측정 전)은 0 → MinMax(최솟값 0) → 시퀀스 뒤를 0 으로 패딩(가장 긴 입원 길이까지)
  - 조건은 이 0 을 실제 값처럼 비교한다.
원래 단위로 같은 판정을 한다: 스케일된 0 = 원래 값 0 (값이 모두 양수라 MinMax 최솟값이 0).

비교하는 두 판정
  code     : 원본 코드 그대로 (0 채움 · 패딩 포함)
  measured : 실제 측정(앞 값 채움 포함)된 시점만으로 같은 조건
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
WIDE = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\data\mimic-iv-derived\paper_leads\events_6h_wide_paper_como.csv")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else r"C:\data\mimic-iv-derived\paper_leads\axiom_zero_fill_audit_6h.csv")

d = pd.read_csv(WIDE, low_memory=False)
d = d[~d["concept:name"].isin(["Urine output", "Death", "Discharge from hospital"])]
d = d[~d["concept:name"].astype(str).str.contains("std", case=False, na=False)]
sizes = d.groupby("hadm_id").size()
L = int(sizes.max())                                   # 원본: 필터 전 최대 길이
keep = sizes[sizes > 4].index
d = d[d.hadm_id.isin(keep)].copy()
y = d.groupby("hadm_id").hospital_expire_flag.first()
n_rows = d.groupby("hadm_id").size()
print(f"입원 {len(n_rows):,} · 사망률 {y.mean():.3f} · 시퀀스 길이 L={L} · 행 수 중앙값 {n_rows.median():.0f}")
print(f"패딩 0 이 붙는 입원: {(n_rows < L).mean():.1%}")

g = d.groupby("hadm_id", sort=False)


def feat(col):
    ff = g[col].ffill()
    obs = ff.notna()
    return ff, obs


def per_hadm(mask_series):
    return mask_series.groupby(d.hadm_id).any()


rows = []


def report(name, code, meas, n_meas):
    code, meas = code.reindex(n_rows.index).fillna(False), meas.reindex(n_rows.index).fillna(False)
    n_meas = n_meas.reindex(n_rows.index).fillna(0)
    fp = code & ~meas
    fn = ~code & meas
    rows.append({
        "공리 조건": name,
        "측정 있는 입원%": 100 * (n_meas > 0).mean(),
        "원본 판정 해당%": 100 * code.mean(),
        "실측 판정 해당%": 100 * meas.mean(),
        "판정 달라짐%": 100 * (code != meas).mean(),
        "  원본만 해당(0 때문에 켜짐)%": 100 * fp.mean(),
        "  실측만 해당(0 때문에 꺼짐)%": 100 * fn.mean(),
        "사망률|원본 해당": y[code].mean() if code.any() else np.nan,
        "사망률|실측 해당": y[meas].mean() if meas.any() else np.nan,
    })


def any_cmp(col, op, thr):
    ff, obs = feat(col)
    hit = obs & op(ff, thr)
    n_obs = obs.groupby(d.hadm_id).sum()
    meas = per_hadm(hit)
    zero_hit = op(0.0, thr)                             # 0 이 조건을 만족하나
    has_zero = (n_obs < n_rows) | (n_rows < L)
    code = meas | (has_zero & zero_hit)
    return code, meas, n_obs


def all_cmp(col, op, thr):
    ff, obs = feat(col)
    n_obs = obs.groupby(d.hadm_id).sum()
    bad = obs & ~op(ff, thr)
    meas = (n_obs > 0) & ~per_hadm(bad)
    zero_ok = op(0.0, thr)
    full = (n_obs == n_rows) & (n_rows == L)
    code = ~per_hadm(bad) & (full | zero_ok)
    return code, meas, n_obs


lt = lambda a, b: a < b
le = lambda a, b: a <= b
gt = lambda a, b: a > b
ge = lambda a, b: a >= b

report("GCS < 8 (한 번이라도)", *any_cmp("gcs", lt, 8.0))
report("젖산 > 4 (한 번이라도)", *any_cmp("Lactate", gt, 4.0))
report("혈소판 < 50 (모든 시점)", *all_cmp("Platelet Count", lt, 50.0))
report("빌리루빈 >= 2 (한 번이라도)", *any_cmp("Total Bilirubin", ge, 2.0))
c1, m1, n1 = all_cmp("Respiratory Rate", ge, 29.0)
c2, m2, _ = all_cmp("Respiratory Rate", lt, 9.0)
report("호흡수 >= 29 또는 < 9 (모든 시점)", c1 | c2, m1 | m2, n1)
report("수축기혈압 <= 100 (한 번이라도)", *any_cmp("Arterial Blood Pressure systolic", le, 100.0))
report("크레아티닌 >= 1.5 (모든 시점)", *all_cmp("Creatinine (serum)", ge, 1.5))
report("CRP >= 100 (한 번이라도)", *any_cmp("C-Reactive Protein", ge, 100.0))
report("백혈구 > 30 (한 번이라도)", *any_cmp("White Blood Cells", gt, 30.0))

age = g["anchor_age"].first()
report("나이 > 65", age > 65, age > 65, age.notna().astype(int))
c = g[["acute kidney injury", "aids", "cad", "cancer", "cirrhosis", "copd", "hiv", "kidney disease",
       "metastatic cancer"]].max()
chronic = c.max(axis=1) > 0
report("만성질환 (9개 중 하나)", chronic, chronic, pd.Series(1, index=chronic.index))

# 젖산 안 떨어짐: 0 이 아닌 값만 보므로 0 채우기 영향 없음 — 참고로 같이 센다
ff, obs = feat("Lactate")
lac = pd.DataFrame({"h": d.hadm_id, "v": ff.fillna(0.0)})
def lnc(s):
    nz = s[s != 0].to_numpy()
    return bool(np.all(np.diff(nz) >= 0) and np.any(nz > 2.0)) if len(nz) > 1 else False
lnc_s = lac.groupby("h").v.apply(lnc)
report("젖산 안 떨어짐 (0 제외)", lnc_s, lnc_s, obs.groupby(d.hadm_id).sum())

t = pd.DataFrame(rows).set_index("공리 조건")
t.to_csv(OUT, encoding="utf-8-sig")
print(t.round(1).to_string())
print(f"\n-> {OUT}")
