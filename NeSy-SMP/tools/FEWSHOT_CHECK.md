> ## 🔴 2026-09-15 정정 — 이 문서의 결론 세 개가 틀렸다
>
> 1. **"sepsis 가이드라인 원문이 없다" → 있다.** `pipeline_out/ssc2021_guideline.txt` (SSC 2021 전문, 6,371줄).
>    파일명으로만 찾아서 놓쳤다.
> 2. **"현재 파이프라인은 가이드라인을 읽지 않는다" → 반만 맞다.** 기본 경로는 하드코딩 10문장이지만,
>    `--pdf` 모드로 **실제 SSC 2021 에서 추출한 결과**(`pipeline_out/extracted_triples.json`, 12개)가 이미 있다.
> 3. **아래 PADIS few-shot 수치(P 63.6 / R 35.0)는 세션 오염뿐 아니라 설계 자체가 오염돼 있다.**
>    few-shot 예시 12개가 **전부** 채점 gold(20개) 안에 있고, 맞힌 7개 중 5개가 예시에 이미 있던 것이다.
>    새 세션에서 돌려도 이 수치는 의미가 없다.
>
> ### 실제 원문 regex 추출 — 겉보기 precision 100%, 근거로 보면 12개 중 2개
>
> | 트리플 | 근거 문장 | 지지하나 |
> |---|---|:-:|
> | Lactate → Death | "lactate 수치와 사망률의 연관은 잘 확립돼 있다" | ✅ |
> | SepticShock → Death | "패혈성 쇼크의 높은 사망 위험을 고려해…" | ✅ |
> | MeanArterialPressure → Death | "두 군의 90일 사망률이 **비슷했다**(41.0% vs 43.8%)" | ❌ **반대** |
> | KidneyDisease → Death | "Tonelli M, Manns B… (2002)" — **참고문헌 목록** | ❌ |
> | SepticShock → Sepsis | "qSOFA 를 단독 선별도구로 쓰지 말 것" | ❌ |
> | Age → Death | MRSA 광범위 항생제 투여 | ❌ |
> | Pneumonia → Death | 인플루엔자 폐렴에서 뉴라미니다제 억제제 효과 없음 | ❌ |
> | HIV → Death | 아프리카 고용량 수액소생술 | ❌ |
> | Sepsis → Death (2건) · SepticShock → Sepsis/Death (2건) | 프로토콜 준수·항생제 시점·ED 지연 | ❌ |
>
> **gold 와 일치하는데 근거가 틀린 이유:** 추출기가 gold 개념 사전의 단어가 "mortality" 근처에 나오면
> gold 모양 트리플을 낸다. **gold 일치율은 추출 능력을 재지 못한다.**
>
> ### 그래서 채점 기준을 바꿔야 한다
> - **(가) few-shot 예시와 채점 gold 가 겹치면 안 된다** — 교차 도메인(PADIS 규칙으로 sepsis 추출, 반대도) 또는 held-out
> - **(나) '근거 문장이 트리플을 실제로 지지하나'를 1차 지표로** — gold 일치는 보조
>
> → (가)·(나)를 적용한 sepsis 재추출 설계는 **맨 아래 §7** 과 `tools/FEWSHOT_SEPSIS_README.md`.

---

# 규칙 추출 재현 점검 — 현재 파이프라인 vs few-shot

`tools/rule_extraction_check.py` 로 잰 결과. 2026-09-10.

---

## 0. 결론

| | 입력 | precision | recall | F1 |
|---|---|---:|---:|---:|
| **현재 파이프라인** (sepsis, regex) | 코드에 하드코딩된 10문장 | 87.5% | **28.0%** | 42.4% |
| **few-shot** (PADIS, 실제 PDF 문장) | `_gold_sentences.txt` 24문장 | 63.6% | **35.0%** | 45.2% |

**둘 다 재현이 안 된다. 다만 안 되는 이유가 서로 다르고, 둘 다 방법론 문제가 아니다.**

---

## 1. 현재 파이프라인은 가이드라인을 읽지 않는다

`pipeline/guideline_extract.py` 가 읽는 것은 `DEFAULT_GUIDELINE_SENTENCES` —
**모듈에 하드코딩된 10문장**이고, 이미 정답을 진술한 형태다.

```
"Elevated serum lactate increases risk of death in sepsis."
"Thrombocytopenia increases risk of death."
```

