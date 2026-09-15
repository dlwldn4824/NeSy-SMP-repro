# NeSy-SMP 논문 원문 조건 재현 — 전처리·방법

작성 2026-09-16 · 기준 논문: De Santis, Park, Zanichelli. *Neuro-symbolic artificial intelligence for real-time sepsis
mortality prediction*. Engineering Applications of AI 177 (2026) 114920 · 공개 코드 FabrizioDeSantis/NeSy-SMP (e7ee0ab)

원칙: **논문 원문을 따른다 → 원문에 없으면 공개 코드를 따른다 → 둘 다 없으면 표준 구현(mimic-code)을 따른다.**
숫자(환자 수·사망률)를 맞추려고 기준을 조정하지 않는다.

---

## 전체 흐름

```
MIMIC-IV (로컬 SQLite, v3.x)
 ├─ 1 코호트        data/build_cohort_paper.py         → cohort_sepsis3_paper.csv        26,251 입원
 ├─ 2 동반질환 NLP  extract_comorbidities_paper.py     → comorbidities_paper_wide.csv    52,488 퇴원기록
 ├─ 3 이벤트 추출   data/build_dataset_gcs.py --cohort → dataset_gcs_paper.csv           22,827,568 행
 ├─ 4 관찰 창       data/make_leadtime_csvs.py         → events_{6,12,24,48}h_before_death_gcs.csv
 ├─ 5 wide 변환     data/long_to_wide.py → data/merge_comorbidities.py → events_{h}h_wide_paper_como.csv
 └─ 6 학습·평가     upstream_faithful/stratified_main.py (원본 + 패치 5개, epoch 50/20)
실행: scripts/run_paper_repro.ps1 (1~6) · scripts/run_paper_train.ps1 (6만)
```

## 1. 코호트 — 논문 §5.1

| 원문 | 구현 |
|---|---|
| 성인(≥18세) | `anchor_age + (입원연도 − anchor_year)` ≥ 18 (mimic-code age.sql) |
| Sepsis-3: 감염 의심 + SOFA 급성 상승 ≥2 | mimic-code `sepsis3` 를 SQLite·pandas 로 한 줄씩 이식 (아래) |
| 제외 (1) ICU 재원 < 24h | `icustays.los` < 1 제외 |
| 제외 (2) 입원 중 ICU 여러 번 | 같은 hadm 의 ICU stay ≥ 2 제외 |
| 제외 (3) 분석에 필요한 임상 데이터 없음 | **정의 없음** → 기준으로 넣지 않고, 창·전처리에서 데이터가 없어 빠지는 입원으로 둔다 |
| MIMIC-IV v2.2 (2008–2019) | 로컬 DB 는 2020–2022 포함 v3.x → 추정 입원연도 하한(anchor_year_group 시작 + 입원연도 − anchor_year) ≥ 2020 인 입원 제외 |

**Sepsis-3 이식 (MIT-LCP/mimic-code, mimic-iv/concepts)**
- `antibiotic.sql` — prescriptions 에서 항생제 이름 목록·경로(눈·귀·국소 제외)·제형(크림·젤 등 제외)
- `suspicion_of_infection.sql` — 배양 후 72h 안 항생제 → 배양 시각 / 항생제 후 24h 안 배양 → 항생제 시각
- `sofa.sql` — ICU 시간 격자(첫 HR 기준 −24h부터)마다 6개 장기 점수, 직전 24h 최악값의 합
  - 입력: PaO2/FiO2(동맥혈 가스 + 4h 이내 FiO2, 침습 환기 여부) · 혈소판 · 빌리루빈 · MAP · 승압제 4종 용량 · GCS(삽관 시 15) · 크레아티닌 · 24h 소변량
  - 환기 상태: `ventilator_setting` · `oxygen_delivery` → `ventilation` (14h 간격 규칙)
- `sepsis3.sql` — 감염 의심 시각 −48h ~ +24h 안에 SOFA ≥2 인 첫 시점
- BigQuery 의미 유지: 시간차 = 시 경계 수, NULL 비교는 거짓, MAX 는 NULL 무시

| 단계 | n | 사망률 |
|---|---:|---:|
| Sepsis-3 | 41,296 | 18.1% |
| 성인 | 41,296 | 18.1% |
| 2008–2019 | 35,808 | 16.9% |
| ICU ≥ 24h | 32,148 | 16.7% |
| 입원 중 ICU 1회 | **26,251** | **15.1%** |
| 논문 | 19,328 | 18% |

코호트 특성: 나이 중앙값 68 · Sepsis-3 시점 SOFA 중앙값 3 · ICU 재원 중앙값 3.1일

## 2. 동반질환 23개 — 논문 §4 · §5.1

- 원문: spaCy NER + 규칙 매칭, **History of Present Illness · Past Medical History 섹션**에서 추출
- 입력: MIMIC-IV-Note 퇴원기록 중 ICU 입원분(`discharge_icu.csv.gz`, 52,488건)
- 공개 코드 그대로: medspaCy(pyrush · target_matcher · ConText · sectionizer), TargetRule 26개, copd·cad 정규화,
  `context_graph.edges` 에서 부정·가족력이 아닌 대상
