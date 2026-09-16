# PADIS 규칙 추출 — zero-shot · one-shot · few-shot 비교

작성 2026-09-17 · 설계는 sepsis 점검(`SHOT_COUNT_CHECK.md`)과 같고 **도메인만 PADIS(섬망)** 로 바꿨다.
스크립트 `NeSy-SMP/tools/padis_holdout.py` · 분할 `NeSy-SMP/tools/padis_holdout_split.json`
원문·프롬프트·추출 결과·판정 원본은 저작권 때문에 저장소 밖 `C:\data\padis_fewshot\` 에 있다.

## 설계

| 항목 | 내용 |
|---|---|
| 정답(gold) | `configs/padis_concepts.json` 관계 트리플 **20개** (subClassOf · hasOutcome 제외) |
| 분할 | 주어 개념 그룹 단위 → **예시 6 / 확인용(held-out) 14**. DeepSedation·SedationIntensity 는 한 그룹. precludes 는 1개뿐이라 held-out |
| 조건 | zero-shot 예시 0 · one-shot 1개(`SeverePain increasesRiskOf Delirium`, 6개 중 시드 20260917 추첨) · few-shot 6개. **held-out 14개는 셋 다 같다** |
| 원문 | 2018 PADIS 영어 본문 전체(서지·감사의 글·참고문헌 제외) 7조각 + 2025 Focused Update 영어 권고 요약표(Table 1) 1조각. 로컬의 2025 PDF 는 본문이 한국어 번역이라 영어 표만 사용 |
| 추출 | 조각마다 **대화 기록 없는 새 에이전트**, 프롬프트 파일 1개만 읽음 · 8조각 × 3조건 × 2회 = 48회. 프롬프트 문구는 sepsis 와 같음(도메인 설명·개념 목록만 PADIS) |
| 근거 판정 | 모든 (트리플, evidence) **74건을 섞고 조건·정답 여부를 가려** 새 판정자 2명이 각각 Y / 부분 / N |

예시 6개: BloodTransfusion·PhysicalRestraint·SeverePain·Trauma → Delirium (increasesRiskOf) · MechanicalVentilation hasNoEffectOn Delirium · Melatonin decreasesRiskOf Delirium
확인용 14개: Age·Benzodiazepine·Dementia·Hypertension·DeepSedation·SedationIntensity → Delirium · SedationIntensity → Death · DeepSedation precludes Assessable · Delirium → Death·Immobility · Dexmedetomidine·EarlyMobility decreasesRiskOf Delirium · OpioidUse·PatientSex hasNoEffectOn Delirium

## 결과

| 조건 | 회차 | 추출 (고유) | 확인용 14개 재현 (정답 기준) | **근거 지지 Y** | 부분 | N | 근거 Y 인 확인용 재현 | 반복 일치 (Jaccard) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| zero-shot | 1 | 49 (33) | 7/14 | **57%** | 20 | 1 | 5/14 | **0.83** |
| zero-shot | 2 | 47 (33) | 7/14 | **57%** | 20 | 0 | 5/14 | |
| one-shot | 1 | 34 (33) | 10/14 | **38%** | 21 | 0 | 5/14 | **0.86** |
| one-shot | 2 | 38 (32) | 10/14 | **50%** | 19 | 0 | 5/14 | |
| few-shot | 1 | 41 (32) | 10/14 | **44%** | 23 | 0 | 5/14 | **0.82** |
| few-shot | 2 | 34 (28) | 10/14 | **47%** | 18 | 0 | 5/14 | |

- evidence 가 원문에 그대로 있음: 243건 중 242건 · 개념·술어 목록 밖 0건
- 판정자 2명 일치 **96% (74건 중 71건), Cohen κ = 0.92**. 불일치 3건은 모두 Y ↔ 부분.
- few-shot 은 보여준 예시 6개 중 4개를 다시 냈다 (Melatonin → Delirium 과 SeverePain → Delirium 은 안 냄). one-shot 예시(SeverePain → Delirium)는 어느 조건에서도 안 나왔다.

## 무엇이 달라졌나 — 예시는 "관계"가 아니라 "술어"를 바꿨다

| 원문 진술 | zero-shot | one/few-shot | 판정 |
|---|---|---|---|
| "strong evidence … **associated with** delirium: benzodiazepine use, blood transfusions, age, dementia, … trauma" | `associatedWith` | `increasesRiskOf` (정답 형식) | zero = **Y** · one/few = **부분** ("연관 진술을 위험 증가로 과해석") |
| "Moderate evidence … increase the risk for delirium: history of hypertension; … trauma" | `increasesRiskOf` | `increasesRiskOf` | Y |
| "Sex, opioid use, and mechanical ventilation … **not** to alter the risk of delirium" | `hasNoEffectOn` ×3 | 같음 | Y |
| sedation intensity "predicts increased risk of death, delirium" | `increasesRiskOf` ×2 | 같음 | Y |
| Dexmedetomidine · ABCDE 번들 → 섬망 감소 | `decreasesRiskOf` | 같음 | 부분 (비교약·하위집단·번들 한정) |

- **주어–목적어 쌍으로 보면 세 조건의 확인용 재현은 모두 10/14 로 같다.** zero-shot 은 Age·Benzodiazepine·Dementia → Delirium 을 `associatedWith` 로 냈을 뿐이다.
- 예시(전부 `increasesRiskOf` 형식)를 보여주면 **정답 술어에 맞춰 적중이 7 → 10 으로 오르지만, 근거 지지(Y)는 57% → 38~50% 로 내려간다.** 원문은 "연관"이라고만 썼기 때문이다.
- 즉 PADIS 에서 예시는 새 규칙을 찾게 하지 않고, **정답(사람이 만든 KG)의 표현 방식으로 끌어당긴다.** 정답 기준 재현율만 보면 few-shot 이 좋아 보이는 이유다.

## 어느 조건에서도 안 나온 확인용 4개 — 원문 대조

| 정답 트리플 | 원문 (2018 PADIS) | 해석 |
|---|---|---|
| Delirium increasesRiskOf **Death** | Delirium 결과 항목: 섬망은 사망률과 **일관되게 연관된다고 밝혀지지 않았다** ("NOT been consistently shown to be associated with … mortality") | **정답이 원문과 반대** — gold 오류 후보 |
| Delirium increasesRiskOf Immobility | 섬망 → 운동제한을 진술한 문장을 찾지 못함 | 원문 근거 없음 |
| DeepSedation increasesRiskOf Delirium | 얕은 진정 비교에서 섬망 결과는 효과가 뚜렷하지 않다는 서술 · 깊은 진정 → 섬망 직접 진술 없음 (진정 강도 → 섬망은 추출됨) | 원문 근거 약함 |
| DeepSedation precludes Assessable | "RASS −3 환자는 평가 불가로 간주" · 통증 절의 "RASS ≤ −4 에서는 행동 척도 사용 불가" | 개념 경계 차이 — 추출기는 `DeepSedation precludes SeverePain`(통증 평가)으로 냄 |

## sepsis 결과와 비교

| | sepsis (SSC 2021) | PADIS (2018 + 2025 표) |
|---|---|---|
| 확인용 재현 (정답 기준) | 세 조건 모두 **1/19** | zero **7/14** · one/few **10/14** |
| 근거 지지 Y | zero 70–75% · one 88–89% · few 80% | zero **57%** · one 38–50% · few 44–47% |
| 명백한 오류 (N) | zero-shot 1건 | zero-shot 1건 |
| 반복 일치 | 0.75 / 0.83 / 1.00 | 0.83 / 0.86 / 0.82 |

1. **원문이 위험인자를 문장으로 쓰는가가 결과를 정한다.** SSC 2021 은 치료 가이드라인이라 기존 sepsis 규칙 19개 중 1개만 원문에 있었다. PADIS 2018 은 "위험인자 / 영향 없음"을 ungraded statement 로 명시해 14개 중 10개 쌍이 원문에서 나온다.
2. **예시의 효과가 반대로 나타났다.** sepsis 에서는 예시가 근거 지지율을 올렸지만(오류 감소), PADIS 에서는 예시가 원문의 "연관"을 "위험 증가"로 바꾸게 해 엄격 기준 근거 지지율을 내렸다. 두 경우 모두 **무엇을 뽑는지는 원문이 정하고, 예시는 표현을 정답 쪽으로 맞춘다.**
3. **정답(gold) 자체를 점검해야 한다.** Delirium → Death 는 2018 원문과 반대이고, 위험인자 대부분은 원문이 `associatedWith` 수준으로만 진술한다. PADIS KG 승인(사람 검토) 때 이 두 가지를 같이 봐야 한다.

## 한계
- 판정자도 LLM · 확인용 14개(1개 = 7.1%p) · 조건당 2회.
- 2025 Focused Update 는 영어 요약표만 넣었다 — 본문 근거(멜라토닌·덱스메데토미딘 효과 서술)는 입력에 없다. 표만으로는 여섯 추출 모두 트리플을 내지 않았다.
- 프롬프트 규칙 "중재 효과를 환자 특성 규칙으로 바꾸지 말 것"을 일부 에이전트가 "중재 트리플 자체를 내지 말 것"으로 넓게 읽었다(수면 조각 설명). sepsis 와 같은 문구를 유지하려고 고치지 않았다.
- 정답 20개는 사람이 만든 KG 이고 아직 승인 전(`padis_rules_approved.json` 비어 있음)이다.
