# PADIS 섬망 KG 규칙 의미 정확성 검수표

> 작성: 2026-09-15 · 랩미팅 검수용 초안. **최종 승인은 사람이 한다** — `docs/KG_RULE_REVIEW.csv` 의 `사람_최종판단` 열을 채운 뒤 승인 게이트(`padis/outputs/padis_rules_approved.json`)에 반영할 것. 이 문서는 게이트 파일을 건드리지 않았다.

## 0. 읽는 법

- **검수 범위**: `padis/kg/delirium_kg.py`(권위 소스, 임상 트리플 19개)와 `padis/outputs/padis_rules_draft_v1.json`(19개)의 합집합을 중복 제거한 **23개**. `subClassOf`·`rdf:type`·`evidenceLevel`·`Patient hasOutcome Delirium` 같은 스키마 트리플은 제외.
- **부록 2개(X-01, X-02)**: 두 소스에는 없지만 `NeSy-SMP/configs/padis_concepts.json` 에 있거나 모델 공리(`eda/23_stage34_bilstm_cbm.py` AXIOMS)로 이미 쓰이는 트리플. 집계에서 제외.
- **문장 ID 체계가 두 개다 — 주의.** 같은 문장이라도 번호가 다르다.
  - `raw D-xxx` = `padis/outputs/padis_rules_raw.json` / `padis_rules_review.csv` 의 rule_id (이 문서의 기본 인용).
  - `fs D-xxx` = `padis/outputs/_gold_sentences.txt` 의 번호 (`FEWSHOT_CHECK.md` 가 사용). 대응: fs D-026=raw D-028 · fs D-029=raw D-031 · fs D-032=raw D-035 · fs D-042=raw D-045 · fs D-049=raw D-052 · fs D-051=raw D-054 · fs D-056=raw D-072 · fs D-060=raw D-076.
  - `G-0xx` = `padis/outputs/gold_set_draft.md`.
- **근거방향지지**: `Y` 문장이 그 방향을 직접 진술 · `부분` 방향은 맞지만 비교형/결과변수 불일치/등급 불일치/문맥 추정 등 문제 있음 · `N` 인용 문장이 규칙을 지지하지 않음 · `Y(미검증)` 팀 문서와 방향은 같으나 repo 안의 텍스트로 원문 확인 불가 · `미검증` 근거 문장을 찾지 못해 판단 불가.
- **코호트 데이터**: `notes/eda/out_split/stage5_axiom_data.csv`. MIMIC-IV test set 의 라벨 있는 **앵커 단위** 집계로, **조(crude)·무보정·반복측정**(한 stay 에 앵커 여러 개) 연관이다. 위험차(RD)=P(B|A)−P(B|¬A) (%p), 위험비(RR)=P(B|A)/P(B|¬A). B 는 규칙의 머리이므로 `decreasesRiskOf` 규칙은 **¬섬망 기준**이다. **데이터가 규칙과 어긋나도 가이드라인이 틀렸다는 뜻이 아니다.**
- **원문 한계**: repo 에는 PADIS 2018 전문이 없고 '섬망' 단어를 포함한 추출 문장 86개만 있다. 2025 Focused Update 원문은 전혀 없다. 그래서 **Ungraded Statement(p.18)의 강한 근거 목록은 'greater' 에서 잘려** 치매·선행 혼수·응급수술/외상·APACHE/ASA 부분을 repo 안에서 확인할 수 없다.

## 1. 한눈에 보기

**권고: 승인 12 · 수정 6 · 보류 5** (총 23) · 부록 2건 별도.

| ID | 규칙 | 출처 | 등급(kg/draft) | 지지 | 코호트 RR · RD | 권고 |
|---|---|---|---|:-:|---|:-:|
| R-01 | BenzodiazepineUse –increasesRiskOf→ Delirium | 둘 다 | strong / strong | Y | 1.87 · +25.9 | **승인** |
| R-02 | BloodTransfusion –increasesRiskOf→ Delirium | 둘 다 | strong / strong | Y | 1.04 · +1.3 | **승인** |
| R-03 | Age (≥65) –increasesRiskOf→ Delirium | 둘 다 | strong / strong | Y | 1.15 · +4.4 | **승인** |
| R-04 | Dementia –increasesRiskOf→ Delirium | 둘 다 | strong / strong | Y(미검증) | 1.83 · +24.5 | **승인** |
| R-05 | PriorComa –increasesRiskOf→ Delirium | 둘 다 | strong / strong | Y(미검증) | 없음 | **승인** |
| R-06 | EmergencySurgery (ICU 입실 전) –increasesRiskOf→ Delirium | delirium_kg.py | strong / — | Y(미검증) | 없음 | **승인** |
| R-07 | Trauma –increasesRiskOf→ Delirium | 둘 다 | strong / strong | 부분 | 1.34 · +10.1 | **수정** |
| R-08 | APACHEScore –increasesRiskOf→ Delirium | delirium_kg.py | strong / — | Y(미검증) | 없음 | **수정** |
| R-09 | Hypertension (병력) –increasesRiskOf→ Delirium | 둘 다 | moderate / moderate | Y | 1.15 · +4.3 | **승인** |
| R-10 | NeurologicAdmission –increasesRiskOf→ Delirium | delirium_kg.py | moderate / — | Y | 없음 | **승인** |
| R-11 | PsychoactiveMedication –increasesRiskOf→ Delirium | delirium_kg.py | moderate / — | 부분 | 없음 | **수정** |
| R-12 | DeepSedation (RASS≤−4) –increasesRiskOf→ Delirium | 둘 다 | low / low | 부분 | 1.50 · +14.9 | **수정** |
| R-13 | SedationIntensity –increasesRiskOf→ Death | draft json | — / cohort (가이드라인 등급 밖) | Y | 없음 | **보류** |
| R-14 | PhysicalRestraint –increasesRiskOf→ Delirium | draft json | — / low | 부분 | 없음 | **보류** |
| R-15 | SeverePain (NRS≥4) –increasesRiskOf→ Delirium | draft json | — / inconclusive | N | 0.37 · −23.1 | **보류** |
| R-16 | Dexmedetomidine –decreasesRiskOf→ Delirium | 둘 다 | moderate / moderate | 부분 | 0.60 (¬섬망 기준) · −28.2 (¬섬망 기준) | **수정** |
| R-17 | EnhancedMobilization –decreasesRiskOf→ Delirium | 둘 다 | low / low | 부분 | 1.40 (¬섬망 기준) · +26.2 (¬섬망 기준) | **수정** |
| R-18 | Melatonin –decreasesRiskOf→ Delirium | 둘 다 | low / low | 미검증 | 없음 | **보류** |
| R-19 | Delirium –increasesRiskOf→ Death | draft json | — / strong | 부분 | 없음 | **보류** |
| R-20 | MechanicalVentilation –hasNoEffectOn→ Delirium | 둘 다 | strong / strong | Y | 없음 | **승인** |
| R-21 | OpioidUse –hasNoEffectOn→ Delirium | 둘 다 | strong / strong | Y | 없음 | **승인** |
| R-22 | PatientSex –hasNoEffectOn→ Delirium | 둘 다 | strong / strong | Y | 없음 | **승인** |
| R-23 | DeepSedation (RASS≤−4) –precludes→ DeliriumAssessment | 둘 다 | (없음) / data-derived | 부분 | 4.20 · +32.5 | **승인** |
| X-01 | SedationIntensity –increasesRiskOf→ Delirium | 부록 | — / — | Y | 2.39 · +35.7 | **수정** |
| X-02 | Delirium –increasesRiskOf→ Immobility | 부록 | — / — | 미검증 | 없음 | **보류** |

