"""[PATCH S6] 논문 §4.5 공리 목록 9개에 맞춘다 — LowMAP 을 **Anchor + 함축 둘 다** 넣는다.

논문은 지식 공리 9개를 적어 두었는데(HighLactate · HighBilirubin · HighCRP · HighWBC ·
LowPlatelets · **LowMAP** · AgeRisk · LactateNotClearing · HasChronicCondition → HighMortality),
공개 코드는 그중 **LowMAP 만 빠져 있다.** 평균혈압 함수·술어(`mabp`, `MeanArterialPressureRisk`)는
정의돼 있지만 어떤 공리에도 쓰이지 않고, 옵티마이저 파라미터에도 들어가지 않는다.

이 패치는 네 곳을 바꾼다.

  S6-a `map_below_threshold` 를 결측 인식으로 (0 = 측정 없음). 원본 조건은 `< 65` 를 `.any()` 로 보므로
       측정이 없는 환자(0으로 채워짐)까지 전부 참이 된다 — 실제로 P6 기록에서 활성화율 **100%** 였다.
       S1 이 이 조건을 고치지 않은 것은 어떤 공리도 쓰지 않았기 때문이다.
  S6-b Anchor 공리 추가: 평균혈압 < 65 인 환자에서 `MeanArterialPressureRisk` 가 참
  S6-c 함축 공리 추가: `MeanArterialPressureRisk → P`(사망)
  S6-d 옵티마이저에 `MeanArterialPressureRisk` 파라미터 추가 (없으면 술어가 학습되지 않는다)
       + P6 기록 이름 목록에 `anchor:MAP<65` · `impl:MAP` 추가

적용 대상: `upstream_sensitivity_axiom` 사본 (원본 + P1~P6 + S1 결측 인식).
S1 을 함께 두는 이유 — 결측 처리를 고치지 않으면 MAP 공리가 환자 100% 에서 켜져 공리가 공허해지고,
그러면 "논문 목록대로 넣었을 때의 효과"가 아니라 "결측 버그"를 다시 재는 실험이 된다.

사용: python apply_patch_s6_map.py <대상 stratified_main.py>
"""
from __future__ import annotations

import sys
from pathlib import Path

MAP_COL = ('x[:,(features_dict["Arterial Blood Pressure mean"]*sequence_length-sequence_length):'
           '(features_dict["Arterial Blood Pressure mean"]*sequence_length)]')
SC0 = 'scalers["Arterial Blood Pressure mean"].transform(np.array([[0.0]]))[0][0]'
SC65 = 'scalers["Arterial Blood Pressure mean"].transform(np.array([[65.0]]))[0][0]'


def once(body: str, old: str, new: str) -> str:
    n = body.count(old)
    if n != 1:
        raise SystemExit(f"앵커가 {n}개 — 패치 중단:\n{old[:120]}")
    return body.replace(old, new)


def main(path: str) -> None:
    p = Path(path)
    body = p.read_text(encoding="utf-8")
    if "[PATCH S6]" in body:
        raise SystemExit("이미 S6 가 적용돼 있다")

    # ---- S6-a 결측 인식 (0 = 측정 없음)
    body = once(
        body,
        f"    map_below_threshold = lambda x: ({MAP_COL} < {SC65}).any(axis=1)",
        f"    map_below_threshold = lambda x: (({MAP_COL} < {SC65})"
        f" & (({MAP_COL} != 0) & ({MAP_COL} != {SC0}))).any(axis=1)   # [PATCH S6] 0 은 측정 없음",
    )

    # ---- S6-b Anchor 공리 (나이 앵커 블록 바로 뒤)
    body = once(
        body,
        """            if x_above_age.value.numel()>0:
                formulas_knowledge.extend([
                    Forall(x_above_age, AgeRisk(age(x_above_age), comorbidities(x_above_age))).value,
                ])
""",
        """            if x_above_age.value.numel()>0:
                formulas_knowledge.extend([
                    Forall(x_above_age, AgeRisk(age(x_above_age), comorbidities(x_above_age))).value,
                ])
            # [PATCH S6] 논문 §4.5 목록의 LowMAP — Anchor
            if x_below_map.value.numel()>0:
                formulas_knowledge.extend([
                    Forall(x_below_map, MeanArterialPressureRisk(mabp(x_below_map), comorbidities(x_below_map), age(x_below_map))).value,
                ])
""",
    )

    # ---- S6-c 함축 공리
    body = once(
        body,
        """                Forall(x_All, Implies(AgeRisk(age(x_All), comorbidities(x_All)), P(x_All))).value,
            ])
""",
        """                Forall(x_All, Implies(AgeRisk(age(x_All), comorbidities(x_All)), P(x_All))).value,
                # [PATCH S6] 논문 §4.5 목록의 LowMAP — 함축
                Forall(x_All, Implies(MeanArterialPressureRisk(mabp(x_All), comorbidities(x_All), age(x_All)), P(x_All))).value,
            ])
""",
    )

    # ---- S6-d 옵티마이저 + P6 이름
    body = once(
        body,
        "    params = list(P.parameters()) + list(LactateRisk.parameters())",
        "    params = list(MeanArterialPressureRisk.parameters()) + list(P.parameters()) + list(LactateRisk.parameters())   # [PATCH S6] MAP 술어도 학습 대상에",
    )
    body = once(
        body,
        '                           ("Glucose>100", x_above_glucose), ("WBC>30", x_above_wbc), ("Age>65", x_above_age)):\n'
        '                if _v.value.numel() > 0: _names.append("anchor:" + _n)',
        '                           ("Glucose>100", x_above_glucose), ("WBC>30", x_above_wbc), ("Age>65", x_above_age),\n'
        '                           ("MAP<65", x_below_map)):   # [PATCH S6]\n'
        '                if _v.value.numel() > 0: _names.append("anchor:" + _n)',
    )
    body = once(
        body,
        '            _names += ["impl:" + _n for _n in ("Lactate", "Bilirubin", "Platelet", "LactateNotClearing", "CRP", "Chronic", "WBC", "Age")]',
        '            _names += ["impl:" + _n for _n in ("Lactate", "Bilirubin", "Platelet", "LactateNotClearing", "CRP", "Chronic", "WBC", "Age",\n'
        '                                              "MAP")]   # [PATCH S6]',
    )

    p.write_text(body, encoding="utf-8")
    print(f"S6 적용 완료 -> {p}")
    print("  a 결측 인식 map_below_threshold · b Anchor · c 함축 · d 옵티마이저 + P6 이름")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
