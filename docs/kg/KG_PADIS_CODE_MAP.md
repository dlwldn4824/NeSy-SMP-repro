# PADIS 지식 · 모델링 코드 안내

작성 2026-11-03 · 이지우 · 저장소 `NeSy-SMP-repro`
범위: PADIS(섬망) 쪽 **공리 추출 코드**와 **모델링 코드**의 구성, 실행 방법, 현재 상태

---

## 1. 전체 구조

코드는 두 축으로 나뉩니다.

**(A) 지식 쪽** — 2018 PADIS 가이드라인 원문에서 규칙을 뽑고, 사람이 검수해 승인한 뒤 지식그래프로 만듭니다.
**(B) 모델 쪽** — MIMIC-IV 에서 섬망 코호트를 만들고, 기준선부터 개념 병목·공리 결합까지 단계적으로 올립니다.

```
(A)  PADIS 원문 ──→ 규칙 추출(86건) ──→ 사람 검수 ──→ 승인 ──→ 지식그래프
                                                              │
                                                     공리로 변환
                                                              ↓
(B)  MIMIC-IV ──→ 섬망 코호트 ──→ 기준선 → XGB → BiLSTM → 개념 병목 → 공리 결합
```

지금은 (A)의 **승인 단계가 사람 검수 대기** 상태입니다. 그래서 학습에 실제로 들어가는 공리는
승인 경로가 아니라 **수기로 작성한 지식그래프와 학습 코드 안의 공리 정의**를 쓰고 있습니다(3절·4절 참고).
추출 결과를 공리로 바꾸는 변환기는 따로 만들어 두었고 단독으로 동작합니다(`delirium/42_kg_to_axioms.py`).

---

## 2. 실행 전제

