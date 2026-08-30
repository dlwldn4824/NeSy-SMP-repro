# EDA 결과 정리 (2026-08-30)

| 문서 | 내용 | 대응 |
|---|---|---|
| **[03_STEP1_DATA_CHECK.md](03_STEP1_DATA_CHECK.md)** | **1단계 데이터 확인 7개 항목 전부** + 분기 규칙 판정 | 페이지 「1단계」 |
| [02_DELIRIUM_COHORT_EDA.md](02_DELIRIUM_COHORT_EDA.md) | Delirium cohort ①~⑦ 구현 + 확인항목 6개 | 랩미팅 §3 |
| [01_COHORT_DEFINITION.md](01_COHORT_DEFINITION.md) | (superseded) 초기 코호트 탐색 · 차팅 커버리지 | — |

## 한 줄 요약 3개

1. **UTA = 21.9%** → 분기 규칙 `15–40%` → **구조적 결측이 논문 핵심, LNN 검토**. 게다가 UTA의 78%가 RASS ≤ −4라 "못 쟀다"가 아니라 임상 상태다.
2. **라벨이 LOS를 재고 있다.** "24h 이후 CAM-ICU Positive ≥1회"는 평가횟수 1회 stay에서 5.1%, 17회+ stay에서 76.3%. 24~72h 고정 구간 라벨로 바꿔야 한다.
3. **2020–2022는 투약 분석에서 빼야 한다.** `inputevents` 보유 stay가 41.5%뿐 (다른 시기 ~95%). 진정제 급감은 진료 변화가 아니라 데이터 결손이다.

## 데이터 정책

이 폴더에는 **집계 결과만** 있다. `subject_id` / `hadm_id` / `stay_id` 가 들어간 파일
(코호트 stay 목록, stay별 라벨, 중간 pkl/parquet)은 MIMIC DUA상 공개 저장소에 올릴 수 없어
`.gitignore` 로 막아두었다. 필요하면 아래 스크립트를 각자 로컬에서 돌려 재생성한다.

## 재현

```bash
python notes/eda/cohort_define.py        # 코호트 후보 + 기본 통계
python notes/eda/scan_padis_labels.py    # chartevents 스캔 (PADIS 항목 커버리지)
python notes/eda/scan_label_values.py    # chartevents 스캔 (섬망/RASS 값)
python notes/eda/02_delirium_cohort.py   # ①~⑦ 코호트
python notes/eda/03_cohort_checks.py     # 확인항목 EDA
python notes/eda/04_label_timing.py      # 라벨 교란 · 발생시점
python notes/eda/05_scan_step1.py        # chartevents/inputevents 스캔 (항목 5,6,7)
python notes/eda/06_step1_report.py      # 1단계 항목 1~4
python notes/eda/07_step1_567.py         # 1단계 항목 5~7
```

스크립트는 `학연생/` 를 작업 디렉터리로 가정하고 `notes/eda/` 에 출력한다 (저장소 안에서 돌리려면 스크립트 상단 `OUT` 경로 수정). DB 경로는 각 스크립트 상단 `DB` 상수. 인덱스가 없어 `chartevents` full scan 1회당 약 60–75초.
