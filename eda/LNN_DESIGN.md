# LNN이 맞는가 — 판단 근거와 input/output/흐름

EDA 결과(`03_STEP1_DATA_CHECK.md`, `results_09/`, `results_14_16/`)에 근거한 설계안.

---

## 0. 결론 먼저

| 질문 | 답 |
|---|---|
| LNN이 맞는 방향인가 | **맞다.** 문제의 형태가 구간 진리값과 일치한다 |
| 지금 확정해도 되나 | **아니다.** 값싼 확인 하나를 먼저 해야 한다 (§4) |
| UTA를 `[0,1]`로 두면 되나 | **안 된다.** UTA는 '모름'이 아니라 정보를 가진 상태다 (§2) |

---

## 1. 왜 LTN으로는 안 되는가

LTN에서 술어의 진리값은 **`[0,1]` 사이 실수 하나**다. 섬망 검사 결과는 셋인데:

```
Positive  → Delirium(x) = 1.0
Negative  → Delirium(x) = 0.0
UTA       → Delirium(x) = ???
```

UTA에 쓸 수 있는 값이 없다.

| 시도 | 왜 틀렸나 |
|---|---|
| `0.5` | Real Logic에서 0.5는 **"반쯤 참"** 이다. "모른다"가 아니다. `Benzo(x) → Delirium(x)` 공리에 넣으면 "벤조를 쓰면 섬망이 절반 생긴다"가 되어 학습 신호가 오염된다 |
| 손실에서 제외(masking) | 평가 건수의 **21.9%**, stay의 **40.0%** 가 빠진다. 게다가 무작위가 아니다 — UTA-only stay의 병원 사망률이 **81.7%**(전체 7.4%)라 **가장 위중한 집단이 통째로 사라진다** |
| UTA를 Negative로 | 명백히 틀렸다. UTA→P 전이가 12.9%로 N→P(8.2%)보다 높다 |

LNN은 진리값을 **하한·상한 구간 `[L, U]`** 로 표현한다. `[0,1]`이 "정보 없음"이고, 이게 LTN에 없던 표현력이다.

---

## 2. ⚠️ 그런데 UTA는 "모름"이 아니다 — 이게 핵심

UTA를 `[0,1]`(완전 무지)로 두는 게 자연스러워 보이지만, **데이터가 그렇지 않다고 말한다.**

전이 데이터에서 "이전 상태가 X일 때, 다음 확정 판정이 Positive일 확률":

| 이전 상태 | 다음 확정 판정이 P일 확률 | n |
|---|---:|---:|
| Negative | **8.6%** | 276,564 |
| **UTA** | **45.6%** | 34,302 |
| Positive | **71.4%** | 98,099 |

**UTA는 N과 P 사이 중간에 있다.** 완전 무지라면 이 값이 나올 이유가 없다.

여기에 §3의 RASS 근거를 겹치면 — UTA의 **78.1%가 RASS ≤ −4** — UTA일 때 우리가 아는 것이 꽤 많다:

```
UTA 라는 관측은 다음을 말해준다
  · 환자가 깊이 진정되어 있다        (RASS <= -4, 78.1%)
  · 그 상태가 이어질 가능성이 높다    (UTA -> UTA 71.7%)
  · 섬망 위험이 Negative 보다 높다    (다음 확정 P 45.6% vs 8.6%)
```

→ **`Delirium(x) = [0,1]` 은 정보를 버리는 것이다.**
→ 구간을 데이터로 좁히는 것 자체가 이 연구의 기여가 될 수 있다.

> **연구 프레이밍:** 원 논문은 공리 가중치를 임의 상수(0.8/0.2)로 뒀다. 우리는 두 가지를 근거 기반으로 바꾼다.
> **공리 가중치 ← GRADE 등급** (노션 4.2)
> **관측 불가 술어의 진리 구간 ← 데이터** (여기)

---

## 3. 술어 설계

관측 가능성이 다른 세 가지를 **분리**한다. 지금은 하나로 뭉뚱그려져 있다.

| 술어 | 관측 | 커버리지 (첫 24h) | 정의 |
|---|---|---:|---|
| `DeepSedation(x,t)` | **항상 관측됨** | RASS 83.7% | RASS ≤ −4 |
| `Assessable(x,t)` | **항상 관측됨** | 섬망평가 73.5% | CAM 결과가 P 또는 N |
| `Delirium(x,t)` | **Assessable 일 때만** | — | CAM = Positive |