## 2. 규칙별 검수

### R-01 · BenzodiazepineUse –increasesRiskOf→ Delirium  — 권고: **승인**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-D-01`) |
| 소스 간 불일치 | 없음 (방향·등급 일치) |
| 가이드라인 근거 | p.18 raw D-030 (G-007) · p.19 raw D-031 (G-008, fs D-029) |
| 근거 요약 | 2018 Ungraded Statement: 조절 가능한 인자 중 강한 근거로 섬망과 '연관'된 두 가지가 벤조디아제핀 사용과 수혈. |
| 근거 등급 | delirium_kg.py: strong · draft: strong |
| 근거가 방향을 지지하나 | **Y** — 강한 근거의 연관 진술과 방향 일치. 단 '연관(association)'이지 권고문·인과 진술은 아님. |
| 코호트 데이터 | n(A)=5,166 · RR 1.87 · RD +25.9%p — 방향 일치. 조(crude) 연관이며 초조 환자에게 투여되는 적응증 교란 가능(padis/docs §5). 모델−데이터 −0.279 로 모델이 이 공리를 가장 덜 지킴. |
| 알려진 충돌 | 없음 (2018 진정제 선택 근거 D-022 SEDCOM 도 벤조 대비 덱스 섬망 감소 → 같은 방향) |
| MIMIC 매핑 | 가능 — itemid 221385/221668/221623, stage5 공리 사용 중 |
| 원문 검증 | 확인 |
| **권고** | **승인** — 원문 확인됨, 방향·등급 일치. 교란 주석만 유지. |

### R-02 · BloodTransfusion –increasesRiskOf→ Delirium  — 권고: **승인**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-D-02`) |
| 소스 간 불일치 | 없음. 단 draft mimic_ready=false · concepts '미매핑' 은 stage5 실사용과 불일치(문서 갱신 필요) |
| 가이드라인 근거 | p.18 raw D-030 (G-007) · p.19 raw D-031 (G-008) |
| 근거 요약 | R-01 과 같은 문장. 수혈은 강한 근거의 조절 가능 위험인자 두 가지 중 하나. |
| 근거 등급 | delirium_kg.py: strong · draft: strong |
| 근거가 방향을 지지하나 | **Y** — 강한 근거 연관 진술과 방향 일치. |
| 코호트 데이터 | n(A)=10,697 · RR 1.04 · RD +1.3%p — 거의 무연관. 구현 정의(이전 24h 적혈구 수혈)가 원 연구 노출 정의와 다를 수 있음. 조 연관. |
| 알려진 충돌 | 없음 |
| MIMIC 매핑 | 가능 — eda/25_ 로 inputevents 에서 회수(transfusion24/cum), stage5 사용 중 |
| 원문 검증 | 확인 |
| **권고** | **승인** — 원문 확인됨. 데이터 약한 연관은 노출 정의 문제로 기록. |

### R-03 · Age (≥65) –increasesRiskOf→ Delirium  — 권고: **승인**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-D-03`) |
| 소스 간 불일치 | 없음 (임계 65 양쪽 동일) |
| 가이드라인 근거 | p.18 raw D-030 (G-007) — 문장이 'greater' 에서 잘림 |
| 근거 요약 | Ungraded Statement 의 조절 불가 강한 근거 목록 첫 항목 'greater [age]'. |
| 근거 등급 | delirium_kg.py: strong · draft: strong |
| 근거가 방향을 지지하나 | **Y** — 방향 일치. 단 65세 임계는 가이드라인이 아닌 우리 구현 선택(원문은 연속적 '고령'). |
| 코호트 데이터 | n(A)=53,704 · RR 1.15 · RD +4.4%p — 방향 일치, 크기 작음. 조 연관. |
| 알려진 충돌 | 없음 (p.18 raw D-028 목록의 'older age' 는 신체억제 관련 인자로 추정 — 같은 방향이라 충돌 아님) |
| MIMIC 매핑 | 가능 — anchor_age 기반 |
| 원문 검증 | 부분(문장 절단) |
| **권고** | **승인** — 방향 확인. 임계 65 는 '구현 선택'으로 KG 주석에 명기 권장. |

### R-04 · Dementia –increasesRiskOf→ Delirium  — 권고: **승인**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-D-04`) |
| 소스 간 불일치 | 없음. draft source 가 문장 ID 없이 한국어 의역만 있음 |
| 가이드라인 근거 | p.18 raw D-030 (G-007) 의 잘린 뒷부분으로 추정 — repo 텍스트로 확인 불가 |
| 근거 요약 | 2018 조절 불가 강한 근거 목록에 치매 포함(팀 정리 문서 기준). repo 의 추출 문장은 'greater' 에서 끊겨 치매 부분이 없음. |
| 근거 등급 | delirium_kg.py: strong · draft: strong |
| 근거가 방향을 지지하나 | **Y(미검증)** — 팀 문서·KG 기재와 일치하나 원문 문장 자체는 repo 에 없음. |
| 코호트 데이터 | n(A)=5,824 · RR 1.83 · RD +24.5%p — 방향 일치. 입원 단위 NLP 동반질환 추출이라 오분류 가능. |
| 알려진 충돌 | 없음 |
| MIMIC 매핑 | 가능 — run_extraction_B.py TERMS 'dementia', stage5 사용 중 |
| 원문 검증 | 미검증 |
| **권고** | **승인** — 조건: PDF p.18 Ungraded Statement 원문 1회 대조. |

