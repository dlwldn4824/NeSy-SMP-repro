# One-shot / Few-shot 겹침과 그 KG로 만든 공리의 성능 (상세)

2026-10-11 작성. 원자료 — 트리플 `padis/outputs/llm_triples/llm_triples.csv` (243행, 저작권 때문에 근거 인용문은 제외),
심사 `C:\data\padis_fewshot\score_{gold,blind}.json`, 공리 컴파일·학습 `delirium/30_kg_variants.py`·`33_kg_variants_v2.py`.

---

## 1. 무엇이 어떻게 겹치는가

### 1-1. 숫자

2018 PADIS 가이드라인 조각 8개를 각 설정으로 **2회씩** 추출해 합집합을 만들었다.

| 비교 | 고유 트리플 | 교집합 | Jaccard | 술어 무시 Jaccard |
|---|---|---|---|---|
| one-shot vs few-shot | 35 / 33 | **31** | **0.84** | 0.88 |
| zero-shot vs one-shot | 36 / 35 | 28 | 0.65 | 0.91 |
| zero-shot vs few-shot | 36 / 33 | 26 | 0.60 | 0.84 |
| 세 설정 공통 | — | **25** | — | — |

"술어 무시"는 `(주어, 목적어)` 쌍만 비교한 값이다. one/few 는 0.84 → 0.88 로 거의 안 오르고,
zero vs one 은 0.65 → **0.91** 로 크게 오른다. → **zero 와 one/few 의 차이는 관계명 표현이고,
one 과 few 의 차이는 표현이 아니라 트리플 몇 개의 유무다.**

### 1-2. 겹치는 31개 — 전체 목록

`3way` = 세 설정 공통 · `공리` 열은 우리 컴파일 규칙에서 실행 가능한 공리가 되는지.

| | 트리플 | 공리화 |
|---|---|---|
| 3way | Age − increasesRiskOf → **PhysicalRestraint** | ❌ 결과 미매핑 |
| 3way | Age − associatedWith → **SeverePain** | ❌ 결과 미매핑 |
| | Age − increasesRiskOf → Delirium | ✅ |
| | Benzodiazepine − increasesRiskOf → Delirium | ✅ |
| | BloodTransfusion − increasesRiskOf → Delirium | ✅ |
| | Dementia − increasesRiskOf → Delirium | ✅ |
| 3way | Dexmedetomidine − decreasesRiskOf → Delirium | ✅ |
| 3way | EarlyMobility − decreasesRiskOf → Delirium | ✅ |
| 3way | EarlyMobility − decreasesRiskOf → Death | ⚠️ 같은 쌍에 `hasNoEffectOn` 이 있어 **기각** |
| 3way | EarlyMobility − hasNoEffectOn → Death | (기각 선언) |
| 3way | EarlyMobility − decreasesRiskOf → **PhysicalRestraint** | ❌ 결과 미매핑 |
| 3way | Hypertension − increasesRiskOf → Delirium | ✅ |
| 3way | PhysicalRestraint − increasesRiskOf → Delirium | ✅ (개념 회수 후) |
| 3way | PhysicalRestraint − associatedWith → **Benzodiazepine** | ❌ 결과 미매핑 |
| 3way | PhysicalRestraint − associatedWith → **OpioidUse** | ❌ 결과 미매핑 |
| 3way | SedationIntensity − increasesRiskOf → Delirium | ✅ |
| 3way | SedationIntensity − increasesRiskOf → **Death** | ✅ (사망 머리 공리 1개) |
| 3way | Trauma − increasesRiskOf → Delirium | ✅ |
| 3way | Trauma − increasesRiskOf → **SeverePain** | ❌ 결과 미매핑 |
| | Trauma − associatedWith → **SeverePain** | ❌ 결과 미매핑 |
| 3way | OpioidUse − increasesRiskOf → Delirium | ⚠️ `hasNoEffectOn` 과 충돌 → **기각** |
| 3way | OpioidUse − hasNoEffectOn → Delirium | (기각 선언) |
| 3way | OpioidUse − increasesRiskOf → **SeverePain** | ❌ 결과 미매핑 |
| 3way | MechanicalVentilation − increasesRiskOf → **PhysicalRestraint** | ❌ 결과 미매핑 |
| 3way | MechanicalVentilation − hasNoEffectOn → Delirium | (기각 선언) |
| 3way | PatientSex − associatedWith → **SeverePain** | ❌ 결과 미매핑 |
| 3way | PatientSex − hasNoEffectOn → Delirium | (기각 선언) |
| 3way | Delirium − increasesRiskOf → **PhysicalRestraint** | ❌ 주어가 결과 개념 |
| 3way | Delirium − associatedWith → **Dementia** | ❌ 주어가 결과 개념 |
| 3way | SeverePain − associatedWith → **Hypertension** | ❌ 결과 미매핑 |
| 3way | DeepSedation − precludes → **SeverePain** | ❌ 결과 미매핑 |