정규식이 정확히 이 형태를 잡게 돼 있다. **입력이 곧 정답이라 재현 검증이 성립하지 않는다.**

그 유리한 조건에서도 25개 중 7개만 맞고(recall 28.0%) 1개는 틀린다 —
`Lactate → Sepsis` (정답 `Lactate → Death`). "risk of **death** in **sepsis**" 에서
마지막 개념을 object 로 잡는다. 동반질환 규칙(Cancer·HIV·Cirrhosis·CardiacInsufficiency)은
10문장에 아예 없어서 전멸이다.

> `padis/docs` 가 "원 논문은 자동 추출이라 했으나 실제로는 수작업" 이라고 적어둔 것이
> **우리 재현 코드에서도 그대로**라는 뜻이다.

---

## 2. few-shot 은 실제 원문에서 작동한다 — 하네스 검증 통과

`_gold_sentences.txt` 는 PADIS PDF 에서 뽑은 **진짜 문장 24개**다 (OCR 잡음 포함:
`棺` = β, `??2`, `T able` 같은 줄바꿈 하이픈 깨짐).

프롬프트 조립(9,633자, 예시 12개) → 추출 11개 → 채점까지 **전 구간 동작**한다.
`--concepts` 로 sepsis/PADIS 를 갈아끼울 수 있다.

---

## 3. 🔴 "틀린" 4개 중 3개는 추출 오류가 아니라 가이드라인의 자기모순

> **⚠️ 2026-09-15 정정 (`docs/KG_RULE_REVIEW.md` 검수 결과):** 기계환기는 자기모순이 **아니다.**
> fs D-026 목록에는 "**섬망을 포함한** 신경·정신 질환"이 인자로 들어 있어 섬망 위험인자 목록일 수 없고,
> 간호사 1인당 환자 수·업무량·시간대·침습 기구로 보아 **신체 억제대 사용 예측인자** 목록이다.
> 즉 가이드라인 모순이 아니라 **추출이 억제대 문맥을 섬망으로 잘못 읽은 문맥 상실 오류**다 —
> 문장 단위 추출이 맥락을 잃는다는 이 절의 결론을 오히려 더 강하게 뒷받침한다.
> 덱스메데토미딘(예방 권고 안 함 vs 비교 우위)은 실제 긴장으로 남는다. 아편유사제는 문장 ID 체계가 달라
> (fs D-032 = raw D-035) 재확인 필요.

| 추출 | gold | 근거 문장 |
|---|---|---|
| `Dexmedetomidine hasNoEffectOn Delirium` | `decreasesRiskOf` | **D-049 p21**: "We suggest **not using** ... dexmedetomidine ... **to prevent delirium** in all critically ill adults" |
| `MechanicalVentilation increasesRiskOf Delirium` | `hasNoEffectOn` | **D-026 p18**: "These factors include ... **mechanical ventilation use** (242, 261, 263)" |
| `OpioidUse increasesRiskOf Delirium` | `hasNoEffectOn` | **D-032 p19**: "known delirium risk factors including ... **the use of opioids** and systemic steroids" |

**같은 문서가 두 말을 한다.** 덱스메데토미딘은 D-049(예방 목적, 전체 성인)에서는 권고하지 않는데
D-051(수술 후 저용량)에서는 발생률을 낮춘다. 기계환기·아편유사제는 서술형 목록(D-026·D-032)에서는
위험인자로 나열되는데, PADIS 의 강한 근거 진술에서는 '영향 없음' 이다.

→ **문장 단위 추출은 이 충돌을 풀 수 없다.** 풀려면 그 문장이 *권고문인지 서술인지*,
*GRADE 등급이 몇인지* 를 같이 봐야 하는데 그 맥락은 문장을 잘라내는 순간 사라진다.
지금 KG 가 올바른 방향을 담고 있는 것은 **사람이 판단했기 때문**이다(`delirium_kg.py`).

> **자동 추출을 주장하려면 충돌 해소 정책이 먼저 필요하다.**
> "권고문 > 서술", "strong > moderate > 서술형 목록" 같은 우선순위 규칙.

나머지 1개 `EarlyMobility decreasesRiskOf Death` 는 D-060 의 "reduced mortality" 에서
정당하게 나온 것이고, 우리 gold 에 없을 뿐이다(진짜 오류가 아니다).

---

## 4. recall 35% 는 방법이 아니라 입력의 한계

