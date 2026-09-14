# sepsis 규칙 재추출 — held-out few-shot 실행 안내

> 질문: **"LLM 에 다시 물어도 규칙이 제대로 나오나?"** — 이 추출 과정을 PADIS 에 재사용해도 되는지.
> 랩 결정(기존 규칙을 few-shot 예시로 + SSC 2021 원문 → 재추출 → 기존 규칙과 비교 + 의미 정확도 검토)은 그대로 두고,
> **순환(보여준 규칙으로 채점)** 만 고쳤다.

---

## 1. 무엇을 고쳤나

| 문제 | 증상 | 이번 설계 |
|---|---|---|
| 예시 = 채점 gold | PADIS 선행 실행: 예시 12개가 전부 gold 20개 안, 맞힌 7개 중 5개가 예시 | gold 를 **examples / heldout 으로 분할**. 프롬프트엔 examples 만, recall 은 **heldout 에서만** |
| gold 일치 ≠ 근거 지지 | regex 기준선: gold 기준 precision 100% 인데 근거가 실제로 지지하는 건 12개 중 약 2개 | 모든 예측을 **근거 문장과 함께 사람이 판정**(검토 CSV). 근거 지지 지표를 주지표로 |
| 원문 365KB | 한 프롬프트에 넣기 어렵고, 37% 가 참고문헌 | 앞·뒤 서지 제거 후 **본문 전체를 섹션 6개로 청크** |

---

## 2. 분할 — `tools/sepsis_holdout_split.json`

만드는 스크립트: `tools/make_sepsis_holdout_split.py` (seed `20260915`, 같은 시드면 같은 분할)

**gold 정의**: `configs/clinical_concepts.json` triples ∪ `rules/pkg.txt`,
`increaseRiskOf → increasesRiskOf` 로 오타 통합, `subClassOf` / `type` / `hasOutcome` 제외 → **30개**
(clinical_concepts 25 + pkg 에만 있는 5: associatedWith 4개, Sepsis→Death).

| | 합계 | increasesRiskOf | associatedWith | causedBy | lab/vital 위험인자 | 동반질환 | Sepsis/SepticShock |
|---|---:|---:|---:|---:|---:|---:|---:|
| **examples** (프롬프트에 보임) | 11 | 10 | 1 | 0 | 3 | 6 | 2 |
| **heldout** (채점) | 19 | 15 | 3 | 1 | 7 | 8 | 4 |

- **examples**: Age·Bilirubin·WhiteBloodCells →Death / Cancer·CardiacInsufficiency·Pneumonia →Death, →Sepsis / Sepsis →Death (increasesRiskOf, associatedWith)
- **heldout**: CRP·Platelet·Lactate·LactateNotClearing·MeanArterialPressure·Hypotension →Death, Hypotension causedBy Sepsis,
  ChronicDisease·Cirrhosis·HIV·KidneyDisease →Death(·Sepsis), HIV associatedWith Death, SepticShock →Death·Sepsis (increasesRiskOf, associatedWith)

설계 선택:
- **주어 단위 분할.** held-out 주어는 예시에 주어로 한 번도 안 나온다. 트리플 단위로 나누면
  `Cancer→Death`(예시)만 보고 `Cancer→Sepsis`(held-out)를 원문 없이 패턴으로 맞힐 수 있다.
- **별칭 그룹.** `MeanArterialPressure` 별칭에 "hypotension" 이 있고 `LactateNotClearing` 라벨이 "Lactate" 라서 각각 같은 쪽에 묶었다.
- **층화.** 카테고리 3개 모두 양쪽에, increasesRiskOf·associatedWith 모두 양쪽에.
  **causedBy 는 gold 에 1개뿐**이라 양쪽을 채울 수 없어 heldout 에 뒀다(예시 없이 술어 목록만 보고 내는지 본다).
- 제약을 만족할 때까지 시드 고정 재추첨.

---

