# 패혈증 규칙 추출 · 모델링 코드 안내

작성 2026-11-03 · 이지우 · 저장소 `NeSy-SMP-repro`
대상 논문: De Santis 외, *Neuro-symbolic AI for real-time sepsis mortality prediction*, EAAI 177 (2026) 114920

이 문서 하나로 **① 규칙(공리)을 어떻게 뽑았는지 ② 그 공리가 모델 어디에 들어가는지**를 모두 찾을 수 있게 정리했다.
숫자의 근거가 되는 파일 경로를 각 절 끝에 붙였다.

---

## 0. 세 줄 요약

1. SSC 2021 가이드라인 원문에서 규칙을 다시 뽑아 봤다 — **zero-shot · one-shot · few-shot 각 2회**, 본문 조각 6개씩.
2. **예시 개수는 "무엇이 뽑히는지"를 바꾸지 못했다.** 세 조건 모두 같은 소수의 규칙만 나오고, 기존 규칙 19개 중
   재현된 것은 1개뿐이다. 예시는 **정확도와 반복 일관성**만 올린다(근거 지지 70% → 89%, 반복 일치 0.75 → 1.00).
3. **추출한 규칙은 현재 모델로 들어가지 않는다.** 학습 코드의 공리는 파일에서 읽지 않고 코드에 직접 적혀 있다.
   즉 "추출 → KG → 공리 → 학습" 중 뒤쪽 두 단계가 끊겨 있다.

---

# 1부 — 규칙(공리) 추출

## 1-1. 무엇을 물었나

> "기존 규칙을 few-shot 예시로 주고 SSC 2021 원문에서 다시 뽑으면, 같은 규칙이 나오는가?"

랩에서 정한 이 설계에 결함이 있어 고친 뒤 실행했다.

| 결함 | 고친 방법 |
|---|---|
| 예시로 보여준 규칙으로 채점 (순환) | 정답 30개를 **예시 11 / 확인용 19** 로 나누고, 프롬프트에는 예시만. 재현율은 **확인용에서만** 측정 |
| 정답 일치 ≠ 근거 지지 | 모든 예측을 근거 문장과 함께 **사람이 Y / 부분 / N 판정**. 근거 지지율을 주지표로 |
| 원문 365KB | 서지·참고문헌을 떼고 **본문 전체**를 최상위 섹션 6조각으로 분할(키워드로 고르지 않음) |

분할은 **주어 개념 단위**라 확인용 주어는 예시에 한 번도 주어로 나오지 않는다
(`Cancer→Death` 를 보고 `Cancer→Sepsis` 를 원문 없이 패턴으로 맞히는 것을 막기 위함).

## 1-2. 조건

| 조건 | 프롬프트 예시 | 실행 | 분할 파일 |
|---|---:|---|---|
| zero-shot | 0개 | 2회 (조각 6 × 2) | `splits/sepsis_holdout_split_k0.json` |
| one-shot | 1개 (`Sepsis increasesRiskOf Death`) | 2회 | `splits/sepsis_holdout_split_k1.json` |
| few-shot | 11개 | 2회 | `splits/sepsis_holdout_split.json` |

- 원문·허용 개념·허용 술어·지시문은 세 조건 모두 동일하고 **예시 개수만** 다르다.
- 조각마다 **대화 기록이 없는 새 에이전트**가 프롬프트 파일 하나만 읽고 결과만 쓴다(저장소 경로도, 정답도 주지 않음).
- 근거 판정은 세 조건 + 기존 regex 기준선 **57건을 섞고 출처를 가린 뒤** 판정자 2명이 각각 판정했다.

## 1-3. 결과

| 조건 | 실행 | 추출(고유) | **근거 지지 Y** | 부분 | N | 확인용 19개 재현 | 반복 일치(Jaccard) |
|---|---|---:|---:|---:|---:|---:|---:|
| zero-shot | 1회차 | 10 (7) | **70%** | 2 | 1 | 1/19 | **0.75** |
| zero-shot | 2회차 | 8 (7) | **75%** | 2 | 0 | 1/19 | |
| one-shot | 1회차 | 9 (6) | **89%** | 1 | 0 | 1/19 | **0.83** |
| one-shot | 2회차 | 8 (5) | **88%** | 1 | 0 | 1/19 | |
| few-shot | 1·2회차 | 10 (7) | **80%** | 2 | 0 | 1/19 | **1.00** |
| regex (기존 방식) | — | 12 | 8% | 1 | 10 | 8/19 (근거 맞는 것 1) | — |

판정자 2명이 57건 전부 같게 판정했다 (**Cohen κ = 1.00**).

### 여섯 번의 실행에서 나온 트리플 전부 (고유 8개)

