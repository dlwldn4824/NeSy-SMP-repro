# Knowledge Pipeline — 하드코딩 대체 구현

논문이 주장하는 자동 파이프라인을 코드로 구현한 모듈입니다.  
기존 `create_ckg.py` / `main.py`의 FOL 하드코딩을 **설정 + 컴파일러**로 대체합니다.

## 흐름

```text
가이드라인 문장/텍스트
        ↓  pipeline/guideline_extract.py
(subject, relation, object)  (관계 정규화: increasesRiskOf|associatedWith|causedBy)
        ↓  configs/clinical_concepts.json (+ SNOMED link)
RDF KG + rules/pkg.txt
        ↓  AnyBURL (기존 extract_rules.py) [선택]
Horn rules (filter_rules.py)
        ↓  pipeline/horn_to_ltn.py
pipeline_out/ltn_axioms.json   ← LTN 공리 IR
pipeline_out/predicates.json   ← HighLactate 등 predicate 스펙
```

## 실행

```bash
cd NeSy-SMP
pip install rdflib pandas pypdf

# Surviving Sepsis Campaign PDF에서 규칙 추출 (권장)
python -m pipeline.run_pipeline --pdf "/Users/LEEJIWOO/Downloads/sepsis\ guideline.pdf"

# 기본: curated concepts → KG + grounding/implication axioms
python -m pipeline.run_pipeline

# 시드 가이드라인 문장으로 추출 병합
python -m pipeline.run_pipeline --use-seed-guidelines

# 실제 가이드라인 plain text
python -m pipeline.run_pipeline --guideline path/to/ssc_excerpts.txt

# AnyBURL filtered rules가 있으면 Horn→LTN도 합침
python -m pipeline.run_pipeline --rules rules/process-rule-filtered.csv
```

PDF 추출 산출물:
- `pipeline_out/extracted_triples.json` — 근거 문장 포함 triple
- `pipeline_out/ssc2021_rules.tsv` — 사람이 읽기 쉬운 규칙 표
- `pipeline_out/ltn_axioms.json` — LTN 공리 IR (curated KG + PDF 추출 merge)

하드코딩 `create_ckg.py` 대신:

```bash
python create_ckg_from_config.py
```

## 산출물

| 파일 | 내용 |
|---|---|
| `pipeline_out/clinical_kg.ttl` | RDF |
| `rules/pkg.txt` | AnyBURL 입력 |
| `pipeline_out/predicates.json` | concept→predicate·threshold·feature |
| `pipeline_out/ltn_axioms.json` | data / grounding / implication 공리 IR |

## 하드코딩 대비 매핑

| 기존 | 새 구현 |
|---|---|
| `create_ckg.py` 수동 `g.add(...)` | `configs/clinical_concepts.json` + `build_kg.py` |
| `main.py` threshold Forall | `ltn_axioms.json` `kind=grounding` |
| `main.py` Implies(...) | `ltn_axioms.json` `kind=implication` |
| 수동 predicate 이름 | `predicate_compiler.concept_to_predicate_name` |

## 아직 남은 연결 (다음 작업)

`stratified_main.py`의 하드코딩 `formulas_knowledge.extend([...])` 를  
`ltn_axioms.json`을 읽어 동적으로 구성하는 로더로 교체해야 end-to-end가 완성됩니다.

로더 스케치: `pipeline/load_axioms_into_ltn.py` (예정)
- grounding → threshold mask + Forall(Pred)
- implication → Forall(Implies(body, HighMortality))
- w_D/w_K ← bundle["loss"]
EOF