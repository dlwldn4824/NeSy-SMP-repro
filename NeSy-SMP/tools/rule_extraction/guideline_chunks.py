# -*- coding: utf-8 -*-
"""PDF 에서 뽑은 SSC 2021 원문을 LLM 입력용 섹션 청크로 자른다.

- 앞부분(제목·저자·소속·교신저자)과 뒷부분(Supplementary Information · Author details ·
  Acknowledgements · Declarations · References) 을 버린다. References 는 원문의 37% (134KB) 이고,
  regex 추출기가 참고문헌 제목("...impact of dialytic modality on mortality")에서 트리플을 낸 전례가 있다.
- 본문은 **전부** 쓴다. '위험/예후/사망' 키워드로 섹션을 고르지 않는다 — 그 선택 자체가 gold 를
  아는 사람의 필터이고, "mortality 근처 개념 → 트리플" 이라는 regex 기준선의 편향을 그대로 옮긴다.
- 최상위 섹션 6개 경계에서 자른다(Introduction+Screening, Infection, Haemodynamic management,
  Ventilation, Additional therapies, Long-term outcomes and goals of care).
- 정리: 페이지 번호만 있는 줄, 이미지라 본문이 없는 "Table 1 (continued)" 줄 제거,
  줄끝 하이픈 분리("sep -\\nsis", "dys-\\nregulated") 이어붙이기. 그 밖의 줄바꿈은 유지한다.
"""
from __future__ import annotations

import re
from pathlib import Path

BODY_START = "Introduction"
BODY_END = "Supplementary Information"
SECTIONS = [  # (원문 제목 줄, 청크 id)
    ("Introduction", "01_intro_screening"),
    ("Infection", "02_infection"),
    ("Haemodynamic management", "03_haemodynamic"),
    ("Ventilation", "04_ventilation"),
    ("Additional therapies", "05_additional_therapies"),
    ("Long-term outcomes and goals of care", "06_longterm_goals"),
]
DISPLAY = {"Introduction": "Introduction + Screening and early treatment"}
MAX_CHARS = 60_000   # 이보다 크면 "Recommendation" 줄 경계에서 반으로 나눈다

_PAGE = re.compile(r"^\s*\d{3,4}\s*$")
_TABLE_STUB = re.compile(r"^Table 1( \(continued\)| Table of current recommendations)")
_HYPH_END = re.compile(r"\s?[-‑]\s*$")


def _h(line: str) -> str:
    """NBSP 등 유니코드 공백을 정규화한 제목 비교용 문자열."""
    return " ".join(line.split())


def _clean(lines):
    out = []
    for ln in lines:
        if _PAGE.match(ln) or _TABLE_STUB.match(ln):
            continue
        cur = ln.rstrip()
        if out and _HYPH_END.search(out[-1]) and cur[:1].islower():
            out[-1] = _HYPH_END.sub("", out[-1]) + cur
            continue
        out.append(cur)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _split_big(cid, title, text):
    if len(text) <= MAX_CHARS:
        return [(cid, title, text)]
    lines = text.splitlines()
    mid = len(lines) // 2
    cands = [i for i, l in enumerate(lines) if l.strip() == "Recommendation"] or [mid]
    cut = min(cands, key=lambda i: abs(i - mid))
    a, b = "\n".join(lines[:cut]) + "\n", "\n".join(lines[cut:]) + "\n"
    return _split_big(cid + "a", title + " (1/2)", a) + _split_big(cid + "b", title + " (2/2)", b)


def body_lines(raw: str):
    lines = raw.splitlines()
    s = next(i for i, l in enumerate(lines) if _h(l) == BODY_START)
    e = next(i for i, l in enumerate(lines) if _h(l) == BODY_END)
    return lines[s:e]


def chunk_ssc2021(path: Path):
    """[(chunk_id, section_title, cleaned_text)] 반환."""
    lines = body_lines(path.read_text(encoding="utf-8"))
    idx = []
    for title, cid in SECTIONS:
        hit = [i for i, l in enumerate(lines) if _h(l) == title]
        if not hit:
            raise ValueError(f"섹션 제목을 못 찾음: {title!r}")
        idx.append((hit[0], DISPLAY.get(title, title), cid))
    idx.sort()
    chunks = []
    for k, (i, title, cid) in enumerate(idx):
        j = idx[k + 1][0] if k + 1 < len(idx) else len(lines)
        chunks += _split_big(cid, title, _clean(lines[i:j]))
    return chunks


def cleaned_body(path: Path) -> str:
    return _clean(body_lines(path.read_text(encoding="utf-8")))
