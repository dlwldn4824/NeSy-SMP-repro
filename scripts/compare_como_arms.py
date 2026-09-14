# -*- coding: utf-8 -*-
"""재현 비교표 — 논문 / 동반질환 없음 / ICD 동반질환 / NLP 동반질환.

네 갈래 모두 같은 설정이다: events_6h_wide_s3 베이스, seed 42, epochs 30/15,
reproduce_tables.py 동일. 동반질환 출처만 다르다. 없는 arm 은 건너뛴다.

⚠️ results_s3_6h_como/RESULTS_TABLE1_TABLE2.md 머리말의 "comorbidities: zeros" 는
   보고서 템플릿에 박힌 문구다. 실제 입력 CSV 는 events_6h_wide_s3_como.csv (ICD 병합본) 이다.

사용: python scripts/compare_como_arms.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
RES = Path(r"C:\dev\NeSy-SMP-repro\NeSy-SMP")
OUT = Path(__file__).resolve().parents[1] / "docs" / "REPRO_COMO_COMPARE.md"

ARMS = [
    ("동반질환 없음", RES / "results_s3_6h"),
    ("ICD", RES / "results_s3_6h_como"),
    ("NLP", RES / "results_s3_6h_como_nlp"),
]
# reproduce_tables.py 의 PAPER_T1 (6h, 5-fold macro)
PAPER = {
    "RF": {"Acc": 84.78, "F1": 74.77, "AUC": 88.11},
    "XGBoost": {"Acc": 85.31, "F1": 77.86, "AUC": 88.56},
    "BiLSTM": {"Acc": 83.53, "F1": 76.82, "AUC": 85.35},
    "LTN": {"Acc": 85.65, "F1": 79.20, "AUC": 88.10},
    "NeSy-SMP": {"Acc": 86.45, "F1": 80.35, "AUC": 88.33},
}


def md(df):
    """tabulate 없이 마크다운 표로."""
    cols = [df.index.name or ""] + [str(c) for c in df.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] + ["---:"] * len(df.columns)) + "|"]
    for idx, row in df.iterrows():
        cells = ["" if pd.isna(v) else (f"{v:+.2f}" if "Δ" in str(c) or "−" in str(c) else f"{v:.2f}")
                 for c, v in row.items()]
        out.append("| " + " | ".join([str(idx)] + cells) + " |")
    return "\n".join(out)

MODELS = ["RF", "XGBoost", "BiLSTM", "LTN", "NeSy-SMP"]
METRICS = ["Acc", "F1", "AUC"]

have = []
tabs = {}
for name, d in ARMS:
    f = d / "table1_summary.csv"
    if f.exists():
        t = pd.read_csv(f).set_index("model")
        tabs[name] = t
        have.append(name)
    else:
        print(f"[건너뜀] {name}: {f} 없음")

lines = ["# 재현 비교 — 동반질환 출처별 (6h, Table 1 · 5-fold macro)", "",
         "설정: `events_6h_wide_s3` · seed 42 · epochs 30/15 · `reproduce_tables.py` 동일. "
         "**동반질환 출처만 다르다.**", ""]

for m in METRICS:
    rows = []
    for mod in MODELS:
        r = {"모델": mod, "논문": PAPER[mod][m]}
        for name in have:
            t = tabs[name]
            r[name] = round(float(t.loc[mod, f"{m}_mean"]), 2) if mod in t.index else None
        rows.append(r)
    df = pd.DataFrame(rows).set_index("모델")
    print(f"\n=== {m} ===")
    print(df.to_string())
    lines += [f"## {m}", "", md(df), ""]

# 동반질환의 효과: 각 arm - 없음
if "동반질환 없음" in have and len(have) > 1:
    rows = []
    for mod in MODELS:
        r = {"모델": mod}
        base = tabs["동반질환 없음"]
        for name in have:
            if name == "동반질환 없음" or mod not in tabs[name].index:
                continue
            r[f"{name} − 없음"] = round(float(tabs[name].loc[mod, "AUC_mean"]
                                              - base.loc[mod, "AUC_mean"]), 2)
        rows.append(r)
    df = pd.DataFrame(rows).set_index("모델")
    print("\n=== 동반질환이 AUC 에 준 효과 ===")
    print(df.to_string())
    lines += ["## 동반질환이 AUC 에 준 효과 (arm − 없음)", "", md(df), ""]

# 논문 대비: NeSy-SMP
rows = []
for name in have:
    t = tabs[name]
    if "NeSy-SMP" in t.index:
        rows.append({"arm": name,
                     **{f"{m} Δ논문": round(float(t.loc["NeSy-SMP", f"{m}_mean"] - PAPER["NeSy-SMP"][m]), 2)
                        for m in METRICS}})
if rows:
    df = pd.DataFrame(rows).set_index("arm")
    print("\n=== NeSy-SMP 논문 대비 ===")
    print(df.to_string())
    lines += ["## NeSy-SMP 논문 대비", "", md(df), ""]

if "NLP" not in have:
    lines += ["> ⏳ **NLP arm 미완.** `xgboost.dll` 이 Windows 애플리케이션 제어 정책에 차단되어",
              "> 학습이 시작 30초 만에 중단됐다(`WinError 4551`). 해결되면 이 스크립트를 다시 돌리면 채워진다.", ""]

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"\n-> {OUT}")
