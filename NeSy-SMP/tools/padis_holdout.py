# -*- coding: utf-8 -*-
"""PADIS 규칙 추출 — zero / one / few-shot 비교 (sepsis 점검 `docs/SHOT_COUNT_CHECK.md` 와 같은 설계).

gold   : configs/padis_concepts.json 관계 트리플 20개 (subClassOf · hasOutcome 제외)
원문   : 2018 PADIS 가이드라인 영어 본문 (Devlin et al., CCM 2018) — 서지·감사의 글·참고문헌 제외, 섹션 청크
         + 2025 Focused Update 의 영어 Table 1 (로컬 파일은 본문이 한국어 번역이라 영어 권고 요약표만 사용)
분할   : 주어 개념 그룹 단위 examples / heldout. one-shot 은 examples 중 1개, zero-shot 은 0개. heldout 은 셋 다 같다.
원문·프롬프트·결과는 저작권 때문에 저장소 밖(C:/data/padis_fewshot)에 둔다.

사용:
  python tools/padis_holdout.py build                 # 분할 · 청크 · 프롬프트 3종
  python tools/padis_holdout.py score                 # runs/<cond>_run<k>/*.json 채점 (gold 기준)
  python tools/padis_holdout.py blind --judges 2      # 판정용 블라인드 프롬프트
  python tools/padis_holdout.py unblind               # 판정 결과 집계
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
SRC = Path(r"C:\data\padis_src")
WORK = Path(r"C:\data\padis_fewshot")
SPLIT = ROOT / "tools" / "padis_holdout_split.json"
CONDS = {"zeroshot": 0, "oneshot": 1, "fewshot": None}
EXCLUDE = ("rdf-schema", "22-rdf", "hasOutcome")

CATEGORY = {
    "risk_factor": ["Benzodiazepine", "BloodTransfusion", "DeepSedation", "SedationIntensity", "PhysicalRestraint",
                    "SeverePain", "Age", "Dementia", "Trauma", "Hypertension"],
    "protective": ["Dexmedetomidine", "EarlyMobility", "Melatonin"],
    "no_effect": ["MechanicalVentilation", "OpioidUse", "PatientSex"],
    "delirium_consequence": ["Delirium"],
}
ALIAS_GROUPS = [["DeepSedation", "SedationIntensity"]]   # 둘 다 '진정 깊이' — 한쪽이 다른 쪽 힌트
N_EX_UNITS = {"risk_factor": 4, "protective": 1, "no_effect": 1, "delirium_consequence": 0}
REL_DEFS = {
    "increasesRiskOf": "subject 가 있거나 높으면 object 의 위험이 커진다",
    "decreasesRiskOf": "subject 가 object 의 위험을 낮춘다",
    "associatedWith": "subject 와 object 가 연관된다 (방향·인과를 진술하지 않음)",
    "causedBy": "subject 가 object 에 의해 생긴다",
    "hasNoEffectOn": "subject 가 object 에 영향/연관이 없다고 명시",
    "precludes": "subject 가 object 의 적용·평가를 불가능하게 한다",
}
PROMPT = """당신은 임상 가이드라인 원문에서 지식그래프 트리플을 추출합니다.
입력은 중환자실 성인의 통증·초조/진정·섬망·운동제한·수면장애(PADIS) 임상진료지침의 한 부분입니다 — [{label}].

## 출력 형식
JSON 배열만 출력하세요. 설명·마크다운 금지. 해당 트리플이 없으면 [] 를 출력하세요.
[{{"subject": "...", "predicate": "...", "object": "...", "evidence": "<근거가 된 원문 문장, 원문 그대로 복사>"}}]

## 허용된 술어 (이 밖의 것을 쓰지 마세요)
{relations}

## 허용된 개념 (subject/object 는 반드시 이 id 중 하나. 괄호 안은 원문에서 쓰일 수 있는 표현)
{concepts}
{examples}
## 규칙
{example_rules}- evidence 는 입력 원문에서 **그대로 복사한** 문장이어야 합니다(줄바꿈은 공백으로). 요약·번역·여러 문장 합성 금지.
- evidence 문장 자체가 subject 와 object 사이의 관계를 진술해야 합니다.
  두 개념이 같은 문장에 함께 등장하는 것만으로는 근거가 아닙니다.