## 3. 원문 입력 — 무엇을 넣고 무엇을 뺐나

`tools/guideline_chunks.py`

- **뺀 것**: 제목·저자·소속(본문 "Introduction" 이전), `Supplementary Information` 이후 전부(Author details, Acknowledgements, Declarations, **References 134KB**).
  regex 기준선이 참고문헌 제목("…impact of dialytic modality on mortality")에서 `KidneyDisease→Death` 를 낸 전례가 있다.
- **넣은 것**: **본문 전체.** 위험/예후/사망 섹션만 고르지 **않았다** — 그 선택은 gold 를 아는 사람의 필터이고,
  "mortality 근처 개념 → 트리플" 이라는 regex 편향을 입력 단계로 옮기는 것이다.
- **정리**: 페이지 번호만 있는 줄, 이미지라 내용이 없는 `Table 1 (continued)` 줄 제거, 줄끝 하이픈 분리 이어붙이기.
  Table 2–4(텍스트로 추출된 표)는 남겼다.
- **청크**: 최상위 섹션 경계 6개. 60,000자를 넘으면 `Recommendation` 줄에서 반으로 나누게 돼 있지만 이번엔 해당 없음.

| # | 프롬프트 파일 | 섹션 | 프롬프트 자수 | 원문 자수 |
|---|---|---|---:|---:|
| 1 | `fewshot_sepsis_holdout_01_intro_screening.txt` | Introduction + Screening and early treatment | 25,615 | 22,141 |
| 2 | `fewshot_sepsis_holdout_02_infection.txt` | Infection | 49,755 | 46,351 |
| 3 | `fewshot_sepsis_holdout_03_haemodynamic.txt` | Haemodynamic management | 41,499 | 38,067 |
| 4 | `fewshot_sepsis_holdout_04_ventilation.txt` | Ventilation | 30,066 | 26,658 |
| 5 | `fewshot_sepsis_holdout_05_additional_therapies.txt` | Additional therapies | 34,673 | 31,247 |
| 6 | `fewshot_sepsis_holdout_06_longterm_goals.txt` | Long-term outcomes and goals of care | 39,517 | 36,059 |

목록·크기는 `fewshot_sepsis_holdout_manifest.json` 에도 있다. 영어 원문 기준 청크당 대략 7k–13k 토큰.

프롬프트(`PROMPT_HOLDOUT`, 기존 `PROMPT` 는 그대로 둠)가 기존과 다른 점:
예시는 "형식 참고용이며 원문 근거가 없으면 예시 트리플도 내지 말 것", evidence 는 원문 그대로 복사,
"두 개념이 한 문장에 함께 나오는 것만으로는 근거가 아님", 술어 정의 한 줄씩, 개념 별칭 제공.
술어 목록에서 오타 `increaseRiskOf`, `subClassOf`, `hasOutcome`, 리터럴 비교(`greaterOrEqual`/`lessOrEqual`)는 뺐다.

---

## 4. 사람이 실행하는 절차

> **이 리포를 연 세션(Claude Code 포함)에서 돌리면 안 된다.** 리포 안의 gold 파일을 읽을 수 있거나 이미 읽은 세션은 오염이다.
> 이 README 도 분할 내용을 담고 있으니 LLM 에 붙여넣지 말 것.

### 4-1. 세션 조건 (청크마다 지킴)
1. 웹 채팅 UI 또는 API 에서 **새 대화**를 연다. **청크 하나 = 새 대화 하나.** 이전 청크 대화에 이어서 붙이지 않는다.
2. 메모리 / 프로젝트 지식 / 커스텀 지시 / 파일 검색 기능은 **끈다**. 이 리포 파일을 첨부하지 않는다.
3. 프롬프트 파일 **전체 내용을 그대로** 복사해 첫 메시지로 보낸다. 앞뒤에 아무 말도 덧붙이지 않는다.
4. 응답을 **수정하지 말고** 그대로 저장한다 (코드펜스·설명이 섞여도 병합 스크립트가 처리).
5. 응답이 잘렸으면 같은 대화에서 "이어서 출력" 을 한 번 요청해 뒤에 이어 붙이고, 메모에 기록한다.
6. 기록: 모델명·버전, 날짜, 온도(API 면), 잘림/재요청 여부.

