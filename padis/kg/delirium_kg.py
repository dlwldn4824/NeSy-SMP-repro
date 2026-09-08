from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import RDF, RDFS, OWL, XSD
from utils import visualize

CKG = Namespace("http://example.org/clinical-guideline/")
SNOMED = Namespace("http://snomed.info/id/")
SCHEMA = Namespace("https://schema.org/")

g = Graph()

g.bind("snomed", SNOMED)
g.bind("rdf", RDF)
g.bind("rdfs", RDFS)
g.bind("owl", OWL)
g.bind("xsd", XSD)          # sepsis 코드의 "sct" 이중 bind 수정
g.bind("schema", SCHEMA)
g.bind("ckg", CKG)

# ---------------------------------------------------------------
# 스키마 정의 (술어 4개 + 근거등급 주석)
#  - SCHEMA.increasesRiskOf : 위험 증가 (sepsis 코드와 동일, 오타 통일)
#  - CKG.decreasesRiskOf    : 위험 감소 (중재 권고용, 신규)
#  - CKG.hasNoEffectOn      : 영향 없음 명시 (마이닝 규칙 필터용, 신규)
#  - CKG.precludes          : 평가 불능 가드 (구조적 결측용, 신규)
#  - CKG.evidenceLevel      : PADIS 근거등급 → 공리 가중치 매핑용 리터럴
# ---------------------------------------------------------------
g.add((CKG.decreasesRiskOf, RDF.type, OWL.ObjectProperty))
g.add((CKG.hasNoEffectOn, RDF.type, OWL.ObjectProperty))
g.add((CKG.precludes, RDF.type, OWL.ObjectProperty))
g.add((CKG.evidenceLevel, RDF.type, OWL.DatatypeProperty))

# Outcome
g.add((SNOMED.Delirium, RDFS.subClassOf, SNOMED.Outcome))          # SCTID 2776000
g.add((SNOMED.Patient, SNOMED.hasOutcome, SNOMED.Delirium))

# ---------------------------------------------------------------
# 1. 위험인자 — 강한 근거 (2018 PADIS, Ungraded Statement/strong)
# ---------------------------------------------------------------
# modifiable
g.add((SNOMED.BenzodiazepineUse, RDFS.subClassOf, SNOMED.RiskFactor))   # 벤조디아제핀 투여
g.add((SNOMED.BenzodiazepineUse, SCHEMA.increasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.BenzodiazepineUse, CKG.evidenceLevel, Literal("strong")))

g.add((SNOMED.BloodTransfusion, RDFS.subClassOf, SNOMED.RiskFactor))    # 수혈, SCTID 116859006
g.add((SNOMED.BloodTransfusion, SCHEMA.increasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.BloodTransfusion, CKG.evidenceLevel, Literal("strong")))

# nonmodifiable
g.add((SNOMED.Age, RDFS.subClassOf, SNOMED.RiskFactor))                 # 고령
g.add((SNOMED.Age, SCHEMA.increasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.Age, SCHEMA.greaterOrEqual, Literal(65, datatype=XSD.integer)))
g.add((SNOMED.Age, CKG.evidenceLevel, Literal("strong")))

g.add((SNOMED.Dementia, RDFS.subClassOf, SNOMED.RiskFactor))            # 치매, SCTID 52448006
g.add((SNOMED.Dementia, RDFS.subClassOf, SNOMED.Comorbidity))
g.add((SNOMED.Dementia, SCHEMA.increasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.Dementia, CKG.evidenceLevel, Literal("strong")))

g.add((SNOMED.PriorComa, RDFS.subClassOf, SNOMED.RiskFactor))           # 선행 혼수, SCTID 371632003
g.add((SNOMED.PriorComa, SCHEMA.increasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.PriorComa, CKG.evidenceLevel, Literal("strong")))

g.add((SNOMED.EmergencySurgery, RDFS.subClassOf, SNOMED.RiskFactor))    # ICU 전 응급수술
g.add((SNOMED.EmergencySurgery, SCHEMA.increasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.EmergencySurgery, CKG.evidenceLevel, Literal("strong")))

g.add((SNOMED.Trauma, RDFS.subClassOf, SNOMED.RiskFactor))              # 외상, SCTID 417746004
g.add((SNOMED.Trauma, SCHEMA.increasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.Trauma, CKG.evidenceLevel, Literal("strong")))

