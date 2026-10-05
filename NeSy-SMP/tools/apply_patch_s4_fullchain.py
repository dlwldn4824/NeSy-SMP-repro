"""[PATCH S4] 빠진 연결 5개를 추가한다 — 공리를 사망 예측까지 end-to-end 로 잇는다.

원본 코드의 knowledge 공리는 함축(→ P)이 8개뿐이고, GCS·호흡수·수축기혈압·크레아티닌·평균혈압의
위험 술어는 **앵커만 있고 사망 함축이 없다**. 기울기 확인(`eda/38_grad_path_check.py` · 같은 구조)에서
이런 공리는 사망 로짓에 기울기가 정확히 0 이었다 — 학습에 영향을 줄 경로가 없다.

이 패치는 다음 5개를 함축 공리로 추가한다 (계산 방식·가중치·에폭은 그대로).
    GCSRisk · RespiratoryRateRisk · ArterialBloodPressureSystolicRisk ·
    CreatinineRisk · MeanArterialPressureRisk  →  P(x)

적용 대상: upstream_sensitivity_axiom 사본 (= S1 결측 처리 수정 + P6 기록 포함).
사용: python apply_patch_s4_fullchain.py <upstream_sens_fullchain/stratified_main.py>
"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
if "[PATCH S4]" in s:
    sys.exit(f"skip (already patched): {p}")

a = ("                Forall(x_All, Implies(AgeRisk(age(x_All), comorbidities(x_All)), "
     "P(x_All))).value,\n")
add = (
    "                # [PATCH S4] 원본에 없던 함축 5개 — 앵커만 있던 술어를 사망까지 연결\n"
    "                Forall(x_All, Implies(GCSRisk(gcs(x_All), comorbidities(x_All), age(x_All)), P(x_All))).value,\n"
    "                Forall(x_All, Implies(RespiratoryRateRisk(respiratory_rate(x_All), comorbidities(x_All), age(x_All)), P(x_All))).value,\n"
    "                Forall(x_All, Implies(ArterialBloodPressureSystolicRisk(abps(x_All), comorbidities(x_All), age(x_All)), P(x_All))).value,\n"
    "                Forall(x_All, Implies(CreatinineRisk(creatinine(x_All), comorbidities(x_All), age(x_All)), P(x_All))).value,\n"
    "                Forall(x_All, Implies(MeanArterialPressureRisk(mabp(x_All), comorbidities(x_All), age(x_All)), P(x_All))).value,\n"
)
assert s.count(a) == 1, "함축 블록(AgeRisk 줄)을 못 찾음"
s = s.replace(a, a + add)

# P6 기록 패치의 이름 목록도 늘려야 assert 가 통과한다
b = ('            _names += ["impl:" + _n for _n in ("Lactate", "Bilirubin", "Platelet", '
     '"LactateNotClearing", "CRP", "Chronic", "WBC", "Age")]')
c = ('            _names += ["impl:" + _n for _n in ("Lactate", "Bilirubin", "Platelet", '
     '"LactateNotClearing", "CRP", "Chronic", "WBC", "Age",\n'
     '                                              "GCS", "RR", "SBP", "Creatinine", "MAP")]'
     '   # [PATCH S4]')
assert s.count(b) == 1, "P6 이름 목록을 못 찾음"
s = s.replace(b, c)

# MeanArterialPressureRisk 는 원본에서 optimizer params 에 빠져 있다 → 학습되지 않으면 함축이 상수가 된다
d = "    params = list(P.parameters()) + list(LactateRisk.parameters())"
e = ("    params = list(MeanArterialPressureRisk.parameters()) "
     "+ list(P.parameters()) + list(LactateRisk.parameters())   # [PATCH S4] MAP 술어도 학습 대상에")
assert s.count(d) == 1, "optimizer params 줄을 못 찾음"
s = s.replace(d, e)

p.write_text(s, encoding="utf-8")
print(f"patched: {p}  (함축 5개 추가 · P6 이름 5개 추가 · MAP 술어 학습 대상 포함)")
