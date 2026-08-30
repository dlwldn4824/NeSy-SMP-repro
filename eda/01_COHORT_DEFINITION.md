# 코호트 정의 (EHR 규칙만, 지식 없음)

> ⚠️ **Delirium 예측 코호트는 이 문서가 아니라 [`02_DELIRIUM_COHORT_EDA.md`](02_DELIRIUM_COHORT_EDA.md) 를 본다.**
> 이 문서는 랩미팅 §3 스펙(환자당 첫 stay · prevalent delirium 제외 · 24h 이후 assessable 요구)을 받기 전에
> 만든 것이라 코호트 규칙이 다르다 (입원당 첫 stay · 전체 기간 섬망 ever).
> 여기서 여전히 유효한 것: **careunit 문자열이 풀네임이라는 점(§0), 항목별 차팅 커버리지(§5), 시대별 커버리지 근거.**

DB: `C:\Users\dlwld\Downloads\MIMIC4-hosp-icu.db` (MIMIC-IV, read-only)
스크립트: `notes/eda/cohort_define.py` · 출력: `cohort_candidates.csv`, `cohort_attrition_C2.csv`, `careunit_by_era.csv`, `cohort_C2_stays.csv`

원칙: **코호트는 EHR 규칙으로 먼저 고정한다. 가이드라인/KG는 코호트 정의에 개입하지 않는다.**

---

## 0. 정의에 쓴 규칙 4개

| 축 | 규칙 | 이유 |
|---|---|---|
| 나이 | `anchor_age + (intime.year - anchor_year) >= 18` | PADIS는 성인 ICU 대상. (이 DB의 ICU는 사실상 전부 성인이라 실제로는 0명도 안 걸러짐) |
| 재원 | ICU `los >= 1.0` day | 24시간 관찰창을 쓰려면 최소 1일 필요. 기존 NeSy-SMP 필터와 동일 |
| 진료과 | `first_careunit` 고정 | 65k 전체는 내과·심장수술·외상이 섞여 있어 한 코호트로 못 씀 |
| 시대 | `patients.anchor_year_group` | **`intime` 연도가 아님.** MIMIC-IV는 환자별로 날짜가 랜덤 시프트되어 있어 intime 연도는 의미 없음 |

`first_careunit` 문자열은 축약어가 아니라 풀네임이다 (`Medical Intensive Care Unit (MICU)`). 코드에서 `"MICU"`로 매칭하면 **0명**이 나온다.

---

## 1. 코호트 후보 3개 — 확정 숫자

`first_stay_per_hadm` = 한 입원에 ICU가 여러 번이면 첫 stay만. (권장 기본값)

| 코호트 | 정의 | stays | 환자 | 병원사망 | 30일사망 | 1년사망 | 나이 median (IQR) | 여성 | ICU LOS median (IQR) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **C1** | MICU only, 2014–2019 | 4,335 | 3,923 | **17.9%** | 23.0% | 39.0% | 64 (52–75) | 44.7% | 2.76 (1.73–5.37) |
| **C2** | MICU + MICU/SICU, 2014–2019 | **7,593** | 6,628 | **17.5%** | 23.2% | 39.9% | 65 (52–76) | 45.9% | 2.56 (1.66–4.77) |
| **C3** | 전체 adult ICU, 전 기간 (상한 참고) | 67,224 | 53,714 | **11.0%** | 14.3% | 27.5% | 67 (55–77) | 43.5% | 2.42 (1.57–4.49) |

모두 adult + ICU LOS ≥ 1일 적용.

전체 stay 기준(첫 stay 제한 없이) 숫자는 `cohort_candidates.csv`에 `scope=all_stays` / `first_stay_per_patient` 로 같이 들어있다. 환자 단위로 자르면 C2는 5,884명 / 사망 17.8%.

---

## 2. C2 attrition (권장 코호트가 어떻게 줄어드는가)

| 단계 | stays | 환자 | 직전 대비 |
|---|---:|---:|---:|
| 0. 전체 ICU stay | 94,458 | 65,366 | — |
| 1. adult (age≥18) | 94,458 | 65,366 | 100.0% |
| 2. ICU LOS ≥ 1일 | 74,829 | 54,551 | 79.2% |
| 3. first_careunit ∈ {MICU, MICU/SICU} | 27,147 | 20,252 | 36.3% |
| 4. anchor_year_group 2014–2019 | 8,525 | 6,871 | **31.4%** |
| 5. 입원의 첫 ICU stay | 7,593 | 6,628 | 89.1% |

**시대 컷이 제일 비싸다 (69% 손실).** MICU 계열은 2008–2010에 몰려 있고 뒤로 갈수록 줄어든다 (MICU: 6,200 → 3,307 → 2,724 → 2,164 → 1,175).