### R-05 · PriorComa –increasesRiskOf→ Delirium  — 권고: **승인**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-D-06`) |
| 소스 간 불일치 | 없음. draft source 문장 ID 없음 |
| 가이드라인 근거 | p.18 raw D-030 잘린 뒷부분으로 추정 — repo 텍스트로 확인 불가 |
| 근거 요약 | 조절 불가 강한 근거 목록의 '선행 혼수'(팀 문서 기준). |
| 근거 등급 | delirium_kg.py: strong · draft: strong |
| 근거가 방향을 지지하나 | **Y(미검증)** — 팀 문서와 일치하나 원문 문장 미확보. '선행(prior)'의 시점 정의가 모호. |
| 코호트 데이터 | 없음 |
| 알려진 충돌 | 간접 중첩: 혼수(RASS −4/−5)는 DeepSedation(R-12)·평가불능(R-23)과 정의가 겹침 |
| MIMIC 매핑 | 부분 — GCS 채널은 23_ 스크립트 입력에 있으나 PriorComa 개념·'선행' 시점 미정의 |
| 원문 검증 | 미검증 |
| **권고** | **승인** — 조건: PDF 원문 대조. 모델 투입 전 DeepSedation 과 시점·정의 분리 필요. |

### R-06 · EmergencySurgery (ICU 입실 전) –increasesRiskOf→ Delirium  — 권고: **승인**

| 항목 | 내용 |
|---|---|
| 출처 파일 | delirium_kg.py |
| 소스 간 불일치 | ⚠ delirium_kg.py 에만 있음 (draft 누락) |
| 가이드라인 근거 | p.18 raw D-030 잘린 뒷부분으로 추정 — repo 텍스트로 확인 불가 |
| 근거 요약 | 원문 항목은 '입실 전 응급수술 또는 외상' 한 덩어리로 알려져 있음. KG 는 이를 EmergencySurgery 와 Trauma 둘로 쪼갬. |
| 근거 등급 | delirium_kg.py: strong · draft: — |
| 근거가 방향을 지지하나 | **Y(미검증)** — 방향은 팀 문서와 일치. 'ICU 입실 전' 한정자가 트리플에 없고 주석에만 있음. |
| 코호트 데이터 | 없음 |
| 알려진 충돌 | R-07(Trauma) 과 원문상 한 항목 |
| MIMIC 매핑 | 미매핑 — admissions.admission_type·services 로 구성 가능하나 미구현 |
| 원문 검증 | 미검증 |
| **권고** | **승인** — 조건: PDF 원문 대조 + draft 에 추가 여부 결정. '입실 전' 한정자 명시. |

### R-07 · Trauma –increasesRiskOf→ Delirium  — 권고: **수정**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-D-05`) |
| 소스 간 불일치 | 등급 불일치 가능: 두 파일 모두 strong 이나 원문 moderate 목록에도 'trauma' 가 있음 |
| 가이드라인 근거 | p.19 raw D-033 (moderate 목록, 확인) · p.18 raw D-030 뒷부분('입실 전 응급수술 또는 외상', 미확인) |
| 근거 요약 | 2018: 중간 근거로 위험을 높이는 인자로 고혈압 병력·신경계 질환 입원·외상·향정신성 약물을 나열. |
| 근거 등급 | delirium_kg.py: strong · draft: strong |
| 근거가 방향을 지지하나 | **부분** — 방향은 맞음. 그러나 확인 가능한 원문은 '외상'을 moderate 로 둠. strong 은 '입실 전' 한정일 때만. |
| 코호트 데이터 | n(A)=12,445 · RR 1.34 · RD +10.1%p — 방향 일치. NLP 동반질환 'trauma' 로 입실 전 시점 제한 없음 → moderate 정의에 더 가까움. |
| 알려진 충돌 | 원문 내부: strong(입실 전 응급수술·외상) vs moderate(외상) |
| MIMIC 매핑 | 가능 — TERMS 'trauma', 단 '입실 전' 시점 미구현. stage5 에서 strong(가중 1.0)으로 사용 중 |
| 원문 검증 | 부분 |
| **권고** | **수정** — 현재 구현(시점 제한 없음)에는 moderate 가 맞음. 입실 전 한정 구현 시에만 strong. |

### R-08 · APACHEScore –increasesRiskOf→ Delirium  — 권고: **수정**

| 항목 | 내용 |
|---|---|
| 출처 파일 | delirium_kg.py |
| 소스 간 불일치 | ⚠ delirium_kg.py 에만 있음 (draft 누락). ASA 점수 누락 |
| 가이드라인 근거 | p.18 raw D-030 잘린 뒷부분으로 추정 — repo 텍스트로 확인 불가 |
| 근거 요약 | 조절 불가 강한 근거 목록의 'APACHE 및 ASA 점수 상승'(팀 문서 기준). |
| 근거 등급 | delirium_kg.py: strong · draft: — |
| 근거가 방향을 지지하나 | **Y(미검증)** — 방향 일치하나 연속 점수에 임계값이 없어 단항 술어로 컴파일 불가. ASA 누락. |
| 코호트 데이터 | 없음 |
| 알려진 충돌 | MechanicalVentilation 무영향(R-20) 해석 시 중증도 교란의 축과 겹침 |
| MIMIC 매핑 | 불가(대체 필요) — MIMIC-IV 에 APACHE 없음. SOFA/SAPS-II/OASIS 대체는 동일 개념 아님 |
| 원문 검증 | 미검증 |
| **권고** | **수정** — 임계값·대체 점수 정의와 ASA 포함 여부를 정해야 공리로 쓸 수 있음. |

### R-09 · Hypertension (병력) –increasesRiskOf→ Delirium  — 권고: **승인**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-D-07`) |
| 소스 간 불일치 | 없음. draft source 문장 ID 없음(raw D-033 로 고정 가능) |
| 가이드라인 근거 | p.19 raw D-033 |
| 근거 요약 | 중간 근거로 위험 증가: 고혈압 병력 포함. |
| 근거 등급 | delirium_kg.py: moderate · draft: moderate |
| 근거가 방향을 지지하나 | **Y** — moderate 목록에 명시, 방향·등급 일치. |
| 코호트 데이터 | n(A)=73,958 · RR 1.15 · RD +4.3%p — 방향 일치, 크기 작음. 유병률 높은 입원 단위 NLP 변수라 희석 가능. |
| 알려진 충돌 | 없음 |
| MIMIC 매핑 | 가능 — TERMS 'hypertension', stage5 사용 중 |
| 원문 검증 | 확인 |
| **권고** | **승인** — 원문 확인, 방향·등급 일치. |

