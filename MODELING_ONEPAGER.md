# 모델링 미팅 1페이지 (섬망 예측 / 평가 단위 split)

저장소: https://github.com/dlwldn4824/NeSy-SMP-repro
상세: `eda/SPLIT_SPEC.md`(설계·표본) · `eda/SPLIT_DESIGN.md`(근거) · `eda/LNN_DESIGN.md`(논리층)
재현 스크립트: `eda/20_baseline_carryforward.py`

---

## 30초 오프닝

> 예측 단위를 stay → **CAM 평가 시점**으로 바꿨습니다. instance 29,500 → **345,505**.
> 그리고 **무학습 baseline 을 먼저 쟀습니다.** 변수 2개짜리 룩업표가 **전체 AUROC 84.9** 를 냅니다.
> **전체 AUROC 는 헤드라인으로 못 씁니다.** 계층을 섞어서 나온 수입니다.
> 진짜 여백은 **앵커=N(신규 발생) 계층 하나**에 있고, 거기 baseline 은 **AUROC 63.7 / AUPRC 23.0** 입니다.

---

## 1) 넘어야 할 선 — 무학습 baseline (환자 단위 70/30, test 103,306 instance)

| 계층 | n | Positive% | B0 F1(bin) | B0 F1(macro) | **B2 AUROC** | **B2 AUPRC** |
|---|---:|---:|---:|---:|---:|---:|
| **전체** | 103,306 | 31.0 | 61.8 | 73.9 | **84.9** | 71.6 |
| **앵커=N** (신규 발생) | 68,961 | 12.0 | 35.5 | 64.1 | **63.7** | **23.0** |
| 앵커=P (지속/회복) | 21,692 | 78.1 | 76.3 | 58.9 | 62.3 | 83.0 |
| 앵커=U (관측 불가) | 12,653 | 53.3 | 54.2 | 61.4 | 64.1 | 65.5 |

- **B0** = 직전 확정 상태를 그대로 이월 (prev==P → 1). 학습 없음.
- **B2** = `직전 확정상태 × 현재 앵커` 6칸 룩업표. train 에서 칸별 Positive 율만 추정. 학습 없음.

B2 룩업표 (train, Positive%):

| 직전 \ 앵커 | N | P | U |
|---|---:|---:|---:|
| N | 9.0 | 64.8 | 45.7 |
| P | 43.4 | 85.4 | 78.1 |
| 없음 | 10.8 | 69.8 | 42.3 |

### 🔴 여기서 나오는 결론 하나

**전체 AUROC 84.9 는 "예측을 잘해서"가 아니라 계층의 기저율이 12% / 78% / 53% 로 갈라져 있어서 나온다.**
계층 안으로 들어가면 같은 룩업표가 62~64 로 주저앉는다. 전체 지표만 보고하면 모델이 무엇을 더했는지 알 수 없다.

> 이건 우리가 이미 한 번 겪은 함정과 같은 종류다 — `MEETING_ONEPAGER.md` §2 의 Table 1(macro) vs Table 2(binary). 집계 방식이 헤드라인을 만든다. **이번엔 미리 못 박고 시작한다.**

---

## 2) 모델 사다리 — 무엇을 순서대로 돌리나

| # | 모델 | 무엇을 확인하나 | 새로 만들 것 | 재사용 |
|---|---|---|---|---|
| **B0–B2** | 무학습 룩업 | 바닥 | ✅ 완료 | `eda/20_` |
| **M1** | XGBoost (평탄 피처) | 시계열 없이 어디까지 | 피처 빌더 | `reproduce_tables.py` XGB 블록 |
| **M2** | BiLSTM | 시계열이 값을 더하나 | Dataset 클래스 | `model/models.py` `LSTMModel` (양방향·attention 구현됨) |
| **M3** | CBM (개념층) | 개념 병목의 비용 | 헤드 3개 | M2 backbone |
| **M4** | LTN (+PADIS 공리) | 논리층이 CBM 대비 뭘 더하나 | 공리 로딩 | `pipeline/load_axioms_into_ltn.py`, `stratified_main.py` 553–633 |
| **M5** | LNN (구간 진리값) | 구간 표현이 실제로 필요한가 | 전부 | 없음 (공개 구현 빈약) |

### 입력 / 출력 (확정, `SPLIT_SPEC.md` §3)

```
X  [시계열] 앵커 이전 24h — RASS(커버 100%, median 5회) · 진정제 3계열
             · mobility · pain · GCS · 활력징후            ⚠️ 뒤 3개는 §4 블로커
   [누적]   입실~앵커 경과시간 · n_assess · uta_frac · 직전 확정상태 · 누적 benzo
   [정적]   age · gender · careunit · era · ED 경유

y  앵커 이후 24h 안에 확정 CAM Positive ≥ 1
   보조출력  DeepSedation(RASS≤−4, 기저 18.0%) · Assessable(기저 71.0%)
```

`Assessable` 을 보조 출력으로 두면 **라벨 못 붙인 28.3% 가 버려지지 않는다** — 그 instance 가 `Assessable=0` 의 양성 예시가 된다.

### 🔴 기존 코드에서 반드시 고쳐야 하는 곳

