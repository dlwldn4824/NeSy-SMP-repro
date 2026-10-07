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

## 민감도 실험 A — 논문 조건 아님

| # | 파일 | 바꾼 것 |
|---|---|---|
| S1 | stratified_main.py 공리 조건 5개 (GCS<8 · 수축기혈압≤100 · 크레아티닌≥1.5(모든 시점) · 혈소판<50(모든 시점) · 호흡수 이상(모든 시점)) | 값 0(시퀀스 뒤 패딩)과 원래 값 0 의 변환값(첫 측정 전 빈칸 — 최솟값이 음수인 변수는 0 이 아님)을 '측정 없음'으로 보고 조건 판정에서 뺀다. '모든 시점' 조건은 측정이 1개 이상 있어야 참 |

목적: 0 채우기가 공리 판정을 틀리게 만드는 영향을 분리 (`tools/audit/axiom_zero_fill_audit.py`: GCS 72.7%·수축기혈압 29.1% 잘못 켜짐, 크레아티닌 27.1% 잘못 꺼짐, 혈소판 5.4% 잘못 켜짐).
나머지(젖산·빌리루빈·CRP·백혈구·나이·만성질환·젖산 안 떨어짐)는 0 채우기 영향이 없어 그대로.

---

## 기록 패치 P6 — 학습 동작 불변 (2026-09-17)

| # | 파일 | 바꾼 것 |
|---|---|---|
| P6 | stratified_main.py LTN w/ knowledge(NeSy-SMP) 학습 루프 | formula 값을 `detach()` 로 **읽기만** 해서 epoch 마다 `p6_knowledge_log.jsonl` 에 기록: 학습 batch 평균 data/knowledge satisfaction · 규칙별 activation(코드 판정으로 켜진 환자 비율) · 공리별 satisfaction · 그 epoch 이 val F1 최고인지 |

적용: `tools/patches/apply_patch_p6.py <stratified_main.py>`. `variants/upstream_faithful_log/` = `variants/upstream_faithful/` + P6, `variants/upstream_sensitivity_axiom/` 에도 P6 적용.
원본은 knowledge satisfaction 을 출력하지 않아(`compute_satisfaction_level` 호출이 주석 처리) missing-aware 비교를 위해 추가. 원본은 torch 시드를 고정하지 않으므로 같은 코드 재실행도 AUC 가 조금 달라질 수 있다.

---

## 민감도 실험 C — 빠진 사망 연결 추가 (논문 조건 아님)

| # | 파일 | 원래 | 바꾼 것 | 이유 |
|---|---|---|---|---|
| S4 | stratified_main.py:559 | `x[glucose_above_threshold==1]` — **함수 객체와 1 을 비교**해 변수가 항상 빈 집합 | `x[glucose_above_threshold(x)==1]` | 혈당 공리가 아예 적용되지 않던 버그. 고치면 앵커가 처음으로 켜진다(해당 입원 약 80%) |
| S3 | stratified_main.py:647-651 | 함축(`Implies(XxxRisk, P)`) 공리가 8개 — Lactate·Bilirubin·Platelet·LactateNotClearing·CRP·Chronic·WBC·Age | GCS · 수축기혈압 · 호흡수 · 크레아티닌 · 혈당 함축 **5개 추가** (P6 기록 이름 목록도 5개 확장) | 이 5개는 앵커만 있어 **사망 예측 P 에 기울기가 0** 이었다(`eda/38_grad_path_check.py` 동일 구조에서 ∂sat/∂사망로짓 = 0). 결측 0 채우기로 잘못 켜지던 규칙이 모두 여기 속해, 민감도 A(S1)의 효과가 0 이었던 원인으로 본다 |

목적: **"연결을 제대로 하면 지식 효과(NeSy-SMP − LTN)가 생기는가"** 를 6h 한 시점에서 확인한다.
주의: 새 함축 중 '수축기혈압 ≤ 100 → 사망'(해당 71%) · '혈당 > 100 → 사망'(해당 80%)은 데이터와 충돌해 성능을 끌어내릴 수 있다. 떨어지면 그대로 보고한다.