### R-10 · NeurologicAdmission –increasesRiskOf→ Delirium  — 권고: **승인**

| 항목 | 내용 |
|---|---|
| 출처 파일 | delirium_kg.py |
| 소스 간 불일치 | ⚠ delirium_kg.py 에만 있음 (draft 누락) |
| 가이드라인 근거 | p.19 raw D-033 |
| 근거 요약 | 중간 근거로 위험 증가: 신경계 질환으로 인한 입원. |
| 근거 등급 | delirium_kg.py: moderate · draft: — |
| 근거가 방향을 지지하나 | **Y** — moderate 목록에 명시, 방향 일치. |
| 코호트 데이터 | 없음 |
| 알려진 충돌 | 없음 (단 신경계 질환 자체가 CAM-ICU 평가 가능성에 영향 → 측정 편향 가능) |
| MIMIC 매핑 | 미매핑 — services(NMED/NSURG)·first_careunit(Neuro) 로 구성 가능, 미구현 |
| 원문 검증 | 확인 |
| **권고** | **승인** — 원문 확인. draft 에 매핑과 함께 추가할지 결정 필요. |

### R-11 · PsychoactiveMedication –increasesRiskOf→ Delirium  — 권고: **수정**

| 항목 | 내용 |
|---|---|
| 출처 파일 | delirium_kg.py |
| 소스 간 불일치 | ⚠ delirium_kg.py 에만 있음 (draft 누락) |
| 가이드라인 근거 | p.19 raw D-033 |
| 근거 요약 | 중간 근거로 위험 증가: 향정신성 약물 사용(예: 항정신병약, 항경련제). |
| 근거 등급 | delirium_kg.py: moderate · draft: — |
| 근거가 방향을 지지하나 | **부분** — 방향은 명시되나 범위가 모호(벤조·덱스도 향정신성). 항정신병약은 섬망 환자에게 처방되는 역인과 가능. |
| 코호트 데이터 | 없음 |
| 알려진 충돌 | 개념 중첩: Benzo(R-01, 증가) · Dexmed(R-16, 감소)와 클래스가 겹쳐 모순 공리 생성 위험 |
| MIMIC 매핑 | 미매핑 — prescriptions/inputevents 에서 항정신병약·항경련제 추출 필요 |
| 원문 검증 | 확인 |
| **권고** | **수정** — 범위를 '항정신병약·항경련제(벤조·덱스 제외)'로 한정하고 투여가 발생보다 앞선 경우만 인정. |

### R-12 · DeepSedation (RASS≤−4) –increasesRiskOf→ Delirium  — 권고: **수정**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-D-08`) |
| 소스 간 불일치 | 없음 (양쪽 low). 단 근거 논리 자체에 문제 |
| 가이드라인 근거 | (논리) 2018 얕은 진정 조건부 권고의 '대우' · p.14 raw D-017 (G-002) · 반대 근거 p.14 raw D-016 |
| 근거 요약 | D-017: 가이드라인 근거에 포함되지 않은 코호트 연구 1건에서 진정 강도가 용량-의존적으로 섬망 위험을 예측. D-016: 얕은 진정은 섬망 발생 감소와 연관 없음(RR 0.96, low). |
| 근거 등급 | delirium_kg.py: low · draft: low |
| 근거가 방향을 지지하나 | **부분** — '얕은 진정 권고'의 대우는 논리적으로 성립 안 함. 가이드라인 자체 RCT 풀링(D-016)은 섬망 효과 없음. 지지는 등급 밖 코호트 1건뿐. |
| 코호트 데이터 | n(A)=6,677 · RR 1.50 · RD +14.9%p — 방향 일치. 단 각성 수준이 CAM-ICU 양성률 자체를 올림(p.21 raw D-048) → 측정 인공물 섞임. 라벨 있는 앵커만 집계. |
| 알려진 충돌 | D-016(얕은 진정 섬망 무효과) · 이중 역할(R-23 평가불능) |
| MIMIC 매핑 | 가능 — itemid 228096, stage5 사용 중(lookback 시점 분리 필요) |
| 원문 검증 | 확인 |
| **권고** | **수정** — 근거를 D-017(코호트, 등급 밖)로 교체하고 등급을 'cohort'로 표기. '권고의 대우' 논리 삭제. |

### R-13 · SedationIntensity –increasesRiskOf→ Death  — 권고: **보류**

| 항목 | 내용 |
|---|---|
| 출처 파일 | draft json (`PADIS-D-09`) |
| 소스 간 불일치 | ⚠ draft json 에만 있음. 목적어가 Delirium 아님 |
| 가이드라인 근거 | p.14 raw D-017 (G-002) |
| 근거 요약 | 가이드라인 근거에 포함되지 않은 코호트 연구 1건: 진정 강도가 사망·섬망·발관 지연을 예측. |
| 근거 등급 | delirium_kg.py: — · draft: cohort (가이드라인 등급 밖) |
| 근거가 방향을 지지하나 | **Y** — 문장이 사망 방향을 직접 진술. 다만 단일 코호트, 가이드라인이 채택한 근거 아님. |
| 코호트 데이터 | 없음 (stage5 는 SedationIntensity→Delirium 만 측정, 부록 X-01) |
| 알려진 충돌 | 없음 |
| MIMIC 매핑 | 가능 — 228096 + hospital_expire_flag |
| 원문 검증 | 확인 |
| **권고** | **보류** — 섬망 예측 공리가 아니고 가이드라인 등급 밖. 사망 보조과제를 둘 때만 재검토. |

### R-14 · PhysicalRestraint –increasesRiskOf→ Delirium  — 권고: **보류**