**분해하면 31개 = 공리 11개 + 기각 선언·충돌 6개 + 개념→개념 14개** 다.
주어별로는 EarlyMobility 4 · OpioidUse 3 · PhysicalRestraint 3 · Trauma 3 · Age 3 개가 많고,
나머지는 1~2개씩이다.

### 1-3. 다른 6개

| 어디에만 | 트리플 | 왜 공리에 영향이 없나 |
|---|---|---|
| one-shot | DeepSedation − precludes → Dexmedetomidine | 결과가 개념(약물) → 미매핑 |
| one-shot | Propofol − increasesRiskOf → MechanicalVentilation | 결과가 개념 → 미매핑 |
| one-shot | SedationIntensity − associatedWith → EarlyMobility | 결과가 개념 → 미매핑 |
| one-shot | SeverePain − associatedWith → EarlyMobility | 결과가 개념 → 미매핑 |
| few-shot | OpioidUse − associatedWith → SeverePain | 결과가 개념 → 미매핑 |
| few-shot | OpioidUse − decreasesRiskOf → SeverePain | 결과가 개념 → 미매핑 |

**여섯 개 전부 `개념 → 개념` 관계다.** 우리 컴파일 규칙은 결과(머리)가 `Delirium`·`Death`·
평가가능성일 때만 공리를 만들기 때문에([delirium/30_kg_variants.py:111](../../delirium/30_kg_variants.py)),
one/few 의 차이는 **공리 단계에서 전부 사라진다.**

### 1-4. 같은 설정을 두 번 돌렸을 때의 변동

| 설정 | 회차1 | 회차2 | 양쪽 공통 | 재현율 |
|---|---|---|---|---|
| zero-shot | 33 | 33 | 30 | 83% |
| one-shot | 33 | 32 | 30 | **86%** |
| few-shot | 32 | 28 | 27 | 82% |

**one↔few 차이(Jaccard 0.84)는 같은 설정 재실행 변동(0.82~0.86)과 같은 크기다.**
즉 "few-shot 이 one-shot 과 다른 KG 를 만든다"고 말할 근거가 없다.

### 1-5. 관계명(술어)은 분명히 달라진다

| 설정 | associatedWith | increasesRiskOf | decreasesRiskOf | hasNoEffectOn | precludes |
|---|---|---|---|---|---|
| zero-shot | **43** | 26 | 18 | 9 | 0 |
| one-shot | 19 | **33** | 10 | 8 | 2 |
| few-shot | 23 | **30** | 13 | 8 | 1 |

예시를 주면 모호한 `associatedWith` 가 단정적인 `increasesRiskOf` 로 뒤집힌다(43 → 30 전후).
같은 쌍에서 술어만 바뀌는 대표 예가 `Age → Delirium`, `Benzodiazepine → Delirium`,
`BloodTransfusion → Delirium`, `Dementia → Delirium`, `Trauma → Delirium` 5개다.

### 1-6. 정답 형식 점수는 올라가고 근거 지지율은 떨어진다

| 설정 | gold(held-out 14개) 재현 | 심사 "근거가 뒷받침한다" Y% | 보여준 예시 재현 |
|---|---|---|---|
| zero-shot | **7/14** · 7/14 | **57.1% · 57.4%** | — |
| one-shot | **10/14** · 10/14 | 38.2% · 50.0% | 0/1 |
| few-shot | **10/14** · 10/14 | 43.9% · 47.1% | **4/6** |

