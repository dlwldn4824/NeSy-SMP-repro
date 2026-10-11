# 부록 — 원자료 그대로 (겹친 공리 · 가짜 공리 생성 · 계산식 · 매핑)

본문 [KG_SHOT_OVERLAP_AND_AXIOMS.md](KG_SHOT_OVERLAP_AND_AXIOMS.md) 의 수치가 어디서 나왔는지
확인할 수 있게 **뽑아 놓은 값을 가공 없이** 싣는다.

---

## A. One-shot ∩ Few-shot 31개 — 전체 목록 (원자료)

`3way` = Zero-shot 에도 있는 것 · `판정` = 공리 컴파일 결과.
출처 `padis/outputs/llm_triples/llm_triples.csv` (설정별 2회 합집합).

```
  3way  Age                    -associatedWith  -> SeverePain             결과 미매핑
        Age                    -increasesRiskOf -> Delirium               공리
  3way  Age                    -increasesRiskOf -> PhysicalRestraint      결과 미매핑
        Benzodiazepine         -increasesRiskOf -> Delirium               공리
        BloodTransfusion       -increasesRiskOf -> Delirium               공리
        DeepSedation           -precludes       -> SeverePain             결과 미매핑
  3way  Delirium               -associatedWith  -> Dementia               결과 미매핑
  3way  Delirium               -increasesRiskOf -> PhysicalRestraint      결과 미매핑
        Dementia               -increasesRiskOf -> Delirium               공리
  3way  Dexmedetomidine        -decreasesRiskOf -> Delirium               공리
  3way  EarlyMobility          -decreasesRiskOf -> Death                  기각 (hasNoEffectOn 충돌)
  3way  EarlyMobility          -decreasesRiskOf -> Delirium               공리
  3way  EarlyMobility          -decreasesRiskOf -> PhysicalRestraint      결과 미매핑
  3way  EarlyMobility          -hasNoEffectOn   -> Death                  기각 선언
  3way  Hypertension           -increasesRiskOf -> Delirium               공리
  3way  MechanicalVentilation  -hasNoEffectOn   -> Delirium               기각 선언
  3way  MechanicalVentilation  -increasesRiskOf -> PhysicalRestraint      결과 미매핑
  3way  OpioidUse              -hasNoEffectOn   -> Delirium               기각 선언
  3way  OpioidUse              -increasesRiskOf -> Delirium               기각 (hasNoEffectOn 충돌)
  3way  OpioidUse              -increasesRiskOf -> SeverePain             결과 미매핑
  3way  PatientSex             -associatedWith  -> SeverePain             결과 미매핑
  3way  PatientSex             -hasNoEffectOn   -> Delirium               기각 선언
  3way  PhysicalRestraint      -associatedWith  -> Benzodiazepine         결과 미매핑
  3way  PhysicalRestraint      -associatedWith  -> OpioidUse              결과 미매핑
  3way  PhysicalRestraint      -increasesRiskOf -> Delirium               공리
  3way  SedationIntensity      -increasesRiskOf -> Death                  공리
  3way  SedationIntensity      -increasesRiskOf -> Delirium               공리
  3way  SeverePain             -associatedWith  -> Hypertension           결과 미매핑
        Trauma                 -associatedWith  -> SeverePain             결과 미매핑
  3way  Trauma                 -increasesRiskOf -> Delirium               공리
  3way  Trauma                 -increasesRiskOf -> SeverePain             결과 미매핑
```

집계: **공리 11 · 기각 선언 4 · 충돌 기각 2 · 결과 미매핑 14 = 31**

> ⚠️ 보고서 초안의 "개념 → 개념 14개" 목록에 `PhysicalRestraint → OpioidUse` 가 두 번 들어가 있었다.
> 빠진 한 줄은 **`Trauma −associatedWith→ SeverePain`** 이다 (`Trauma → SeverePain` 은 술어가 다른
> 두 트리플로 각각 들어온다 — `increasesRiskOf`(세 설정 공통) · `associatedWith`(one/few 만)).

주어별 개수: EarlyMobility 4 · OpioidUse 3 · PhysicalRestraint 3 · Trauma 3 · Age 3 ·
PatientSex 2 · Delirium 2 · MechanicalVentilation 2 · SedationIntensity 2 · 나머지 1개씩.

