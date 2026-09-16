"""연결 명세 → 실행: 추출된 명세를 논문 조건 재현 6h 학습 입력에 적용 (학습 없음).

사용: python grounding_compile.py <spec.json> [<spec.json> ...]
  - provenance 가 unspecified 인 칸은 compile_defaults 로 채운다 (관찰 창 전체 · any · 결측 unknown)
  - unknown: 해당 변수 측정이 하나도 없는 입원 → 참/거짓 어디에도 넣지 않음
  - 0/1 동반질환 flag 는 NLP 결과라 '측정 없음'이 없다 → present = flag 1, 나머지 거짓
비교용: 같은 개념의 원저자 코드 조건(연산자·집계)을 결측 제외로 계산한 값을 옆에 둔다.
"""
from __future__ import annotations

import json
import operator as op
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
T = Path(__file__).resolve().parent
SCHEMA = json.loads((T.parent / "configs" / "grounding_spec_schema.json").read_text(encoding="utf-8"))
DEF = SCHEMA["compile_defaults"]
WIDE = Path(r"C:\data\mimic-iv-derived\paper_leads\events_6h_wide_paper_como.csv")
OPS = {"<": op.lt, "<=": op.le, ">": op.gt, ">=": op.ge, "==": op.eq}
# 원저자 stratified_main.py 조건 (rule_activation_table.py 와 같음)
CODE = {"Lactate": (">", 4, "any"), "Total Bilirubin": (">=", 2, "any"), "Platelet Count": ("<", 50, "all"),
        "C-Reactive Protein": (">=", 100, "any"), "White Blood Cells": (">", 30, "any"),
        "anchor_age": (">", 65, "first"), "Arterial Blood Pressure mean": ("<", 65, "any"),
        "gcs": ("<", 8, "any"), "Respiratory Rate": (">=", 29, "all"), "Arterial Blood Pressure systolic": ("<=", 100, "any"),
        "Creatinine (serum)": (">=", 1.5, "all")}

specs = [s for f in sys.argv[1:] for s in json.loads(Path(f).read_text(encoding="utf-8"))]
cols = sorted({s["variable"] for s in specs if s.get("variable")})
d = pd.read_csv(WIDE, low_memory=False, usecols=lambda c: c in set(cols) | {"hadm_id", "concept:name", "hospital_expire_flag"})
d = d[~d["concept:name"].isin(["Urine output", "Death", "Discharge from hospital"])]
sz = d.groupby("hadm_id").size()
d = d[d.hadm_id.isin(sz[sz > 4].index)]
g = d.groupby("hadm_id")
y = g.hospital_expire_flag.first()
N = len(y)


def evaluate(var, opname, thr, agg):
    v = d[["hadm_id", var]].dropna()
    if var == "anchor_age" or agg == "first":
        v = v.groupby("hadm_id")[var].first().to_frame().reset_index()
    hit = OPS[opname](v[var], thr)
    by = hit.groupby(v.hadm_id)
    res = (by.all() if agg == "all" else by.any()).reindex(y.index)  # NaN = unknown
    return res


def summarize(res):
    known = res.notna()
    t = res.fillna(False).astype(bool)
    return {"참%": round(100 * t.mean(), 1), "unknown%": round(100 * (~known).mean(), 1),
            "사망률|참": round(100 * y[t].mean(), 1) if t.any() else None,
            "사망률|거짓": round(100 * y[known & ~t].mean(), 1) if (known & ~t).any() else None}


rows = []
for s in specs:
    var, prov = s.get("variable"), s.get("provenance") or {}
    base = {"concept": s.get("concept"), "type": s.get("statement_type"), "variable": var,
            "명세": f"{s.get('operator')} {s.get('threshold')}", "→": (s.get("consequent") or {}).get("object")}
    if s.get("statement_type") != "risk_condition" or not var:
        rows.append({**base, "실행": "건너뜀 (위험 조건 아님 / 변수 없음)"})
        continue
    agg = s.get("aggregation") or DEF["aggregation"]
    if var in d.columns and d[var].dropna().isin([0, 1]).all() and s.get("operator") in ("present", "==", None):
        t = g[var].max().reindex(y.index).fillna(0) == 1
        rows.append({**base, "집계": "flag", **summarize(t.astype(object)), "실행": "OK"})
        continue
    thr = s.get("threshold")
    if s.get("operator") not in OPS or not isinstance(thr, (int, float)):
        rows.append({**base, "실행": "건너뜀 (연산자·단일 임계값 없음)"})
        continue
    r = {**base, "집계": agg + (" (기본값)" if s.get("aggregation") is None else ""), **summarize(evaluate(var, s["operator"], thr, agg)), "실행": "OK"}
    if var in CODE:
        co, ct, ca = CODE[var]
        cs = summarize(evaluate(var, co, ct, ca))
        r.update({"원저자 코드 조건": f"{co} {ct} ({ca})", "코드 조건 참%": cs["참%"], "코드 사망률|참": cs["사망률|참"]})
    rows.append(r)

out = pd.DataFrame(rows)
print(f"6h 학습 입력 입원 {N:,}")
print(out.to_string(index=False))
out.to_csv(T / "llm_runs" / "grounding_compile_6h.csv", index=False, encoding="utf-8-sig")