- 인용문 자체는 거의 전부 원문 그대로였다(`evidence 원문 그대로` 41/41 · 34/34 · 38/38 · 48/49 …).
  즉 모델이 문장을 지어내지는 않았다.
- 그런데 **어느 설정에서도 "근거가 실제로 뒷받침하는 gold 규칙"은 5/14 로 같다.**
  one/few 가 gold 10/14 를 맞추는 동안 늘어난 5개는 **원문 근거 없이 맞힌 것**이다.
- few-shot 은 보여준 예시 6개 중 4개를 그대로 돌려줬다(one-shot 은 1개 중 0개).

→ **예시의 효과는 "새 지식 발견"이 아니라 ① 관계명을 스키마에 맞추기 ② 예시 자체를 되돌려주기 다.**
한계는 프롬프트가 아니라 **원문**이다 — PADIS 본문에 근거 문장이 있는 gold 규칙이 5/14 뿐이다.

---

## 2. 그 KG로 만든 공리의 성능 — 왜 그렇게 나왔나

### 2-1. 컴파일에서 얼마나 떨어지는가

| KG | 트리플 | 실행 가능 공리 | 효과없음 기각 | 미매핑 | 머리=섬망 | 머리=사망 |
|---|---|---|---|---|---|---|
| 합의(교집합) | 25 | 7 | 2 | 12 | 6 | 1 |
| zero-shot | 36 | 12 | 3 | 16 | 11 | 1 |
| **one-shot** | 35 | **11** | 2 | 18 | 10 | 1 |
| **few-shot** | 33 | **11** | 2 | 16 | 10 | 1 |
| 합집합 | 44 | 16 | 3 | 20 | 15 | 1 |
| 사람 KG | 20 | 15 | 0 | 2 | 13 | 1 |

**트리플의 절반가량이 "미매핑"으로 버려진다**(16~20개). 사람 KG 는 2개뿐이다 —
사람은 애초에 "무엇을 예측할지"를 알고 쓰기 때문이다. LLM 은 가이드라인을 읽은 대로
`억제대 → 섬망`, `섬망 → 억제대`, `통증 → 고혈압` 같은 **개념 사이 관계**를 많이 만들고,
그중 결과가 `섬망`·`사망`인 것만 공리가 된다.

또 모든 조건에서 **머리가 사망인 공리는 단 1개**(`진정강도 → 사망`)다. 이게 뒤에서 중요하다.

### 2-2. 조건별 공리 집합과 만족도

| 공리 | 합의 | one-shot | few-shot | zero-shot | 합집합 | 사람 KG |
|---|---|---|---|---|---|---|
| Dexmedetomidine → ¬Delirium | 0.727 | 0.712 | 0.712 | 0.719 | 0.708 | 0.709 |
| EarlyMobility → ¬Delirium | 0.967 | 0.964 | 0.964 | 0.965 | 0.962 | 0.962 |
| Hypertension → Delirium | **0.425** | **0.414** | **0.414** | 0.418 | 0.414 | 0.412 |
| PhysicalRestraint → Delirium | 0.700 | 0.673 | 0.673 | 0.682 | 0.670 | 0.668 |
| SedationIntensity → Delirium | 0.843 | 0.826 | 0.826 | 0.834 | 0.823 | 0.822 |
| SedationIntensity → **Death** | 0.701 | 0.685 | 0.685 | 0.694 | 0.682 | 0.680 |
| Trauma → Delirium | 0.872 | 0.819 | 0.819 | 0.878 | 0.831 | 0.802 |
| Age → Delirium | — | 0.600 | 0.600 | 0.582* | 0.604 | 0.591 |
| Benzodiazepine → Delirium | — | 0.701 | 0.701 | 0.661* | 0.707 | 0.688 |
| BloodTransfusion → Delirium | — | 0.827 | 0.827 | 0.791* | 0.841 | 0.806 |
| Dementia → Delirium | — | 0.925 | 0.925 | 0.894* | 0.930 | 0.914 |
| DeepSedation → Delirium | — | — | — | — | — | 0.892 |
| DeepSedation → ¬UTA | — | — | — | — | — | 0.892 |
| SeverePain → Delirium | — | — | — | — | — | 0.625 |
| Melatonin → ¬Delirium | — | — | — | — | — | 0.993 |