이렇게 두면 진리값 배정이 깔끔해진다:

```
Assessable(x,t) = 1  →  Delirium(x,t) = [1,1] 또는 [0,0]   (확정)
Assessable(x,t) = 0  →  Delirium(x,t) = [L,U]              (구간, L·U는 데이터로)
```

**`Assessable` 자체가 PADIS 대상이다.** 가이드라인 D-01이 "타당한 도구로 정기 섬망 평가"를 권고하므로, 평가 불가 상태는 결측이 아니라 **가이드라인 이탈**이다. 이건 4.5절 Prior-vs-Evidence 대조의 재료가 된다.

> **주의 — 가드 술어가 붕괴하는 문제.** 노션 4.3의 "선택 1: `∀x Assessable(x) ∧ DeepSedation(x) → Delirium(x)`" 는 데이터상 성립하기 어렵다. UTA의 78%가 RASS ≤ −4 이므로 `¬Assessable ≈ DeepSedation` 이고, `Assessable ∧ DeepSedation` 은 거의 공집합이다. **선택 1은 선택 2의 특수한 경우로 붕괴한다.**

---

## 4. 🔴 확정 전에 해야 할 것 — 값싼 확인

**LNN은 LTN보다 구현이 훨씬 덜 성숙하다.** 공개 구현이 적고 학습이 까다롭다. 여기에 프로젝트를 걸기 전에, **문제가 실제로 존재하는지 LTN에서 먼저 보여야 한다.**

기존 LTN 코드로 UTA 처리만 바꿔 4번 돌린다:

| 세팅 | UTA 처리 | 확인하는 것 |
|---|---|---|
| A | 손실에서 제외 (masking) | 기준선 |
| B | `Delirium = 0.5` | 0.5가 실제로 해로운가 |
| C | `Delirium = 0` (Negative 취급) | 흔한 실수의 대가 |
| D | UTA인 stay 전체 제외 | 선택편향의 크기 |

**판정 기준:**

```
A~D 성능이 크게 갈린다        → UTA 표현이 실제 문제다.  LNN 정당화됨.
A~D 가 비슷하다               → 표현 문제가 아니다.      LNN은 과잉. LTN 개선에 집중.
D 만 크게 다르다              → 표현이 아니라 선택편향 문제.  가중치/보정으로 해결.
```

이 확인은 **기존 코드로 며칠이면 된다.** 결과가 곧 논문의 Motivation 절이 된다 — "구간 진리값이 필요하다"는 주장에 숫자 근거가 생긴다.

**이걸 건너뛰고 LNN으로 가면**, 리뷰어의 첫 질문("왜 LTN으로는 안 되는가")에 답할 근거가 없다.

---

## 5. Input / Output

### 관찰창 = ICU 입실 후 첫 24시간 (스펙 ④)

**입력 — 시계열** (첫 24h, 커버리지는 `chk13_coverage_unified.csv`)

| 변수 | 첫 24h 보유 | stay당 측정 |
|---|---:|---:|
| RASS | 83.7% | median 14회 |
| GCS | 92.3% | median 39회 |
| Mobility (JH-HLM, 순서형 8단계) | 95.4% | median 27회 |
| Pain NRS | 84.9% | median 23회 |
| 섬망평가 (P/N/UTA 시퀀스) | 73.5% | median 2회 |
| 활력징후 | ~100% | — |

**입력 — 투약** (첫 24h 노출, `chk9_sedative_first24h.csv`)

| 약물 | 첫 24h 노출 |
|---|---:|
| propofol | 30.0% |
| midazolam | 8.1% |
| lorazepam | 5.0% |
| dexmedetomidine | 4.8% |

⚠️ 첫 24h로 자르면 재원 전체 대비 절반으로 준다 (lorazepam 13.0% → 5.0%). **진정제 변수는 생각보다 얇다.**

**입력 — 정적**

`age`, `gender`, `first_careunit`, `anchor_year_group`, 응급실 경유 여부

**입력 — 파생 (UTA 축)** ← 이게 이 연구의 특징