---

## B. 겹친 공리 11개 — 조건별 만족도 (원자료)

`delirium/33_kg_variants_v2.py` 결과 `stage33/kg_variant_axiom_sat_v2.csv` 를 피벗한 것.
빈칸은 그 KG 에 없는 공리.

```
공리                                          합의(교집합) one-shot few-shot zero-shot  합집합  사람KG
Age-associatedWith->Delirium                       —        —        —     0.582   0.604      —
Age-increasesRiskOf->Delirium                      —    0.600    0.600        —    0.604   0.591
Benzodiazepine-associatedWith->Delirium            —        —        —     0.661   0.707      —
Benzodiazepine-increasesRiskOf->Delirium           —    0.701    0.701        —    0.707   0.688
BloodTransfusion-associatedWith->Delirium          —        —        —     0.791   0.841      —
BloodTransfusion-increasesRiskOf->Delirium         —    0.827    0.827        —    0.841   0.806
DeepSedation-increasesRiskOf->Delirium             —        —        —        —       —    0.892
DeepSedation-precludes->Assessable                 —        —        —        —       —    0.892
Dementia-associatedWith->Delirium                  —        —        —     0.894   0.930      —
Dementia-increasesRiskOf->Delirium                 —    0.925    0.925        —    0.930   0.914
Dexmedetomidine-decreasesRiskOf->Delirium      0.727    0.712    0.712    0.719   0.708   0.709
EarlyMobility-decreasesRiskOf->Delirium        0.967    0.964    0.964    0.965   0.962   0.962
Hypertension-increasesRiskOf->Delirium         0.425    0.414    0.414    0.418   0.414   0.412
Melatonin-decreasesRiskOf->Delirium                —        —        —        —       —    0.993
PhysicalRestraint-increasesRiskOf->Delirium     0.700    0.673    0.673    0.682   0.670   0.668
SedationIntensity-increasesRiskOf->Death       0.701    0.685    0.685    0.694   0.682   0.680
SedationIntensity-increasesRiskOf->Delirium    0.843    0.826    0.826    0.834   0.823   0.822
SeverePain-increasesRiskOf->Delirium               —        —        —        —       —    0.625
Trauma-associatedWith->Delirium                    —        —        —     0.878   0.831      —
Trauma-increasesRiskOf->Delirium               0.872    0.819    0.819    0.878   0.831   0.802
```

**one-shot 열과 few-shot 열이 소수점까지 동일하다** — 공리 집합이 같기 때문이다.
zero-shot 은 같은 5쌍(나이·벤조·수혈·치매·외상)을 `associatedWith` 로 들고 있어 **가중치 등급만** 다르다.

---

## C. 가짜 공리는 어떻게 만드는가 (실험별로 다르다)

음성 대조군의 목적은 **"공리의 내용이 성능에 기여하는지"** 를 보는 것이다. 그래서 공리의 개수·강도·
구조는 그대로 두고 **내용만 망가뜨린** 집합을 만든다. 실험마다 망가뜨리는 지점이 다르다.

공리의 내부 표현은 7칸 튜플이다.

```
(이름, 개념, 방향(+1/−1), 임계값(z), 머리, 머리부정 여부, 근거등급)
예) ("DeepSedation→Delirium", "RASSmin", -1, z(-4.0), "Delirium", False, "low")
```

### C-1. 머리 무작위 — `delirium/31_axiom_control.py`

```python
HEADS_POOL = ["Delirium", "Death"]

def shuffled_heads(seed):
    rng = random.Random(seed)
    ax = [(nm, cn, sgn, thr, rng.choice(HEADS_POOL), rng.random() < 0.5, g)
          for nm, cn, sgn, thr, hd, neg, g in REAL]
    return ax, REAL_W
```

앞부분(어떤 환자에서 켜지는지)은 그대로 두고 **결론만 무작위로 바꾼다.**
→ "조기 거동이면 섬망이 **아니다**" 가 "조기 거동이면 **사망한다**" 처럼 바뀐다.

### C-2. 앞부분 무작위 — 같은 파일

