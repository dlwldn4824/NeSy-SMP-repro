# README_PADIS (Phase 1)

이 문서는 `padis/` 폴더의 Phase 1 구현이 무엇을 하는지, 어떤 산출물을 남기는지 요약합니다.

## Phase 1 목표

`PADIS_Guideline_2018.pdf`에서 Sedation/Delirium 관련 excerpt만 사용해:

1. `padis_rules_raw.json`: Rule Registry raw(모두 pending)
2. `padis_rules_review.csv`: human review용 CSV(pending, approved? 비어있음)
3. `padis_smoke_gold_validation_report.md`: gold set(10~20개) 기반 자동 smoke validation
4. `mimic_coverage_report_smoke.md`: MIMIC-feasibility light check
5. 승인 이후: `padis_rules_approved.json` + `padis_kg.json`

## 실행

```powershell
cd c:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro

python -m padis.extraction.phase1_smoke_extraction `
  --pdf padis/inputs_local/PADIS_Guideline_2018.pdf `
  --out-dir padis/outputs `
  --excerpt-pages 4
```

Gold set 파일(사람이 채움):
`padis/rules/gold_set_smoke.json`

Review CSV에서 `approved?=yes`로 표시 후:
```powershell
python -m padis.review.approve_rules `
  --review-csv padis/outputs/padis_rules_review.csv `
  --out-approved padis/outputs/padis_rules_approved.json
```

Approved rules로 KG:
```powershell
python -m padis.kg.build_padis_kg_from_approved `
  --approved-json padis/outputs/padis_rules_approved.json `
  --out-kg padis/outputs/padis_kg.json
```

## 중요한 정책

- PDF 원문/추출 캐시는 `padis/inputs_local/` 및 `padis/outputs_local/`로 분리하고 `.gitignore` 처리
- Phase 1에서는 neural training/cohort 확정을 하지 않는다
- KG edge는 `rule_id` 중심으로 연결하며, `source_text` 전체를 KG edge에 중복 저장하지 않는다

