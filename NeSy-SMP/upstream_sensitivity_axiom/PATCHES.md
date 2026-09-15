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
