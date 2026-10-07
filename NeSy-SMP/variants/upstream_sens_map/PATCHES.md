# upstream_sens_map — 논문 §4.5 공리 목록 9개에 맞춘 실행본 (실험 D4)

원본 + 실행 패치(P1~P5) + 기록(P6) + 결측 인식(S1) + **LowMAP 추가(S6)**.

논문 §4.5 는 지식 공리 9개를 적어 두었다 — HighLactate · HighBilirubin · HighCRP · HighWBC ·
LowPlatelets · **LowMAP** · AgeRisk · LactateNotClearing · HasChronicCondition → HighMortality.
공개 코드는 이 중 **LowMAP 만 빠져 있다**: 평균혈압 함수(`mabp`)와 술어(`MeanArterialPressureRisk`)는
정의돼 있는데 어떤 공리에도 쓰이지 않고 옵티마이저 파라미터에도 없다.

| # | 바꾼 것 | 이유 |
|---|---|---|
| S6-a | `map_below_threshold` 를 결측 인식으로 (0 = 측정 없음) | 원본 조건은 `< 65` 를 `.any()` 로 보므로 측정 없는 환자(0 채움)까지 참이 된다. P6 기록에서 활성화율이 **100%** 였다 |
| S6-b | Anchor 공리 추가 — 평균혈압 < 65 → `MeanArterialPressureRisk` | 논문 목록의 LowMAP |
| S6-c | 함축 공리 추가 — `MeanArterialPressureRisk → P` | 같음 |
| S6-d | 옵티마이저에 MAP 술어 파라미터 추가 + P6 이름 `anchor:MAP<65` · `impl:MAP` | 파라미터가 없으면 술어가 학습되지 않는다 |

적용: `tools/patches/apply_patch_s6_map.py <stratified_main.py>` (대상은 `upstream_sensitivity_axiom` 사본)

**S1 을 함께 두는 이유** — 결측 처리를 고치지 않으면 MAP 공리가 환자 100% 에서 켜져 공리가 공허해진다.
그러면 "논문 목록대로 넣었을 때의 효과"가 아니라 "결측 버그"를 다시 재는 실험이 된다.
비교 대상은 같은 S1 기반인 `results_sens_axiom_6h` (NeSy 91.17 / LTN 91.23) 다.

**S3·S4 와의 차이** — `upstream_sensitivity_connect` 는 논문 목록에 **없는** 판정기 5개를 사망과 이었다.
이 실행본은 반대로 **논문 목록에 있는데 코드에 없는** 공리 하나를 되살린다. 이쪽이 "논문 충실" 조건이다.

---

## 아래는 상속한 패치 기록 (upstream_sensitivity_axiom)

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

목적: 0 채우기가 공리 판정을 틀리게 만드는 영향을 분리 (`tools/axiom_zero_fill_audit.py`: GCS 72.7%·수축기혈압 29.1% 잘못 켜짐, 크레아티닌 27.1% 잘못 꺼짐, 혈소판 5.4% 잘못 켜짐).
나머지(젖산·빌리루빈·CRP·백혈구·나이·만성질환·젖산 안 떨어짐)는 0 채우기 영향이 없어 그대로.

---

## 기록 패치 P6 — 학습 동작 불변 (2026-09-17)

| # | 파일 | 바꾼 것 |
|---|---|---|
| P6 | stratified_main.py LTN w/ knowledge(NeSy-SMP) 학습 루프 | formula 값을 `detach()` 로 **읽기만** 해서 epoch 마다 `p6_knowledge_log.jsonl` 에 기록: 학습 batch 평균 data/knowledge satisfaction · 규칙별 activation(코드 판정으로 켜진 환자 비율) · 공리별 satisfaction · 그 epoch 이 val F1 최고인지 |

적용: `tools/apply_patch_p6.py <stratified_main.py>`. `upstream_faithful_log/` = `upstream_faithful/` + P6, `upstream_sensitivity_axiom/` 에도 P6 적용.
원본은 knowledge satisfaction 을 출력하지 않아(`compute_satisfaction_level` 호출이 주석 처리) missing-aware 비교를 위해 추가. 원본은 torch 시드를 고정하지 않으므로 같은 코드 재실행도 AUC 가 조금 달라질 수 있다.