| 위치 | 지금 | 바꿀 것 |
|---|---|---|
| `reproduce_tables.py` **336–339** | `StratifiedKFold` 를 **기록 단위**로, key=`hadm_id` | `StratifiedGroupKFold(groups=subject_id)` — 안 고치면 환자의 88.3% 가 train/test 양쪽에 걸린다 |
| `model/models.py` **46** | `nn.Linear(23, h)` (동반질환 23 고정) | 정적+누적 블록 차원으로 |
| `stratified_main.py` **539–540** | `w_D/w_K = 0.8/0.2` 하드코딩 | GRADE 기반 (`padis_rules_draft_v1.json` 에 등급 있음) |

---

## 3) 평가 프로토콜 — 미리 못 박는다

```
주 지표     앵커=N 계층의 AUPRC   (기저 12.0%, baseline 23.0)
필수 동반   같은 계층 AUROC + 전체·계층별 전부 + B2 대비 델타
분할        환자 단위 70/15/15, (Positive 경험 × instance 수) 층화
외부검증    2011-2016 학습 / 2017-2019 평가 (era 는 알려진 교란)
가중치      stay 당 instance cap 20 또는 1/n_instance
금지        전체 AUROC 단독 보고 · macro-F1 단독 보고
```

**왜 AUPRC 인가**: 앵커=N 계층은 기저 12% 다. 이 불균형에서 AUROC 는 둔하고, "새로 생길 사람을 미리 잡는다"는 임상 주장은 정밀도-재현율 곡선에 직접 대응한다.

---

## 4) 한계 5가지 (먼저 말하기)

1. **mobility / pain / GCS 값이 아직 없다.** `00_extract.py` 의 `VALUE_IDS` 가 CAM·RASS 만 값으로 뽑는다. DB 엔 다 있다(보유율 100 / 96.2 / 100%). **재추출 전엔 M2 입력이 반쪽이다 — 유일한 하드 블로커.**
2. **앵커=N 계층의 절대 성능은 낮게 나올 것이다.** baseline AUPRC 23.0 에서 출발한다. 델타로 말해야 하고, "AUPRC 0.35" 같은 수를 그대로 보여주면 약해 보인다.
3. **PADIS 공리 8건을 LTN 이 아직 못 읽는다.** KG 쪽은 해결됐다 — `padis/kg/delirium_kg.py` 가 `decreasesRiskOf` / `hasNoEffectOn` / `precludes` 를 정의했다. 남은 건 소비 경로: `relation_vocab.json` 어휘 등록 + `horn_to_ltn.py` 가 셋을 **각각 다르게** 컴파일해야 한다(부정 함축 / 마이닝 필터 / Assessable 가드).
4. **M4 에 collapse 리스크.** 음의 방향 공리가 없으면 술어가 전부 양의 방향으로 쏠려 **원 논문 Table 3 의 LTN-AK collapse** 가 재현된다. 3번을 안 고치면 M4 가 상수 예측으로 붕괴할 수 있다.
5. **LNN 은 공개 구현이 빈약하다.** M5 착수 전 M3↔M4 결과로 게이트를 통과해야 한다.

---

## 5) 교수님께 확인할 질문

1. **주 지표**를 "앵커=N 계층 AUPRC"로 잡는 데 동의하시는지?
   → 전체 AUROC 는 룩업표가 이미 84.9 라 헤드라인으로 못 씁니다.
2. **평가 단위 전환**을 승인하시는지?
   → 승인되면 코호트 A안/B안 결정이 불필요해집니다 (`COHORT_AB_DECISION.md` 폐기). 대신 원 논문과의 직접 비교는 포기합니다.
3. **트랙을 둘로 갈까요, 섬망 하나로 집중할까요?**
   → (a) Sepsis 재현(stay 단위, 기존 파이프라인) + 섬망 신규 병행 / (b) 섬망 집중
4. **LNN 게이트 기준**: M3(3-way CBM) ≈ M4/M5 면 LNN 을 접는 데 동의하시는지?

**기본 제안(답이 없으면):**
`00_extract.py` 재추출 → **M1·M2 먼저** (2주) → M3 에서 게이트 판단 → 통과 시 M4.
M5(LNN)는 게이트 통과 후에만. 관계 어휘 확장(§4-3)은 데이터와 무관하니 병렬로.

---

## 6) 붙임 — 숫자 출처

| 수 | 스크립트 | 산출물 |
|---|---|---|
| instance 345,505 / 환자 40,070 / 계층 3종 | `eda/19_split_spec.py` | `out_split/spec2_*.csv` |
| baseline B0–B2 | `eda/20_baseline_carryforward.py` | `out_split/base_carryforward.csv` |
| 입력 커버리지 (RASS 100% 등) | `eda/19_split_spec.py` | `out_split/spec3_*.csv` |
| PADIS 규칙 19개 + 근거등급 | — | `padis/kg/delirium_kg.py`(본문) · `padis/outputs/padis_rules_draft_v1.json`(MIMIC 매핑) |

전제: 성인 + ICU LOS ≥ 24h + 입실 후 240h 캡. 분할 seed 42.