### 4-2. 파일 저장 규칙
실행(run)마다 폴더를 나눈다. "다시 물어도 같은가" 를 보려면 **최소 2회**(run1, run2) 권장.

```
tools/llm_runs/run1/fewshot_sepsis_holdout_01_intro_screening.result.json
tools/llm_runs/run1/fewshot_sepsis_holdout_02_infection.result.json
...
tools/llm_runs/run1/fewshot_sepsis_holdout_06_longterm_goals.result.json
tools/llm_runs/run1/RUN_NOTE.txt      ← 모델명·날짜·특이사항
```

### 4-3. 병합 → 채점 → 검토 CSV
(파이썬: `C:/dev/NeSy-SMP-repro/.venv/Scripts/python.exe`, 작업 폴더 `NeSy-SMP/`)

```bash
# ① 병합 (6개 파일, 파싱 실패가 있으면 exit 1)
python tools/merge_llm_outputs.py "tools/llm_runs/run1/fewshot_sepsis_holdout_*.result.json" \
    -o tools/llm_runs/run1/merged.json

# ② held-out 채점 + 검토 CSV
python tools/rule_extraction_check.py --score tools/llm_runs/run1/merged.json \
    --split tools/sepsis_holdout_split.json --review-csv tools/llm_runs/run1/review.csv

# ③ 사람이 review.csv 를 채운 뒤 집계
python tools/rule_extraction_check.py --score-review tools/llm_runs/run1/review.csv \
    --split tools/sepsis_holdout_split.json
```

프롬프트를 다시 만들 때(분할·개념을 바꿨을 때만):
```bash
python tools/make_sepsis_holdout_split.py
python tools/rule_extraction_check.py --build-prompt pipeline_out/ssc2021_guideline.txt \
    --examples-from tools/sepsis_holdout_split.json --chunk --out tools/fewshot_sepsis_holdout.txt
```
> 분할이나 프롬프트를 바꾸면 이전 run 결과와 비교할 수 없다. 바꿨다면 run 폴더 이름에 표시한다.

### 4-4. 검토 CSV 채우는 법
열: `no, subject, predicate, object, evidence, 근거가_지지하나(Y/부분/N), 메모, 원문에_evidence_있음(자동), gold_구분(검토 후 열람), chunk`

- **`gold_구분` 열은 판정을 모두 채운 뒤에 본다** (엑셀에서 열 숨기기). gold 여부를 알면 판정이 기운다.
- 가능하면 2인이 따로 채우고 불일치만 논의한다.
- 판정 기준 — **evidence 문장 하나만** 보고 판단한다(원문 다른 곳에 근거가 있을 것 같다는 추측은 반영하지 않는다):

| 판정 | 기준 |
|---|---|
| **Y** | 문장이 subject–object 관계를 진술하고, 술어(방향 포함)가 맞다 |
| **부분** | 관계는 진술되나 술어가 어긋남(연관만 말하는데 increasesRiskOf 등), 개념 매핑이 느슨함(치료 전략 ↔ 수치), 특정 하위집단 한정 |
| **N** | 관계 진술 없음 / 반대 진술("similar", "no difference") / 중재·프로그램 효과 문장 / 참고문헌 / 원문에 없는 문장 |

- `원문에_evidence_있음(자동)`: `Y(본문)` · `Y(본문 밖: 참고문헌·서지)` · `N(원문에 없음)` — 문자·숫자만 남겨 부분문자열 대조.
  `N` 은 LLM 이 문장을 지어냈거나 고쳐 쓴 것이므로 판정은 N.

---