```python
def shuffled_antecedents(seed):
    rng = random.Random(seed)
    pool = [a[1] for a in REAL if a[1] is not None]
    out = []
    for nm, cn, sgn, thr, hd, neg, g in REAL:
        if cn is None:
            out.append((nm, cn, sgn, thr, hd, neg, g)); continue
        new = rng.choice(pool)
        out.append((nm, new, sgn, _zthr(new, 0.0) if CTYPE_C[CI[new]] != "bin" else 0.5,
                    hd, neg, g))
    return out, REAL_W
```

결론은 그대로 두고 **조건 개념을 다른 개념으로 바꿔 끼운다.**
→ "고령이면 섬망" 이 "진정제 비율이 높으면 섬망" 같은 식으로 섞인다.

### C-3. 머리·부정 재배치 — `delirium/35`·`39` (A4 수정 후)

```python
def fake_axioms(seed):
    # A4: 머리/부정을 새로 뽑으면 가짜 쪽 "사망" 머리가 진짜(13개 중 1개)보다 훨씬 많아져
    #     비교가 공리 내용이 아니라 머리 분포 차이가 된다. 그래서 **같은 집합을 섞기만** 한다.
    rng = random.Random(seed)
    heads = [a[4] for a in REAL]; negs = [a[5] for a in REAL]
    rng.shuffle(heads); rng.shuffle(negs)
    return [(nm, cn, sgn, thr, heads[i], negs[i], g)
            for i, (nm, cn, sgn, thr, hd, neg, g) in enumerate(REAL)]
```

**C-1 의 결함을 고친 버전이다.** C-1 은 `random.choice(["Delirium","Death"])` 로 머리를 새로 뽑으므로
가짜 쪽 "사망" 머리가 평균 50% 가 된다. 진짜는 13개 중 1개(7.7%)뿐이다. 사망 머리 공리는
사망 로짓으로 gradient 가 흐르므로, **그 상태로 비교하면 "공리 내용" 대신 "사망 머리 비율"을 재게 된다.**
그래서 진짜의 머리 집합(섬망 12 · 사망 1)과 부정 집합을 **순서만 섞어** 쓴다.

### C-4. 재타깃 실험용 — `delirium/41_retarget_axioms.py`

```python
def fake_antecedents(ax, seed):
    """앞부분(개념·방향·임계값)을 공리 사이에서 재배치 — 집합·머리·부정은 보존."""
    rng = random.Random(seed)
    idx = [i for i, a in enumerate(ax) if a[1] is not None]
    ants = [(ax[i][1], ax[i][2], ax[i][3]) for i in idx]
    rng.shuffle(ants)
    out = list(ax)
    for k, i in enumerate(idx):
        nm, cn, sgn, thr, hd, neg, g = ax[i]
        out[i] = (nm, ants[k][0], ants[k][1], ants[k][2], hd, neg, g)
    return out
```

재타깃 실험에서는 **공리 11개의 머리가 전부 `Death` 로 같다.** 그러니 머리를 섞어도 아무것도
바뀌지 않는다. 그래서 이 실험의 음성 대조군은 **앞부분을 공리 사이에서 재배치**한다
(개념·방향·임계값을 묶음째 다른 공리로 옮긴다).

### C-5. 패혈증 쪽

패혈증은 원저자 코드를 그대로 쓰기 때문에 가짜 공리 실험을 하지 않았다. 대신
**같은 설정 2회 실행**(r1·r2)과 **gradient 직접 측정**으로 같은 질문에 답했다.

---

## D. 만족도·활성화율은 어떻게 계산하나

### D-1. 공리 만족도

`delirium/29_outcome_mortality.py` 의 `axiom_sat()` — 원저자 코드와 같은 연산이다.

```python
for nm, cn, sgn, thr, hd, neg, _g in ax:
    a = sigmoid(sgn * (z_concept - thr) / TAU)        # 앞부분 진리값 (TAU = 0.35)
    b = p_del if hd == "Delirium" else p_death        # 결론 진리값
    if neg: b = 1.0 - b
    sat = 1.0 - a + a * b                             # 함축 Reichenbach
    per_axiom = 1.0 - sqrt(mean((1.0 - sat) ** 2))    # 전칭 pMeanError (p=2)
```