| 항목 | 내용 |
|---|---|
| 출처 파일 | draft json (`PADIS-D-10`) |
| 소스 간 불일치 | ⚠ draft json 에만 있음 |
| 가이드라인 근거 | p.18 raw D-027 (G-006) |
| 근거 요약 | '이러한 사건'으로 계획외 발관, 기구 제거, 초조 증가 등과 함께 섬망·지남력 장애 위험 증가를 나열. 문장 안에 주어(억제대)가 없고 앞 문맥에서 추정. |
| 근거 등급 | delirium_kg.py: — · draft: low |
| 근거가 방향을 지지하나 | **부분** — 주어가 문장 밖(문맥 추정). 관찰 연구 연관 나열이며 등급 진술 아님. draft 의 'low' 는 원문 등급이 아님. |
| 코호트 데이터 | 없음 |
| 알려진 충돌 | 역방향: p.18 raw D-028 이 섬망을 억제대 사용의 관련 인자로 나열(추정) → 인과 방향 불명 |
| MIMIC 매핑 | 부분 — itemid 확인됨, 값 미추출, stay 보유율 50.1% |
| 원문 검증 | 부분(주어 문맥) |
| **권고** | **보류** — 주어 문맥 확인 전이고 역인과가 뚜렷함. PDF p.18 절 제목 확인 후 재검토. |

### R-15 · SeverePain (NRS≥4) –increasesRiskOf→ Delirium  — 권고: **보류**

| 항목 | 내용 |
|---|---|
| 출처 파일 | draft json (`PADIS-D-11`) |
| 소스 간 불일치 | ⚠ draft json 에만 있음. 그런데 stage5 AXIOMS 에 이미 들어가 있음 |
| 가이드라인 근거 | p.9 raw D-014 (G-015) |
| 근거 요약 | 아편유사제 안전성 우려와 관련된 결과(장폐색, 기계환기 기간, 감염, 섬망, 재원일수)를 신중히 평가해야 한다는 서술. |
| 근거 등급 | delirium_kg.py: — · draft: inconclusive |
| 근거가 방향을 지지하나 | **N** — 문장은 '아편유사제 안전성'에 관한 것이며 통증→섬망 방향을 진술하지 않음. |
| 코호트 데이터 | n(A)=25,618 · RR 0.37 · RD −23.1%p — 데이터 반대 방향. NRS 점수는 의사소통 가능한 환자에게서만 기록되는 선택 편향(섬망·진정 환자 제외). |
| 알려진 충돌 | 간접: OpioidUse 무영향(R-21, strong) |
| MIMIC 매핑 | 가능 — 통증 NRS itemid, stage5 사용 중(draft mimic_ready=false 는 갱신 안 됨) |
| 원문 검증 | 확인(불지지) |
| **권고** | **보류** — 인용 문장이 규칙을 지지하지 않음. 원문 근거 확보 전까지 공리에서 제외(삭제 권장). |

### R-16 · Dexmedetomidine –decreasesRiskOf→ Delirium  — 권고: **수정**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-D-12`) |
| 소스 간 불일치 | 관계·등급 일치. 단 draft 인용문(2018 SEDCOM, 비교군 미다졸람)이 주장(2025, 비교군 프로포폴)과 비교군이 다름 |
| 가이드라인 근거 | 2025 Focused Update(repo 에 원문 없음) · p.16 raw D-022/D-023/D-024/D-025 · p.21 raw D-052 (fs D-049) · p.21 raw D-054 (fs D-051) · p.22 raw D-056 · p.23 raw D-072 (fs D-056) |
| 근거 요약 | 2018 근거: SEDCOM 은 벤조 대비 섬망 RR 0.71, PRODEX 는 프로포폴 대비 48h 시점 섬망 감소, 그러나 풀링·MIDEX 는 유의 효과 없음. 2018 권고는 모든 성인에서 섬망 '예방' 목적 덱스 사용을 제안하지 않음. 2025 는 프로포폴 대비 덱스(조건부/중등도)로 팀 문서에 기재. |
| 근거 등급 | delirium_kg.py: moderate · draft: moderate |
| 근거가 방향을 지지하나 | **부분** — 근거는 모두 비교형(벤조 또는 프로포폴 대비)이며 절대 효과가 아님. 예방 목적 권고는 반대(D-052). |
| 코호트 데이터 | n(A)=8,061 · RR 0.60 (¬섬망 기준) · RD −28.2 (¬섬망 기준)%p — 데이터 반대: 섬망 56.9% vs 28.8%(조RR≈1.98). 초조·섬망 환자에게 투여되는 적응증 교란(D-072 권고 자체가 섬망 환자 대상). 가이드라인 오류 근거 아님. |
| 알려진 충돌 | FEWSHOT_CHECK §3: D-052 예방 목적 비권고 vs D-054 수술 후 저용량 발생 감소 |
| MIMIC 매핑 | 가능 — itemid 225150/229420, stage5 사용 중 |
| 원문 검증 | 부분(2025 미확보) |
| **권고** | **수정** — '프로포폴(또는 벤조) 대비' 비교형 쌍 제약으로 재표현하고 모집단(기계환기 진정)을 한정. 2025 원문 대조 필요. |

### R-17 · EnhancedMobilization –decreasesRiskOf→ Delirium  — 권고: **수정**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-D-13`) |
| 소스 간 불일치 | 관계·등급 일치. 개념명 불일치: KG/draft 'EnhancedMobilization' vs concepts·stage5 'EarlyMobility' |
| 가이드라인 근거 | 2025 Focused Update(repo 에 원문 없음) · p.24 raw D-076 (G-014, fs D-060) |
| 근거 요약 | 2025: 강화된 재활은 섬망 '기간'을 소폭 줄임(조건부/낮음, 팀 문서 기준). 2018 인용문은 ABCDEF 번들 준수율이 사망 감소·혼수/섬망 없는 ICU 일수 증가와 연관된다는 전후비교 코호트. |
| 근거 등급 | delirium_kg.py: low · draft: low |
| 근거가 방향을 지지하나 | **부분** — 결과 변수가 발생이 아니라 기간/일수. 2018 인용은 재활 단독이 아닌 번들. '강화(용량)'와 '조기(시점)'는 다른 중재. |
| 코호트 데이터 | n(A)=10,960 · RR 1.40 (¬섬망 기준) · RD +26.2 (¬섬망 기준)%p — 방향 일치(섬망 7.5% vs 33.7%). 단 JH-HLM 은 '달성한 이동 수준'이라 깨어 있고 덜 아픈 환자만 해당 → 역선택. 중재 강도 아님. |
| 알려진 충돌 | 없음 |
| MIMIC 매핑 | 부분 — JH-HLM/Braden 달성 수준 기록(stage5 사용), 중재 용량 자체는 측정 불가 |
| 원문 검증 | 부분(2025 미확보) |
| **권고** | **수정** — 결과를 '섬망 기간/일 단위 상태'로 한정하거나 발생 예측에서는 가중치 축소. 개념명 통일. |