## 5. 지표

| 지표 | 정의 | 읽는 법 |
|---|---|---|
| recall(examples) | 예시 적중 / 11 | **참고용.** 보여준 것이라 높아도 증거가 아님 |
| **recall(heldout)** | held-out 적중 / 19 | gold 기준 추출 재현. 단독으로 쓰지 않음 |
| precision(비예시) | held-out 적중 / (예측 − 예시 적중) | gold 모양 트리플을 내는 비율. regex 도 100% 가 나온다 |
| **근거 지지 held-out recall** | 판정 Y 인 held-out 트리플 / 19 | **주지표** — 보여주지 않은 규칙을 올바른 근거와 함께 찾았나 |
| **근거 지지율** | 판정 Y / 판정한 전체 예측 | 의미 정확도(semantic precision) |
| gold 밖 & Y | gold 에 없는데 근거가 맞는 것 | gold 누락 후보 — 오류로 세지 않는다 |
| 원문에 없음 비율 | 자동열 N / 전체 | 근거 조작(환각) |

**PADIS 재사용 판단**은 "근거 지지 held-out recall" 과 "근거 지지율" 을 regex 기준선 행과 비교하고,
run1·run2 사이에 held-out 적중 집합이 얼마나 같은지(겹침/합집합)로 본다.

---

## 6. 비교 행 — regex 기준선 (`pipeline_out/extracted_triples.json`)

```bash
python tools/rule_extraction_check.py --score pipeline_out/extracted_triples.json \
    --split tools/sepsis_holdout_split.json --review-csv tools/review_regex_baseline.csv
```

| 방법 | 예측 | recall(examples) | recall(heldout) | precision(비예시) | 근거 지지 held-out recall | 근거 지지율 |
|---|---:|---:|---:|---:|---:|---:|
| regex 기준선 | 12 | 36.4% (4/11) | **42.1% (8/19)** | **100% (8/8)** | 잠정 10.5% (2/19)* | 잠정 ~17% (2/12)* |
| LLM held-out run1 | | | | | | |
| LLM held-out run2 | | | | | | |

\* `FEWSHOT_CHECK.md` 상단 정정 배너의 판독(근거가 지지하는 것: Lactate→Death, SepticShock→Death — 둘 다 held-out).
`review_regex_baseline.csv` 의 판정 열은 **비어 있다** — 회의 전 사람이 채워 확정할 것.
자동열: 12개 중 11개 `Y(본문)`, 1개(`KidneyDisease→Death`) `Y(본문 밖: 참고문헌·서지)`.

**gold 기준 숫자(42.1% / 100%)만 보면 regex 가 그럴듯해 보인다는 것 자체가 이 설계의 요점이다.**

---

## 7. 한계 (회의에서 같이 말할 것)

- **개념 목록은 공유된다.** held-out 개념(CRP, HIV …)도 허용 개념 목록에 있으므로 "무엇이 중요한 개념인지"는 모델이 안다.
  gold 모양 추측은 근거 검토로만 걸러진다.
- **예시가 같은 gold 에서 나왔다.** 형식(주로 X→Death)은 여전히 전달된다. 완전한 차단은 교차 도메인(PADIS 규칙을 예시로) 설계가 필요.
- **held-out 19개는 작다.** 1개 차이가 5.3%p. 구간을 넓게 읽는다.
- **gold 자체가 SSC 2021 에서 온 게 아닐 수 있다.** SSC 는 치료 가이드라인이라 동반질환→Sepsis 같은 역학 규칙의 근거가 본문에 없을 수 있다
  → 낮은 recall 이 추출 실패인지 입력 부재인지는 검토 CSV 의 gold 밖·못 뽑은 항목을 원문 검색으로 확인해야 구분된다.
- 청크 경계를 넘는 근거(섹션 제목 + 다음 문단)는 놓칠 수 있다. PDF 추출 잡음(표·줄바꿈)은 남아 있다.