| 트리플 | 나온 실행 | 정답셋 | 판정 |
|---|---|---|---|
| `Lactate associatedWith Death` | **6/6** | 정답셋 밖 | Y · Y |
| `Lactate associatedWith Sepsis` | **6/6** | 정답셋 밖 | Y · Y |
| `Lactate associatedWith SepticShock` | **6/6** | 정답셋 밖 | 부분 · 부분 |
| `Sepsis increasesRiskOf Death` | **6/6** | 예시 | Y · Y |
| `SepticShock increasesRiskOf Death` | **6/6** | **확인용** | Y · Y |
| `Hypotension associatedWith SepticShock` | 4/6 | 정답셋 밖 | 부분 · 부분 |
| `Sepsis causedBy Pneumonia` | 4/6 | 정답셋 밖 | Y · Y |
| `MeanArterialPressure associatedWith Death` | 1/6 (zero-shot) | 정답셋 밖 | **N · N** |

데이터: `docs/kg/sepsis_shot_triples_matrix.csv`

## 1-4. 해석

1. **무엇이 뽑히는지는 예시가 아니라 원문이 정한다.** 예시 0·1·11개가 거의 같은 트리플을 낸다.
   기존 규칙 19개 중 18개는 어느 조건에서도 나오지 않는다 → **기존 sepsis 규칙 대부분은 SSC 2021 본문에 쓰여 있지 않다.**
   SSC 는 치료 가이드라인이라 "어떤 환자가 위험한가"라는 역학 서술 자체가 적다. 'LLM 이 못 찾는다'가 아니라 '거기에 없다'.
2. **예시는 정확도와 일관성을 올린다.** 예시가 없으면 치료 시기에 관한 문장을 환자 특성 규칙으로 잘못 바꾸는 오류가 생기고
   (`MeanArterialPressure associatedWith Death` — 유일한 명백한 오류), 반복 일치도가 0.75 로 낮다.
   예시 1개만 있어도 근거 지지 88~89% · 일치 0.83, 11개면 일치 1.00.
3. **'정답셋 밖'이 곧 오류는 아니다.** 8개 중 5개가 정답셋 밖인데 판정은 Y 또는 부분이다.
   젖산·저혈압은 패혈성 쇼크 정의의 구성요소라 '부분'으로 판정됐고, `Sepsis causedBy Pneumonia` 는
   기존 정답셋이 빠뜨린 쪽에 가깝다 → **정답셋 자체의 보완 후보**다.

## 1-5. 파일 지도 (추출)

| 단계 | 경로 |
|---|---|
| 원문 조각화 | `NeSy-SMP/tools/rule_extraction/guideline_chunks.py` |
| 분할 생성 (시드 20260915 / 20260917) | `NeSy-SMP/tools/rule_extraction/make_sepsis_holdout_split.py` → `splits/sepsis_holdout_split{,_k0,_k1}.json` |
| 프롬프트 | `NeSy-SMP/tools/rule_extraction/prompts/{zeroshot,oneshot,fewshot}_sepsis_holdout_01~06_*.txt` (+ `*_manifest.json`) |
| 추출 결과(원본) | `NeSy-SMP/tools/rule_extraction/llm_runs/{zeroshot,oneshot,fewshot}_run{1,2}/*.result.json` · `merged.json` · `review.csv` |
| 병합 · 채점 | `merge_llm_outputs.py` · `rule_extraction_check.py` |
| 블라인드 근거 판정 | `llm_runs/blind_review_k01_j{1,2}_unblinded.csv` (+ `_blind_key_k01_j*.csv`) |
| 조건별 집계 | `docs/kg/sepsis_shot_triples_matrix.csv` (이 문서의 표) |
| 실행 절차 상세 | `NeSy-SMP/tools/rule_extraction/README.md` |
| 설계 근거 · 결과 | `docs/kg/KG_FEWSHOT_PIPELINE_CHECK.md` §7–8 · `docs/kg/KG_SHOT_COUNT_SEPSIS.md` |

### 원저자 쪽 원본 파이프라인 (참고)

| 역할 | 경로 | 내용 |
|---|---|---|
| 지식그래프 | `NeSy-SMP/create_ckg.py` | rdflib 로 트리플을 **사람이 직접** 써 넣는다 (가이드라인 자동 추출이 아니다) |
| 규칙 채굴 | `NeSy-SMP/extract_rules.py` | AnyBURL 로 `rules/pkg.txt` 에서 규칙 채굴 |
| 규칙 필터 | `NeSy-SMP/filter_rules.py` | 채굴 결과 선별 |
| 개념·술어 목록 | `NeSy-SMP/configs/clinical_concepts.json` · `relation_vocab.json` | 정답셋 30개의 출처 |

