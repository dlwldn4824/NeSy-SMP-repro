# -*- coding: utf-8 -*-
"""규칙 추출이 '제대로 나오는지' 확인한다.

두 가지를 한다.
  (1) 현재 파이프라인(pipeline/guideline_extract.py) 이 뽑은 트리플을 gold 와 대조해 P/R/F1
  (2) few-shot 프롬프트를 만들어 파일로 뺀다 — 기존 규칙을 예시로, 가이드라인 원문을 입력으로

gold 는 두 벌이다.
  configs/clinical_concepts.json 의 triples (25개) — 개념 스키마와 짝이 맞는 정본
  rules/pkg.txt (83개) — AnyBURL 학습용. 오타 변형(increaseRiskOf)과 subClassOf 가 섞여 있다.

⚠️ 현재 추출기는 가이드라인 원문이 아니라 DEFAULT_GUIDELINE_SENTENCES(손으로 쓴 10문장)를 읽는다.
   그 문장들은 이미 정답을 진술한 형태라 이걸로 재는 재현율은 상한이지 재현성 검증이 아니다.

사용:
  python tools/rule_extraction_check.py                       # 현재 파이프라인 채점
  python tools/rule_extraction_check.py --build-prompt <txt>  # few-shot 프롬프트 생성
  python tools/rule_extraction_check.py --score <triples.json># 외부 결과 채점

held-out (순환 없는 점검, 2026-09-15 추가 — tools/FEWSHOT_SEPSIS_README.md):
  # 분할의 examples 만 예시로, SSC 2021 본문을 섹션 청크별 프롬프트로
  python tools/rule_extraction_check.py --build-prompt pipeline_out/ssc2021_guideline.txt \\
      --examples-from tools/sepsis_holdout_split.json --chunk --out tools/fewshot_sepsis_holdout.txt
  # 예시셋 / held-out / gold 밖 을 따로 채점 + 사람 검토용 CSV
  python tools/rule_extraction_check.py --score <merged.json> --split tools/sepsis_holdout_split.json \\
      --review-csv tools/review_<name>.csv
  # 사람이 채운 CSV 집계 (근거 지지율)
  python tools/rule_extraction_check.py --score-review tools/review_<name>.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

NORM_REL = {"increaseRiskOf": "increasesRiskOf"}


def norm(t):
    return (t["subject"], NORM_REL.get(t["predicate"], t["predicate"]), t["object"])


CONCEPTS = ROOT / "configs" / "clinical_concepts.json"


def load_gold():
    cfg = json.loads(CONCEPTS.read_text(encoding="utf-8"))
    g_cfg = {norm(t) for t in cfg["triples"]
             if not norm(t)[1].startswith(("rdf-schema", "22-rdf", "hasOutcome"))}
    g_pkg = set()
    pkg = ROOT / "rules" / "pkg.txt"
    if not pkg.exists() or "padis" in CONCEPTS.name:
        return g_cfg, g_pkg
    for ln in pkg.read_text(encoding="utf-8").splitlines():
        p = ln.split("\t")
        if len(p) == 3:
            g_pkg.add(norm({"subject": p[0], "predicate": p[1], "object": p[2]}))
    return g_cfg, g_pkg


def score(pred, gold, name):
    tp = pred & gold
    p = len(tp) / len(pred) if pred else 0.0
    r = len(tp) / len(gold) if gold else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    print(f"\n  vs {name} (gold {len(gold)}개)")
    print(f"    precision {100*p:5.1f}%  recall {100*r:5.1f}%  F1 {100*f:5.1f}%"
          f"   (맞음 {len(tp)} / 예측 {len(pred)})")
    if pred - gold:
        print(f"    ✗ gold 에 없는 것 {len(pred - gold)}:")
        for t in sorted(pred - gold):
            print(f"        {t[0]} -{t[1]}-> {t[2]}")
    miss = gold - pred
    if miss:
        print(f"    · 못 뽑은 것 {len(miss)} (상위 10)")
        for t in sorted(miss)[:10]:
            print(f"        {t[0]} -{t[1]}-> {t[2]}")
    return p, r, f


PROMPT = """당신은 임상 가이드라인에서 지식그래프 트리플을 추출합니다.

## 출력 형식
JSON 배열만 출력하세요. 설명 금지.
[{{"subject": "...", "predicate": "...", "object": "...", "evidence": "<근거가 된 원문 한 문장>"}}]

## 허용된 술어 (이 밖의 것을 쓰지 마세요)
{relations}