`*` = 같은 관계가 `associatedWith` 로 들어와 **가중치 등급만 낮은**(low 0.3 vs strong 1.0) 경우.

읽을 점 세 가지:

1. **one-shot 과 few-shot 의 공리 집합이 글자 단위로 동일하다** (11개, 만족도도 소수점까지 같다).
   → AUROC 가 같게 나온 것은 우연이 아니라 **같은 공리를 학습한 것**이다.
2. **어느 조건에서나 핵심 7개가 공통**이고, 조건이 커질 때 늘어나는 것은
   `Age · Benzodiazepine · BloodTransfusion · Dementia → Delirium` 4개뿐이다.
3. zero-shot 과 one/few 의 차이는 그 4~5개의 **가중치 등급**과 `Trauma` 한 줄의 중복뿐이다.

### 2-3. 성능

| KG | 공리 수 | AUROC (회수 전 / 회수 후) |
|---|---|---|
| 기준선(공리 없음) | 0 | 82.9 / 83.0 |
| 합의(교집합) | 6 → 7 | 83.1 / 83.35 |
| zero-shot | 11 → 12 | 83.0 / 83.17 |
| **one-shot** | 10 → 11 | 82.9 / **83.39** |
| **few-shot** | 10 → 11 | 82.9 / **83.39** |
| 합집합 | 15 → 16 | 82.9 / 83.33 |
| 사람 KG | 13 → 15 | 82.9 / 83.13 |

시드 3개 SD 는 0.41~0.88 이다. **모든 차이가 SD 안에 들어간다.**

### 2-4. 성능이 움직이지 않은 이유 — 하나씩

**① 공리가 담은 정보를 모델이 이미 입력으로 갖고 있다.**
`Age → Delirium` 은 나이가 개념·입력 피처로 이미 들어가 있고, `Benzodiazepine → Delirium` 도
벤조 투여 비율이 피처다. 공리는 "나이가 많으면 섬망 확률을 올려라"라는 **단조 제약**을 추가하는데,
데이터가 이미 그 방향을 말해 주고 있으므로 **새 정보가 아니다.**

**② 만족도가 처음부터 높다 → 밀어낼 여지가 없다.**
위 표에서 대부분 0.6~0.97 이다. 공리 손실은 `1 − 만족도` 에 비례하므로, 만족도가 0.9 대인
공리(치매 0.93 · 조기거동 0.96)는 손실에 거의 기여하지 않는다.

**③ 공리 항의 gradient 가 과제 손실의 0.4% 다.**
섬망 쪽에서 직접 측정한 값이다([delirium/38_grad_path_check.py](../../delirium/38_grad_path_check.py)).
게다가 공리 12개 중 11개는 머리가 `Delirium` 이라 **사망 로짓으로 가는 gradient 가 정확히 0** 이다.
§2-1 에서 "머리가 사망인 공리가 1개뿐"이라고 한 것이 여기서 그대로 드러난다.

**④ 유일하게 만족도가 낮은 공리는 데이터가 반대하는 공리다.**
`Hypertension → Delirium` 0.41~0.43 으로 전 조건에서 가장 낮다. 그런데 이 규칙은
**환자 70.5% 에서 켜지면서 활성화군 사망률이 21.6%(전체 21.2%)** 로 차이가 없다.
즉 만족도가 낮은 이유는 "모델이 아직 못 배웠다"가 아니라 **"코호트에서 성립하지 않는다"** 다.
이걸 세게 밀면 성능이 떨어진다(가중치 w 0.2 → 1.0 → 2.0 에서 82.77 → 82.61 → 82.58).

**⑤ 공리를 늘려도 늘어나는 건 ①②에 해당하는 공리들이다.**
합집합(16개)이 합의(7개)보다 낫지 않은 이유다. 공리 수와 성능의 상관이 없다.