- 중재(치료·검사·프로그램)의 효과를 말하는 문장을 환자 특성 → 결과 트리플로 바꾸지 마세요.
- 가이드라인이 "연관/효과 없음"을 명시하면 hasNoEffectOn 을 쓰세요.
- 한 문장에서 여러 트리플이 나올 수 있습니다.
- 개념 목록에 없는 대상은 버리세요.

## 입력 가이드라인 원문 [{label}]
{text}
"""
EX_BLOCK = "\n## 형식 예시 — 기존에 승인된 트리플 {n}개 (출력 형식 참고)\n{lines}\n"
EX_RULES = ("- 위 예시는 **출력 형식 참고용**입니다. 예시에 있는 트리플이라도 아래 입력 원문에 근거 문장이 없으면 내지 마세요.\n"
            "- 예시에 없는 개념·술어라도 원문 근거가 있으면 추출하세요.\n")


def cfg():
    return json.loads((ROOT / "configs" / "padis_concepts.json").read_text(encoding="utf-8"))


def gold():
    return sorted({(t["subject"], t["predicate"], t["object"]) for t in cfg()["triples"]
                   if not t["predicate"].startswith(EXCLUDE)})


def cat_of(s):
    return next(c for c, m in CATEGORY.items() if s in m)


# ───────────── 분할 ─────────────
def make_split(seed=20260917):
    g = gold()
    grp = {m: a[0] for a in ALIAS_GROUPS for m in a}
    units = {}
    for t in g:
        units.setdefault(grp.get(t[0], t[0]), []).append(t)
    rels = {t[1] for t in g}
    single = {r for r, n in Counter(t[1] for t in g).items() if n == 1}
    forced = {u for u, ts in units.items() if any(t[1] in single for t in ts)}
    by_cat = {}
    for u in sorted(units):
        by_cat.setdefault(cat_of(units[u][0][0]), []).append(u)
    rng = random.Random(seed)
    for attempt in range(1, 20001):
        exu = set()
        for c, us in by_cat.items():
            exu |= set(rng.sample([u for u in us if u not in forced], N_EX_UNITS[c]))
        ex = sorted(t for u in exu for t in units[u])
        ho = sorted(t for u in units if u not in exu for t in units[u])
        if ({t[1] for t in ho} == rels and {t[1] for t in ex} == rels - single and 5 <= len(ex) <= 7):
            break
    else:
        sys.exit("분할 실패")
    one = random.Random(20260917).choice(ex)
    rec = lambda t: {"subject": t[0], "predicate": t[1], "object": t[2], "category": cat_of(t[0])}
    sp = {"name": "padis_holdout_split", "seed": seed, "rejection_attempt": attempt,
          "gold_definition": "configs/padis_concepts.json triples, subClassOf/hasOutcome 제외",
          "n_gold": len(g), "categories": CATEGORY, "alias_groups": ALIAS_GROUPS,
          "note": "주어 그룹 단위 분할. precludes 는 gold 에 1개뿐이라 heldout. one-shot 예시는 examples 중 random.Random(20260917).choice",
          "examples": [rec(t) for t in ex], "oneshot_example": rec(one), "heldout": [rec(t) for t in ho]}
    SPLIT.write_text(json.dumps(sp, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"gold {len(g)} → examples {len(ex)} / heldout {len(ho)} (시도 {attempt})  one-shot 예시: {one}")
    return sp


# ───────────── 원문 청크 ─────────────
_HDR = re.compile(r"^(Copyright © 2018 by the Society|Devlin et al\s*$|Critical Care Medicine www\.ccmjournal\.org|"
                  r"e\d{3} www\.ccmjournal\.org|Online Special Article)")


def _clean(lines):
    out = []
    for ln in lines:
        if _HDR.match(ln.strip()):
            continue
        cur = ln.rstrip()
        if out and re.search(r"[A-Za-z]-\s*$", out[-1]) and cur[:1].islower():
            out[-1] = re.sub(r"-\s*$", "", out[-1]) + cur
            continue
        out.append(cur)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def _split_big(cid, title, text, max_chars=45_000):
    if len(text) <= max_chars:
        return [(cid, title, text)]
    lines = text.splitlines()
    mid = len(lines) // 2
    cands = [i for i, l in enumerate(lines) if l.startswith("Question:")] or [mid]
    cut = min(cands, key=lambda i: abs(i - mid))
    return (_split_big(cid + "a", title + " (1/2)", "\n".join(lines[:cut]) + "\n", max_chars)
            + _split_big(cid + "b", title + " (2/2)", "\n".join(lines[cut:]) + "\n", max_chars))


def chunks():
    L = (SRC / "padis2018.txt").read_text(encoding="utf-8").splitlines()
    s = next(i for i, l in enumerate(L) if l.startswith("linical practice guidelines are published")) - 1
    e = next(i for i, l in enumerate(L) if l.strip() == "ACKNOWLEDGMENTS")
    heads = [("METHODS", None), ("PAIN", "01_pain"), ("AGITATION/SEDATION", "02_agitation_sedation"),
             ("DELIRIUM", "03_delirium"), ("IMMOBILITY (REHABILITATION/", "04_immobility"),
             ("SLEEP DISRUPTION", "05_sleep_summary")]
    idx = {h: next(i for i in range(s, e) if L[i].strip() == h) for h, _ in heads}
    bounds = [(s, idx["AGITATION/SEDATION"], "01_intro_pain", "2018 PADIS: 서론·방법·Pain"),
              (idx["AGITATION/SEDATION"], idx["DELIRIUM"], "02_agitation_sedation", "2018 PADIS: Agitation/Sedation"),
              (idx["DELIRIUM"], idx["IMMOBILITY (REHABILITATION/"], "03_delirium", "2018 PADIS: Delirium"),
              (idx["IMMOBILITY (REHABILITATION/"], idx["SLEEP DISRUPTION"], "04_immobility", "2018 PADIS: Immobility"),
              (idx["SLEEP DISRUPTION"], e, "05_sleep_summary", "2018 PADIS: Sleep disruption·Summary")]
    out = []
    for a, b, cid, title in bounds:
        text = _clean(L[a:b])
        if cid == "01_intro_pain":
            text = "C" + text if text.startswith("linical") else text
        out += _split_big(cid, title, text)
    U = (SRC / "padis2025.txt").read_text(encoding="utf-8").splitlines()
    a = next(i for i, l in enumerate(U) if l.strip() == "TABLE 1.")
    b = next(i for i, l in enumerate(U) if l.strip() == "N/A = not applicable.")
    out.append(("06_focused_update_2025", "2025 PADIS Focused Update: Table 1 (권고 요약)", _clean(U[a:b + 1])))
    return out


def build():
    sp = make_split()
    c = cfg()
    concepts = "\n".join(f"- {x['id']}  ({', '.join([x.get('snomed_label', '')] + x.get('aliases', []))})"
                         for x in c["concepts"])
    relations = "\n".join(f"- {r}: {d}" for r, d in REL_DEFS.items())
    fmt = lambda ts: "\n".join(f'  {{"subject": "{t["subject"]}", "predicate": "{t["predicate"]}", "object": "{t["object"]}"}}'
                               for t in ts)
    ch = chunks()
    WORK.mkdir(parents=True, exist_ok=True)
    manifest = {"chunks": [], "split": SPLIT.name}
    for k, (cid, title, text) in enumerate(ch, 1):
        (WORK / f"chunk_{cid}.txt").write_text(text, encoding="utf-8")
        label = f"조각 {k}/{len(ch)}: {title}"
        for cond, n in CONDS.items():
            ex = [] if n == 0 else [sp["oneshot_example"]] if n == 1 else sp["examples"]
            body = PROMPT.format(label=label, relations=relations, concepts=concepts, text=text,
                                 examples=EX_BLOCK.format(n=len(ex), lines=fmt(ex)) if ex else "",
                                 example_rules=EX_RULES if ex else "")
            (WORK / f"prompt_{cond}_{cid}.txt").write_text(body, encoding="utf-8")
        manifest["chunks"].append({"id": cid, "title": title, "chars": len(text)})
        print(f"  {cid:28s} {len(text):7,}자  {title}")
    (WORK / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"프롬프트 {len(ch)} × {len(CONDS)} → {WORK}")


# ───────────── 채점 ─────────────
def _alnum(s):
    return re.sub(r"[^0-9a-z]", "", str(s).lower())


def load_run(d: Path):
    items = []
    for f in sorted(d.glob("*.json")):
        txt = f.read_text(encoding="utf-8").strip()
        m = re.search(r"\[.*\]", txt, re.S)
        arr = json.loads(m.group(0)) if m else []
        for t in arr:
            t["_chunk"] = f.stem
        items += arr
    return items


def score():
    sp = json.loads(SPLIT.read_text(encoding="utf-8"))
    key = lambda t: (t["subject"], t["predicate"], t["object"])
    ho = {key(t) for t in sp["heldout"]}
    exs = {key(t) for t in sp["examples"]}
    src = _alnum("".join((WORK / f"chunk_{c['id']}.txt").read_text(encoding="utf-8")
                         for c in json.loads((WORK / "manifest.json").read_text(encoding="utf-8"))["chunks"]))
    ids = {x["id"] for x in cfg()["concepts"]}
    rows, sets = [], {}
    for d in sorted((WORK / "runs").glob("*_run*")):
        cond = d.name.split("_run")[0]
        shown = set() if cond == "zeroshot" else {key(sp["oneshot_example"])} if cond == "oneshot" else exs
        items = load_run(d)
        uniq = {key(t) for t in items}
        sets[d.name] = uniq
        ev_ok = sum(_alnum(t.get("evidence", "")) in src and bool(_alnum(t.get("evidence", ""))) for t in items)
        off = sum(t["subject"] not in ids or t["object"] not in ids or t["predicate"] not in REL_DEFS for t in items)
        rows.append({"run": d.name, "추출": len(items), "고유": len(uniq), "held-out 재현": f"{len(uniq & ho)}/{len(ho)}",
                     "보여준 예시 재현": f"{len(uniq & shown)}/{len(shown)}", "gold 밖": len(uniq - ho - exs),
                     "evidence 원문 그대로": f"{ev_ok}/{len(items)}", "개념·술어 목록 밖": off,
                     "held-out 적중": sorted(f"{s}-{p}->{o}" for s, p, o in uniq & ho)})
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    for cond in CONDS:
        rs = [k for k in sets if k.startswith(cond + "_run")]
        for a, b in combinations(rs, 2):
            j = len(sets[a] & sets[b]) / max(len(sets[a] | sets[b]), 1)
            print(f"  반복 일치 {cond}: Jaccard {j:.2f} ({len(sets[a] & sets[b])}/{len(sets[a] | sets[b])})")
    (WORK / "score_gold.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


# ───────────── 블라인드 판정 ─────────────
JUDGE = """당신은 임상 가이드라인에서 추출된 지식그래프 트리플이 근거 문장에 의해 지지되는지 판정합니다.
각 행은 (subject, predicate, object) 트리플과 그 근거로 제시된 원문 문장(evidence)입니다. **evidence 문장 하나만** 보고 판정하세요.
원문 다른 곳에 근거가 있을 것 같다는 추측이나 의학 지식은 반영하지 마세요.

