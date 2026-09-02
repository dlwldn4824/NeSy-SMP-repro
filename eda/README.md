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

## ⚠️ 숫자 혼동 주의 — 유병률이 문서마다 다르다

세 숫자가 돌아다니는데 **전부 맞고, 전부 다른 것을 센다.** 인용할 때 반드시 정의를 같이 쓸 것.

| 값 | 정의 | 분모 | 어디 |
|---|---|---|---|
| **48.4%** | 재원 **전 기간** 중 Positive ≥1 | C2 (MICU+MICU/SICU, 2014–2019) 판정가능 7,347 | `01_COHORT_DEFINITION.md` (superseded) |
| **22.5%** | **24h 이후 퇴실까지** Positive ≥1 | 스펙 ①~⑦ 코호트 23,939 | `02_DELIRIUM_COHORT_EDA.md` |
| **15.6%** | **24–72h 고정 창**에서 Positive ≥1 | ⑤통과 중 창 내 판정≥1인 22,867 | `results_14_16/` (14·16) |
| *25.6%* | 24–72h 창, **⑤ 미적용**(첫 24h P 포함) | base3 중 창 내 판정≥1인 29,500 | `chk16_ab_compare.csv` |

**왜 다른가:** 관찰 기간이 길수록 Positive를 만날 기회가 많다. 48.4%가 제일 큰 건 섬망이 많아서가 아니라 **재원 전체를 봤기 때문**이다. 15.6%가 제일 정직한 숫자다 — 모든 환자에게 동일한 48시간 창을 준다.

**현재 권장은 15.6%(24–72h, ⑤ 적용)** 이지만 ⑤ 적용 여부는 미결이다 (§14·16 결과 참조).

## ⚠️ 커버리지 숫자를 인용할 때

`03_STEP1_DATA_CHECK.md`의 커버리지는 전부 **전체 재원 중 1회라도** 기준이라 **상한값**이다.
예측 입력 가용성은 **첫 24h** 기준이 맞고, 두 값은 같은 문서의 「항목별 첫 24h 대조」 표에 나란히 있다.
예: RASS 89.9%(전체 재원) / 83.7%(첫 24h).

단 **항목 6·7은 재원 전체가 맞다** — 진료 패턴 질문이라 첫 24h로 자르면 질문이 바뀐다.

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

두 명령은 경로 기준이 어긋나지 않도록 **저장소 루트(`NeSy-SMP-repro`)에서 순서대로** 실행한다.
`00_extract.py`와 `09_remaining_eda.py`는 기본적으로 중간 파일과 결과를 `notes/eda/`에 저장하고 읽는다.

필수 패키지:

```bash
pip install pandas pyarrow
# csv.gz 모드만 추가
pip install duckdb
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
- `00_extract.py`가 정상 종료되어 `_icu_base.parquet`, `_label_values.parquet`,
  `_padis_item_stay_counts.parquet`, `_step1_sed.parquet`가 생성된 것을 확인한 다음 `09`를 실행한다.
- 중간 파일에는 `subject_id`, `hadm_id`, `stay_id`가 포함되므로 **GitHub에 커밋하지 않는다.**
  저장소에는 `chk*.csv` 형태의 집계 결과만 올린다.
- 원본 데이터가 있는 PC에서의 전체 실행 검증이 필요하다. 실행 중 P/N/UTA 미매핑 값 경고가 나오면
  그대로 무시하지 말고 출력된 실제 값을 확인한 뒤 매핑 규칙을 보완한다.