임계값 출처를 대조한 결과, 코드에만 있는 임계값은 SSC 2021 도 채굴 결과도 아니고
저자가 SOFA·qSOFA·MEWS·APACHE II 등을 참고해 직접 정한 값으로 보인다 (`docs/repro/REPRO_AXIOM_THRESHOLD_SOURCES.md`).

---

# 2부 — 모델링 코드

## 2-1. 구조

입력 CSV(환자 × 시계열 변수) → BiLSTM 인코더 → 사망 확률 술어 `P` + 위험 술어 13개 →
데이터 공리와 지식 공리의 만족도를 섞은 손실.

```
loss = 1 - ( w_data * SatAgg(데이터 공리) + w_knowledge * SatAgg(지식 공리) ),  w_data 0.8 / w_knowledge 0.2

  데이터 공리 : 모든 사망 환자에 대해  P(x)         (전칭, p=2)
                모든 생존 환자에 대해  not P(x)     (전칭, p=6)
  지식 공리   : Anchor      조건 충족 -> 위험 술어 참   (13개, 조건은 데이터로 판정)
                Implication 위험 술어 -> P (사망)       (8개)
```

함축은 Reichenbach(`1 - a + a*b`), 전칭은 pMeanError 를 쓴다 — LTN 라이브러리 연산 그대로다.

## 2-2. 공리가 코드 어디에 있나

`NeSy-SMP/variants/upstream_faithful/stratified_main.py` 기준 행 번호다.

| 내용 | 행 |
|---|---|
| 위험 술어 13개 생성 (`MLP(sequence_length, 64)`) | 471~505 |
| 변수 추출 함수 · **임계값 조건** (젖산 4.0 · GCS 8 · 혈소판 50 · CRP 100 · 백혈구 30 · 나이 65 …) | 520~540 |
| 손실 가중치 `w_data = 0.8` · `w_knowledge = 0.2` | 542 |
| 조건을 만족하는 환자 묶음 만들기 (`x_below_gcs`, `x_above_lactate` …) | 548~573 |
| **Anchor 공리 조립** | 575~636 |
| **Implication 공리 조립** (위험 술어 → 사망) | 637~646 |
| 만족도 집계와 손실 | 647~655 |

> **공리는 파일에서 읽지 않는다.** 이 스크립트가 여는 파일은 결과 저장 한 곳(696행)뿐이다.
> 즉 1부에서 추출한 트리플이나 `create_ckg.py` 의 KG 는 학습에 **전혀 들어가지 않는다.**

## 2-3. 실행본 목록 (조건별 복제본)

원본 코드를 조건마다 복제하고 패치만 다르게 걸었다. 각 폴더의 `PATCHES.md` 에 바꾼 줄이 적혀 있다.

| 폴더 (`NeSy-SMP/variants/`) | 패치 | 쓰임 |
|---|---|---|
| `upstream_faithful` | P1~P5 (실행에 꼭 필요한 수정만) | 논문 조건 재현 기준선 |
| `upstream_faithful_log` | + P6 기록 | 공리별 활성화율·만족도 기록 |
| `upstream_sensitivity_axiom` | + S1 결측 인식 | 결측을 0으로 채워 규칙이 오작동하던 문제 |
| `upstream_sensitivity_connect` | + S3 · S4 | 판정기 5개를 사망과 추가 연결 + 혈당 공리 버그 수정 |
| `upstream_sensitivity_connect4` | + S5 | 위에서 혈당 함축만 제외 |
| `upstream_sens_map` | + S6 | 논문 §4.5 목록에 있는데 코드에 없던 `LowMAP` 추가 |
| `upstream_sens_subset` | + S7 | 학습셋 비율 조절 (`NESY_SUBSET`) |
| `upstream_sens_padis` | + S2 | PADIS 임상 변수 5개를 입력에 추가 |

패치 적용 스크립트는 `NeSy-SMP/tools/patches/apply_patch_*.py` 다. 원본 파일은 고치지 않고 복제본에만 적용한다.

## 2-4. 실행 방법

```bash
# 결과를 쓸 폴더를 현재 디렉터리로 두고, 입력 CSV 를 환경변수로 지정한다
cd <결과 폴더>
NESY_DATA=<경로>/events_6h_wide_paper_como.csv python <저장소>/NeSy-SMP/variants/upstream_faithful/stratified_main.py

# 학습셋 비율 실험은 비율을 함께 지정한다
NESY_SUBSET=0.1 NESY_DATA=<같은 CSV> python <저장소>/NeSy-SMP/variants/upstream_sens_subset/stratified_main.py
```