중요한 성질 — `a` 가 작으면(공리가 거의 켜지지 않으면) `sat ≈ 1` 이 된다. **그래서 만족도는
"공리가 옳은 정도"가 아니라 "공리가 위반되지 않는 정도"다.** 자주 켜지는 공리는 산술적으로 낮게 나온다.

### D-2. 활성화율

패혈증 쪽은 기록 패치 P6 가 **코드의 판정 조건으로 켜진 환자 비율**을 epoch 마다 적는다
(`results_*/p6_knowledge_log.jsonl` 의 `activation`). 모델 예측이 아니라 **데이터 조건**이다.

섬망 쪽 감사 표(활성화 환자 사망률)는 `delirium/37_axiom_audit.py` 에서 test 앵커 158,876건에
대해 공리 앞부분이 참인 환자군을 뽑아 실제 사망률을 센 것이다.

---

## E. 개념 → 실행 조건 매핑과 술어 가중치 (원자료)

`delirium/30_kg_variants.py` 그대로.

```python
# (KG 개념 -> (우리 연속 개념 이름, 방향, 원 단위 임계))  방향 +1: 임계 이상이 참
MAPPING = {
    "Benzodiazepine":   ("BenzoFrac",    +1, 1e-6),
    "DeepSedation":     ("RASSmin",      -1, -4.0),
    "SedationIntensity":("RASSnegmean",  -1, -2.0),
    "SeverePain":       ("PainNRSmax",   +1, 4.0),
    "Age":              ("Age",          +1, 65.0),
    "Dexmedetomidine":  ("DexmedFrac",   +1, 1e-6),
    "Propofol":         ("PropofolFrac", +1, 1e-6),
    "EarlyMobility":    ("MobJHHLM",     +1, 4.0),
    "Immobility":       ("MobJHHLM",     -1, 3.0),
}
# 개념 회수 후(v2) 추가
MAPPING |= {"BloodTransfusion": (..., +1, 0.5), "Dementia": (..., +1, 0.5),
            "Trauma": (..., +1, 0.5), "Hypertension": (..., +1, 0.5)}

HEADS = {"Delirium": "Delirium", "Death": "Death",
         "UnableToAssess": "CurrentUTA", "Assessable": "Assessable"}

PRED_W = {"increasesRiskOf": "strong", "decreasesRiskOf": "moderate",
          "associatedWith": "low", "precludes": "derived"}
GRADE_W = {"strong": 1.0, "moderate": 0.6, "low": 0.3, "derived": 0.5,
           "cohort": 0.3, "inconclusive": 0.2, "external": 0.5}
```

컴파일 규칙(기각·미매핑이 생기는 자리):

```python
no_effect = {(s, o) for s, p, o in triples if p == "hasNoEffectOn"}
...
if (s, o) in no_effect:        dropped.append(...)   # 같은 쌍에 '효과 없음' → 기각
if p not in PRED_W:            unmapped.append(...)  # 술어 미지원
if s not in MAPPING:           unmapped.append(...)  # 주어 미매핑
head = "CurrentUTA" if (p == "precludes" and o in ("Assessable","UnableToAssess")) else HEADS.get(o)
if head is None or (head not in ("Delirium","Death") and head not in CI):
                               unmapped.append(...)  # 결과 미매핑  ← 가장 많이 걸리는 규칙
```

`hasNoEffectOn` 이 **같은 (주어, 목적어) 쌍의 모든 공리를 기각**한다. 그래서
`OpioidUse → Delirium`(위험 증가)과 `OpioidUse ⊥ Delirium`(효과 없음)이 함께 나오면 둘 다 빠진다.

---

## F. gold 비교 원자료

held-out gold 14개는 사람이 쓴 PADIS KG(`padis/kg/delirium_kg.py`)에서 프롬프트 예시로
보여주지 않은 14개다. few-shot 은 예시 6개, one-shot 은 1개를 보여줬다.

### F-1. gold 적중 목록 (설정별, 2회 모두 동일)