## 허용된 개념 (subject/object 는 반드시 이 id 중 하나)
{concepts}

## 예시 — 같은 과제에서 이미 승인된 트리플 {n_ex}개
{examples}

## 규칙
- 한 문장에서 여러 트리플이 나올 수 있습니다.
- 가이드라인이 "연관 없음"을 명시하면 hasNoEffectOn 을 쓰세요.
- 위험을 낮추는 중재는 decreasesRiskOf 입니다.
- 근거 문장을 찾을 수 없으면 만들지 마세요.
- 개념 목록에 없는 대상은 버리세요.

## 입력 가이드라인 원문
{text}
"""


def build_prompt(text_path: Path, out_path: Path, n_ex: int = 20):
    cfg = json.loads(CONCEPTS.read_text(encoding="utf-8"))
    vocab = json.loads((ROOT / "configs" / "relation_vocab.json").read_text(encoding="utf-8"))
    ex = cfg["triples"][:n_ex]
    body = PROMPT.format(
        relations="\n".join(f"- {r}" for r in vocab["allowed_relations"]),
        concepts="\n".join(f"- {c['id']}  ({c.get('snomed_label','')})" for c in cfg["concepts"]),
        n_ex=len(ex),
        examples="\n".join(f'  {{"subject": "{t["subject"]}", "predicate": "{t["predicate"]}", '
                           f'"object": "{t["object"]}"}}' for t in ex),
        text=text_path.read_text(encoding="utf-8"),
    )
    out_path.write_text(body, encoding="utf-8")
    print(f"few-shot 프롬프트 -> {out_path}  ({len(body):,}자, 예시 {len(ex)}개)")


# ─────────────────────────────────────────────────────────────────────────────
# held-out 점검 (2026-09-15) — 예시로 보여준 규칙과 채점 규칙을 분리한다
# ─────────────────────────────────────────────────────────────────────────────

# 기존 PROMPT 는 그대로 두고(재현용) held-out 전용 템플릿을 따로 둔다. 차이:
#  - 입력이 전체 가이드라인의 한 섹션임을 알린다
#  - 술어 정의를 짧게 준다 / 오타(increaseRiskOf)·subClassOf·hasOutcome·리터럴 비교 술어는 뺀다
#  - 예시는 형식 참고일 뿐, 예시 트리플도 이 원문 근거가 있을 때만 내라고 못박는다
#  - "두 개념이 한 문장에 같이 나옴" 은 근거가 아니라고 명시한다 (regex 기준선의 실패 양상)
PROMPT_HOLDOUT = """당신은 임상 가이드라인 원문에서 지식그래프 트리플을 추출합니다.
입력은 Surviving Sepsis Campaign 2021 가이드라인 본문의 한 부분입니다 — [{chunk_label}].

## 출력 형식
JSON 배열만 출력하세요. 설명·마크다운 금지. 해당 트리플이 없으면 [] 를 출력하세요.
[{{"subject": "...", "predicate": "...", "object": "...", "evidence": "<근거가 된 원문 문장, 원문 그대로 복사>"}}]

## 허용된 술어 (이 밖의 것을 쓰지 마세요)
{relations}

## 허용된 개념 (subject/object 는 반드시 이 id 중 하나. 괄호 안은 원문에서 쓰일 수 있는 표현)
{concepts}

## 형식 예시 — 기존에 승인된 트리플 {n_ex}개 (출력 형식 참고)
{examples}

## 규칙
- 위 예시는 **출력 형식 참고용**입니다. 예시에 있는 트리플이라도 아래 입력 원문에 근거 문장이 없으면 내지 마세요.
- 예시에 없는 개념·술어라도 원문 근거가 있으면 추출하세요.
- evidence 는 입력 원문에서 **그대로 복사한** 문장이어야 합니다(줄바꿈은 공백으로). 요약·번역·여러 문장 합성 금지.
- evidence 문장 자체가 subject 와 object 사이의 관계를 진술해야 합니다.
  두 개념이 같은 문장에 함께 등장하는 것만으로는 근거가 아닙니다.
- 중재(치료·검사·프로그램)의 효과를 말하는 문장을 환자 특성 → 결과 트리플로 바꾸지 마세요.
- 가이드라인이 "연관/효과 없음"을 명시하면 hasNoEffectOn 을 쓰세요.
- 한 문장에서 여러 트리플이 나올 수 있습니다.
- 개념 목록에 없는 대상은 버리세요.

