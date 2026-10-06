"""[PATCH S5] 연결 변형 — 혈당 함축만 뺀다 (함축 4개: GCS · 수축기혈압 · 호흡수 · 크레아티닌).

왜: connect(S3) 의 새 함축 5개 중 **혈당 → 사망**의 만족도가 0.55 로 가장 낮다.
    혈당 > 100 이 입원의 80% 에서 켜지는데 실제 사망률은 15% 라 데이터와 정면 충돌한다.
    이 공리 하나가 AUC 이득을 깎는지 보려면, **그것만** 빼고 같은 조건으로 돌려야 한다.

혈당 버그 수정(S4)은 그대로 둔다 — 앵커는 켜진 채로 두고 사망으로 가는 길만 막는다.
따라서 connect 와의 차이는 '혈당 → 사망' 함축 한 줄뿐이다.

사용: python apply_patch_s5_connect4.py <upstream_sensitivity_connect4/stratified_main.py>
"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
if "[PATCH S5]" in s:
    sys.exit(f"skip (already patched): {p}")
assert "[PATCH S3]" in s and "[PATCH S4]" in s, "connect(S3·S4) 사본이 아니다"

a = ("                Forall(x_All, Implies(GlucoseRisk(glucose(x_All), comorbidities(x_All), "
     "age(x_All)), P(x_All))).value,   # [PATCH S3]\n")
assert s.count(a) == 1, "혈당 함축 줄을 못 찾음"
s = s.replace(a, "                # [PATCH S5] 혈당 함축 제외 — 만족도 0.55 로 데이터와 충돌하는지 분리\n")

b = ('                                              "GCS", "SBP", "RR", "Creatinine", "Glucose")]'
     '   # [PATCH S3]')
c = ('                                              "GCS", "SBP", "RR", "Creatinine")]'
     '   # [PATCH S5] 혈당 함축 제외')
assert s.count(b) == 1, "P6 함축 이름 목록을 못 찾음"
s = s.replace(b, c)

p.write_text(s, encoding="utf-8")
print(f"patched: {p}  (혈당 함축 1줄 제거 · P6 이름 1개 제거 → 함축 12개)")
