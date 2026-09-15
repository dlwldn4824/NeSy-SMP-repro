"""민감도 실험 B — 기록 오류 극단값 제거 (논문 조건 아님).

논문과 공개 코드 모두 이상치 처리를 언급하지 않는다. 논문 조건 재현 입력에는 수축기혈압 119,119 · 심박수 152,143 ·
체온 537°C 같은 값이 남아 있고, 원본 전처리의 MinMax 가 이 값 때문에 정상 범위를 0 근처로 눌러 버린다.

범위는 MIMIC-IV 공식 코드(MIT-LCP/mimic-code, mimic-iv/concepts/measurement)의 유효 범위를 그대로 쓴다:
  vitalsign.sql : 심박수 0<v<300 · 수축기 0<v<400 · 이완기 0<v<300 · 평균 0<v<300 · 호흡수 0<v<70 · 체온(°C) 10<v<50
  chemistry.sql : 크레아티닌 0<v<=150 · 혈당 0<v<=10000 · 칼륨 0<v<=30 · 알부민 0<v<=10
  bg.sql        : 젖산 v<=10000 (+ valuenum>0 없음 → 0 초과만 유지하지 않음)
  complete_blood_count.sql · enzyme.sql · inflammation.sql : 헤모글로빈·혈소판·백혈구·빌리루빈·ALT·AST·CRP v>0
  blood_differential.sql : 림프구·호중구(%) 0<=v<=100
  GCS (3개 항목 합) : 3<=v<=15 (합의 정의 범위 — 공식 코드는 빠진 항목을 채워 합을 만들지만 여기서는 범위만 적용)
원래 이벤트 창(관찰 24h)은 그대로 두고, 창 안의 범위 밖 측정만 지운다.

사용: python tools/filter_valid_ranges.py <long csv in> <long csv out>
"""
from __future__ import annotations

import sys

import pandas as pd

RANGES = {  # concept: (low, high, low_inclusive, high_inclusive)
    "HR": (0, 300, False, False), "SBP": (0, 400, False, False), "DBP": (0, 300, False, False),
    "MAP": (0, 300, False, False), "RR": (0, 70, False, False), "TempC": (10, 50, False, False),
    "Creatinine": (0, 150, False, True), "Glucose": (0, 10000, False, True), "Potassium": (0, 30, False, True),
    "Albumin": (0, 10, False, True), "Lactate": (-float("inf"), 10000, False, True),
    "Hemoglobin": (0, float("inf"), False, False), "Platelets": (0, float("inf"), False, False),
    "WBC": (0, float("inf"), False, False), "Bilirubin": (0, float("inf"), False, False),
    "ALT": (0, float("inf"), False, False), "AST": (0, float("inf"), False, False),
    "CRP": (0, float("inf"), False, False), "Lymphocytes": (0, 100, True, True),
    "Neutrophils": (0, 100, True, True), "GCS": (3, 15, True, True),
}


def main():
    src, dst = sys.argv[1], sys.argv[2]
    d = pd.read_csv(src, low_memory=False)
    keep = pd.Series(True, index=d.index)
    rows = []
    for c, (lo, hi, li, hi_inc) in RANGES.items():
        m = d["concept:name"] == c
        v = d.loc[m, "value"]
        ok = (v >= lo if li else v > lo) & (v <= hi if hi_inc else v < hi)
        bad = m.copy(); bad.loc[m] = ~ok
        keep &= ~bad
        rows.append({"concept": c, "n": int(m.sum()), "removed": int((~ok).sum()), "removed%": round(100 * (~ok).mean(), 3) if m.any() else 0})
    out = d[keep]
    out.to_csv(dst, index=False)
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"rows {len(d):,} -> {len(out):,} (removed {len(d) - len(out):,}) · hadm {out.hadm_id.nunique():,}")


if __name__ == "__main__":
    main()
