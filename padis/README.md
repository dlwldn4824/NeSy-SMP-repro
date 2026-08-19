# PADIS extension (Phase 1)

이 폴더는 기존 `NeSy-SMP-repro/NeSy-SMP`의 Sepsis 재현을 **변경하지 않고**, PADIS guideline 기반
Neuro-Symbolic 파이프라인을 **Phase 1부터 traceability-first**로 확장하기 위한 모듈입니다.

## Phase 1 목표

1. `padis/inputs_local/PADIS_Guideline_2018.pdf`를 Sedation/Delirium 섹션 중심으로 **소수 excerpt** 추출
2. excerpt에서 rule registry(raw) 생성
3. human review CSV 생성
4. (gold set) smoke validation (정확도 확인용)
5. approved rule 기반 KG(소규모) 빌드
6. MIMIC mapping feasibility/coverage(가벼운 점검) 리포트 생성

## 실행(예시)

```powershell
cd c:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro
python -m padis.extraction.phase1_smoke_extraction ^
  --pdf padis/inputs_local/PADIS_Guideline_2018.pdf ^
  --out-dir padis/outputs ^
  --excerpt-pages 4
```

> PDF 원문/추출 캐시는 `padis/inputs_local/` 및 `.gitignore` 정책으로 로컬 전용으로 관리합니다.