## 입력 가이드라인 원문 [{chunk_label}]
{text}
"""

REL_DEFS = {
    "increasesRiskOf": "subject 가 있거나 높으면 object 의 위험이 커진다",
    "decreasesRiskOf": "subject 가 object 의 위험을 낮춘다",
    "associatedWith": "subject 와 object 가 연관된다 (방향·인과를 진술하지 않음)",
    "causedBy": "subject 가 object 에 의해 생긴다",
    "hasNoEffectOn": "subject 가 object 에 영향/연관이 없다고 명시",
    "precludes": "subject 가 object 의 적용·평가를 불가능하게 한다",
}


def load_split(path: Path):
    sp = json.loads(path.read_text(encoding="utf-8"))
    ex = {norm(t) for t in sp["examples"]}
    ho = {norm(t) for t in sp["heldout"]}
    if ex & ho:
        sys.exit(f"분할 오류: examples 와 heldout 이 겹친다 {sorted(ex & ho)}")
    return sp, ex, ho


def build_holdout_prompts(text_path: Path, out_path: Path, split_path: Path, chunk: bool):
    cfg = json.loads(CONCEPTS.read_text(encoding="utf-8"))
    vocab = json.loads((ROOT / "configs" / "relation_vocab.json").read_text(encoding="utf-8"))
    sp, _, _ = load_split(split_path)
    rels = [r for r in vocab["allowed_relations"] if r in REL_DEFS]
    ex = sp["examples"]
    common = dict(
        relations="\n".join(f"- {r}: {REL_DEFS[r]}" for r in rels),
        concepts="\n".join(f"- {c['id']}  ({', '.join([c.get('snomed_label', '')] + c.get('aliases', []))})"
                           for c in cfg["concepts"]),
        n_ex=len(ex),
        examples="\n".join(f'  {{"subject": "{t["subject"]}", "predicate": "{t["predicate"]}", '
                           f'"object": "{t["object"]}"}}' for t in ex),
    )
    if chunk:
        from guideline_chunks import chunk_ssc2021
        chunks = chunk_ssc2021(text_path)
    else:
        chunks = [("all", "전체", text_path.read_text(encoding="utf-8"))]
    manifest = {"source": str(text_path.name), "split": str(split_path.name),
                "n_examples": len(ex), "chunks": []}
    stem = out_path.with_suffix("")
    for k, (cid, title, text) in enumerate(chunks, 1):
        label = f"섹션 {k}/{len(chunks)}: {title}"
        body = PROMPT_HOLDOUT.format(chunk_label=label, text=text, **common)
        p = out_path if cid == "all" else stem.parent / f"{stem.name}_{cid}.txt"
        p.write_text(body, encoding="utf-8")
        manifest["chunks"].append({"id": cid, "section": title, "prompt": p.name,
                                   "prompt_chars": len(body), "guideline_chars": len(text),
                                   "result_file": f"{stem.name}_{cid}.result.json"})
        print(f"  [{k}/{len(chunks)}] {p.name:48s} 프롬프트 {len(body):7,}자 (원문 {len(text):6,}자)  {title}")
    mp = stem.parent / f"{stem.name}_manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"예시 {len(ex)}개 (split: {split_path.name}) · 청크 {len(chunks)}개 · manifest -> {mp.name}")


def _pct(a, b):
    return f"{100*a/b:5.1f}% ({a}/{b})" if b else "  n/a"


def score_split(pred, split_path: Path):
    sp, ex, ho = load_split(split_path)
    cfg = json.loads(CONCEPTS.read_text(encoding="utf-8"))
    vocab = json.loads((ROOT / "configs" / "relation_vocab.json").read_text(encoding="utf-8"))
    cids = {c["id"] for c in cfg["concepts"]}
    allowed = {NORM_REL.get(r, r) for r in vocab["allowed_relations"]}
    gold = ex | ho
    gold_pairs = {(t[0], t[2]) for t in gold}
    cat = {norm(t): t.get("category", "") for t in sp["examples"] + sp["heldout"]}

    hit_ex, hit_ho, outside = pred & ex, pred & ho, pred - gold
    print(f"\n  held-out 분할: {split_path.name}  (examples {len(ex)} / heldout {len(ho)})")
    print("  ─ ① 예시셋 적중 — 참고용. 프롬프트에 보여준 것이라 높아도 추출 능력의 증거가 아니다")
    print(f"      recall(examples) {_pct(len(hit_ex), len(ex))}")
    print("  ─ ② held-out — 주지표. 프롬프트에 없던 gold")
    print(f"      recall(heldout)  {_pct(len(hit_ho), len(ho))}")
    print(f"      precision(비예시) {_pct(len(hit_ho), len(pred - ex))}   = held-out 적중 / (예측 − 예시 적중)")
    for key, fn in (("관계별", lambda t: t[1]), ("카테고리별", lambda t: cat.get(t, "")),
                    ("object별", lambda t: t[2])):
        tot, hit = Counter(fn(t) for t in ho), Counter(fn(t) for t in hit_ho)
        print(f"      {key}: " + " · ".join(f"{k} {hit[k]}/{tot[k]}" for k in sorted(tot)))
    for t in sorted(ho):
        print(f"        {'✓' if t in hit_ho else '·'} {t[0]} -{t[1]}-> {t[2]}")
    print(f"  ─ ③ gold 밖 {len(outside)}개 — 오류일 수도, gold 가 빠뜨린 것일 수도 (근거 검토로 판정)")
    for t in sorted(outside):
        tags = []
        if (t[0], t[2]) in gold_pairs:
            tags.append("같은 쌍이 gold 에 다른 술어로 있음")
        if t[0] not in cids or t[2] not in cids:
            tags.append("개념 목록 밖")
        if t[1] not in allowed:
            tags.append("허용 술어 밖")
        print(f"        {t[0]} -{t[1]}-> {t[2]}" + (f"   [{'; '.join(tags)}]" if tags else ""))
    print("  ⚠️ gold 일치 ≠ 근거 지지. --review-csv 로 근거를 사람이 검토한 뒤 --score-review 로 집계할 것.")
    return {"examples": ex, "heldout": ho}


def _alnum(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", s.lower())


REVIEW_COLS = ["no", "subject", "predicate", "object", "evidence",
               "근거가_지지하나(Y/부분/N)", "메모",
               "원문에_evidence_있음(자동)", "gold_구분(검토 후 열람)", "chunk"]


def write_review_csv(raw_items, out_csv: Path, split_path: Path | None, guideline: Path | None):
    buckets = None
    if split_path:
        _, ex, ho = load_split(split_path)
        buckets = (ex, ho)
    body, whole = [], ""
    if guideline and guideline.exists():
        raw = guideline.read_text(encoding="utf-8")
        whole = _alnum(raw)
        try:   # 본문(참고문헌·서지 제외) — 원본 줄과 정리본 둘 다 (페이지 번호·하이픈 차이 흡수)
            from guideline_chunks import body_lines, cleaned_body
            body = [_alnum(" ".join(body_lines(raw))), _alnum(cleaned_body(guideline))]
        except Exception:
            body = [whole]
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(REVIEW_COLS)
        for i, t in enumerate(raw_items, 1):
            k = norm(t)
            ev = " ".join(str(t.get("evidence", "")).split())
            if not whole or not ev:
                found = "-"
            elif any(_alnum(ev) in h for h in body):
                found = "Y(본문)"
            elif _alnum(ev) in whole:
                found = "Y(본문 밖: 참고문헌·서지)"
            else:
                found = "N(원문에 없음)"
            if buckets is None:
                gb = "-"
            else:
                gb = "예시" if k in buckets[0] else "held-out" if k in buckets[1] else "gold 밖"
            w.writerow([i, k[0], k[1], k[2], ev, "", "", found, gb, t.get("_chunk", "")])
    print(f"\n검토 CSV -> {out_csv}  ({len(raw_items)}행, UTF-8 BOM)")
    print("  '근거가_지지하나' 는 비워 뒀다. gold_구분 열은 판정을 다 채운 뒤에 볼 것(편향 방지).")


def score_review(csv_path: Path, split_path: Path | None = None):
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    col = "근거가_지지하나(Y/부분/N)"
    gcol = "gold_구분(검토 후 열람)"
    blank = [r for r in rows if not r[col].strip()]
    print(f"검토 CSV: {csv_path}  ({len(rows)}행, 미판정 {len(blank)})")
    groups = {"전체": rows}
    for g in ("예시", "held-out", "gold 밖"):
        groups[g] = [r for r in rows if r.get(gcol) == g]
    for name, rs in groups.items():
        c = Counter(r[col].strip().upper().replace("부분", "P") for r in rs if r[col].strip())
        n = sum(c.values())
        if not rs:
            continue
        print(f"  {name:8s} 판정 {n}/{len(rs)}  Y {c['Y']} · 부분 {c['P']} · N {c['N']}"
              f"   근거 지지율(Y) {_pct(c['Y'], n)}   Y+부분 {_pct(c['Y'] + c['P'], n)}")
    ho_y = {(r["subject"], r["predicate"], r["object"]) for r in groups["held-out"]
            if r[col].strip().upper() == "Y"}
    if split_path:
        _, _, ho = load_split(split_path)
        print(f"  근거 지지 held-out recall {_pct(len(ho_y & ho), len(ho))}"
              "   = 근거 판정 Y 인 held-out 트리플 / held-out 전체")
    else:
        print(f"  held-out 중 근거 판정 Y 인 서로 다른 트리플 {len(ho_y)}개 (--split 을 주면 recall 로 환산)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-prompt", type=Path, help="가이드라인 원문 txt")
    ap.add_argument("--out", type=Path, default=ROOT / "tools" / "fewshot_prompt.txt")
    ap.add_argument("--score", type=Path, help="채점할 트리플 JSON")
    ap.add_argument("--concepts", type=Path, help="개념 설정 (기본: sepsis)")
    ap.add_argument("--n-ex", type=int, default=20, help="few-shot 예시 개수")
    # held-out (2026-09-15)
    ap.add_argument("--examples-from", type=Path,
                    help="분할 JSON — 이 파일의 examples 만 프롬프트 예시로 쓴다 (--n-ex 무시)")
    ap.add_argument("--chunk", action="store_true",
                    help="--examples-from 과 함께: SSC 2021 본문을 섹션별 프롬프트 여러 개로")
    ap.add_argument("--split", type=Path,
                    help="--score 와 함께: 예시셋 / held-out / gold 밖 을 따로 채점")
    ap.add_argument("--review-csv", type=Path,
                    help="--score 와 함께: 예측 트리플 + evidence + 빈 검토 열 CSV")
    ap.add_argument("--guideline", type=Path, default=ROOT / "pipeline_out" / "ssc2021_guideline.txt",
                    help="--review-csv 에서 evidence 가 원문에 실제로 있는지 대조할 원문")
    ap.add_argument("--score-review", type=Path, help="사람이 채운 검토 CSV 집계")
    args = ap.parse_args()
    global CONCEPTS
    if args.concepts:
        CONCEPTS = args.concepts
    g_cfg, g_pkg = load_gold()

    if args.score_review:
        score_review(args.score_review, args.split)
        return

    if args.build_prompt:
        if not args.build_prompt.exists():
            sys.exit(f"원문 없음: {args.build_prompt}")
        if args.examples_from:
            build_holdout_prompts(args.build_prompt, args.out, args.examples_from, args.chunk)
        else:
            build_prompt(args.build_prompt, args.out, args.n_ex)
        return

    if args.score:
        raw_items = json.loads(args.score.read_text(encoding="utf-8"))
        pred = {norm(t) for t in raw_items}
        print(f"채점 대상: {args.score} ({len(raw_items)}개, 중복 제거 {len(pred)}개)")
        if args.split:
            score_split(pred, args.split)
        if args.review_csv:
            write_review_csv(raw_items, args.review_csv, args.split, args.guideline)
        if args.split:
            return
    else:
        from pipeline.guideline_extract import extract_from_texts, DEFAULT_GUIDELINE_SENTENCES
        print("=" * 74)
        print("현재 파이프라인 — pipeline/guideline_extract.py")
        print("=" * 74)
        print(f"입력: DEFAULT_GUIDELINE_SENTENCES {len(DEFAULT_GUIDELINE_SENTENCES)}문장")
        print("  ⚠️ 가이드라인 원문이 아니라 코드에 하드코딩된 문장이다.")
        print("     이미 정답을 진술한 형태라 여기서 나온 recall 은 상한이다.")
        out = extract_from_texts(DEFAULT_GUIDELINE_SENTENCES,
                                 ROOT / "configs" / "clinical_concepts.json",
                                 ROOT / "configs" / "relation_vocab.json")
        pred = {norm(t) for t in out}
        print(f"\n추출 {len(pred)}개")

    score(pred, g_cfg, f"{CONCEPTS.name} 관계 트리플")
    rel = {t for t in g_pkg if not t[1].startswith(("rdf-schema", "22-rdf"))}
    if rel:
        score(pred, rel, "rules/pkg.txt (관계 트리플만)")


if __name__ == "__main__":
    main()