### 2-5. 패혈증 쪽 교차 증거 — ③만으로는 설명이 안 된다

③(전달 경로 부족)이 유일한 원인이라면, 경로가 살아 있는 코드에서는 효과가 나와야 한다.
원저자 패혈증 코드에서 공리별 gradient 를 직접 재 봤다
([NeSy-SMP/tools/audit/grad_path_sepsis.py](../../NeSy-SMP/tools/audit/grad_path_sepsis.py), 학습 없이 1회 측정).

| 공리 종류 | 개수 | 사망 모델 gradient |
|---|---|---|
| Anchor (조건 → 위험 술어) | 10 | **정확히 0** |
| Implication (위험 술어 → 사망) | 8 | 0.42 ~ 0.48 |

논문 손실(w_D 0.8 / w_K 0.2) 기준 **사망 모델에 들어가는 gradient 의 17%가 지식 항에서 온다.**
섬망 쪽 0.4% 와 40배 차이다. **즉 패혈증 원본에서는 공리가 사망 예측까지 제대로 닿는다.**
그런데도 NeSy − LTN 은 +0.01 ~ +0.14 수준이다.

→ 남는 설명은 **①(중복)** 이다. 이걸 직접 확인한 실험이 학습 데이터를 줄여 보는 것이다.

| 학습셋 | XGB | BiLSTM | LTN | NeSy | **NeSy − LTN** |
|---|---|---|---|---|---|
| 100% | 92.67 | 89.71 | 91.27 | 91.02 | −0.25 |
| 10% | 90.59 | 86.26 | 87.90 | 87.86 | −0.04 |
| 5% | 89.80 | 84.51 | 86.29 | 86.18 | −0.11 |
| **1%** | 85.80 | 63.97 | 66.84 | **69.75** | **+2.91** |

**데이터가 1% 로 줄면 공리가 +2.91 을 만든다.** 데이터가 충분할 때 공리가 무효인 것은
공리가 틀렸기 때문이 아니라 **데이터가 같은 것을 이미 말해 주기 때문**이라는 쪽을 지지한다.
(단 1% 에서는 BiLSTM 이 63.97 로 붕괴하고 XGB 85.80 이 여전히 더 높다 —
"적은 데이터에서 NeSy 가 최선"이라는 뜻은 아니다.)

### 2-6. 해상도 한계 — 어디까지 믿을 수 있나

같은 코드·같은 데이터로 두 번 돌린 값이다.

| 예측 시점 | r1 NeSy−LTN | r2 NeSy−LTN | 실행 간 폭 |
|---|---|---|---|
| 12h | +0.14 | +0.28 | 0.14 |
| 24h | +0.31 | −0.21 | **0.52** |

**한 시점에서 ±0.5 이내의 NeSy−LTN 차이는 실행 간 변동과 구분되지 않는다.**
§2-3 의 KG 조건 간 차이(±0.4)도, 연결 추가 실험의 +0.026 도 모두 이 띠 안이다.

---

## 3. 한 줄로

- **겹침** — one/few 는 트리플 31개(0.84)를 공유하고, 다른 6개는 전부 `개념 → 개념` 관계라
  **공리 단계에서 차이가 0** 이 된다. 예시의 효과는 관계명을 스키마에 맞추는 것(`associatedWith` → `increasesRiskOf`)과
  보여준 예시를 되돌려주는 것이고, **근거 지지율은 오히려 57% → 38~50% 로 떨어진다.**
- **성능** — 조건마다 핵심 공리 7개가 같고, 늘어나는 공리는 모델이 이미 입력으로 가진 정보를
  반복한다. 만족도가 낮은 하나(`고혈압 → 섬망`)는 코호트가 반대하는 규칙이다.
  그래서 KG 범위를 바꿔도 ±0.4(SD 안)에서 움직이지 않는다.
- **원인** — "전달 경로가 없어서"는 섬망 쪽에만 맞는 설명이다(패혈증은 17%가 전달됨).
  데이터를 1% 로 줄이면 +2.91 이 나오므로, 현재 결과는 **공리가 데이터와 중복**이라는 쪽이다.