시대 창 대안 (C2 기준):

| 창 | stays | 환자 | 병원사망 | 사망 n |
|---|---:|---:|---:|---:|
| 2014–2019 | 7,593 | 6,628 | 17.5% | 1,332 |
| 2011–2019 | 12,806 | 10,883 | 16.4% | 2,100 |
| 2014–2022 | 9,422 | 8,380 | 18.6% | 1,756 |
| 전 기간 | 24,410 | 19,582 | 15.6% | 3,810 |

시대별 사망률 자체는 거의 안 흔들린다 (전체 adult ICU: 11.6 / 11.6 / 12.1 / 11.6 / 13.5%). 즉 **시대 컷의 목적은 사망률 drift 보정이 아니라 차팅 항목·프로토콜 세대를 맞추는 것**이다. 사망 라벨만 쓸 거면 2011–2019로 넓혀 n을 1.7배 키우는 편이 낫고, PADIS 라벨(RASS/CAM-ICU)을 쓸 거면 항목 도입 시기에 맞춰 다시 잘라야 한다 (§3, 진행 중).

---

## 3. careunit × 시대 교차표 (adult, LOS≥1일)

| first_careunit | 08–10 | 11–13 | 14–16 | 17–19 | 20–22 | 계 |
|---|---:|---:|---:|---:|---:|---:|
| MICU | 6,200 | 3,307 | 2,724 | 2,164 | 1,175 | 15,570 |
| CVICU | 3,201 | 2,696 | 3,041 | 2,601 | 1,859 | 13,398 |
| MICU/SICU | 4,563 | 2,422 | 2,068 | 1,569 | 955 | 11,577 |
| SICU | 3,441 | 2,703 | 2,336 | 1,052 | 732 | 10,264 |
| CCU | 2,840 | 1,839 | 1,689 | 1,278 | 808 | 8,454 |
| TSICU | 2,216 | 1,813 | 1,687 | 1,296 | 920 | 7,932 |
| Neuro Intermediate | 363 | 343 | 344 | 1,964 | 1,813 | 4,827 |
| Neuro SICU | 138 | 105 | 223 | 581 | 398 | 1,445 |
| Neuro Stepdown | 108 | 61 | 428 | 474 | 0 | 1,071 |

Neuro Intermediate는 2017년 이후에만 사실상 존재한다 → **시대와 진료과가 교란되어 있다.** 진료과를 고정하지 않고 시대만 자르면 환자 구성이 통째로 바뀐다.

---

## 4. 권장

```text
기본 코호트 (C2):
  first_careunit ∈ {MICU, MICU/SICU}
  age >= 18
  ICU los >= 1 day
  anchor_year_group ∈ {2014-2016, 2017-2019}
  입원당 첫 ICU stay만
  → 7,593 stays / 6,628 patients / 병원사망 17.5%

민감도 축 (같은 코드로 스위치만):
  - C1 (MICU only)          : 진료과를 더 좁혔을 때 결과가 유지되나
  - 2011-2019 로 확장       : n을 1.7배로 늘렸을 때 유지되나
  - C3 (전체 adult ICU)     : 상한. 여기서만 좋아지면 코호트 특이성 의심

라벨:
  1차 = hospital_expire_flag (지식 없는 baseline, C2에서 17.5% → 클래스 불균형 관리 가능)
  2차 = 30일 사망 (23.2%), ICU LOS
  PADIS 전환 시 = CAM-ICU / RASS 기반 섬망·과진정  ← 항목 커버리지 확인 중 (§5)
```

C2 stay 목록은 `notes/eda/cohort_C2_stays.csv` 에 저장되어 있다 (subject_id, hadm_id, stay_id, intime, outtime, los, age, gender, careunit, era, 라벨 3종).

---

## 5. PADIS 라벨을 실제로 붙일 수 있는가 — 차팅 커버리지

`chartevents` 전체 스캔 (인덱스 없음, full scan 각 ~60초). 스크립트: `scan_padis_labels.py`, `scan_label_values.py`, `build_labels.py`

**stay 중 해당 항목이 1회 이상 기록된 비율 (%)**

