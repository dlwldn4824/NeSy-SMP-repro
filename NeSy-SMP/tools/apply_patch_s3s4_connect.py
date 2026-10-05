"""[PATCH S3 · S4] 빠진 사망 연결 5개 추가 + 혈당 버그 수정.

대상: upstream_sensitivity_connect/stratified_main.py (= upstream_sensitivity_axiom 사본,
      P1–P5 실행 패치 + S1 missing-aware + P6 기록 포함)

S4  혈당 버그 — 함수 객체를 1 과 비교해 변수가 항상 빈 집합이었다.
S3  함축 공리 5개 추가 — GCSRisk · ArterialBloodPressureSystolicRisk · RespiratoryRateRisk ·
    CreatinineRisk · GlucoseRisk 는 앵커만 있고 사망 함축이 없어 P 에 영향이 없었다.
    (P6 기록의 함축 이름 목록도 5개 늘려 로그 길이를 맞춘다.)

사용: python apply_patch_s3s4_connect.py <upstream_sensitivity_connect/stratified_main.py>
"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
if "[PATCH S3]" in s or "[PATCH S4]" in s:
    sys.exit(f"skip (already patched): {p}")

# ---- S4 혈당 버그
a = 'x_above_glucose = ltn.Variable("x_above_glucose", x[glucose_above_threshold==1])'
b = ('x_above_glucose = ltn.Variable("x_above_glucose", x[glucose_above_threshold(x)==1])'
     '   # [PATCH S4] 함수 객체를 1 과 비교해 항상 빈 집합이었다')
assert s.count(a) == 1, "혈당 변수 줄을 못 찾음"
s = s.replace(a, b)

# ---- S3 함축 5개
c = ("                Forall(x_All, Implies(AgeRisk(age(x_All), comorbidities(x_All)), "
     "P(x_All))).value,\n")
add = (
    "                Forall(x_All, Implies(GCSRisk(gcs(x_All), comorbidities(x_All), age(x_All)), P(x_All))).value,   # [PATCH S3]\n"
    "                Forall(x_All, Implies(ArterialBloodPressureSystolicRisk(abps(x_All), comorbidities(x_All), age(x_All)), P(x_All))).value,   # [PATCH S3]\n"
    "                Forall(x_All, Implies(RespiratoryRateRisk(respiratory_rate(x_All), comorbidities(x_All), age(x_All)), P(x_All))).value,   # [PATCH S3]\n"
    "                Forall(x_All, Implies(CreatinineRisk(creatinine(x_All), comorbidities(x_All), age(x_All)), P(x_All))).value,   # [PATCH S3]\n"
    "                Forall(x_All, Implies(GlucoseRisk(glucose(x_All), comorbidities(x_All), age(x_All)), P(x_All))).value,   # [PATCH S3]\n"
)
assert s.count(c) == 1, "함축 블록(AgeRisk 줄)을 못 찾음"
s = s.replace(c, c + add)

# ---- P6 기록의 함축 이름 목록 (앵커 이름은 조건부라 자동으로 늘어난다)
d = ('            _names += ["impl:" + _n for _n in ("Lactate", "Bilirubin", "Platelet", '
     '"LactateNotClearing", "CRP", "Chronic", "WBC", "Age")]')
e = ('            _names += ["impl:" + _n for _n in ("Lactate", "Bilirubin", "Platelet", '
     '"LactateNotClearing", "CRP", "Chronic", "WBC", "Age",\n'
     '                                              "GCS", "SBP", "RR", "Creatinine", "Glucose")]'
     '   # [PATCH S3]')
assert s.count(d) == 1, "P6 함축 이름 목록을 못 찾음"
s = s.replace(d, e)

p.write_text(s, encoding="utf-8")
print(f"patched: {p}  (S4 혈당 버그 1곳 · S3 함축 5개 · P6 이름 5개)")