### R-18 · Melatonin –decreasesRiskOf→ Delirium  — 권고: **보류**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-D-14`) |
| 소스 간 불일치 | 없음 (방향·등급 일치) |
| 가이드라인 근거 | 2025 Focused Update — repo 에 원문·추출 문장 없음 |
| 근거 요약 | 팀 문서 기준: 멜라토닌은 섬망 유병률을 낮출 수 있음(조건부/낮음). |
| 근거 등급 | delirium_kg.py: low · draft: low |
| 근거가 방향을 지지하나 | **미검증** — repo 안의 어떤 텍스트에서도 멜라토닌 문장을 찾지 못함. |
| 코호트 데이터 | 없음 |
| 알려진 충돌 | 없음 |
| MIMIC 매핑 | 미매핑 — prescriptions 추출 필요 |
| 원문 검증 | 미검증 |
| **권고** | **보류** — 원문 확인 불가 + 매핑 없음 → 지금은 모델에 넣을 수 없음. 2025 원문 확인 후 승인 가능. |

### R-19 · Delirium –increasesRiskOf→ Death  — 권고: **보류**

| 항목 | 내용 |
|---|---|
| 출처 파일 | draft json (`PADIS-D-15`) |
| 소스 간 불일치 | ⚠ draft json 에만 있음. 인용 영문장이 repo 원문 어디에도 없음 |
| 가이드라인 근거 | draft 표기 '2018 섬망 결과 절' — 인용문 미확인 · 관련 문장 p.21 raw D-050/D-051 |
| 근거 요약 | D-050/D-051: 빠르게 회복되는 진정 관련 섬망은 섬망 없는 환자와 결과가 비슷했고, 그 밖의 섬망 환자는 결과가 더 나빴음(관찰 연구 1건). |
| 근거 등급 | delirium_kg.py: — · draft: strong |
| 근거가 방향을 지지하나 | **부분** — 관련 서술은 있으나 draft 인용문은 원문으로 확인 안 됨. PADIS 가 이 방향에 'strong' 등급을 준 근거를 찾지 못함. |
| 코호트 데이터 | 없음 |
| 알려진 충돌 | D-050: 진정 관련 섬망은 결과 차이 없음 → 섬망 아형에 따라 방향이 다름 |
| MIMIC 매핑 | 가능 — hospital_expire_flag |
| 원문 검증 | 미검증(인용 불일치) |
| **권고** | **보류** — 섬망 예측 공리가 아님(섬망이 주어). 인용 교정·등급 근거 확인 전까지 제외. |

### R-20 · MechanicalVentilation –hasNoEffectOn→ Delirium  — 권고: **승인**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-N-01`) |
| 소스 간 불일치 | 현재 일치. v1 에서 increasesRiskOf 로 반대였던 이력(_v1_corrections) |
| 가이드라인 근거 | p.19 raw D-032 |
| 근거 요약 | 성별·아편유사제 사용·기계환기는 섬망 발생 위험을 바꾸지 않는다고 강하게 입증됨. |
| 근거 등급 | delirium_kg.py: strong · draft: strong |
| 근거가 방향을 지지하나 | **Y** — 명시적 무영향 진술, 강한 근거. |
| 코호트 데이터 | 없음 (필터 규칙이라 stage5 대상 아님). 데이터에서는 중증도 교란으로 양의 상관이 예상됨. |
| 알려진 충돌 | FEWSHOT_CHECK §3: fs D-026(=raw D-028, p.18) 목록에 기계환기 포함. 단 그 목록은 '섬망'을 인자로 포함하고 억제대 문맥에 위치 → 섬망 위험인자 목록이 아닐 가능성 높음(추정) |
| MIMIC 매핑 | 미매핑 — procedureevents/ventilation derived(chk15_b_ventilation.csv) |
| 원문 검증 | 확인 |
| **권고** | **승인** — 강한 근거 명시. fs D-026 은 다른 결과(억제대 사용)의 인자 목록으로 보여 실제 모순이 아닐 가능성 큼. |

### R-21 · OpioidUse –hasNoEffectOn→ Delirium  — 권고: **승인**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-N-02`) |
| 소스 간 불일치 | 없음 |
| 가이드라인 근거 | p.19 raw D-032 |
| 근거 요약 | R-20 과 같은 문장. 아편유사제 사용은 섬망 위험을 바꾸지 않음(강한 근거). |
| 근거 등급 | delirium_kg.py: strong · draft: strong |
| 근거가 방향을 지지하나 | **Y** — 명시적 무영향 진술, 강한 근거. |
| 코호트 데이터 | 없음 |
| 알려진 충돌 | FEWSHOT_CHECK §3: fs D-032(=raw D-035, p.19) Evidence Gap 서술이 아편유사제를 '알려진 위험인자'로 나열 · p.9 raw D-014 안전성 우려 결과에 섬망 포함 |
| MIMIC 매핑 | 미매핑 — inputevents(fentanyl 등) 추출 필요 |
| 원문 검증 | 확인 |
| **권고** | **승인** — 등급 있는 진술(strong) > 근거공백 서술. 충돌 정책 적용 전제로 승인. |

### R-22 · PatientSex –hasNoEffectOn→ Delirium  — 권고: **승인**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-N-03`) |
| 소스 간 불일치 | 없음 |
| 가이드라인 근거 | p.19 raw D-032 |
| 근거 요약 | R-20 과 같은 문장. 성별은 섬망 위험을 바꾸지 않음(강한 근거). |
| 근거 등급 | delirium_kg.py: strong · draft: strong |
| 근거가 방향을 지지하나 | **Y** — 명시적 무영향 진술, 강한 근거. |
| 코호트 데이터 | 없음 (is_male 은 모델 입력에만 있음) |
| 알려진 충돌 | 없음 |
| MIMIC 매핑 | 가능 — patients.gender |
| 원문 검증 | 확인 |
| **권고** | **승인** — 원문 확인, 방향·등급 일치. |

### R-23 · DeepSedation (RASS≤−4) –precludes→ DeliriumAssessment  — 권고: **승인**

