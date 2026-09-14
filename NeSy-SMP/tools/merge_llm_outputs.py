# -*- coding: utf-8 -*-
"""청크별 LLM 응답 파일들을 채점용 JSON 하나로 합친다.

응답을 복사해 저장할 때 흔히 섞이는 것을 견딘다:
  ```json 코드펜스, 앞뒤 설명 문장, 빈 배열 [].
각 트리플에 "_chunk" (파일 이름에서 추출) 를 붙인다 — 검토 CSV 의 chunk 열이 된다.
중복은 지우지 않는다(채점은 set 으로 중복 제거, 검토 CSV 는 원래 행을 모두 보여준다).

사용:
  python tools/merge_llm_outputs.py tools/fewshot_sepsis_holdout_*.result.json -o tools/fewshot_sepsis_holdout_merged.json
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
KEYS = ("subject", "predicate", "object", "evidence")


def parse(text: str):
    text = re.sub(r"```(?:json)?", "", text)
    s, e = text.find("["), text.rfind("]")
    if s < 0 or e < s:
        raise ValueError("JSON 배열([...])을 찾지 못함")
    data = json.loads(text[s:e + 1])
    if not isinstance(data, list):
        raise ValueError("최상위가 배열이 아님")
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="청크별 응답 파일 (glob 가능)")
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()

    paths = sorted({p for pat in args.files for p in (glob.glob(pat) or [pat])})
    merged, bad = [], 0
    for p in paths:
        m = re.search(r"_(\d{2}[a-z_]*?[a-z])(?:\.result)?\.(?:json|txt)$", Path(p).name)
        chunk = m.group(1) if m else Path(p).stem
        try:
            items = parse(Path(p).read_text(encoding="utf-8-sig"))
        except Exception as ex:
            print(f"  ✗ {p}: {ex}")
            bad += 1
            continue
        ok = 0
        for t in items:
            if not isinstance(t, dict) or any(k not in t for k in KEYS[:3]):
                print(f"  ! {p}: 필드 누락 항목 건너뜀 {t}")
                continue
            t = {k: t.get(k, "") for k in KEYS} | {"_chunk": chunk}
            merged.append(t)
            ok += 1
        print(f"  ✓ {Path(p).name:55s} {ok:3d}개  (chunk {chunk})")
    args.out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    uniq = {(t["subject"], t["predicate"], t["object"]) for t in merged}
    print(f"합계 {len(merged)}개 (서로 다른 트리플 {len(uniq)}), 파일 {len(paths)}개 중 실패 {bad} -> {args.out}")
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
