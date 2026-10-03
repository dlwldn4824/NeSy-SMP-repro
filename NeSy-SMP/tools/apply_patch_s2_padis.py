"""[PATCH S2] 안 2 — sepsis 학습 입력에 PADIS 변수 5개를 피처로 추가.

원본 전처리는 피처 목록이 코드에 박혀 있다. 그 목록 두 곳(수치 스케일 루프 · 최종 열 선택)에
RASS · Pain NRS · Mobility level · Restraint · Sedative 를 끼운다. 계산 방식은 바꾸지 않는다.
논문 조건 재현이 아니라 **민감도 실험**이므로 코드 사본을 따로 둔다.

사용: python apply_patch_s2_padis.py <upstream_sens_padis/data/preprocessing.py>
"""
import sys
from pathlib import Path

NEW = '"RASS", "Pain NRS", "Mobility level", "Restraint", "Sedative", '
p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
if "[PATCH S2]" in s:
    sys.exit(f"skip (already patched): {p}")

a = '"Asparate Aminotransferase (AST)", "gcs", "anchor_age"]:'
b = '"Asparate Aminotransferase (AST)", "gcs", ' + NEW + '"anchor_age"]:   # [PATCH S2]'
n = s.count(a)
assert n >= 1, "수치 스케일 루프를 못 찾음"
s = s.replace(a, b)

c = '"Asparate Aminotransferase (AST)", "gcs",' + chr(10)
d = '"Asparate Aminotransferase (AST)", "gcs", ' + NEW + '  # [PATCH S2]' + chr(10)
m = s.count(c)
assert m >= 1, "최종 열 선택 목록을 못 찾음"
s = s.replace(c, d)
p.write_text(s, encoding="utf-8")
print(f"patched: {p}  (수치 루프 {n}곳 · 열 선택 {m}곳)")