- 원문대로 추가: 대상의 섹션이 HPI 또는 PMH 인 것만
- 병합: 입원 단위, 기록 없는 입원은 0 (`merge_comorbidities.py`)
- 코호트 기준: 퇴원기록 있음 91.2% · 동반질환 1개 이상 30.3% · 상위 cad 7.2 · 고혈압 6.9 · COPD 4.7 · 암 4.5%
- ⚠️ 원문 섹션 제한 + 공개 코드 대상 선택을 합치면 유병률이 매우 낮다 (같은 섹션 전체 언급이면 고혈압 38%).
  참고용 두 변형을 함께 저장: `_Bsec`(섹션 내 전체 언급) · `_Aall`(공개 코드 그대로, Colab 결과와 일치 확인)

## 3. 이벤트 추출 — 논문 §5.1 변수

| 구분 | 변수 | 출처 |
|---|---|---|
| 정적 | 나이 · 입원 경로(admission_location) | patients · admissions |
| 동적 바이탈 | 수축기·이완기·평균 혈압, 체온(°F→°C 변환), 심박수, 호흡수 | chartevents |
| 동적 검사 | 크레아티닌, 헤모글로빈, 혈소판, 빌리루빈, 칼륨, 알부민, CRP, 혈당, 젖산, 림프구, 호중구, WBC, ALT, AST | labevents |
| GCS | 눈·언어·운동 합 (시간 단위) | chartevents |
| 결과 | 원내 사망(`hospital_expire_flag`), 사망 시각에 Death 이벤트 | admissions |

- ICU 입실~퇴실 사이 이벤트만 사용
- 약물·기타 검사는 원문 변수 목록에 없어 넣지 않음 (원본 코드의 해당 열은 0/unknown 으로 둠)

## 4. 관찰 창 — 논문 §5.2.1 · 원본 `extract_before_death.py`

- 사망자: 사망 시각에서 lead(6·12·24·48h) 이전 이벤트만 남기고, 그중 마지막 이벤트 기준 직전 24h
- 생존자: ICU 재원 중 무작위 24h (재원이 24h 이하면 전부) — 원본은 난수 고정 없음, 여기서는 seed 32
- 결과: 6h 26,248 입원(15.1%) · 12h 26,237(15.0%) · 24h 26,125(14.7%) · 48h 25,564(12.8%)
  — lead 가 길수록 창에 이벤트가 남지 않는 사망자가 빠진다

## 5. 전처리 — 원본 `data/preprocessing.py` 그대로

1. 이벤트 시각별 한 행(wide), 행의 `concept:name` = 그 시각 마지막 측정 개념
2. 사망·퇴원·Urine output·std 개념 행 제거 → `concept:name` 범주 코드화
3. 범주 열(admission_type · admission_location · medication) 앞뒤 채움 후 코드화
4. 수치 27개: 입원 안에서 앞 값 채움 → 0 채움 → MinMax (전체 데이터 기준)
5. 동반질환 23개: 입원 안에서 앞뒤 채움
6. 이벤트 4개 이하 입원 제외 (6h: 24건)
7. 시퀀스 길이 = 가장 긴 입원 (6h: **709**, 중앙값 35 · p99 76) — 뒤쪽 0 패딩

## 6. 학습·평가 — 원본 `stratified_main.py`

- 라벨 층화 5-fold (seed 42), 각 train 의 20% 를 val
- 모델: RF(100 트리, 깊이 10) · XGBoost(기본값) · BiLSTM(hidden 128, 2층, 50 epoch) · LTN(20) · NeSy-SMP(LTN + 지식 공리, 20)
  - RF·XGB 입력: 변수별 0 제외 평균·표준편차
  - BiLSTM: val macro-F1 최고 가중치를 **저장만 하고 test 에는 마지막 epoch 모델** (원본 그대로)
  - LTN·NeSy: val macro-F1 최고 가중치로 test
  - 지식 공리: 코드에 직접 정의된 weak anchoring(GCS·젖산·혈소판·젖산 비청소·빌리루빈·호흡수·수축기혈압·크레아티닌·CRP·만성질환·WBC·나이) + 사망 함축 8개, 데이터:지식 = 0.8:0.2
- 지표: Accuracy · macro F1 · macro Precision · macro Recall · AUROC (fold 평균 ± 표준편차)

**원본 코드에 넣은 패치 5개** (`upstream_faithful/PATCHES.md`)
| # | 내용 | 이유 |
|---|---|---|
| P1 | 입력 CSV 경로를 환경변수로 | 원래 48h 파일 경로 하드코딩 |
| P2 | fold 별 지표 JSON 저장 | 계산 변경 없음 |
| P3 | 약물 범주 없을 때 출력문 건너뜀 | 없으면 KeyError |
| P4 | 위험 MLP 입력 크기를 시퀀스 길이로 계산 | 원래 6h=254 를 lead 마다 손으로 바꿈 |
| P5 | RF·XGB 표준편차를 평균보다 먼저 계산 | **공개 코드 그대로는 Fold 1 에서 TypeError 로 멈춤** |

## 7. 논문과 여전히 다른 것

| 항목 | 이유 |
|---|---|
| 코호트 26,251 · 15.1% (논문 19,328 · 18%) | 제외 (3) 정의 없음 · 로컬 DB 버전 차이(v3.x) |
| DB 버전 | v2.2 원본이 PC 에 없어 연도로 근사 |
| 생존자 창 난수 | 원본 난수 미고정 |
| KG → 규칙 → 공리 과정 | 공개 코드에서 학습과 연결돼 있지 않음(공리는 코드에 직접 기재). 규칙 채굴(AnyBURL) 미실행 |
| Table 2 (OOF bootstrap) | 원본 집계 코드 미공개 |
