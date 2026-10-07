# LLM 추출 트리플 (zero / one / few-shot × 2회)

`llm_triples.csv` — 2018 PADIS 가이드라인 조각 8개를 zero/one/few-shot 프롬프트로 각 2회 추출한 결과의
**트리플(subject · predicate · object)만** 담았다. 모드·회차·조각 단위로 구분된다.

## 원문을 넣지 않은 이유

추출 결과의 `evidence` 항목은 가이드라인 **본문 문장을 그대로 인용**한다. 저작권 때문에 저장소에는 넣지 않고,
문장이 있었는지만 `evidence_있음` 열(1/0)로 남겼다. 원문·프롬프트·원본 응답은 저장소 밖에 있다.

| 내용 | 위치 |
|---|---|
| 가이드라인 조각 원문 | `C:\data\padis_fewshot\chunk_*.txt` |
| 프롬프트 | `C:\data\padis_fewshot\prompt_{zeroshot,oneshot,fewshot}_*.txt` |
| 원본 응답(evidence 포함) | `C:\data\padis_fewshotuns\{mode}_run{1,2}\*.json` |
| 심사·블라인드 검토 | `C:\data\padis_fewshot\judge_out_j*.csv` · `blind_review_unblinded.csv` |

## 이 트리플로 한 비교

- 모드 간 겹침: one∩few **31개** (Jaccard 0.84) · 3-way 교집합 **25개** (근거 Y 13 · gold 일치 10).
- 예시를 주면 술어 표현이 바뀐다(`associatedWith` → `increasesRiskOf`): gold 일치 7/14 → 10/14,
  대신 근거 지지율 57% → 38~50%.
- KG 범위별 공리 비교 결과는 `docs/delirium/DELIRIUM_OUTCOME_SWITCH_2026-10-03.md` 참고.
