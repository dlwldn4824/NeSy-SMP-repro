"""NeSy-SMP 원본 지식 규칙 전체 — activation sanity table (논문 조건 재현 6h 입력, 학습 없음).

stratified_main.py 519-640 에서 조건(lambda)이 정의된 것을 전부 센다.
  - 학습 loss 에 들어가는 weak anchoring 13개 (젖산 안 떨어짐의 부정 포함)
  - 정의됐지만 loss 에 안 들어가는 2개: glucose(버그 — 함수와 1 을 비교해 항상 빈 집합) · MAP(정의만)

세 가지 activation (입원 단위 %)
  기대(논리)       : 규칙 문장 그대로, 실제 측정값만으로 판정 ('모든 시점'은 측정 1개 이상일 때)
  현재 코드        : 원본 판정 — 첫 측정 전 빈칸 0 · 시퀀스 뒤 패딩 0 을 값으로 비교, glucose 는 버그대로 0
  missing-aware   : 민감도 A(패치 S1)의 판정 — 0(패딩·빈칸·실측 0)을 측정 없음으로 제외
원래 단위로 계산한다 (MinMax 는 순서를 보존하므로 비교 결과는 같다; 원래 값 0 이 실측인 경우만 S1 에서 결측 취급).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
WIDE = Path(r"C:\data\mimic-iv-derived\paper_leads\events_6h_wide_paper_como.csv")
OUT = Path(r"C:\data\mimic-iv-derived\rule_activation_table_6h.csv")

d = pd.read_csv(WIDE, low_memory=False)
d = d[~d["concept:name"].isin(["Urine output", "Death", "Discharge from hospital"])]
sizes = d.groupby("hadm_id").size()
L = int(sizes.max())
d = d[d.hadm_id.isin(sizes[sizes > 4].index)].copy()
H = d.hadm_id
g = d.groupby("hadm_id", sort=False)
n_rows = g.size()
y = g.hospital_expire_flag.first()
has_pad = n_rows < L
rows = []


def ff(col):
    v = g[col].ffill()
    return v, v.notna()


def anyh(m):
    return m.groupby(H).any().reindex(n_rows.index, fill_value=False)


def sumh(m):
    return m.groupby(H).sum().reindex(n_rows.index, fill_value=0)


def add(rule, used, n_meas, exp, code, ma, note=""):
    exp, code, ma = (s.reindex(n_rows.index).fillna(False).astype(bool) for s in (exp, code, ma))
    mort = lambda m: round(100 * y[m].mean(), 1) if m.any() else None
    rows.append({
        "규칙 (코드 정의)": rule, "loss 사용": used, "측정 있는 입원%": round(100 * (n_meas > 0).mean(), 1),
        "기대(논리)%": round(100 * exp.mean(), 1), "현재 코드%": round(100 * code.mean(), 1),
        "missing-aware%": round(100 * ma.mean(), 1),
        "코드≠기대 입원%": round(100 * (code != exp).mean(), 1),
        "missing-aware≠기대%": round(100 * (ma != exp).mean(), 1),
        "사망률|기대 켜짐": mort(exp), "사망률|코드 켜짐": mort(code), "문제": note,
    })


def any_rule(name, col, op, thr, used="예", note=""):
    v, obs = ff(col)
    n_obs = sumh(obs)
    exp = anyh(obs & op(v, thr))
    zero_ok = op(0.0, thr)
    code = exp | (((n_obs < n_rows) | has_pad) & zero_ok)
    ma = anyh(obs & (v != 0) & op(v, thr))
    add(name, "예" if used == "예" else used, n_obs, exp, code, ma, note)


def all_rule(col, op, thr):
    v, obs = ff(col)
    n_obs = sumh(obs)
    exp = (n_obs > 0) & ~anyh(obs & ~op(v, thr))
    zero_ok = op(0.0, thr)
    code = ~anyh(obs & ~op(v, thr)) & ((((n_obs == n_rows) & ~has_pad)) | zero_ok)
    real = obs & (v != 0)
    ma = (sumh(real) > 0) & ~anyh(real & ~op(v, thr))
    return n_obs, exp, code, ma


lt, le, gt, ge = (lambda a, b: a < b), (lambda a, b: a <= b), (lambda a, b: a > b), (lambda a, b: a >= b)

any_rule("GCS < 8 (한 번이라도)", "gcs", lt, 8.0, note="0 이 '8 미만'으로 잡혀 전원 켜짐")
any_rule("젖산 > 4 (한 번이라도)", "Lactate", gt, 4.0)
n, e, c, m = all_rule("Platelet Count", lt, 50.0)
add("혈소판 < 50 (모든 시점)", "예", n, e, c, m, "측정 없는 입원·빈칸 0 이 '50 미만'으로 켜짐")
any_rule("빌리루빈 ≥ 2 (한 번이라도)", "Total Bilirubin", ge, 2.0)
n1, e1, c1, m1 = all_rule("Respiratory Rate", ge, 29.0)
_, e2, c2, m2 = all_rule("Respiratory Rate", lt, 9.0)
add("호흡수 ≥ 29 (모든 시점) 또는 < 9 (모든 시점)", "예 (수축기혈압 규칙과 함께일 때만)", n1, e1 | e2, c1 | c2, m1 | m2,
    "'모든 시점' 조건이라 거의 성립 안 함")
any_rule("수축기혈압 ≤ 100 (한 번이라도)", "Arterial Blood Pressure systolic", le, 100.0, note="0 이 '100 이하'로 잡혀 전원 켜짐")
n, e, c, m = all_rule("Creatinine (serum)", ge, 1.5)
add("크레아티닌 ≥ 1.5 (모든 시점)", "예", n, e, c, m, "패딩 0 때문에 절대 안 켜짐")
any_rule("CRP ≥ 100 (한 번이라도)", "C-Reactive Protein", ge, 100.0, note="MIMIC 에서 CRP 측정 자체가 드묾")
any_rule("백혈구 > 30 (한 번이라도)", "White Blood Cells", gt, 30.0)
age = g["anchor_age"].first()
a = age > 65
add("나이 > 65", "예", age.notna().astype(int), a, a, a)
cm = g[["acute kidney injury", "aids", "cad", "cancer", "cirrhosis", "copd", "hiv", "kidney disease",
        "metastatic cancer"]].max()
ch = cm.max(axis=1) > 0
add("만성질환 (동반질환 9개 중 하나)", "예", pd.Series(1, index=ch.index), ch, ch, ch,
    "동반질환 추출이 적게 잡힘(유병률 낮음)")
v, obs = ff("Lactate")
lac = pd.DataFrame({"h": H, "v": v.fillna(0.0)})


def lnc(s):
    nz = s[s != 0].to_numpy()
    return bool(np.all(np.diff(nz) >= 0) and np.any(nz > 2.0)) if len(nz) > 1 else False


ln = lac.groupby("h").v.apply(lnc).reindex(n_rows.index).fillna(False)
add("젖산 안 떨어짐 (0 제외 측정값이 비감소 & 한 번이라도 > 2)", "예", sumh(obs), ln, ln, ln)
add("젖산 떨어짐 (위 규칙의 부정)", "예", sumh(obs), ~ln, ~ln, ~ln, "측정 없는 입원도 '떨어짐'으로 켜짐(기대 정의상 동일)")
v, obs = ff("Glucose")
exp_g = anyh(obs & (v > 100.0))
add("혈당 > 100 (한 번이라도)", "아니오 — 코드 버그", sumh(obs), exp_g, pd.Series(False, index=n_rows.index),
    pd.Series(False, index=n_rows.index), "x[glucose_above_threshold==1]: 함수와 1 비교 → 항상 빈 집합")
v, obs = ff("Arterial Blood Pressure mean")
exp_m = anyh(obs & (v < 65.0))
code_m = exp_m | (((sumh(obs) < n_rows) | has_pad) & (0.0 < 65.0))
add("평균혈압 < 65 (한 번이라도)", "아니오 — 정의만 됨", sumh(obs), exp_m, code_m, anyh(obs & (v != 0) & (v < 65.0)),
    "변수만 만들고 어떤 공식에도 안 씀")

t = pd.DataFrame(rows)
t.to_csv(OUT, index=False, encoding="utf-8-sig")
print(f"입원 {len(n_rows):,} · 시퀀스 길이 {L} · 패딩 있는 입원 {100 * has_pad.mean():.1f}%")
print(t.to_string(index=False))
