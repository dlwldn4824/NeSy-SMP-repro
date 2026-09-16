"""연결 명세 소규모 시험 — 채점.

정답(grounding_gold.json)과 추출 결과(llm_runs/grounding_run*/{Q,L,M,K}.json)를 칸 단위로 비교한다.
  - 매칭: 같은 조각 · 같은 variable(정답이 null 이면 concept) · consequent.object 가 정답 목록 안
  - 칸: variable · operator · threshold · unit · statement_type · combine(Q)
  - 지어내지 않음: 원문에 없는 aggregation · time_window · missing_policy 를 null 로 뒀는가
  - evidence: 원문에 그대로 있는가 · threshold 숫자가 evidence 안에 있는가
  - 반복 일치: (variable, operator, threshold, consequent) 집합 Jaccard
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
T = Path(__file__).resolve().parent
GOLD = json.loads((T / "grounding_gold.json").read_text(encoding="utf-8"))["items"]
RUNS = sorted(p for p in (T / "llm_runs").glob("grounding_run*") if p.is_dir())
ws = lambda s: re.sub(r"\s+", " ", str(s or "")).strip()
unit_norm = lambda u: re.sub(r"\s+", "", str(u)).lower() if u is not None else None


def num_eq(a, b):
    if isinstance(b, list):
        return isinstance(a, list) and len(a) == len(b) and all(abs(float(x) - y) < 1e-9 for x, y in zip(a, b))
    if b is None:
        return a is None
    try:
        return a is not None and not isinstance(a, list) and abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return False


def evidence_ok(ev, chunk):
    ev, src = ws(ev), ws(chunk)
    if ev and ev in src:
        return True
    parts = [ws(p) for p in re.split(r"\n|(?=g\.add\()", str(ev or "")) if ws(p)]
    return bool(parts) and all(p in src for p in parts)


def obj(s):
    c = s.get("consequent") or {}
    return c.get("object") if isinstance(c, dict) else None


def field_scores(g, s):
    prov = s.get("provenance") or {}
    op_ok_set = [g.get("operator")] + g.get("operator_alt", [])
    if g["id"] == "M1":
        op_ok_set = [None, "=="]
    unit_ok = (unit_norm(s.get("unit")) == unit_norm(g.get("unit"))) or (
        g.get("unit") is None and prov.get("unit") in ("catalog", "unspecified"))
    tw = s.get("time_window")
    tw_null = tw is None or (isinstance(tw, dict) and all(v is None for v in tw.values()))
    r = {
        "variable": s.get("variable") == g.get("variable"),
        "operator": s.get("operator") in op_ok_set if "operator" in g else True,
        "threshold": num_eq(s.get("threshold"), g.get("threshold")) if "threshold" in g else True,
        "unit": unit_ok if "unit" in g else True,
        "statement_type": s.get("statement_type") in g["statement_type"],
        "no_invented_aggregation": s.get("aggregation") is None,
        "no_invented_time_window": tw_null,
        "no_invented_missing": s.get("missing_policy") is None,
    }
    if "combine_min_count" in g:
        cb = s.get("combine") or {}
        r["combine"] = isinstance(cb, dict) and cb.get("min_count") == g["combine_min_count"]
    return r


rows, extras, keysets = [], [], {}
for run in RUNS:
    keysets[run.name] = set()
    for ch in "QLMK":
        chunk = (T / f"grounding_chunk_{ch}.txt").read_text(encoding="utf-8")
        f = run / f"{ch}.json"
        specs = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        for s in specs:
            keysets[run.name].add((ch, s.get("variable") or s.get("concept"), s.get("operator"),
                                   json.dumps(s.get("threshold")), obj(s)))
        used = set()
        for g in [x for x in GOLD if x["chunk"] == ch]:
            cands = [(i, s) for i, s in enumerate(specs) if i not in used
                     and ((s.get("variable") == g["variable"]) if g["variable"] else (s.get("concept") == g["concept"]))
                     and (g.get("consequent_object") is None or obj(s) in g["consequent_object"])]
            if not cands and g["variable"] is None:  # not_groundable 인데 변수를 붙인 경우도 개념으로 찾는다
                cands = [(i, s) for i, s in enumerate(specs) if i not in used and s.get("concept") == g["concept"]]
            if not cands:
                rows.append({"run": run.name, "chunk": ch, "gold": g["id"], "found": False, "optional": g.get("optional", False)})
                continue
            i, s = max(cands, key=lambda c: sum(field_scores(g, c[1]).values()))
            used.add(i)
            fs = field_scores(g, s)
            rows.append({"run": run.name, "chunk": ch, "gold": g["id"], "found": True, "optional": g.get("optional", False),
                         **fs, "evidence_verbatim": evidence_ok(s.get("evidence"), chunk),
                         "spec": json.dumps({k: s.get(k) for k in ("variable", "operator", "threshold", "unit", "statement_type", "consequent")}, ensure_ascii=False)})
        for i, s in enumerate(specs):
            if i in used:
                continue
            thr = s.get("threshold")
            nums = thr if isinstance(thr, list) else ([thr] if thr is not None else [])
            ev = ws(s.get("evidence"))
            extras.append({"run": run.name, "chunk": ch, "concept": s.get("concept"), "variable": s.get("variable"),
                           "operator": s.get("operator"), "threshold": thr, "statement_type": s.get("statement_type"),
                           "object": obj(s), "evidence_verbatim": evidence_ok(s.get("evidence"), chunk),
                           "threshold_in_evidence": all(re.search(rf"(?<![\d.]){re.escape(str(n)).replace(r'\.0', r'(\.0)?')}(?![\d])", ev) for n in nums),
                           "evidence": ev[:160]})

df = pd.DataFrame(rows)
ex = pd.DataFrame(extras)
df.to_csv(T / "llm_runs" / "grounding_score_items.csv", index=False, encoding="utf-8-sig")
ex.to_csv(T / "llm_runs" / "grounding_score_extras.csv", index=False, encoding="utf-8-sig")

FIELDS = ["variable", "operator", "threshold", "unit", "statement_type", "no_invented_aggregation",
          "no_invented_time_window", "no_invented_missing", "evidence_verbatim"]
print("=== 필수 정답 항목 기준 ===")
req = df[~df.optional]
for run, d in req.groupby("run"):
    f = d[d.found]
    line = {"찾음": f"{len(f)}/{len(d)}"}
    for k in FIELDS:
        line[k] = f"{int(f[k].sum())}/{len(f)}"
    if "combine" in f:
        q = f[f.chunk == "Q"]
        line["combine(Q)"] = f"{int(q['combine'].fillna(False).sum())}/{len(q)}"
    print(run, line)
print("\n=== 조각별 필수 항목 완전 일치 (모든 칸 맞음) ===")
full = req[req.found].copy()
full["all_ok"] = full[FIELDS].all(axis=1) & full.get("combine", pd.Series(True, index=full.index)).fillna(True).astype(bool)
print(full.groupby(["run", "chunk"]).all_ok.agg(["sum", "size"]).to_string())
print("\n=== 틀린 칸 ===")
for _, r in req.iterrows():
    if not r.found:
        print(r.run, r.gold, "못 찾음")
        continue
    bad = [k for k in FIELDS + (["combine"] if r.chunk == "Q" else []) if r.get(k) is False]
    if bad:
        print(r.run, r.gold, bad, r.spec)
print("\n=== 선택 항목 (not_groundable 등) ===")
print(df[df.optional][["run", "gold", "found"]].to_string(index=False))
print("\n=== 정답에 없는 추가 명세 ===")
print(ex.to_string(index=False) if len(ex) else "(없음)")
if len(keysets) == 2:
    a, b = keysets.values()
    print(f"\n반복 일치 Jaccard (variable, operator, threshold, consequent): {len(a & b) / len(a | b):.2f}  ({len(a & b)}/{len(a | b)})")
