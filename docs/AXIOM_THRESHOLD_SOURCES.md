# 학습 코드 공리 임계값의 출처 대조

작성 2026-09-17 · 질문: **KG(`create_ckg.py`)에도 SSC 2021에도 없는 임계값(GCS·호흡수·수축기혈압·크레아티닌 등)은 어디서 왔나?**
앞선 점검: AnyBURL 채굴 규칙에는 임계값이 없음(`KG_RULE_MINING_CHECK.md`) · 원문에 적힌 임계값은 자동 추출 가능(`GROUNDING_SPEC_CHECK.md`)

## 1. 논문 본문이 말하는 것 (로컬 PDF 텍스트)

- §4.1: 지식은 "particularly the Surviving Sepsis Campaign (Evans et al., 2021)"에서 추출. 개념 예시로 lactate · bilirubin · creatinine · 혈압 · 심박수 · 체온 · GCS · platelet · 산소포화도를 든다.
- §4.3: 임계값은 "can be systematically retrieved by executing queries over the knowledge graph".
- §4.5 **knowledge axiom 목록 (9개)**: HighLactate · HighBilirubin · HighCRP · HighWBC · LowPlatelets · **LowMAP** · AgeRisk · LactateNotClearing · HasChronicCondition → HighMortality.
- 본문에 **숫자로 적힌 임계값은 젖산 > 4.0 mmol/L 하나뿐**이다 (weak anchoring 예시, 2회).
- **GCS · 호흡수 · 수축기혈압 · 크레아티닌 · 혈당은 공리 목록에 없다.** 반대로 LowMAP 은 목록에 있지만 코드에서 쓰이지 않는다.
- 코드 주석: `stratified_main.py:450` 수축기혈압·평균혈압·호흡수·심박수 함수 위에 `# mews score risk`. 공개 저장소 `main.py` 는 호흡수∧수축기혈압 조건을 변수명 **`qSOFA_clinical_concept_values`** 로 기록한다.

## 2. 코드 조건 ↔ 후보 출처

일치: 값·방향이 같음 · 부분: 값은 같고 부등호 경계나 용도가 다름 · 없음: 대조한 출처 중 같은 값 없음

| 코드 조건 (`stratified_main.py`) | 논문·KG | SSC 2021 (로컬 원문) | 가장 가까운 출처 | 판정 |
|---|---|---|---|---|
| 젖산 > 4 (한 번이라도) | 논문 > 4.0 · KG ≥ 4 | 수치 없음 (1.6~2.5 는 선별 연구 범위) | **SSC 2012**: "lactate ≥ 4 mmol/L" 이면 초기 소생술 시작 | 일치 (SSC 2012 · 논문) |
| 젖산 안 떨어짐 (> 2 포함) | 논문 개념만 | 치료 목표로 젖산 감소 권고 | **Sepsis-3** 패혈성 쇼크: 젖산 > 2 mmol/L | 부분 (쇼크 정의의 값) |
| 빌리루빈 ≥ 2 | KG ≥ 2 | 없음 | **SSC 2012** 중증 패혈증: > 2 mg/dL · **SOFA** 간 2점: 2.0–5.9 | 일치 (경계 ≥/>) |
| 혈소판 < 50 (모든 시점) | KG ≤ 50 | 없음 | **SOFA** 응고 3점: < 50 ×10³/µL (SSC 2012 는 < 100) | 일치 (SOFA) |
| CRP ≥ 100 | KG ≥ 100 | 없음 | SSC 2012: "정상치 +2 SD 초과" (숫자 없음) | 없음 |
| 백혈구 > 30 | KG ≥ 30 | 없음 | SSC 2012: > 12,000 · APACHE II: 20–39.9 / ≥ 40 구간 | 없음 |
| 나이 > 65 | KG ≥ 65 (결과 = Sepsis) | 65세 이상 대상 MAP 시험 언급 (위험인자 진술 아님) | APACHE II 나이 65–74 구간 시작 · CURB-65 나이 ≥ 65 (*) | 부분 |
| 평균혈압 < 65 (정의만, 안 씀) | 논문 LowMAP · KG ≤ 65 | **초기 목표 MAP 65** (치료 목표) | Sepsis-3 쇼크: MAP ≥ 65 유지에 승압제 필요 · SOFA 심혈관 1점: MAP < 70 | 부분 (치료 목표값) |
| **GCS < 8** (앵커만) | 없음 | qSOFA: GCS < 15 | **SOFA** 신경 3점: 6–9 · 외상 중증 두부손상/기관삽관 기준 **GCS ≤ 8** (*) | 부분 (≤ 8 을 < 8 로?) |
| **수축기혈압 ≤ 100** (앵커만) | 없음 | **qSOFA ≤ 100 mmHg** | Sepsis-3 qSOFA ≤ 100 · **MEWS** 81–100 = 1점 | **일치 (qSOFA)** |
| **호흡수 ≥ 29 또는 < 9 (모든 시점)** (앵커만) | 없음 | qSOFA: ≥ 22 | **MEWS**: < 9 = 2점 · 21–29 = 2점 · ≥ 30 = 3점 | 부분 (< 9 일치, ≥ 29 는 ≥ 30 과 1 차이) |
| **크레아티닌 ≥ 1.5 (모든 시점)** (앵커만) | 없음 | 수치 없음 (RRT 시험 대상 AKI 정의: 기준치 3배 + 0.5 mg/dL 상승) | **APACHE II** 1.5–1.9 = +2점 · SOFA 1.2–1.9 / 2.0–3.4 · SSC 2012 > 2.0 · KDIGO 기준치 1.5배(상대값) | 부분 (APACHE II 구간 하한) |
| 혈당 > 100 (버그로 미사용) | 없음 | 인슐린 시작 ≥ 180 mg/dL | SSC 2012 고혈당: > 140 mg/dL | 없음 |