```
one-shot / few-shot  10/14
  Age-increasesRiskOf->Delirium
  Benzodiazepine-increasesRiskOf->Delirium
  Dementia-increasesRiskOf->Delirium
  Dexmedetomidine-decreasesRiskOf->Delirium
  EarlyMobility-decreasesRiskOf->Delirium
  Hypertension-increasesRiskOf->Delirium
  OpioidUse-hasNoEffectOn->Delirium
  PatientSex-hasNoEffectOn->Delirium
  SedationIntensity-increasesRiskOf->Death
  SedationIntensity-increasesRiskOf->Delirium

zero-shot            7/14   (위 목록에서 Age · Benzodiazepine · Dementia 세 개가 빠진 것)
```

### F-2. "근거가 실제로 뒷받침한다"고 판정된 gold (여섯 실행 전부 동일)

```
5/14
  Hypertension-increasesRiskOf-Delirium
  OpioidUse-hasNoEffectOn-Delirium
  PatientSex-hasNoEffectOn-Delirium
  SedationIntensity-increasesRiskOf-Death
  SedationIntensity-increasesRiskOf-Delirium
```

### F-3. 그래서 숫자를 어떻게 읽나 (초안 수정)

| 설정 | gold 적중 | 그중 근거 지지 | **근거 없이 맞힌 것** |
|---|---|---|---|
| zero-shot | 7 | 5 | **2** |
| one-shot | 10 | 5 | **5** |
| few-shot | 10 | 5 | **5** |

- 예시를 주어 **늘어난 3개가 바로 `Age` · `Benzodiazepine` · `Dementia` → Delirium** 이고,
  이 세 개는 **근거 지지 목록에 없다.**
- 즉 "형식 점수 7/14 → 10/14" 의 증가분은 전부 **원문 근거 없이 맞힌 것**이다.
  (초안에 "늘어난 5개" 라고 적었는데, 증가분은 3개이고 근거 미지지 총량이 2 → 5 로 늘어난 것이다.)
- 전체 트리플 기준 "근거 지지 Y%" 는 zero 57.1 · 57.4 / one 38.2 · 50.0 / few 43.9 · 47.1 이다.
- 인용문 자체는 원문 그대로였다: `evidence 원문 그대로` 41/41 · 34/34 · 34/34 · 38/38 · 48/49 · 47/47.
- few-shot 은 보여준 예시 6개 중 **4개를 그대로 다시 출력**했다(one-shot 0/1).

---

## G. 패혈증 쪽 원자료

### G-1. 공리별 gradient (D5 · 학습 없이 1회 측정)

`NeSy-SMP/tools/audit/grad_path_sepsis.py` · 결과 `audit/grad_sepsis_6h/grad_path_sepsis.csv`
(fold 1 · 배치 20개 평균 · 체크포인트 `results_paper_6h/ltn_w_k.pth`)

```
공리,종류,배치수,만족도,사망모델 gradient,자기술어 gradient
impl:Age,함축,20,0.6645,0.45661901,0.265196
impl:Bilirubin,함축,20,0.6899,0.42202289,0.224324
impl:CRP,함축,20,0.6852,0.4283838,0.21071
impl:Chronic,함축,20,0.6524,0.47298493,0.235779
impl:Lactate,함축,20,0.6485,0.47834582,0.225745
impl:LactateNotClearing,함축,20,0.6698,0.4493614,0.217846
impl:Platelet,함축,20,0.6523,0.47317432,0.227522
impl:WBC,함축,20,0.6447,0.48357004,0.220284
anchor:Age>65,앵커,20,0.5053,0.0,0.411208
anchor:Bilirubin>=2,앵커,20,0.4681,0.0,0.344999
anchor:CRP>=100,앵커,3,0.475,0.0,0.38501
anchor:Chronic,앵커,20,0.5248,0.0,0.371754
anchor:GCS<8,앵커,20,0.5072,0.0,0.46397
anchor:Lactate>4,앵커,14,0.5287,0.0,0.364231
anchor:LactateClearing(neg),앵커,20,0.5017,0.0,0.328937
anchor:LactateNotClearing,앵커,14,0.4975,0.0,0.333133
anchor:Platelet<50,앵커,19,0.524,0.0,0.342235
anchor:WBC>30,앵커,8,0.536,0.0,0.334786
```

```json
{"데이터공리 gradient(θ_P)": 0.22478,
 "지식공리 gradient(θ_P)": 0.185457,
 "논문손실 기준 지식 몫": 0.170994,
 "θ_P gradient 가 0 인 공리 수": 10, "공리 수": 18}
```

