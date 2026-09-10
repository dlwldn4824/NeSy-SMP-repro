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
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

NORM_REL = {"increaseRiskOf": "increasesRiskOf"}


def norm(t):
    return (t["subject"], NORM_REL.get(t["predicate"], t["predicate"]), t["object"])


def load_gold():
    cfg = json.loads((ROOT / "configs" / "clinical_concepts.json").read_text(encoding="utf-8"))
    g_cfg = {norm(t) for t in cfg["triples"]}
    g_pkg = set()
    for ln in (ROOT / "rules" / "pkg.txt").read_text(encoding="utf-8").splitlines():
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
    cfg = json.loads((ROOT / "configs" / "clinical_concepts.json").read_text(encoding="utf-8"))
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-prompt", type=Path, help="가이드라인 원문 txt")
    ap.add_argument("--out", type=Path, default=ROOT / "tools" / "fewshot_prompt.txt")
    ap.add_argument("--score", type=Path, help="채점할 트리플 JSON")
    args = ap.parse_args()

    g_cfg, g_pkg = load_gold()

    if args.build_prompt:
        if not args.build_prompt.exists():
            sys.exit(f"원문 없음: {args.build_prompt}")
        build_prompt(args.build_prompt, args.out)
        return

    if args.score:
        pred = {norm(t) for t in json.loads(args.score.read_text(encoding="utf-8"))}
        print(f"채점 대상: {args.score} ({len(pred)}개)")
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

    score(pred, g_cfg, "configs/clinical_concepts.json triples")
    score(pred, {t for t in g_pkg if t[1] != "rdf-schema#subClassOf"
                 and t[1] != "22-rdf-syntax-ns#type"}, "rules/pkg.txt (관계 트리플만)")


if __name__ == "__main__":
    main()