- 1회 = 5-fold × 5모델(XGBoost · RF · BiLSTM · LTN · NeSy) = **모델 적합 25건**, 6h 기준 **15~17시간**.
- 메모리를 약 26GB 쓰므로 **한 번에 하나만** 돌려야 한다. 직렬 실행 큐는 `scripts/queues/queue_research_*.ps1`.
- 공리 동작 감사는 `NeSy-SMP/tools/audit/grad_path_sepsis.py` (학습 없이 공리별 gradient 측정).

## 2-5. 섬망 쪽 모델링 (비교군)

패혈증 코드와 별개로, 추출한 KG 를 실제로 학습에 넣어 비교한 것은 섬망 코호트다.

| 내용 | 경로 |
|---|---|
| 기본 모델 (BiLSTM · 개념 병목) | `delirium/23_stage34_bilstm_cbm.py` |
| 공리 정의와 만족도 계산 | `delirium/29_outcome_mortality.py` (`AX_RISK` 93행 · `make_axioms` 120행 · `axiom_sat` 126행) |
| KG 범위별 공리 컴파일 | `delirium/30_kg_variants.py` · `delirium/33_kg_variants_v2.py` |
| 음성 대조군 · 가중치 스윕 | `delirium/31_axiom_control.py` |
| 구조 가설 (경로를 좁히면?) | `delirium/35_structural_bottleneck.py` |
| gradient 경로 점검 | `delirium/38_grad_path_check.py` |
| 논문식 손실 재현 (LTN 라이브러리) | `delirium/39_ltn_paper_loss.py` · `delirium/40_ltn_paper_loss_delirium.py` |
| 공리 머리를 사망으로 재타깃 | `delirium/41_retarget_axioms.py` |

---

## 3. 두 축 사이의 끊김 (가장 중요한 한 가지)

```
 [1부]  가이드라인 원문 -> LLM 추출 -> 트리플 -> (사람 검수) -> KG
                                                      :
                                             연결 없음 X
                                                      :
 [2부]  입력 CSV -> BiLSTM -> 술어 -> 코드에 직접 적힌 공리 21개 -> 손실
```

- 패혈증 학습 코드는 KG 파일을 읽지 않는다. 공리를 바꾸려면 **코드를 고쳐야** 한다(그래서 변형 폴더가 8개다).
- 추출한 KG 를 실제로 학습에 넣어 비교한 것은 섬망 쪽뿐이다(`delirium/30`·`33`: KG 6종, 실행 가능 공리 6~16개,
  성능은 모두 기준선 ±0.4 안).
- 패혈증에서 같은 비교를 하려면 **트리플 → 공리 컴파일 경로를 새로 붙여야 한다.**
  연결 명세 형식과 컴파일러 초안은 `NeSy-SMP/tools/grounding/` 에 있다
  (`grounding_compile.py`, 스키마 `NeSy-SMP/configs/grounding_spec_schema.json`, 점검 `docs/kg/KG_GROUNDING_SPEC.md`).

---

## 4. 한계와 주의

1. **확인용 정답은 19개뿐이다.** 1개 = 5.3%p 라 재현율 수치는 거칠다.
2. **판정자도 LLM 이다.** 두 판정자가 완전히 일치했고(κ = 1.00) 이전 판정자와도 24건 중 22건 일치했지만,
   임상 전문가 판정으로 한 번 교차 확인하면 좋다.
3. 조건당 2회 실행이다. 반복 일치도는 그 2회 사이의 값이다.
4. **저작권** — 프롬프트 파일 22개(약 700KB)에 SSC 2021 본문이 그대로 들어가 있고 현재 저장소에 포함돼 있다.
   PADIS 쪽은 같은 이유로 원문·프롬프트·원본 응답을 저장소 밖(`C:/data/padis_fewshot`)에 두었으므로,
   **패혈증 쪽도 같은 기준으로 옮기는 것을 제안한다**(생성 스크립트와 트리플만 저장소에 남긴다).
   외부 공개 전에는 정리가 필요하다.

---

## 5. 이 문서와 함께 보기

| 궁금한 것 | 문서 |
|---|---|
| 예시 개수 비교 상세 | `docs/kg/KG_SHOT_COUNT_SEPSIS.md` |
| 추출 설계와 기준선 | `docs/kg/KG_FEWSHOT_PIPELINE_CHECK.md` |
| 공리 임계값의 출처 | `docs/repro/REPRO_AXIOM_THRESHOLD_SOURCES.md` |
| 공리가 사망 예측까지 닿는가 | `docs/repro/REPRO_GRAD_PATH_SEPSIS.md` |
| 전체 실험 결과 집계 | `docs/repro/REPRO_RESULTS_ALL_2026-10-28.md` |
| 현재 진행 상황과 로드맵 | `docs/meetings/2026-10-28_ROADMAP.html` |