단서 — 원저자 코드는 **위험 술어 MLP 를 저장하지 않는다**(`torch.save(lstm.state_dict())` 뿐).
그래서 위험 술어는 같은 구조로 새로 초기화한 상태에서 쟀다. **0/비0 판정은 정확하고, 크기는
"학습 종료 시점"이 아니라 "초기값에서의" 크기다.**

### G-2. 패혈증 전체 결과 (6h, 달리 적지 않으면 5-fold 평균 AUROC)

```
조건                     XGB     RF    BiLSTM   LTN    NeSy   NeSy-LTN
원본 6h                 92.67  91.18   89.71  91.27  91.02   -0.25
S1 결측수정 6h           92.67  91.18   90.33  91.23  91.17   -0.06
연결5 r1 (S3+S4)        92.67  91.18   89.22  91.14  91.18   +0.04
연결5 r2 (S3+S4)        92.67  91.18   90.25  91.23  91.24   +0.01
혈당제외4 (S5)           92.67  91.18   89.85  90.95  91.09   +0.14
D4 논문목록 MAP (S6)     92.67  91.18   89.13  91.03  90.89   -0.14
D6 학습셋 10%            90.59  89.37   86.26  87.90  87.86   -0.04
D6 학습셋 5%             89.80  88.43   84.51  86.29  86.18   -0.11
D6 학습셋 1%             85.80  85.90   63.97  66.84  69.75   +2.91
PADIS변수 48h            88.53  87.82   84.97  87.12  86.98   -0.14
원본 48h                 87.66  86.77   84.55  86.24  86.22   -0.02
원본 12h   r1 / r2       91.81  90.39   87.39  89.78  89.92   +0.14
                                        88.12  89.79  90.07   +0.28
원본 24h   r1 / r2       90.59  89.20   85.93  88.49  88.80   +0.31
                                        86.61  88.63  88.42   -0.21
```

XGB·RF 가 조건마다 동일한 것은 패치가 **NeSy 공리 경로만** 바꿨다는 확인이다
(D6 는 학습 데이터를 줄였으므로 XGB·RF 도 함께 내려간다).

### G-3. 48h 는 "관찰 창"이 아니라 "예측 시점"이다 (초안 수정)

초안 1-4-5 에 "PADIS 변수 관찰 범위를 48시간까지 늘렸다"고 적혀 있는데, 48h 는 **사망 48시간 전에
예측한다**는 뜻의 lead time 이다. 입력 CSV 가 `events_48h_wide_paper_como_padis.csv` 로,
6h·12h·24h 와 같은 변수 집합을 **더 이른 시점**에서 본 것이다.
따라서 "더 많은 임상 정보가 도움이 되었다"가 아니라 **"더 이른 시점에서도 PADIS 변수 추가 효과가
유지됐다"**(모든 모델 +0.8~0.9, NeSy−LTN −0.14) 로 읽어야 한다.

---

## H. 초안에 추가하면 좋을 설명 세 가지

1. **"공리 11개"와 "트리플 31개"를 구분해서 쓸 것.** 본문 1-1-5 처럼 표로 분리해 두면 좋다.
   특히 머리가 `Death` 인 공리는 **전 조건에서 `SedationIntensity → Death` 하나뿐**이라는 점을
   1-1 에서 미리 밝혀 두면 1-3(타깃 교체)·gradient 논의가 자연스럽게 이어진다.
2. **만족도는 "옳음"이 아니라 "위반되지 않음"이라는 성질**(부록 D-1)을 1-2-6 에 각주로 넣을 것.
   이게 없으면 `고혈압 → 섬망` 0.41 을 "모델이 못 배운 규칙"으로 읽게 된다.
3. **가짜 공리 생성 방식이 실험마다 다르다는 것**(부록 C)을 1-3-6(2단계 학습) 앞에 한 줄로
   밝혀 둘 것. 2단계 학습의 가짜 공리는 C-3(머리·부정 재배치)이고, 재타깃 실험은 C-4(앞부분
   재배치)다. 같은 "가짜"라는 말이 다른 조작을 가리킨다.
