# EDA 결과 정리 (2026-08-30)

| 문서 | 내용 | 대응 |
|---|---|---|
| **[03_STEP1_DATA_CHECK.md](03_STEP1_DATA_CHECK.md)** | **1단계 데이터 확인 7개 항목 전부** + 분기 규칙 판정 | 페이지 「1단계」 |
| [02_DELIRIUM_COHORT_EDA.md](02_DELIRIUM_COHORT_EDA.md) | Delirium cohort ①~⑦ 구현 + 확인항목 6개 | 랩미팅 §3 |
| [01_COHORT_DEFINITION.md](01_COHORT_DEFINITION.md) | (superseded) 초기 코호트 탐색 · 차팅 커버리지 | — |

## 수행 상태

1단계 **7개 항목 전부 완료** + 「전체 MIMIC 데이터 확인」(31개 테이블 전수 인벤토리) 완료.
분기 규칙은 **UTA 완료(21.9%)**, **eICU는 조건 미판정**(로컬에 eICU 데이터 없음) — 대신 **대체 경로를 미리 계산**했다.
남은 미수행: eICU 데이터 확보, Google Drive 폴더 확인(로그인 필요).
상세는 [03_STEP1_DATA_CHECK.md](03_STEP1_DATA_CHECK.md) 「수행 상태」 표.

## 한 줄 요약 3개

1. **UTA = 21.9%** → 분기 규칙 `15–40%` → **구조적 결측이 논문 핵심, LNN 검토**. 게다가 UTA의 78%가 RASS ≤ −4라 "못 쟀다"가 아니라 임상 상태다.
2. **라벨이 LOS를 재고 있다.** "24h 이후 CAM-ICU Positive ≥1회"는 평가횟수 1회 stay에서 5.1%, 17회+ stay에서 76.3%. 24~72h 고정 구간 라벨로 바꿔야 한다.
3. **2020–2022는 투약 분석에서 빼야 한다.** `inputevents` 보유 stay가 41.5%뿐 (다른 시기 ~95%). 진정제 급감은 진료 변화가 아니라 데이터 결손이다.

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

DB 경로는 각 스크립트 상단 `DB` 상수. 인덱스가 없어 `chartevents` full scan 1회당 약 60–75초.

## 다른 PC에서 처음부터 돌릴 때

위 스크립트들은 이전 단계가 남긴 중간 파일(`_icu_base.pkl`, `_label_values.parquet` 등)을
전제로 한다. 그 파일들은 환자 식별자가 들어 있어 `.gitignore` 로 막혀 있으므로,
저장소만 받은 PC에서는 **먼저 원본에서 중간 파일을 다시 만들어야 한다.**

```bash
python eda/00_extract.py          # 원본 -> 중간 파일 4종 (이 스크립트만 원본 DB를 읽는다)
python eda/09_remaining_eda.py    # 항목 2·4·5·9 + 1·7·8 보강
```

`00_extract.py` 는 파일 상단 `===== 여기만 고치세요 =====` 블록에서 두 줄만 고치면 된다.

```python
SRC_MODE    = "sqlite"                                        # 또는 "csvgz"
SQLITE_PATH = "C:/Users/.../MIMIC4-hosp-icu.db"               # 역슬래시 말고 슬래시
```

- `.db` 를 갖고 있으면 `sqlite` 모드. 필요 패키지는 `pandas`, `pyarrow` 뿐이다.
- physionet `csv.gz` 만 있으면 `csvgz` 모드 (`pip install duckdb` 필요).
  chartevents 등 5개 파일이면 되고 압축 상태로 약 3GB다.
- 구글 드라이브에 마운트한 `.db` 는 잠금을 못 걸어 열리지 않는다
  (`unable to open database file`). 그때는 `SQLITE_IMMUTABLE = True` 로 바꾼다.