못 뽑은 13개 중 대부분은 **24문장 안에 근거 문장이 없다** —
Dementia · Hypertension · Melatonin · PhysicalRestraint · PatientSex · SedationIntensity→Death 등.
`_gold_sentences.txt` 는 smoke test 용 표본이지 가이드라인 전문이 아니다.

**전문을 넣기 전에는 recall 을 방법 평가에 쓰면 안 된다.**

---

## 5. ⚠️ 이 숫자의 한계

**이번 PADIS 추출은 오염돼 있다.** 추출을 수행한 세션이 같은 대화에서 이미
PADIS gold 규칙(`padis_rules_draft_v1.json`, `delirium_kg.py`)을 읽은 상태였다.
따라서 위 63.6% / 35.0% 는 **낙관적 상한**이고 방법 성능의 추정치가 아니다.

**깨끗한 수치를 얻으려면 gold 를 본 적 없는 세션에서 `tools/fewshot_padis.txt` 를 그대로 돌려야 한다.**

---

## 6. 남은 것

1. **Surviving Sepsis Campaign 가이드라인 원문** — 리포에도 디스크에도 없다. 이게 있어야 sepsis 쪽 본 실험이 된다.
2. **PADIS 전문** — 24문장이 아니라 전체를 넣어야 recall 이 의미를 갖는다.
3. **충돌 해소 정책** (§3) — 자동 추출 주장의 전제.
4. **깨끗한 세션에서 재실행** (§5).

---

### 사용법

```bash
# 현재 파이프라인 채점 (sepsis)
python tools/rule_extraction_check.py

# few-shot 프롬프트 생성
python tools/rule_extraction_check.py --concepts configs/padis_concepts.json \
    --build-prompt ../padis/outputs/_gold_sentences.txt --out tools/fewshot_padis.txt

# 모델이 돌려준 JSON 채점
python tools/rule_extraction_check.py --concepts configs/padis_concepts.json \
    --score tools/fewshot_padis_result.json
```

---

## 7. held-out 재추출 점검 — sepsis × SSC 2021 (2026-09-15 추가)

랩 결정("기존 규칙을 few-shot 예시로 + SSC 2021 원문 → 재추출 → 기존 규칙과 비교 + 의미 정확도 검토")은 유지하고,
위 배너의 두 결함을 고친 설계다. 실행 절차 전체는 **`tools/FEWSHOT_SEPSIS_README.md`**.

### 7-1. 설계

| 결함 | 고친 방법 |
|---|---|
| 예시로 보여준 규칙으로 채점 (순환) | gold 30개(clinical_concepts ∪ pkg, 오타 통합, subClassOf/type/hasOutcome 제외)를 **examples 11 / heldout 19** 로 분할. 프롬프트에는 examples 만. **recall 은 heldout 에서만** |
| gold 일치 ≠ 근거 지지 | 모든 예측을 evidence 와 함께 **사람이 Y/부분/N 판정** (검토 CSV). 근거 지지 지표가 주지표 |
| 원문 365KB | 서지·참고문헌 제거, **본문 전체**를 최상위 섹션 6개 청크로. 키워드로 섹션을 고르지 않음 |

분할(`tools/sepsis_holdout_split.json`, seed 20260915)은 **주어 개념 단위**라 held-out 주어는 예시에 한 번도 주어로 안 나온다.
카테고리(lab/vital 위험인자 · 동반질환 · Sepsis/SepticShock)와 관계(increasesRiskOf · associatedWith)가 양쪽에 모두 들어가게 층화했고,
gold 에 1개뿐인 causedBy(Hypotension→Sepsis)는 heldout 에 뒀다.

| | 합계 | increasesRiskOf | associatedWith | causedBy |
|---|---:|---:|---:|---:|
| examples | 11 | 10 | 1 | 0 |
| heldout | 19 | 15 | 3 | 1 |

### 7-2. 지표

- **① recall(examples)** — 참고용. 보여준 것이라 높아도 의미 없음
- **② recall(heldout)** · precision(비예시) — gold 기준. 단독으로 결론 내지 않는다
- **③ gold 밖** — 오류 또는 gold 누락 후보. "같은 쌍이 gold 에 다른 술어로 있음" / "개념 목록 밖" / "허용 술어 밖" 태그
- **주지표: 근거 지지 held-out recall** (판정 Y 인 held-out 트리플 / 19) 과 **근거 지지율** (판정 Y / 전체 예측)
- 보조: evidence 가 원문에 실제로 있나 (자동 — `Y(본문)` / `Y(본문 밖: 참고문헌·서지)` / `N(원문에 없음)`)
- 재현성: 같은 프롬프트를 **새 세션에서 2회 이상** 돌려 held-out 적중 집합 비교