| 항목 | 내용 |
|---|---|
| 출처 파일 | 둘 다 (`PADIS-G-01`) |
| 소스 간 불일치 | 관계 일치. KG 는 evidenceLevel 없음, draft 는 'data-derived'. 목적어명 불일치: DeliriumAssessment / Assessable(concepts) / CurrentUTA(stage5) |
| 가이드라인 근거 | 가이드라인 문장 아님(draft 명시) · 보조: p.21 raw D-045 (fs D-042) |
| 근거 요약 | D-045: 여러 연구에서 RASS −3 환자도 다수가 '평가 불가'로 분류되어 RASS 0~−2 범위만 분석 가능했음. |
| 근거 등급 | delirium_kg.py: (없음) · draft: data-derived |
| 근거가 방향을 지지하나 | **부분** — 깊은 진정→평가 불가 방향은 D-045 가 뒷받침하나 등급 있는 진술이 아니며 CAM-ICU 도구 절차·데이터 관측에 기반. |
| 코호트 데이터 | n(A)=6,677 · RR 4.20 · RD +32.5%p — 방향 강하게 일치. 단 P(UTA\|깊은진정)=42.6% 로 결정론적 '불가'는 아님(lookback vs 현재 시점 차이). |
| 알려진 충돌 | R-12 와 이중 역할(시점 분리 필요) |
| MIMIC 매핑 | 가능 — 228096 + 228332(UTA) |
| 원문 검증 | 해당없음(비가이드라인) |
| **권고** | **승인** — 구조적 가드로 타당. 논문에서 '가이드라인 외(도구 절차·데이터)'로 표기하고 soft 제약으로 사용. |

## 3. 부록 — 두 소스 밖에서 발견된 트리플

- **X-01 · SedationIntensity –increasesRiskOf→ Delirium** (padis_concepts.json · stage5 AXIOMS (두 소스엔 없음)) — 근거: p.14 raw D-017 (G-002). 지지 Y: 문장이 방향을 직접 진술. 단 가이드라인 근거에 포함되지 않은 연구. 코호트: n(A)=15,202 · RR 2.39 · RD +35.7%p — 방향 일치, 크기 큼. 각성 수준이 CAM-ICU 양성률을 올리는 측정 효과(D-048) 섞임. R-12 와 거의 같은 변수(RASS). → **수정**: R-12 와 통합하거나 둘 중 하나만 유지하고, 출처 파일(KG/draft)에 등록할지 결정.
- **X-02 · Delirium –increasesRiskOf→ Immobility** (padis_concepts.json (두 소스엔 없음)) — 근거: 찾지 못함. 지지 미검증: 근거 문장 없음. 코호트: 없음 → **보류**: 출처 불명. 섬망 예측 공리도 아님.

## 4. 요약

### 4.1 권고 집계

- **승인 12**: R-01 BenzodiazepineUse, R-02 BloodTransfusion, R-03 Age, R-04 Dementia, R-05 PriorComa, R-06 EmergencySurgery, R-09 Hypertension, R-10 NeurologicAdmission, R-20 MechanicalVentilation, R-21 OpioidUse, R-22 PatientSex, R-23 DeepSedation
- **수정 6**: R-07 Trauma, R-08 APACHEScore, R-11 PsychoactiveMedication, R-12 DeepSedation, R-16 Dexmedetomidine, R-17 EnhancedMobilization
- **보류 5**: R-13 SedationIntensity, R-14 PhysicalRestraint, R-15 SeverePain, R-18 Melatonin, R-19 Delirium

근거방향지지 분포: N 1 · Y 9 · Y(미검증) 4 · 미검증 1 · 부분 8

### 4.2 두 소스 간 불일치

현재(draft v2 기준) 두 파일 사이에 **관계 방향이 반대인 규칙은 없다.** v1 의 반대 방향 3건(MechanicalVentilation, Propofol, DeepSedation→UTA)은 `_v1_corrections` 로 이미 고쳐졌다. 남은 불일치는 다음과 같다.

- **delirium_kg.py 에만 있음 (4)**: R-06 EmergencySurgery, R-08 APACHEScore, R-10 NeurologicAdmission, R-11 PsychoactiveMedication — draft 에 MIMIC 매핑과 함께 추가할지 결정 필요.
- **draft json 에만 있음 (4)**: R-13 SedationIntensity→Death, R-14 PhysicalRestraint→Delirium, R-15 SeverePain→Delirium, R-19 Delirium→Death — 네 건 모두 권고 '보류'. draft 주석은 'delirium_kg.py 가 이긴다'고 적었으므로 권위 소스에 없는 규칙이다.
- **등급 문제(양쪽 동일하게 틀렸을 가능성)**: R-07 Trauma — 두 파일 strong, 확인 가능한 원문(p.19 raw D-033)은 moderate.
- **인용 불일치**: R-16 Dexmed(2025 '프로포폴 대비' 주장에 2018 '미다졸람 대비' SEDCOM 문장 인용) · R-17 EnhancedMobilization(2025 재활 권고에 2018 ABCDEF 번들 문장 인용) · R-19 Delirium→Death(인용 영문장이 repo 원문에 없음) · R-15 SeverePain(아편유사제 안전성 문장 인용).
- **이름 불일치(컴파일 시 조인 실패 위험)**: EnhancedMobilization↔EarlyMobility · BenzodiazepineUse↔Benzodiazepine↔Benzo · Age↔OlderAge · DeliriumAssessment↔Assessable↔CurrentUTA.
- **stale 필드**: draft `mimic_ready=false` 인 BloodTransfusion·SeverePain·EnhancedMobilization 이 stage5 공리에 이미 사용됨. draft `_summary.increasesRiskOf=11` 은 실제 12(D-01~D-11 + D-15).
- **모델 코드와의 불일치**: `eda/23_stage34_bilstm_cbm.py` AXIOMS 는 보류 권고인 SeverePain(R-15), 두 소스 밖인 SedationIntensity→Delirium(X-01)을 쓰고, Trauma 를 strong(가중 1.0)으로 쓴다.

### 4.3 사람이 결정해야 할 항목

1. **R-16 Dexmedetomidine** — 비교형(쌍 제약)으로 바꿀지, 단항 규칙을 유지하되 모집단(기계환기 진정)·비교군을 한정할지. 2018 예방 비권고(D-052)와의 관계 정리.
2. **R-17 EnhancedMobilization** — 결과가 '기간'인 권고를 '발생' 예측 공리로 쓸지. 쓴다면 가중치 축소 여부.
3. **R-12 DeepSedation→Delirium** — '얕은 진정 권고의 대우'라는 근거를 버리고 등급 밖 코호트(D-017)로 교체할지. X-01 SedationIntensity 와 통합할지.
4. **R-07 Trauma** — moderate 로 내릴지, '입실 전' 시점을 구현하고 strong 유지할지.
5. **R-11 PsychoactiveMedication** · **R-08 APACHEScore** — 개념 범위/임계값·대체 점수 정의.
6. **R-15 SeverePain** — 공리에서 제거할지(이미 모델에 들어가 있음).
7. **R-13, R-14, R-18, R-19** — 보류 유지 또는 제거.
8. **원문 대조가 필요한 조건부 승인**: R-04 Dementia · R-05 PriorComa · R-06 EmergencySurgery · (R-08 APACHE) — PDF p.18 Ungraded Statement 한 문단만 확인하면 된다. R-18 Melatonin·R-16·R-17 은 2025 Focused Update 원문 확인이 필요하다.
9. **draft 누락 4건(R-06, R-08, R-10, R-11)** 을 draft/매핑 계층에 추가할지.