| 코호트 | RASS | CAM-ICU | Delirium assessment | Pain NRS | CPOT | Mobility | Restraint | GCS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 전체 adult ICU LOS≥1d | 89.9 | 79.7 | 79.4 | 95.3 | 16.6 | 99.9 | 49.5 | 100.0 |
| 2008–2010 | 67.9 | 46.1 | 44.2 | 96.6 | 5.7 | 99.9 | 44.9 | 99.9 |
| 2011–2013 | 99.1 | 91.6 | 86.1 | 97.3 | 6.2 | 100.0 | 50.0 | 100.0 |
| 2014–2016 | 99.9 | 97.2 | 99.4 | 97.2 | 7.1 | 100.0 | 52.2 | 100.0 |
| 2017–2019 | 99.9 | 96.3 | 99.2 | 94.7 | 30.3 | 100.0 | 50.4 | 100.0 |
| 2020–2022 | 99.9 | 93.2 | 97.6 | 86.1 | 58.9 | 100.0 | 54.8 | 100.0 |
| **C2 (2014–2019)** | **99.9** | **97.4** | **99.7** | 95.6 | 16.9 | 100.0 | 46.1 | 100.0 |

**이게 시대 컷의 진짜 근거다.** 2008–2010은 RASS 68% / 섬망평가 44%밖에 안 찍혀 있다. 즉 §2에서 "시대 컷이 69%를 버린다"고 했지만, PADIS 라벨을 쓰는 순간 **2011년 이전은 어차피 못 쓴다.** 사망 라벨만 쓸 때만 전 기간 확장이 의미가 있다.

CPOT는 2017년 이후에 도입되어 C2에서 16.9%뿐이다 → **통증 라벨은 CPOT 말고 Pain NRS(95.6%)를 써야 한다.**

C2에서 stay당 측정 횟수 median: RASS 14회, 섬망평가 7회, GCS 39회, mobility 27회, Pain 23회. 시계열로 쓸 만한 밀도다.

---

## 6. 라벨 후보 유병률 (C2 기준)

섬망 라벨은 `itemid 228332 Delirium assessment` (값: Positive / Negative / UTA)를 쓴다. CAM-ICU 개별 feature 항목(228300 등)은 기록 수가 수천 건대로 적어 파생 라벨로 쓰기 어렵다.

| 라벨 | 정의 | C2 유병률 |
|---|---|---:|
| `delirium_ever` | Delirium assessment = Positive 1회 이상 | **48.4%** (판정 가능 stay 7,347 기준) |
| `deep_sedation_ever` | RASS ≤ −3 1회 이상 (과진정) | 40.2% |
| `agitation_ever` | RASS ≥ +2 1회 이상 | 22.1% |
| `hospital_expire_flag` | 병원 사망 | 17.5% |

- 판정 불가(UTA만 기록) stay는 7,593 중 246개(3.2%)뿐 → **버려도 코호트가 거의 안 줄어든다.**
- 섬망 유병률이 시대별로 안정적이다 (판정된 stay 기준 32–38%, MICU 계열만 보면 48–55%). 시대 컷이 라벨 정의를 흔들지 않는다.

**주의해야 할 상관:**

| | 섬망 없음 | 섬망 있음 |
|---|---:|---:|
| 병원 사망률 | 7.8% | **23.4%** |
| 과진정(RASS≤−3) 동반 | 11.7% | **67.1%** |
| ICU LOS median | 1.91일 | **3.93일** |
| 나이 median | 63 | 66 |

섬망과 과진정이 67% 겹친다. PADIS 자체가 "진정제가 섬망을 유발한다"고 말하는 축이므로, **진정 관련 변수를 그냥 feature로 넣으면 KG 공리와 입력이 같은 정보를 두 번 쓰게 된다.** 진정 변수를 넣은 모델 / 뺀 모델을 둘 다 돌려야 한다.

---

## 7. 결론

```text
확정 코호트 (C2):
  first_careunit ∈ {MICU, MICU/SICU} · age>=18 · ICU los>=1d
  · anchor_year_group ∈ {2014-2016, 2017-2019} · 입원당 첫 ICU stay
  → 7,593 stays / 6,628 patients

주 라벨: delirium_ever = 48.4%   (판정가능 7,347 stay, UTA-only 246개 제외)
부 라벨: deep_sedation_ever 40.2% / agitation_ever 22.1% / hospital_expire_flag 17.5%

시대 창을 2014-2019로 잡은 이유 = 사망률 drift가 아니라 RASS·섬망평가 차팅률.
  2008-2010 RASS 68% / 섬망 44%  → 사용 불가
  2011-2013 RASS 99% / 섬망 86%  → 사망 라벨만 쓸 때 확장 가능 (n 1.7배)
  2014-2019 RASS 99.9% / 섬망 99.7%

민감도 축: C1(MICU only, 섬망 55.3%) · 2011-2019 확장 · C3(전체 adult ICU, 상한)
```

파일: `cohort_C2_stays.csv` (stay 목록), `stay_labels_padis.parquet` (stay별 라벨), `label_prevalence.csv`, `cohort_candidates.csv`, `careunit_by_era.csv`, `cohort_attrition_C2.csv`
