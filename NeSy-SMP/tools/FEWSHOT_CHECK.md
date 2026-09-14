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
