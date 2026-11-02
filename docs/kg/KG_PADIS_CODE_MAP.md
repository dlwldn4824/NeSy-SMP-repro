# PADIS — 공리 추출 · 모델링 코드 위치와 실행 방법

작성 2026-11-03 · 저장소 `NeSy-SMP-repro` · 모든 경로는 저장소 루트 기준
실행 파이썬: `C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe`

---

## 0. 먼저 설정하는 것

| 변수 | 뜻 | 값 |
|---|---|---|
| `EDA_DATA` | 중간 테이블 캐시 (입력) | `notes/eda` |
| `EDA_OUT` | 결과 저장 폴더 | `C:\data\padis_eda_out` |
| `MIMIC_DB` | MIMIC-IV SQLite | `C:\Users\dlwld\Downloads\MIMIC4-hosp-icu.db` |
| `PYTHONIOENCODING` | 한글 출력 | `utf-8` |

```bash
cd <저장소 루트>
export EDA_DATA=notes/eda
export EDA_OUT=C:/data/padis_eda_out
export MIMIC_DB=C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db
export PYTHONIOENCODING=utf-8
```

저장소 밖에 두는 것 (저작권): PADIS 원문 `C:\data\padis_src\` · 프롬프트·원본 응답·판정 `C:\data\padis_fewshot\`

---

## 1. 공리(규칙) 추출

### 1-1. 1차 추출 → 사람 검수 → 승인 → KG

| 순서 | 파일 | 실행 | 출력 |
|---|---|---|---|
| 1 | `padis/extraction/phase1_full_extraction.py` | `python padis/extraction/phase1_full_extraction.py --pdf <PADIS.pdf> --out-dir padis/outputs --gold-size 15` | `padis/outputs/padis_rules_raw.json` (86개) · `gold_set_draft.json` (15) · `PHASE1_PADIS_REPORT.md` |
| 2 | `padis/review/build_human_review_csv.py` | `python padis/review/build_human_review_csv.py` (기본 경로 사용) | `padis/outputs/padis_rules_human_review.csv` (86행) |
| 3 | 사람이 CSV 의 판정 열을 채움 | — | 같은 CSV |
| 4 | `padis/review/approve_rules.py` | `python padis/review/approve_rules.py --review-csv padis/outputs/padis_rules_human_review.csv` | `padis/outputs/padis_rules_approved.json` |
| 5 | `padis/kg/build_padis_kg_from_approved.py` | `python padis/kg/build_padis_kg_from_approved.py --approved-json padis/outputs/padis_rules_approved.json` | `padis/outputs/padis_kg.json` |

현재 상태: 4번 출력 `padis_rules_approved.json` 의 `approved_rules` 가 **0건**(검수 미완).
학습에 실제로 쓰는 공리는 이 경로가 아니라 1-3 의 수기 KG 와 `delirium/29_outcome_mortality.py` 안의 정의다.

### 1-2. 예시 개수 비교 (zero-shot · one-shot · few-shot)

| 항목 | 위치 |
|---|---|
| 스크립트 | `NeSy-SMP/tools/rule_extraction/padis_holdout.py` |
| 분할 | `NeSy-SMP/tools/rule_extraction/splits/padis_holdout_split.json` (예시 6 / 확인용 14) |
| 프롬프트 템플릿 | `NeSy-SMP/tools/rule_extraction/prompts/fewshot_padis.txt` |
| 프롬프트(조각 8개) · 원본 응답 · 판정 | `C:\data\padis_fewshot\` (저장소 밖) |
| 추출 트리플만 (저장소) | `padis/outputs/llm_triples/llm_triples.csv` (243행: mode · run · chunk · s · p · o) |
| 결과 문서 | `docs/kg/KG_SHOT_COUNT_PADIS.md` · 겹침 `docs/kg/KG_SHOT_OVERLAP_AND_AXIOMS.md` · 부록 `KG_SHOT_OVERLAP_APPENDIX.md` |

```bash
python NeSy-SMP/tools/rule_extraction/padis_holdout.py build     # 분할 + 프롬프트 생성
python NeSy-SMP/tools/rule_extraction/padis_holdout.py score     # 정답 대조
python NeSy-SMP/tools/rule_extraction/padis_holdout.py blind --judges 2   # 판정용 섞기
python NeSy-SMP/tools/rule_extraction/padis_holdout.py unblind   # 판정 결과 복원
```

추출 자체는 조각마다 대화 기록 없는 새 에이전트가 프롬프트 파일 하나만 읽고 결과 JSON 만 쓴다.

### 1-3. 학습에 실제로 들어가는 KG · 공리

| 내용 | 위치 |
|---|---|
| 수기 KG (rdflib, 술어 4종 + 근거등급) | `padis/kg/delirium_kg.py` |
| 개념·술어 목록 | `NeSy-SMP/configs/padis_concepts.json` · `relation_vocab.json` |
| 공리 정의 (학습 코드 안) | `delirium/29_outcome_mortality.py` — `AX_RISK` **93행** · `AX_MED` 111행 · `AX_DIRECT` 114행 · `make_axioms()` 120행 · `axiom_sat()` 126행 |
| 공리 실행 명세 | `docs/kg/KG_PADIS_RULE_EXEC_SPEC.csv` (21행) · 검수표 `docs/kg/KG_RULE_REVIEW_PADIS.csv` (25행) |
| KG 범위별 공리 컴파일 | `delirium/30_kg_variants.py` · `delirium/33_kg_variants_v2.py` |

---

## 2. 모델링

### 2-1. 실행 순서

번호가 실행 순서다. 중간 번호만 따로 돌리면 입력이 없다.

| 번호 | 단계 | 비고 |
|---|---|---|
| `00` ~ `09` | MIMIC 추출 · 코호트 정의 · 라벨 생성 | `MIMIC_DB` 필요, 출력은 `EDA_DATA` 캐시 |
| `10` ~ `21` | 창 설계 · 시간 분할 · 분할 명세 | |
| `22` ~ `28` | 2단계 XGB · 3·4단계 BiLSTM + 개념 병목 | 모델 본체 |
| `29` ~ `34` | 예측 대상 교체 · KG 범위 · 음성 대조군 · 개념 회수 · 도메인 이동 | |
| `35` ~ `41` | 구조 가설 · 제약 투영 · 공리 감사 · gradient · 논문식 손실 · 재타깃 | 공리 진단 |

의존: `29` 는 `23` 의 앞부분을 `exec` 하고, `30`~`41` 은 `29` 의 앞부분을 `exec` 한다.
**같은 폴더 기준 상대 참조라 파일을 옮기면 깨진다.**

### 2-2. 스크립트별 실행 명령과 결과 위치

| 파일 | 명령 | 결과 |
|---|---|---|
| `delirium/23_stage34_bilstm_cbm.py` | `python delirium/23_stage34_bilstm_cbm.py` | `$EDA_OUT/out_split/` |
| `delirium/22_stage2_xgb.py` | `python delirium/22_stage2_xgb.py` | `$EDA_OUT/out_split/stage2_xgb.csv` · `stage2_ablation.csv` |
| `delirium/29_outcome_mortality.py` | `python delirium/29_outcome_mortality.py --seeds 42,7,2024 --epochs 10` | `$EDA_OUT/stage29/` |
| `delirium/30_kg_variants.py` | `python delirium/30_kg_variants.py --seeds 42,7,2024` | `$EDA_OUT/stage30/` |
| `delirium/31_axiom_control.py` | `python delirium/31_axiom_control.py --seeds 42,7,2024` | `$EDA_OUT/stage31/` |
| `delirium/32_recover_concepts.py` | `python delirium/32_recover_concepts.py` | `$EDA_DATA/_axiom_padis2_events.parquet` |
| `delirium/33_kg_variants_v2.py` | `python delirium/33_kg_variants_v2.py --seeds 42,7,2024` | `$EDA_OUT/stage33/` |
| `delirium/34_domain_shift.py` | `python delirium/34_domain_shift.py --seeds 42,7,2024` | `$EDA_OUT/stage34/` |
| `delirium/35_structural_bottleneck.py` | `python delirium/35_structural_bottleneck.py --seeds 42,7,2024 --epochs 12` | `$EDA_OUT/stage35/structural.csv` |
| `delirium/36_constraint_projection.py` | `python delirium/36_constraint_projection.py --seeds 42,7,2024` | `$EDA_OUT/stage36/` |
| `delirium/37_axiom_audit.py` | `python delirium/37_axiom_audit.py` | `$EDA_OUT/stage37/` |
| `delirium/38_grad_path_check.py` | `python delirium/38_grad_path_check.py` | `$EDA_OUT/stage38/` |
| `delirium/39_ltn_paper_loss.py` | `ANTECEDENT=pred python delirium/39_ltn_paper_loss.py --seeds 42,7,2024 --epochs 10` | `$EDA_OUT/stage39/` (`ANTECEDENT=data` → `stage39_data/`) |
| `delirium/40_ltn_paper_loss_delirium.py` | `ANTECEDENT=pred python delirium/40_ltn_paper_loss_delirium.py --seeds 42,7,2024 --epochs 10` | `$EDA_OUT/stage40/` (`data` → `stage40_data/`) |
| `delirium/41_retarget_axioms.py` | `python delirium/41_retarget_axioms.py --seeds 42,7,2024 --epochs 10` | `$EDA_OUT/stage41/` |

공통 인자: `--seeds` (기본 `42,7,2024`) · `--epochs` (기본 10) · `--tag` (29 만, 기본 `stage29`)

### 2-3. 일괄 실행

| 파일 | 내용 |
|---|---|
| `scripts/queues/queue_research_*.ps1` | 순서·대기 조건이 들어간 실행 큐 (UTF-8 BOM 으로 저장해야 함) |
| 예약 등록 | Windows 작업 스케줄러 `NeSyResearchQueue*` |

### 2-4. 모델 안에서 공리가 쓰이는 지점

`delirium/29_outcome_mortality.py`

| 내용 | 행 |
|---|---|
| 공리 목록 `AX_RISK` (위험인자 → 섬망 11개) | 93 |
| `AX_MED` (섬망 → 사망) | 111 |
| `AX_DIRECT` (직접 사망 공리, 기본 비활성) | 114 |
| `make_axioms(use_med, use_direct)` | 120 |
| `axiom_sat()` — 함축 Reichenbach · 전칭 pMeanError | 126 |
| `Net2` (BiLSTM + 개념 병목 + 섬망 중간 개념) | 146 |
| `run()` — 학습 루프, 손실 = BCE + 개념 + 공리 | 175 |

논문식 손실(`1 − (w_D·SatAgg(D) + w_K·SatAgg(K))`, LTN 라이브러리 연산)은 `delirium/39`·`40` 에 따로 있다.

---

## 3. 데이터 위치

| 내용 | 경로 |
|---|---|
| MIMIC-IV SQLite | `C:\Users\dlwld\Downloads\MIMIC4-hosp-icu.db` |
| 중간 테이블 캐시 (`_icu_base.pkl`, `_label_values.parquet` 등) | `notes/eda/` |
| 학습 결과 | `C:\data\padis_eda_out\stage*` |
| PADIS 원문 | `C:\data\padis_src\` (저장소 밖) |
| shot 실험 프롬프트·원본 응답·판정 | `C:\data\padis_fewshot\` (저장소 밖) |

---

## 4. 관련 문서

| 내용 | 파일 |
|---|---|
| 모델 사다리 · 평가 프로토콜 | `docs/delirium/DELIRIUM_MODELING_ONEPAGER.md` |
| 분할 명세 | `docs/delirium/DELIRIUM_SPLIT_SPEC.md` |
| 공리 설계 | `docs/delirium/DELIRIUM_LNN_DESIGN.md` |
| 음성 대조군 · 개념 회수 · 도메인 이동 | `docs/delirium/DELIRIUM_AXIOM_CONTROL_2026-10-04.md` |
| 예측 대상 교체 · KG 범위 | `docs/delirium/DELIRIUM_OUTCOME_SWITCH_2026-10-03.md` |
| 예시 개수 비교 | `docs/kg/KG_SHOT_COUNT_PADIS.md` |
| 규칙 검수 | `docs/kg/KG_RULE_REVIEW_PADIS.md` |
| 폴더 설명 | `delirium/README.md` · `padis/README.md` |
