# PHASE 1 PADIS Report (Sedation/Delirium → Rule Registry)

작성 기준: `padis/extraction/phase1_full_extraction.py` + `padis/mimic_mapping/mimic_raw_availability_check.py`

---

## 1) 처리한 PADIS section (Sedation/Delirium)

- 추출 window (page): **1..31**
- window 선택 로직(휴리스틱):
  - `Agitation/Sedation` 및 `Delirium` 키워드가 등장하는 시작점을 잡고,
  - `Immobility/Sleep` 키워드로 종료 경계를 찾되,
  - 경계가 너무 짧게 잡히는 경우(+30 page fallback) 실제 본문 커버를 우선하도록 보정함.

> 참고: PDF 내 “topics/contents list”가 section 키워드를 먼저 포함하는 경우가 있어, 경계 폭이 좁게 잡히면 fallback으로 확장함.

---

## 2) Rule extraction 결과 (전체 section 기준)

- total extracted rules (raw): **68**
- domain:
  - `A-PADIS`: **68**

### 2.1 source_type 분포
- `risk_factor_statement`: **10**
- `recommendation`: **10**
- `evidence`: **23**
- `no_recommendation`: **0**
- `research_gap`: **3**

### 2.2 relation 분포
- `pending`: **60**
- `increasesRiskOf`: **2**
- `decreasesRiskOf`: **4**
- `associatedWith`: **1**
- `preferredOver`: **1**

### 2.3 negation/no-recommendation 처리
- `negation_present == true`: **14**
- `no_recommendation`/`not recommended`로 분류된 rule: **0**
- `research_gap`(근거/해석이 불충분함)으로 분류된 rule: **3**

#### negation 예시
- `rule_id: D-015`
  - negation_present: `true`
  - source_page: `14`
  - source_text(일부):
    - “**One recent cohort study not considered...** independently, ... predicts ... delirium ...”

#### no-recommendation 예시
- 현재 전체 Sedation/Delirium window 추출 결과에서는 `no_recommendation` 라벨이 **생성되지 않음**.
- 대신 `research_gap` 라벨로 근거 불확실성을 일부 잡았으나, “명시적 not recommended/no recommendation” 문구는 이 PDF 텍스트 추출에서 상대적으로 약하게 드러남.

---

## 3) Human review 단계(아직 pending 유지)

- `padis/outputs/padis_rules_review.csv` 생성됨.
- 현재 추출된 규칙 전부 `review_status=pending`으로 남아 있음.
- `approved?`는 사람이 “yes”로 바꾼 뒤에만 approved JSON 및 KG가 생성됨.

---

## 4) Gold set smoke validation 실행 여부

- gold_set_size: **15** (현재 단계의 gold set은 “draft”로 자동 초안 생성된 상태이며, 사람 독립 검증/수정이 필요함)
- `padis/outputs/padis_smoke_gold_validation_report.md`:
  - **exact-match 15/15 (acc=1.00)**

중요:
- 위 1.00은 “현재 gold_set_draft에 포함된 expected_*가 추출 heuristic과 동일 계열”이라 **정확도(추출기 성능)를 보장하는 진짜 평가로 보기 어렵습니다.**
- 다음 단계에서 gold_set_smoke.json을 Sedation/Delirium 본문에 근거해 사람이 독립적으로 정리한 뒤, validation을 다시 돌려야 “진짜 정확도”를 측정할 수 있습니다.

---

## 5) MIMIC raw availability (raw DB 기반 feasibility)

산출물:
- `padis/outputs/mimic_raw_availability_report.md`
- `padis/outputs/mimic_raw_availability.json`

핵심 수치(성인 ICU admissions 기준):
- total_adult_icu_admissions: **85,242**
- mechanically_ventilated_hadm: **37,589** (ratio **0.4410**)
- RASS hadm: **433** (ratio **0.00508**)
  - (distinct subjects with records): **424**
- CAM-ICU hadm: **66,005** (ratio **0.7743**)
  - (distinct subjects with records): **51,581**
- ventilation + RASS + CAM hadm: **260** (ratio **0.00305**)
- sedative exposure hadm: **53,469** (ratio **0.6273**)
- ventilation + RASS + CAM + sedative exposure (any overlap) hadm:
  - **198** (from `ventilation_and_rass_and_cam_and_sedative_hadm`)
- ventilation + RASS + CAM + sedative + opioid hadm:
  - **249**

해석:
- “CAM-ICU” 단독은 매우 커버되지만,
- “RASS”는 raw coverage가 매우 낮아서,
- `delirium target`을 CAM-ICU 기반으로 두더라도 “RASS를 함께 쓰는 cohort”는 작게 남을 가능성이 큼.

---

## 6) 기존 preprocessing schema vs raw availability (핵심 차이)

현재 `padis/extraction`에서 계산한 `experiment_usable`(= preprocessing feature schema 기준) 결과:
- 68개 rule 모두 `experiment_usable=no` (**68/68**)

하지만 raw DB feasibility는 RASS/CAM/ventilation/sedative가 실제로 존재함:
- RASS available_in_raw_mimic (hadm=**433**) 등

따라서 현재의 `experiment_usable=no`는
“MIMIC에 데이터가 없다”가 아니라,
**현재 repo의 preprocessing / feature schema가 PADIS 변수(RASS/CAM/진정제 노출)를 아직 추출/표현하지 못해서** 발생한 것입니다.

즉 Phase 2(또는 이후)로 가기 위해서는:
- preprocessing/event extraction/feature naming을 PADIS 변수에 맞게 확장해야 함.

---

## 7) cohort 후보(현재 수치 기반)

- target을 “Delirium(CAM-ICU 기반)”으로 두고
  - “RASS도 함께 사용”하거나(예: RASS history 기반 rule)
  - mechanical ventilation 상태까지 포함하면,
  - **ventilation + RASS + CAM hadm = 260** 수준의 작은 cohort가 가능성이 높음.

또는 RASS 의존도를 낮추면(cohort 정의 변경) 더 큰 규모가 열릴 수 있으므로,
이 선택은 Phase 2 설계에서 결정해야 함.

---

## 8) 부족/보류 사항 (확정하면 안 되는 것)

아직 확정하지 않음:
1. PADIS prediction target 최종 정의(델리리움 정의가 CAM인지/혼합인지)
2. rule의 최종 relation/source_type 분류 정확도
   (현재 heuristic은 `evidence/research_gap`는 일부 잡았지만 `no_recommendation`(명시적 not recommended/no recommendation 문구)는 0으로 남아 있음)
3. approved 전체 rule KG를 “전체 확정”해서 쓰는지 여부(현재 Phase 1은 pending 대기)

추가로 필요한 후속 작업:
1. gold_set_smoke.json을 사람이 독립적으로 채워서 진짜 정확도 평가로 재실행
2. extraction의 source_type/evidence/no_recommendation 분류 휴리스틱 개선
3. MIMIC raw availability → preprocessing(feature schema) 확장 연결

---

## 9) 다음 단계 제안(Phase 2 준비)

- 먼저 사람이 `padis/rules/gold_set_smoke.json`(draft expected_*)을 수정
- 그 뒤 validation을 다시 실행해서 “추출기 정확도”를 실제로 측정
- 그 다음에야 padding 없이 KG/constraint/모델 학습 단계로 확장