```
uta_frac        첫 24h 섬망평가 중 UTA 비율
deep_sed_frac   첫 24h 중 RASS <= -4 인 시간 비율   (전체 11.3%, stay별 극단 쏠림)
n_assess        첫 24h 평가 횟수
never_assessed  첫 24h 평가 0회          (4.9%)
all_uta         첫 24h 전부 UTA          (13.3%)
```

> `never_assessed` + `all_uta` = **18.2%** 는 "첫 24h에 섬망이 없었다"고 말할 수 없는 stay다. 별도 플래그로 유지한다.

**입력 — 선택 (ED, 연결률 42.7%)**

`medrecon` 입원 전 벤조·항콜린제 복용 / `triage` 도착 시 중증도

### 출력

| | 정의 | 유병률 |
|---|---|---:|
| **주 출력** | 24–72h 창 내 CAM Positive ≥ 1 | **15.6%** (A안) / 25.6% (B안) |
| 보조 | `DeepSedation` — RASS ≤ −3 | — |
| 보조 | `Assessable` — 창 내 판정 가능 | 52.1% |

⚠️ 24–72h 창에서 판정이 0회인 stay가 **47.9%** 다. 그중 67.8%는 72h 이전 ICU 퇴실, 사망은 5.1%뿐. **경쟁위험보다 조기 퇴실이 주 탈락 사유**다.

---

## 6. 흐름

```
[첫 24h 관찰창]
  시계열 (RASS·GCS·mobility·pain·vitals)
  투약   (propofol / benzo / dexmed)
  정적   (age·careunit·era)
  파생   (uta_frac · deep_sed_frac · n_assess)
         │
         ▼
  ┌──────────────┐
  │   backbone   │   BiLSTM 또는 GRU
  │  (논리 없음)  │   원 논문과 동일 구조 유지
  └──────┬───────┘
         │
         ▼
  ┌─────────────────────────────────┐
  │  개념층 (Concept Bottleneck)      │
  │   DeepSedation(x)   ← RASS 로 지도학습 (항상 관측)
  │   Assessable(x)     ← CAM 유무로 지도학습 (항상 관측)
  │   Delirium(x)       ← Assessable 일 때만 지도학습
  └─────────────────────────────────┘
         │              ▲
         │              │  PADIS 공리 (GRADE → 가중치)
         │              │    Benzo      → increasesRiskOf → Delirium
         │              │    DeepSedation → ¬Assessable
         │              │    Delirium   → increasesRiskOf → Immobility
         ▼
  ┌──────────────┐
  │  24-72h 예측  │  Delirium ∈ {0,1}
  └──────────────┘

손실 = w_D · 데이터항 + w_K · 지식항(공리 만족도)
       └ Assessable=0 인 시점에서 Delirium 항은
         점값이 아니라 [L,U] 구간 제약으로 들어간다  ← LNN 이 필요한 지점
```

**리뷰어 대비:** 이 구조는 사실상 **Concept Bottleneck Model + 논리층**이다. 노션 5.2가 예상한 질문("논리층이 CBM 대비 뭘 더 주는가")에 대한 우리 답은 **"CBM은 관측 불가 개념에 값을 강제해야 하지만, 논리층은 구간으로 남길 수 있다"** 가 된다. CBM baseline은 반드시 같이 돌려야 한다.

---

## 7. 다음 순서

```
1. §4 LTN ablation 4종      ← 가장 먼저. 며칠. LNN 정당화의 근거
2. 코호트 A/B 확정          ← 랩미팅 결정 대기
3. 술어 3종 라벨 생성       ← DeepSedation / Assessable / Delirium
4. 구간 [L,U] 산출 방법 결정 ← 데이터 기반. §2 전이 통계가 출발점
5. baseline (XGB/RF/BiLSTM/CBM)
6. LNN 구현
```

**1번이 2번을 안 기다린다.** 코호트가 A든 B든 UTA 표현 문제는 같으므로, 지금 시작할 수 있다.

---

근거 파일: `results_09/chk4_transition_matrix.csv`(전이) · `chk2_first_cam_rass.csv`(UTA×RASS) · `chk13_coverage_unified.csv`(첫 24h 커버리지) · `chk9_sedative_first24h.csv`(투약) · `results_14_16/chk16_ab_compare.csv`(A/B)