### 4.4 충돌 해소 정책이 필요한 자기모순

| 대상 | 한쪽 | 다른 쪽 | 제안 판정 |
|---|---|---|---|
| Dexmedetomidine | p.21 raw D-052(fs D-049) 권고: 모든 성인에서 섬망 예방 목적 사용 비제안 | p.21 raw D-054(fs D-051) 수술 후 저용량 발생 감소 · p.16 D-022/D-025 비교 RCT · 2025 프로포폴 대비 제안 | 충돌이 아니라 **PICO 차이**(예방/전체 vs 진정/기계환기 vs 수술 후). 모집단·비교군 한정자를 붙여 둘 다 보존 |
| MechanicalVentilation | p.19 raw D-032 strong 무영향 | p.18 raw D-028(fs D-026) 서술형 인자 목록 | 등급 진술 > 서술 목록. 게다가 해당 목록은 '섬망'을 인자로 포함해 **섬망 위험인자 목록이 아닐 가능성**(억제대 문맥, PDF 확인 필요) |
| OpioidUse | p.19 raw D-032 strong 무영향 | p.19 raw D-035(fs D-032) Evidence Gap 의 '알려진 위험인자' 나열 · p.9 raw D-014 | 등급 진술 > Evidence Gap/안전성 서술 |
| Trauma | p.18 strong 목록 '입실 전 응급수술 또는 외상'(미확인) | p.19 raw D-033 moderate '외상' | 한정자가 더 구체적인 쪽이 해당 범위에서만 우선. 한정자 미구현이면 moderate |
| DeepSedation | 2018 얕은 진정 조건부 권고(다른 결과 근거) · D-017 코호트 | p.14 raw D-016 얕은 진정의 섬망 무효과(RCT 풀링, low) | 권고의 대우는 규칙 근거로 불인정. 등급 밖 코호트는 'cohort' 로 표기 |

**제안 정책 (우선순위 순)**

1. **문서 층위**: 등급 있는 권고문(Recommendation, GRADE) · 근거강도가 명시된 Ungraded Statement > Rationale 속 개별 연구 서술 > Evidence Gaps/Remarks 서술 > 다른 절 문맥의 나열.
2. **같은 층위 안에서**: strong > moderate > low/very low > inconclusive > 등급 없는 나열.
3. **판본**: 같은 PICO 라면 2025 Focused Update > 2018. PICO 가 다르면 충돌이 아니라 **범위가 다른 두 규칙**이며 모집단/비교군/결과 한정자를 붙인다.
4. **hasNoEffectOn(strong)** 은 같은 개념에 대한 서술형 increasesRiskOf 와 마이닝 규칙을 기각한다.
5. **등급 밖 근거**(가이드라인이 채택하지 않은 코호트, 데이터 관측)는 규칙에 남기되 등급을 `cohort`/`derived` 로 표기하고 가이드라인 등급과 섞지 않는다.
6. **코호트 데이터 불일치는 기각 사유가 아니다.** 교란(Dexmed 적응증), 선택(SeverePain NRS), 측정(각성 수준→CAM-ICU 양성률, D-048) 분석의 대상으로만 쓴다.
7. **문장 단위 추출 시 절 제목을 함께 보존**한다(fs D-026 사례). 문맥 없는 문장은 자동 규칙화하지 않는다.

### 4.5 설계상 추가 지적

- `evidenceLevel` 하나에 서로 다른 척도가 섞여 있다: 2018 위험인자 절의 **연관 근거강도**(strong/moderate), 권고문의 **GRADE 확실성**(conditional/low), 2025 권고의 확실성(moderate), 그리고 draft 의 `cohort`/`data-derived`. 이 값을 곧바로 공리 가중치(`GRADE_W`)로 쓰면 '연관의 확실성'과 '중재 효과의 확실성'이 같은 자로 취급된다.
- 2018 위험인자 진술은 **Ungraded, nonactionable** 연관 진술이다. `increasesRiskOf` 를 인과로 읽지 않도록 KG 주석이나 논문에 명기할 것.
- 양의 방향 공리가 9:3 으로 기울어 있다는 23_ 스크립트 주석(collapse 주의)을 감안하면, 음의 방향 두 건(R-16, R-17)이 모두 '수정' 대상이라는 점이 모델 설계에 직접 영향을 준다.

## 5. 검증하지 못한 것

- PADIS 2018 p.18 Ungraded Statement 의 'greater' 이후 부분 → R-04, R-05, R-06, R-08 과 R-07 의 strong 근거.
- 2025 Focused Update 전체 → R-16(프로포폴 대비·moderate), R-17(기간 단축·low), R-18(멜라토닌).
- R-19 draft 인용문 'Delirium is associated with increased mortality…' — repo 의 어떤 원문에서도 찾지 못함.
- p.18 raw D-027/D-028 의 주어가 '신체억제대'라는 판단 — 두 문장이 섬망 절 시작(raw D-029) 직전에 있고 D-028 이 섬망을 인자로 나열한다는 점에 근거한 **추정**.
- 2018 진정제 선택 권고문 본문(프로포폴 또는 덱스를 벤조보다 선호) — '섬망' 단어가 없어 추출 문장에 없음. p.15 raw D-019 는 2013 PAD 권고를 인용한 것.

## 6. 참고 파일

- 규칙: `padis/kg/delirium_kg.py` · `padis/outputs/padis_rules_draft_v1.json` · `NeSy-SMP/configs/padis_concepts.json`
- 원문 문장: `padis/outputs/padis_rules_raw.json` · `padis/outputs/_gold_sentences.txt` · `padis/outputs/gold_set_draft.md` · `padis/rules/gold_set_smoke.json`
- 해석: `padis/docs/PADIS_섬망_지식그래프_정리.md` · `NeSy-SMP/tools/FEWSHOT_CHECK.md` §3
- 데이터: `notes/eda/out_split/stage5_axiom_data.csv` (산출 코드 `eda/23_stage34_bilstm_cbm.py`)