술어 뜻:
{relations}

판정:
- Y: 문장이 subject–object 관계를 진술하고, 술어(방향 포함)가 맞다
- 부분: 관계는 진술되나 술어가 어긋남(연관만 말하는데 increasesRiskOf 등), 개념 매핑이 느슨함, 특정 하위집단·비교 조건 한정
- N: 관계 진술 없음 / 반대 진술 / 중재·프로그램 효과를 환자 특성 규칙으로 바꿈 / 문장이 관계와 무관

출력: CSV 만 (헤더 포함, 설명 금지). 열: row_id,판정,이유   (판정은 Y / 부분 / N, 이유는 한 줄, 쉼표 대신 · 사용)

{rows}
"""


def blind(judges: int):
    sp = json.loads(SPLIT.read_text(encoding="utf-8"))
    pool = {}
    for d in sorted((WORK / "runs").glob("*_run*")):
        for t in load_run(d):
            ev = " ".join(str(t.get("evidence", "")).split())
            pool.setdefault((t["subject"], t["predicate"], t["object"], ev), set()).add(d.name)
    items = list(pool.items())
    random.Random(20260917).shuffle(items)
    key_rows, lines = [], []
    for i, ((s, p, o, ev), srcs) in enumerate(items, 1):
        rid = f"P{i:03d}"
        key_rows.append({"row_id": rid, "subject": s, "predicate": p, "object": o, "evidence": ev, "src": ";".join(sorted(srcs))})
        lines.append(f"[{rid}] ({s}, {p}, {o})\n  evidence: {ev}")
    with (WORK / "_blind_key.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(key_rows[0]))
        w.writeheader()
        w.writerows(key_rows)
    body = JUDGE.format(relations="\n".join(f"- {r}: {d}" for r, d in REL_DEFS.items()), rows="\n".join(lines))
    for j in range(1, judges + 1):
        (WORK / f"judge_prompt_j{j}.txt").write_text(body, encoding="utf-8")
    print(f"판정 대상 {len(items)}건 (트리플+evidence 고유) → judge_prompt_j1..{judges}.txt")


def unblind():
    sp = json.loads(SPLIT.read_text(encoding="utf-8"))
    key = {r["row_id"]: r for r in csv.DictReader((WORK / "_blind_key.csv").open(encoding="utf-8-sig"))}
    ho = {(t["subject"], t["predicate"], t["object"]) for t in sp["heldout"]}
    js = {}
    for f in sorted(WORK.glob("judge_out_j*.csv")):
        txt = f.read_text(encoding="utf-8-sig")
        rows = list(csv.DictReader(txt[txt.index("row_id"):].splitlines()))
        js[f.stem[-2:]] = {r["row_id"].strip(): r["판정"].strip().replace("부분", "P") for r in rows}
    names = sorted(js)
    if len(names) >= 2:
        a, b = js[names[0]], js[names[1]]
        common = [k for k in key if k in a and k in b]
        po = sum(a[k] == b[k] for k in common) / len(common)
        ca, cb = Counter(a[k] for k in common), Counter(b[k] for k in common)
        pe = sum(ca[x] * cb[x] for x in set(ca) | set(cb)) / len(common) ** 2
        print(f"판정자 일치 {po:.2%} · Cohen κ {(po - pe) / (1 - pe) if pe < 1 else 1:.2f} ({len(common)}건)")
        diff = [k for k in common if a[k] != b[k]]
        for k in diff:
            r = key[k]
            print(f"  불일치 {k}: {r['subject']}-{r['predicate']}->{r['object']}  {names[0]}={a[k]} {names[1]}={b[k]}")
    j0 = js[names[0]]
    by_run = {}
    for rid, r in key.items():
        for run in r["src"].split(";"):
            by_run.setdefault(run, []).append((rid, r))
    out = []
    for run in sorted(by_run):
        vals = Counter(j0.get(rid, "?") for rid, _ in by_run[run])
        n = sum(vals.values())
        ho_y = {(r["subject"], r["predicate"], r["object"]) for rid, r in by_run[run]
                if j0.get(rid) == "Y" and (r["subject"], r["predicate"], r["object"]) in ho}
        out.append({"run": run, "판정 건수(트리플+evidence)": n, "Y": vals["Y"], "부분": vals["P"], "N": vals["N"],
                    "근거 지지 Y%": round(100 * vals["Y"] / n, 1) if n else None,
                    "근거 지지 held-out 재현": f"{len(ho_y)}/{len(ho)}", "held-out Y": sorted("-".join(t) for t in ho_y)})
        print(json.dumps(out[-1], ensure_ascii=False))
    with (WORK / "blind_review_unblinded.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["row_id", "subject", "predicate", "object", "evidence", "src", "heldout"] + [f"판정_{n}" for n in names])
        for rid, r in key.items():
            w.writerow([rid, r["subject"], r["predicate"], r["object"], r["evidence"], r["src"],
                        (r["subject"], r["predicate"], r["object"]) in ho] + [js[n].get(rid, "") for n in names])
    (WORK / "score_blind.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "score", "blind", "unblind"])
    ap.add_argument("--judges", type=int, default=2)
    a = ap.parse_args()
    {"build": build, "score": score, "blind": lambda: blind(a.judges), "unblind": unblind}[a.cmd]()