### 7-3. 기준선 — regex 추출 (`pipeline_out/extracted_triples.json`)

```
  held-out 분할: sepsis_holdout_split.json  (examples 11 / heldout 19)
  ─ ① 예시셋 적중 — 참고용
      recall(examples)  36.4% (4/11)
  ─ ② held-out — 주지표. 프롬프트에 없던 gold
      recall(heldout)   42.1% (8/19)
      precision(비예시) 100.0% (8/8)
      관계별: associatedWith 3/3 · causedBy 0/1 · increasesRiskOf 5/15
  ─ ③ gold 밖 0개
```

gold 로만 보면 held-out recall 42% · precision 100% 로 그럴듯하다. 그러나 배너의 판독으로는 근거가 지지하는 held-out 트리플이
Lactate→Death, SepticShock→Death **2개(잠정 10.5%)** 뿐이다. `tools/review_regex_baseline.csv` 판정 열은 비워 뒀으니 회의 전 확정할 것.
자동 대조에서 `KidneyDisease→Death` 근거는 `Y(본문 밖: 참고문헌·서지)` 로 잡힌다.

### 7-4. 실행

```bash
# (이미 생성됨) 분할 · 청크 프롬프트 6개
python tools/make_sepsis_holdout_split.py
python tools/rule_extraction_check.py --build-prompt pipeline_out/ssc2021_guideline.txt \
    --examples-from tools/sepsis_holdout_split.json --chunk --out tools/fewshot_sepsis_holdout.txt

# (사람) fewshot_sepsis_holdout_0N_*.txt 를 청크마다 '새 대화'에 그대로 붙여넣고
#        응답을 tools/llm_runs/run1/fewshot_sepsis_holdout_0N_*.result.json 으로 저장

# 병합 → 채점 + 검토 CSV
python tools/merge_llm_outputs.py "tools/llm_runs/run1/fewshot_sepsis_holdout_*.result.json" -o tools/llm_runs/run1/merged.json
python tools/rule_extraction_check.py --score tools/llm_runs/run1/merged.json \
    --split tools/sepsis_holdout_split.json --review-csv tools/llm_runs/run1/review.csv

# (사람) review.csv 판정 채우기 — gold_구분 열은 다 채운 뒤에 열람
python tools/rule_extraction_check.py --score-review tools/llm_runs/run1/review.csv --split tools/sepsis_holdout_split.json
```

> ⚠️ 추출은 **이 리포를 본 적 없는 세션**에서만 돌린다. §5 의 PADIS 수치가 오염된 이유와 같다.
> 기존 옵션(`--build-prompt` 단독, `--score` 단독, `--concepts`, `--n-ex`)의 동작은 바뀌지 않았다.


---

## 8. run1 결과 — held-out few-shot + 블라인드 근거 검수 (2026-09-15)

### 절차
1. SSC 2021 본문 6조각을 **서로 다른 새 서브에이전트 6개**가 동시에 추출. 리포 경로도, 평가라는 사실도, 정답 규칙도 주지 않았다.
   프롬프트는 리포 밖으로 복사해 넘겼고, **모든 추출 에이전트가 도구를 정확히 2번(파일 읽기·쓰기)만 썼다** — 다른 파일을 뒤지지 않았다는 흔적.
2. few-shot 결과 10개와 regex 기준선 12개를 **섞고, 출처와 정답 여부를 가린 채** 새 서브에이전트 하나가 근거 지지를 판정(Y / 부분 / N).
3. 판정 후 키로 해제 → `tools/llm_runs/run1/blind_review_unblinded.csv`

### 결과

| | 추출 | **근거 지지율 (블라인드)** | held-out 일치 | **근거 지지 held-out recall** |
|---|---:|---:|---:|---:|
| **few-shot LLM** | 10 (고유 7) | **100%** (10/10 Y) | 5.3% (1/19) | **5.3%** (1/19) |
| **regex (기존)** | 12 | **8%** (Y 1 · 부분 1 · N 10) | 42.1% (8/19) | **5.3%** (1/19) |

