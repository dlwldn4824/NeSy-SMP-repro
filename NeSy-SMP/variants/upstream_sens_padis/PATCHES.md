# upstream_sens_padis — 원본 + 실행 패치(P1~P5) + 기록(P6) + **PADIS 임상 변수 주입(S2)**

이 실행본은 "안 2"(PADIS 변수 주입) 실험용이다. 공리는 **원본 그대로**이고,
입력 변수에 PADIS 쪽 임상 변수 5개(RASS · Pain NRS · Mobility level · Restraint · Sedative)를 더한다.
S1(결측 인식) 은 **들어 있지 않다** — 변수 추가만의 효과를 보기 위한 설정이다.

| # | 파일 | 바꾼 것 | 이유 |
|---|---|---|---|
| S2 | data/preprocessing.py (피처 목록 2곳) | 하드코딩된 변수 목록에 `RASS` · `Pain NRS` · `Mobility level` · `Restraint` · `Sedative` 추가 (`# [PATCH S2]`) | 논문 공리를 그대로 두고 **입력 변수만** 늘렸을 때 성능이 어디서 오는지 분리한다. 변수 추출은 `NeSy-SMP/data/add_padis_vars.py` |

입력 CSV: `paper_leads/events_{6,12,24,48}h_wide_paper_como_padis.csv`
결과: `results_sens_padisvars_{6,12,24}h` (48h 는 큐 7 에서 실행) · 6h·12h·24h 에서 모든 모델 +0.7~1.1,
NeSy−LTN 은 +0.12 / +0.10 → **향상은 공리가 아니라 추가 변수에서 온다.**

---

## 아래는 공통 실행 패치 (upstream_faithful 과 동일)

# upstream_faithful — 원본 코드 + 실행에 꼭 필요한 패치만

원본: FabrizioDeSantis/NeSy-SMP (`UPSTREAM_COMMIT.txt`). 아래 5개 외에는 한 글자도 바꾸지 않았다.

| # | 파일 | 원래 | 바꾼 것 | 이유 |
|---|---|---|---|---|
| P1 | stratified_main.py | 입력 경로 `data/subset/events_48h_before_death_gcs.csv` 하드코딩 | 환경변수 `NESY_DATA` (기본값은 원래 경로) · import 경로 추가 | lead time 별 CSV 를 지정해 돌리기 위해 |
| P2 | stratified_main.py | 평균±표준편차만 `stratified_results.txt` 에 씀 | fold 별 지표를 `fold_metrics.json` 에도 씀 | fold 짝 비교용. 계산은 그대로 |
| P3 | data/preprocessing.py | `get_loc("Administration of vasopressor")` 출력 | 그 범주가 있을 때만 출력 | 논문 §5.1 변수 목록에 약물이 없다 → 범주가 없으면 KeyError 로 멈춤. 출력문일 뿐 계산 무관 |
| P5 | stratified_main.py (RF/XGB 피처 3곳) | `features = [mean(lst)...]` 다음 줄에서 `std(lst) for lst in features` — 이미 평균(float)으로 바뀐 리스트로 표준편차 계산 | 표준편차를 먼저 원래 값 리스트로 계산한 뒤 평균 | **공개 코드 그대로는 Fold 1 에서 `TypeError: 'float' object is not iterable` 로 멈춘다.** 의도(변수별 0 제외 평균·표준편차)는 명확해 순서만 바꿈 |
| P4 | model/models.py | `MLP.fc1 = Linear(254)` (주석에 lead 별 289/261/275) | `Linear(input_size + 23 + 1)` | 원저자가 lead 마다 손으로 바꾸던 값(시퀀스 길이 + 동반질환 23 + 나이 1)을 계산으로 |

실행: 결과 폴더를 cwd 로 두고 `NESY_DATA=<csv> python <이 폴더>/stratified_main.py` (기본 epoch 50/20).

---

## 기록 패치 P6 — 학습 동작 불변 (2026-09-17)

| # | 파일 | 바꾼 것 |
|---|---|---|
| P6 | stratified_main.py LTN w/ knowledge(NeSy-SMP) 학습 루프 | formula 값을 `detach()` 로 **읽기만** 해서 epoch 마다 `p6_knowledge_log.jsonl` 에 기록: 학습 batch 평균 data/knowledge satisfaction · 규칙별 activation(코드 판정으로 켜진 환자 비율) · 공리별 satisfaction · 그 epoch 이 val F1 최고인지 |

적용: `tools/apply_patch_p6.py <stratified_main.py>`. `upstream_faithful_log/` = `upstream_faithful/` + P6, `upstream_sensitivity_axiom/` 에도 P6 적용.
원본은 knowledge satisfaction 을 출력하지 않아(`compute_satisfaction_level` 호출이 주석 처리) missing-aware 비교를 위해 추가. 원본은 torch 시드를 고정하지 않으므로 같은 코드 재실행도 AUC 가 조금 달라질 수 있다.
