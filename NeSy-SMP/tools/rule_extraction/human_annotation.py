# -*- coding: utf-8 -*-
"""사람 어노테이션 ↔ LLM 판정 비교 (2026-11-17 회의 결정사항 1·2)

회의 결정
    "2명 이상 어노테이션 결과 비교 분석 (일부 샘플 대상)"
    "LLM 으로 평가 가능한 공리 부분만 추출하여 수동 검증"

지금 상태
    근거 판정(Y / 부분 / N)은 **LLM 판정자 2명**이 했다. 패혈증 57건(두 판정자 완전 일치 κ=1.00),
    PADIS 74건. 사람 판정은 아직 없다. 이 스크립트는 그 비교를 위한 것이다.

두 단계로 쓴다.

  1) sample — 사람이 채울 **블라인드 시트**를 만든다.
        LLM 판정·출처(zero/one/few-shot·regex)·정답셋 여부를 모두 가리고 순서를 섞는다.
        같은 시트를 두 사람이 각자 채운다 (파일명에 이름을 붙여 저장).

        python human_annotation.py sample --domain sepsis --n 40 --out-dir <폴더>
        python human_annotation.py sample --domain padis  --n 40 --out-dir <폴더>

  2) score — 채운 시트를 모아 일치도를 낸다.
        사람1↔사람2, 사람↔LLM 각각 일치율과 Cohen κ, 그리고 불일치 항목 목록을 낸다.

        python human_annotation.py score --domain sepsis --sheets <사람1.csv> <사람2.csv>

판정 기준 (LLM 판정자에게 준 것과 같게 유지할 것)
    Y    근거 문장이 그 관계를 직접 진술한다
    부분 관련은 있으나 정의상의 포함이거나 방향·대상이 어긋난다
    N    근거가 그 관계를 지지하지 않는다 (다른 관계를 말하거나, 중재 효과를 환자 특성으로 바꿨다)

주의
    PADIS 쪽 evidence 에는 가이드라인 원문 문장이 들어 있다. 시트는 저장소 밖(기본 C:/data)에 만든다.
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCES = {
    # 도메인: (판정 원본 csv, 판정 열 이름들)
    "sepsis": (ROOT / "NeSy-SMP/tools/rule_extraction/llm_runs/blind_review_k01_j1_unblinded.csv",
               ROOT / "NeSy-SMP/tools/rule_extraction/llm_runs/blind_review_k01_j2_unblinded.csv"),
    "padis": (Path(r"C:/data/padis_fewshot/blind_review_unblinded.csv"), None),
}
NORM = {"Y": "Y", "y": "Y", "P": "부분", "부분": "부분", "N": "N", "n": "N"}


def read_csv(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load(domain):
    """(row_id, subject, predicate, object, evidence, src, llm1, llm2) 목록."""
    a, b = SOURCES[domain]
    if domain == "sepsis":
        j1, j2 = {r["row_id"]: r for r in read_csv(a)}, {r["row_id"]: r for r in read_csv(b)}
        return [dict(row_id=k, subject=v["subject"], predicate=v["predicate"], object=v["object"],
                     evidence=v["evidence"], src=v["src"],
                     llm1=NORM.get(v["판정"].strip(), v["판정"].strip()),
                     llm2=NORM.get(j2.get(k, {}).get("판정", "").strip(), ""))
                for k, v in j1.items()]
    return [dict(row_id=r["row_id"], subject=r["subject"], predicate=r["predicate"],
                 object=r["object"], evidence=r["evidence"], src=r["src"],
                 llm1=NORM.get(r["판정_j1"].strip(), r["판정_j1"].strip()),
                 llm2=NORM.get(r["판정_j2"].strip(), r["판정_j2"].strip()))
            for r in read_csv(a)]


def sample(domain, n, out_dir, seed):
    rows = load(domain)
    # 출처별로 고르게 뽑는다 — 한 조건에만 몰리면 조건 간 비교를 못 한다
    by_src = {}
    for r in rows:
        by_src.setdefault(r["src"], []).append(r)
    rng = random.Random(seed)
    for v in by_src.values():
        rng.shuffle(v)
    picked, i = [], 0
    while len(picked) < min(n, len(rows)):
        added = False
        for v in by_src.values():
            if i < len(v) and len(picked) < n:
                picked.append(v[i]); added = True
        if not added:
            break
        i += 1
    rng.shuffle(picked)                      # 출처 순서가 드러나지 않게 다시 섞는다

    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    sheet = out_dir / f"사람판정_{domain}_{len(picked)}건.csv"
    key = out_dir / f"_정답키_{domain}.csv"            # 채점용. 판정자에게 주지 않는다
    with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["번호", "주어", "관계", "목적어", "근거 문장", "판정(Y/부분/N)", "이유"])
        for i, r in enumerate(picked, 1):
            w.writerow([i, r["subject"], r["predicate"], r["object"], r["evidence"], "", ""])
    with open(key, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["번호", "row_id", "출처", "LLM1", "LLM2"])
        for i, r in enumerate(picked, 1):
            w.writerow([i, r["row_id"], r["src"], r["llm1"], r["llm2"]])
    print(f"시트 {sheet}  ({len(picked)}건)")
    print(f"정답키 {key}  — 판정자에게 주지 말 것")
    print("\n두 사람이 같은 시트를 각자 복사해 채운 뒤 파일명에 이름을 붙여 저장하세요.")
    print("  예: 사람판정_%s_%d건_연서.csv · _지우.csv" % (domain, len(picked)))


def kappa(a, b):
    """Cohen κ. 두 판정 목록의 우연 일치를 보정한 일치도."""
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def score(domain, sheets, out_dir):
    key = {r["번호"]: r for r in read_csv(Path(out_dir) / f"_정답키_{domain}.csv")}
    filled = {}
    for p in sheets:
        name = Path(p).stem.split("_")[-1]
        filled[name] = {r["번호"]: NORM.get(r["판정(Y/부분/N)"].strip(), r["판정(Y/부분/N)"].strip())
                        for r in read_csv(p)}
    nums = [k for k in key if all(k in v and v[k] for v in filled.values())]
    if not nums:
        sys.exit("채워진 판정이 없다 — 시트의 '판정(Y/부분/N)' 열을 먼저 채우세요")
    people = list(filled)
    print(f"[{domain}] 채점 대상 {len(nums)}건 · 판정자 {people}")

    if len(people) >= 2:
        a = [filled[people[0]][k] for k in nums]
        b = [filled[people[1]][k] for k in nums]
        print(f"\n사람 {people[0]} ↔ {people[1]}: 일치 {100 * sum(x == y for x, y in zip(a, b)) / len(a):.1f}% "
              f"· κ {kappa(a, b):.2f}")
    for who in people:
        h = [filled[who][k] for k in nums]
        for llm in ("LLM1", "LLM2"):
            m = [key[k][llm] for k in nums]
            print(f"사람 {who} ↔ {llm}: 일치 {100 * sum(x == y for x, y in zip(h, m)) / len(h):.1f}% "
                  f"· κ {kappa(h, m):.2f}")

    print("\n[불일치 항목] 사람과 LLM1 이 다른 것")
    src_mismatch = Counter()
    for k in nums:
        h = {w: filled[w][k] for w in people}
        if any(v != key[k]["LLM1"] for v in h.values()):
            src_mismatch[key[k]["출처"]] += 1
            print(f"  #{k:>3s} {key[k]['row_id']:>4s} 출처 {key[k]['출처']:<14s} "
                  f"LLM {key[k]['LLM1']:<3s} ← 사람 {h}")
    if src_mismatch:
        print("\n출처별 불일치 수:", dict(src_mismatch))
    print("\n판정 분포")
    for who in people:
        print(f"  {who:8s}", dict(Counter(filled[who][k] for k in nums)))
    print(f"  {'LLM1':8s}", dict(Counter(key[k]['LLM1'] for k in nums)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("sample", help="블라인드 시트 만들기")
    s1.add_argument("--domain", choices=["sepsis", "padis"], required=True)
    s1.add_argument("--n", type=int, default=40)
    s1.add_argument("--out-dir", default=r"C:/data/annotation")
    s1.add_argument("--seed", type=int, default=20261117)
    s2 = sub.add_parser("score", help="채운 시트 채점")
    s2.add_argument("--domain", choices=["sepsis", "padis"], required=True)
    s2.add_argument("--sheets", nargs="+", required=True)
    s2.add_argument("--out-dir", default=r"C:/data/annotation")
    a = ap.parse_args()
    if a.cmd == "sample":
        sample(a.domain, a.n, a.out_dir, a.seed)
    else:
        score(a.domain, a.sheets, a.out_dir)


if __name__ == "__main__":
    main()