- **LLM 은 뽑은 것이 전부 정확하다.** gold 밖 5개(`Sepsis causedBy Pneumonia`, `Hypotension associatedWith SepticShock`,
  `Lactate associatedWith Death/Sepsis/SepticShock`)도 근거가 모두 맞았다.
- **regex 의 42.1% 는 가짜 일치다.** gold 와 일치한 12개 중 근거가 실제로 맞는 건 `SepticShock → Death` 하나.
  나머지는 프로토콜 준수·항생제 시점·qSOFA·참고문헌 목록·"사망률이 비슷했다" 같은 문장에서 나왔다.
- **근거가 맞는 것만 세면 두 방식이 5.3% 로 같다.**
- 부수 발견 — `Lactate`: gold 는 `increasesRiskOf Death` 인데 원문은 **연관만** 진술한다.
  LLM 은 `associatedWith` 를 골랐고(Y), regex 의 `increasesRiskOf` 는 방향 과대로 '부분' 판정. **gold 가 원문보다 강하게 적혀 있다.**

### 🔴 결론

> **기존 sepsis 규칙 대부분은 SSC 2021 원문에 쓰여 있지 않다.**
> 원문을 충실히 읽으면 그 규칙들이 나오지 않고(근거 지지 100% · 재현 5.3%),
> 단어를 맞추면 무관한 문장에서 나온다(재현 42.1% · 근거 지지 8%).
> **원 논문 규칙은 이 가이드라인에서 추출됐다기보다 일반 임상 지식으로 작성된 것**으로 보인다.

**PADIS 에 주는 함의:** LLM 추출은 "가이드라인에 쓰인 것"을 정확히 뽑는다. 원 논문식 규칙 세트(검사값·동반질환 → 사망)를
기대하면 안 되고, **가이드라인에 근거가 있는 규칙만** 남는다고 봐야 한다. 실제로 PADIS KG 검수(`docs/KG_RULE_REVIEW.md`)에서는
23개 중 12개가 원문 근거로 승인됐다 — PADIS 는 원문 기반으로 만들어졌다는 점에서 sepsis 와 대조적이다.

### 재현성·판정 신뢰도 — run2 로 확인

**추출 재현성:** 같은 프롬프트를 **새 서브에이전트 6개로 한 번 더**(run2) 돌렸다.
조각별 개수(6·1·0·1·0·2)와 **고유 트리플 7개가 run1 과 완전히 같다 (Jaccard 1.00).**
→ 회의의 질문 "한 번 더 시켰을 때 제대로 나오는지"에 대한 직접적인 답: **같게 나온다.**

**판정 신뢰도:** run2 결과 + regex 12개를 **다른 시드로 섞어 두 번째 블라인드 판정자**에게 넘겼다.

| | 판정자 1 (run1) | 판정자 2 (run2) |
|---|---|---|
| few-shot LLM | Y 10 · 부분 0 · N 0 | Y 8 · 부분 2 · N 0 |
| regex (같은 12항목) | Y 1 · 부분 1 · N 10 | Y 1 · 부분 1 · N 10 |

- **regex 12항목에서 두 판정자가 12/12 일치 — Cohen κ = 1.00.**
- LLM 에서 갈린 2개는 둘 다 **정의상의 관계**다(젖산 상승·저혈압이 패혈성 쇼크 *정의의 구성요소*).
  판정자 2 가 "정의적 포함은 연관 진술이 아니다"라며 '부분'으로 봤다. 연구 전체에서 판정자끼리 갈린 건 이 경계 사례 2개뿐.
- 근거 지지 held-out recall 은 두 라운드 모두 **5.3%** (SepticShock → Death).

### 남는 한계
- **판정자도 LLM**(같은 계열)이다. κ = 1.00 은 기준 적용이 일관됐다는 뜻이지 사람 판단과 같다는 보장은 아니다 — 사람이 N 10개를 한 번 훑어볼 것.
- **격리는 지시에 의존.** 추출 에이전트 12개 모두 도구를 2번만 썼다(판정자 2 는 3번). 준수의 흔적이지 보장은 아니다.
- **격리는 지시에 의존.** 도구 2회 사용이 준수의 흔적이지 보장은 아니다.
- **held-out 19개** → 트리플 하나가 5.3%p. 두 방식의 5.3% '동률'도 1개 대 1개다.
- **SSC 2021 은 치료 가이드라인**이라 위험인자 서술 자체가 적다. 결론은 '이 가이드라인에는 없다' 이지 'LLM 이 못 찾는다' 가 아니다.