(*) 검색 결과 요약으로만 확인 — 원문 표를 직접 보지 못함.

## 3. 결론

1. **코드에만 있는 임계값은 SSC 2021 이 아니라 여러 중증도 점수에서 온 것으로 보인다.**
   - 수축기혈압 ≤ 100 → **qSOFA** (SSC 2021·Sepsis-3에 그대로 있음) — 저장소 `main.py` 도 이 조합을 "qSOFA"라 부른다.
   - 호흡수 < 9 · 수축기혈압 주석 → **MEWS** (코드 주석 `# mews score risk`). 호흡수 ≥ 29 는 MEWS 3점(≥ 30)과 1 차이 — "> 29"를 옮기다 경계가 바뀐 것으로 추정.
   - 혈소판 < 50 · 빌리루빈 2 → **SOFA** / SSC 2012 · 젖산 4 → **SSC 2012**(이전 판).
   - 크레아티닌 1.5 → **APACHE II** 구간 하한과만 같다. GCS < 8 → 외상의 "GCS ≤ 8" 관행과 가깝지만 부등호가 다르다.
2. **호흡수 · 수축기혈압은 이름은 qSOFA, 값은 qSOFA 와 MEWS 가 섞여 있다.** qSOFA 호흡수 기준은 ≥ 22 인데 코드는 ≥ 29 / < 9 이고, "3개 중 2개 동시"가 아니라 "호흡수(모든 시점) 그리고 수축기혈압(한 번이라도)"이다.
3. **CRP ≥ 100 · 백혈구 > 30 · 혈당 > 100 은 대조한 가이드라인·점수 어디에도 같은 값이 없다.** CRP·백혈구는 손으로 쓴 KG 에만 있다.
4. 따라서 논문의 "가이드라인 → KG → 규칙 채굴 → FOL 공리" 중 **임계값은 SSC 2021 도 채굴도 아닌, 저자가 SOFA·qSOFA·MEWS·APACHE II·SSC 2012 등을 참고해 직접 정한 값**으로 보는 것이 가장 일관된다. 논문과 코드 어디에도 출처가 적혀 있지 않아 **확정은 저자 확인이 필요**하다.

## 한계
- 값이 같다는 것만으로 출처라고 단정할 수 없다 (임상에서 흔한 기준값이 여러 점수에 겹침).
- 원문 직접 확인: 논문 PDF · SSC 2021(로컬) · Sepsis-3(SOFA·qSOFA·쇼크 정의, PMC) · SSC 2012 진단 기준(PMC).
  2차 출처 확인: MEWS(PMC 논문의 표) · APACHE II(Merck Manual 표).
  검색 요약만: CURB-65 나이 ≥ 65 · 외상 GCS ≤ 8 · APACHE II 나이 구간.
- 원저자 저장소의 커밋 이력은 보지 않았다.

## 출처
- 논문: De Santis et al., EAAI 177 (2026) 114920 (로컬 PDF)
- SSC 2021: Evans et al., 2021 (`NeSy-SMP/pipeline_out/ssc2021_guideline.txt`)
- Sepsis-3 (SOFA 표·qSOFA·패혈성 쇼크): https://pmc.ncbi.nlm.nih.gov/articles/PMC4968574/
- SSC 2012 (Dellinger et al.): https://pmc.ncbi.nlm.nih.gov/articles/PMC7095153/
- MEWS 표: https://pmc.ncbi.nlm.nih.gov/articles/PMC12372822/ (원전 Subbe et al., QJM 2001)
- APACHE II 표: https://www.merckmanuals.com/professional/multimedia/table/acute-physiologic-assessment-and-chronic-health-evaluation-apache-ii-scoring-system
- 외상 GCS ≤ 8: https://pmc.ncbi.nlm.nih.gov/articles/PMC4091894/ (검색 요약)
- CURB-65: https://en.wikipedia.org/wiki/CURB-65 (검색 요약)