g.add((SNOMED.APACHEScore, RDFS.subClassOf, SNOMED.RiskFactor))         # 중증도 점수 상승
g.add((SNOMED.APACHEScore, SCHEMA.increasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.APACHEScore, CKG.evidenceLevel, Literal("strong")))

# ---------------------------------------------------------------
# 2. 위험인자 — 중간 근거 (2018 PADIS, moderate)
# ---------------------------------------------------------------
g.add((SNOMED.Hypertension, RDFS.subClassOf, SNOMED.RiskFactor))        # 고혈압 병력, SCTID 38341003
g.add((SNOMED.Hypertension, RDFS.subClassOf, SNOMED.Comorbidity))
g.add((SNOMED.Hypertension, SCHEMA.increasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.Hypertension, CKG.evidenceLevel, Literal("moderate")))

g.add((SNOMED.NeurologicAdmission, RDFS.subClassOf, SNOMED.RiskFactor)) # 신경계 질환 입원
g.add((SNOMED.NeurologicAdmission, SCHEMA.increasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.NeurologicAdmission, CKG.evidenceLevel, Literal("moderate")))

g.add((SNOMED.PsychoactiveMedication, RDFS.subClassOf, SNOMED.RiskFactor))  # 향정신성 약물
g.add((SNOMED.PsychoactiveMedication, SCHEMA.increasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.PsychoactiveMedication, CKG.evidenceLevel, Literal("moderate")))

# 깊은 진정 (2018: 얕은 진정 권고의 대우, Conditional/low)
g.add((SNOMED.DeepSedation, RDFS.subClassOf, SNOMED.RiskFactor))        # RASS <= -4
g.add((SNOMED.DeepSedation, SCHEMA.increasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.DeepSedation, SCHEMA.lessOrEqual, Literal(-4, datatype=XSD.integer)))
g.add((SNOMED.DeepSedation, CKG.evidenceLevel, Literal("low")))

# ---------------------------------------------------------------
# 3. 보호인자 — 중재 권고 (2025 Focused Update)
# ---------------------------------------------------------------
g.add((SNOMED.Dexmedetomidine, RDFS.subClassOf, SNOMED.ProtectiveFactor))  # SCTID 437750002
g.add((SNOMED.Dexmedetomidine, CKG.decreasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.Dexmedetomidine, CKG.evidenceLevel, Literal("moderate")))
# 주의: 원 권고는 "propofol 대비" 비교형 -> flat triple로는 comparator 표현 불가 (한계로 기록)

g.add((SNOMED.EnhancedMobilization, RDFS.subClassOf, SNOMED.ProtectiveFactor))  # 조기 재활/이동
g.add((SNOMED.EnhancedMobilization, CKG.decreasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.EnhancedMobilization, CKG.evidenceLevel, Literal("low")))
# 주의: 원 권고의 outcome은 발생이 아니라 "기간(duration) 감소"

g.add((SNOMED.Melatonin, RDFS.subClassOf, SNOMED.ProtectiveFactor))     # SCTID 41199001
g.add((SNOMED.Melatonin, CKG.decreasesRiskOf, SNOMED.Delirium))
g.add((SNOMED.Melatonin, CKG.evidenceLevel, Literal("low")))

# ---------------------------------------------------------------
# 4. 영향 없음 — 명시적 null (2018 PADIS, strong) : 마이닝 규칙 거부 필터
# ---------------------------------------------------------------
g.add((SNOMED.PatientSex, CKG.hasNoEffectOn, SNOMED.Delirium))
g.add((SNOMED.OpioidUse, CKG.hasNoEffectOn, SNOMED.Delirium))
g.add((SNOMED.MechanicalVentilation, CKG.hasNoEffectOn, SNOMED.Delirium))  # SCTID 40617009
g.add((SNOMED.PatientSex, CKG.evidenceLevel, Literal("strong")))
g.add((SNOMED.OpioidUse, CKG.evidenceLevel, Literal("strong")))
g.add((SNOMED.MechanicalVentilation, CKG.evidenceLevel, Literal("strong")))

# ---------------------------------------------------------------
# 5. 구조적 결측 가드 — 깊은 진정 중에는 CAM-ICU 평가 불가
# ---------------------------------------------------------------
g.add((SNOMED.DeliriumAssessment, RDF.type, OWL.Class))                 # CAM-ICU/ICDSC
g.add((SNOMED.DeepSedation, CKG.precludes, SNOMED.DeliriumAssessment))

visualize(g)
