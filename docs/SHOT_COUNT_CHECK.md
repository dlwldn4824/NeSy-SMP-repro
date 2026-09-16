# sepsis 규칙 추출 — 예시 개수 비교 (zero-shot · one-shot · few-shot)

작성 2026-09-17 · 설계는 `NeSy-SMP/tools/FEWSHOT_CHECK.md` §7–8 과 같고 **예시 개수만** 바꿨다.

## 설계

| 조건 | 프롬프트 예시 | 실행 | 비고 |
|---|---:|---|---|
| zero-shot | 0개 | 2회 (조각 6개 × 2) | `tools/sepsis_holdout_split_k0.json` |
| one-shot | 1개 — `Sepsis increasesRiskOf Death` | 2회 | 11개 중 `random.Random(20260917)` 로 추첨 · `split_k1.json` |
| few-shot | 11개 | 2회 (9/15 실행분 재사용) | `split.json` |

- 가이드라인: SSC 2021 본문 6조각, 원문·허용 개념·술어·규칙 문구 모두 동일
- **확인용 정답(held-out) 19개는 세 조건 모두 같다** — 재현율은 이 19개로만 잰다
- 추출: 조각마다 **대화 기록 없는 새 에이전트**, 프롬프트 파일 1개만 읽고 결과만 씀 (24개 전부 도구 2회 사용)
- 근거 판정: 세 조건 + regex 기준선 **57건을 섞고 출처를 가려** 새 판정자 2명이 각각 판정 (Y / 부분 / N)

## 결과

| 조건 | 실행 | 추출 (고유) | **근거 지지 Y** | 부분 | N | 확인용 19개 재현 | 반복 일치 (Jaccard) |
|---|---|---:|---:|---:|---:|---:|---:|
| zero-shot | 1회차 | 10 (7) | **70%** | 2 | 1 | 1/19 | **0.75** |
| zero-shot | 2회차 | 8 (7) | **75%** | 2 | 0 | 1/19 | |
| one-shot | 1회차 | 9 (6) | **89%** | 1 | 0 | 1/19 | **0.83** |
| one-shot | 2회차 | 8 (5) | **88%** | 1 | 0 | 1/19 | |
| few-shot | 1회차 | 10 (7) | **80%** | 2 | 0 | 1/19 | **1.00** |
| regex (기존) | — | 12 | 8% | 1 | 10 | 8/19 (근거 맞는 것 1) | — |

- **판정자 2명이 57건 전부 같게 판정 — Cohen κ = 1.00.** 지난번 판정자와도 기준 항목 24건 중 22건 일치(92%).
- **세 조건 모두 확인용 19개 중 1개(`SepticShock → Death`)만 재현한다.** 뽑히는 트리플이 조건과 거의 무관하게 같다:
  `Sepsis→Death` · `SepticShock→Death` · `Lactate associatedWith Death/Sepsis/SepticShock` (+ 조건·회차에 따라 `Hypotension associatedWith SepticShock`, `Sepsis causedBy Pneumonia`)
- Y 가 아닌 판정은 거의 전부 **정의상의 포함**(젖산·저혈압은 패혈성 쇼크 정의의 구성요소) → '부분'.
  진짜 오류(N)는 **zero-shot 1건뿐**: 치료 시기 문장("승압제 시작·MAP 달성 지연")에서 `MeanArterialPressure associatedWith Death` 를 뽑음.

## 해석

1. **무엇이 뽑히는지는 예시 개수가 아니라 원문이 정한다.** 예시 0·1·11개 모두 같은 소수의 규칙만 나오고, 기존 규칙 19개 중 18개는 어느 조건에서도 나오지 않는다.
   → 9/15 결론("기존 sepsis 규칙 대부분은 SSC 2021 원문에 쓰여 있지 않다")이 **예시에 끌려 나온 결과가 아님**을 확인.
2. **예시는 정확도와 일관성을 올린다.** 예시가 없으면 치료 효과 문장을 환자 특성 규칙으로 잘못 바꾸는 오류가 생기고(N 1건), 반복 일치도가 0.75 로 낮다.
   예시 1개만 있어도 근거 지지 88~89%, 일치도 0.83 으로 올라간다. 11개면 일치도 1.00.
3. 한계: 판정자도 LLM · 확인용 19개(1개 = 5.3%p) · 조건당 2회.

산출물: `NeSy-SMP/tools/llm_runs/{zeroshot,oneshot}_run{1,2}/` · `tools/llm_runs/blind_review_k01_j{1,2}_unblinded.csv` · 프롬프트 `tools/{zeroshot,oneshot}_sepsis_holdout_*.txt`