| 항목 | 값 |
|---|---|
| 파이썬 | `C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe` |
| 작업 위치 | 저장소 루트 (모든 경로는 루트 기준) |
| `EDA_DATA` | `notes/eda` — 추출해 둔 중간 테이블 캐시 |
| `EDA_OUT` | `C:\data\padis_eda_out` — 학습 결과 |
| `MIMIC_DB` | `C:\Users\dlwld\Downloads\MIMIC4-hosp-icu.db` |
| 저장소 밖 | 가이드라인 원문 `C:\data\padis_src\` · 추출 프롬프트와 원본 응답 `C:\data\padis_fewshot\` (저작권) |

---

## 3. 규칙 추출 코드

### 3-1. 본 파이프라인

| 단계 | 스크립트 | 산출물 | 상태 |
|---|---|---|---|
| 1 | `padis/extraction/phase1_full_extraction.py` | `padis/outputs/padis_rules_raw.json` — 규칙 **86건** | 정상 |
| 2 | `padis/review/build_human_review_csv.py` | `padis/outputs/padis_rules_human_review.csv` — **86행** (우선순위 상 24 · 중 34 · 하 28) | 정상 |
| 3 | 사람이 판정 열 작성 | 같은 CSV | **대기 중** |
| 4 | `padis/review/approve_rules.py` | `padis/outputs/padis_rules_approved.json` | 승인 **0건** (3단계 대기) |
| 5 | `padis/kg/build_padis_kg_from_approved.py` | `padis/outputs/padis_kg.json` | 미생성 (4단계 대기) |

4·5단계는 코드 자체에 문제가 없습니다. 임시 입력(`padis_rules_draft_v1.json`, 19건)으로 돌려 보면
지식그래프가 **edge 19개**로 정상 생성됩니다. 막혀 있는 것은 **3단계 사람 검수**뿐입니다.

### 3-2. 예시 개수 비교 (zero-shot · one-shot · few-shot)

같은 원문·같은 정답으로 프롬프트의 **예시 개수만** 바꿔 각 2회씩 추출한 실험입니다.
스크립트는 `NeSy-SMP/tools/rule_extraction/padis_holdout.py` (`build` → `score` → `blind` → `unblind`),
정답 분할은 예시 6 / 확인용 14 입니다.

| 조건 | 확인용 14개 재현 | 근거 지지 | 반복 일치 |
|---|---|---|---|
| zero-shot | 7/14 | 57% | 0.83 |
| one-shot | 10/14 | 38~50% | 0.86 |
| few-shot | 10/14 | 44~47% | 0.82 |

상세는 `docs/kg/KG_SHOT_COUNT_PADIS.md`, 추출된 트리플 전체는 `padis/outputs/llm_triples/llm_triples.csv`(243행)에 있습니다.

### 3-3. 학습에 실제로 쓰는 공리

| 내용 | 위치 |
|---|---|
| 수기 지식그래프 (rdflib, 술어 4종 + 근거등급) | `padis/kg/delirium_kg.py` |
| 공리 정의 (학습 코드 안) | `delirium/29_outcome_mortality.py` — `AX_RISK` 93행, `AX_MED` 111행, `make_axioms()` 120행, `axiom_sat()` 126행 |
| 개념 · 술어 목록 | `NeSy-SMP/configs/padis_concepts.json` · `relation_vocab.json` |
| 공리 실행 명세 · 검수표 | `docs/kg/KG_PADIS_RULE_EXEC_SPEC.csv` · `docs/kg/KG_RULE_REVIEW_PADIS.csv` |
| 트리플 → 공리 변환기 (단독 실행, MIMIC 불필요) | `delirium/42_kg_to_axioms.py` |

---

## 4. 모델링 코드

`delirium/` 폴더의 번호가 곧 실행 순서입니다. 한 줄기 파이프라인이라 중간 번호만 따로 돌리면 입력이 없습니다.

| 구간 | 내용 | 산출물 |
|---|---|---|
| `00` ~ `09` | MIMIC 추출 · 코호트 정의 · 라벨 생성 | `notes/eda/` 캐시 |
| `10` ~ `21` | 창 설계 · 시간 분할 · 분할 명세 · 기준선 | `notes/eda/out_split/` |
| `22` ~ `28` | 2단계 XGBoost, 3·4단계 BiLSTM + 개념 병목 | `notes/eda/out_split/stage2_*.csv` |
| `29` ~ `34` | 예측 대상 교체 · KG 범위별 공리 · 음성 대조군 · 개념 회수 · 도메인 이동 | `C:\data\padis_eda_out\stage29~34\` |
| `35` ~ `42` | 구조 가설 · 제약 투영 · 공리 감사 · gradient 경로 · 논문식 손실 · 공리 재타깃 | `…\stage35~41\` |

집계한 결과표는 저장소 안 `delirium/results/{01_12, 09_13, 14_16, 29_41}/` 에 모아 두었습니다(총 88개 CSV).

### 공리가 모델에 들어가는 지점

`delirium/29_outcome_mortality.py` 한 파일에 모여 있습니다.

| 내용 | 행 |
|---|---|
| 공리 목록 (위험인자 → 섬망 11개) | 93 |
| 섬망 → 사망 공리 | 111 |
| 공리 집합 구성 함수 | 120 |
| 만족도 계산 (함축 Reichenbach · 전칭 pMeanError) | 126 |
| 모델 정의 (BiLSTM + 개념 병목 + 섬망 중간 개념) | 146 |
| 학습 루프 (손실 = 예측 + 개념 + 공리) | 175 |

논문과 같은 형태의 손실(`1 − (0.8·데이터 만족도 + 0.2·지식 만족도)`, LTN 라이브러리 연산)은
`delirium/39_ltn_paper_loss.py` 와 `delirium/40_ltn_paper_loss_delirium.py` 에 별도로 구현해 두었습니다.

---

## 5. 현재 상태 점검 (2026-11-03)

파이썬 파일 **96개 전부 문법 검사 통과**, `delirium/` 스크립트가 읽는 중간 캐시 파일 **전부 존재**를 확인했습니다.
추출 쪽은 실제로 다시 돌려 확인했습니다 — 1단계 추출(86건 재현) · 2단계 검수 CSV 생성(86행) ·
4단계 승인 스크립트 · 5단계 지식그래프 생성(edge 19) · 트리플 → 공리 변환 · 예시 개수 비교 채점.

**막혀 있는 것은 두 가지뿐이고, 둘 다 같은 원인입니다.**

| 항목 | 상태 | 원인과 해결 |
|---|---|---|
| `padis/outputs/padis_rules_approved.json` | 승인 0건 | 86행 검수 CSV 의 판정 열이 비어 있음 → **사람 검수가 필요** |
| `padis/outputs/padis_kg.json` | 미생성 | 위 승인 결과가 입력이라 아직 실행하지 않음 (코드는 정상 동작 확인) |

모델링 쪽 `00` ~ `41` 전체 재실행은 하지 않았습니다. DB 스캔과 GPU 학습으로 수십 시간이 걸리고,
단계별 결과 파일이 모두 남아 있어 실행 이력은 확인됩니다.

---

## 6. 처음 보실 때 권하는 순서

1. `delirium/README.md` — 폴더 구성과 스크립트 사이 의존 관계
2. `delirium/29_outcome_mortality.py` 93~175행 — 공리 정의부터 학습 루프까지 한 화면
3. `docs/delirium/DELIRIUM_MODELING_ONEPAGER.md` — 모델 사다리와 평가 프로토콜
4. `docs/kg/KG_SHOT_COUNT_PADIS.md` — 예시 개수 비교 결과

---

## 부록. 실행 명령

### 규칙 추출

```bash
python padis/extraction/phase1_full_extraction.py --pdf C:/data/padis_src/padis2018.pdf \
    --out-dir padis/outputs --gold-size 15
python padis/review/build_human_review_csv.py
python padis/review/approve_rules.py --review-csv padis/outputs/padis_rules_human_review.csv
python padis/kg/build_padis_kg_from_approved.py --approved-json padis/outputs/padis_rules_approved.json
python delirium/42_kg_to_axioms.py <triples.json> [...] -o axioms.json
python NeSy-SMP/tools/rule_extraction/padis_holdout.py score
```

### 모델링

```bash
export EDA_DATA=notes/eda
export EDA_OUT=C:/data/padis_eda_out
export MIMIC_DB=C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db
export PYTHONIOENCODING=utf-8

python delirium/23_stage34_bilstm_cbm.py
python delirium/29_outcome_mortality.py --seeds 42,7,2024 --epochs 10
python delirium/30_kg_variants.py  --seeds 42,7,2024
python delirium/31_axiom_control.py --seeds 42,7,2024
python delirium/35_structural_bottleneck.py --seeds 42,7,2024 --epochs 12
ANTECEDENT=pred python delirium/39_ltn_paper_loss.py --seeds 42,7,2024 --epochs 10
ANTECEDENT=pred python delirium/40_ltn_paper_loss_delirium.py --seeds 42,7,2024 --epochs 10
python delirium/41_retarget_axioms.py --seeds 42,7,2024 --epochs 10
```

공통 인자는 `--seeds`(기본 `42,7,2024`)와 `--epochs`(기본 10)입니다.
`29` 는 `23` 의 앞부분을, `30`~`41` 은 `29` 의 앞부분을 그대로 실행하므로 **파일을 다른 폴더로 옮기면 깨집니다.**

### 결과 위치

| 스크립트 | 결과 |
|---|---|
| `22_stage2_xgb.py` | `notes/eda/out_split/stage2_xgb.csv` · `stage2_ablation.csv` |
| `29` ~ `41` | `C:\data\padis_eda_out\stage29` ~ `stage41` (`39`·`40` 은 `ANTECEDENT=data` 일 때 `_data` 접미사) |
| `32_recover_concepts.py` | `notes/eda/_axiom_padis2_events.parquet` |
| `42_kg_to_axioms.py` | 표준출력으로 공리 코드 (파일로 받으려면 `-o`) |
| 집계본 | `delirium/results/29_41/` 등 |
