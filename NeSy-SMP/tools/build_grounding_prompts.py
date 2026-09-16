"""연결 명세(grounding spec) 추출 소규모 시험 — 프롬프트 생성.

입력 조각 4개 (모두 로컬 파일):
  Q  SSC 2021 권고 2 (qSOFA 변수 3개)          pipeline_out/ssc2021_guideline.txt 126-136
  L  SSC 2021 권고 3 (젖산 측정)               164-199
  M  SSC 2021 권고 9 (평균동맥압 목표)          355-379 (마지막 완결 문장까지)
  K  원저자 KG create_ckg.py 트리플 부분       '# Patient' ~ visualize(g) 전
출력: tools/grounding_prompt_{Q,L,M,K}.txt
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SSC = (ROOT / "pipeline_out" / "ssc2021_guideline.txt").read_text(encoding="utf-8").splitlines()
SCHEMA = json.loads((ROOT / "configs" / "grounding_spec_schema.json").read_text(encoding="utf-8"))


def ssc(a, b):
    text = " ".join(l.strip() for l in SSC[a - 1:b])
    text = re.sub(r"(\w) ?- (\w)", r"\1\2", text)  # PDF 줄끝 하이픈 연결
    return text[: text.rfind(". ") + 1] if not text.rstrip().endswith(".") else text.rstrip()


ckg = (ROOT / "create_ckg.py").read_text(encoding="utf-8").splitlines()
k0 = next(i for i, l in enumerate(ckg) if l.startswith("# Patient"))
k1 = next(i for i, l in enumerate(ckg) if l.startswith("visualize("))
CHUNKS = {
    "Q": ("Surviving Sepsis Campaign 2021 가이드라인 본문 — 권고 2", ssc(126, 136)),
    "L": ("Surviving Sepsis Campaign 2021 가이드라인 본문 — 권고 3", ssc(164, 199)),
    "M": ("Surviving Sepsis Campaign 2021 가이드라인 본문 — 권고 9", ssc(355, 379)),
    "K": ("원 논문 저자가 작성한 sepsis 지식그래프 (Python rdflib 코드, 트리플 부분)", "\n".join(ckg[k0:k1]).strip()),
}

catalog = "\n".join(f"- {v['feature']}  [{v['unit']}]" for v in SCHEMA["variable_catalog"])
fields = json.dumps(SCHEMA["spec_fields"], ensure_ascii=False, indent=1)

TEMPLATE = """당신은 임상 지식(가이드라인 문장 또는 지식그래프)을 환자 데이터에서 실행할 수 있는 조건 명세(grounding spec)로 옮깁니다.
입력: {desc}

## 출력 형식
JSON 배열만 출력하세요. 설명·마크다운 금지. 명세로 옮길 것이 없으면 [] 를 출력하세요.
각 원소는 아래 필드를 모두 가집니다 (값이 없으면 null):
{fields}

## 변수 카탈로그 (variable 은 반드시 이 이름 중 하나 또는 null)
{catalog}

## 규칙
1. **입력에 적힌 것만 채우세요.** 입력에 없는 연산자·임계값·단위·시간 창·집계 방식·결측 처리는 추측하지 말고 null 로 두고 provenance 를 "unspecified" 로 적으세요.
   - 흔히 쓰는 기준(예: 임상 상식, 다른 가이드라인, SOFA 점수표)을 알고 있어도 입력에 없으면 쓰지 마세요.
   - variable 을 카탈로그에서 골랐고 입력에 변수 이름이 직접 없으면 provenance.variable = "catalog". unit 을 카탈로그에서 가져왔으면 provenance.unit = "catalog".
2. 원문이 임계값을 하나로 정하지 않고 범위만 주면(예: "기준이 a~b 로 다양했다") threshold = [a, b], operator = null 로 두고 note 에 적으세요. 하나를 고르지 마세요.
3. statement_type:
   - risk_condition: 환자 상태가 결과(사망 등)의 위험·예측과 연결됨
   - diagnostic_criterion: 진단·정의·선별 기준
   - treatment_target: 치료 목표값·치료 방법 (환자 위험 조건으로 바꾸지 마세요)
   - not_groundable: 개념은 있으나 카탈로그 변수로 조건을 만들 수 없음 (variable = null)
4. 여러 조건 중 n 개 이상일 때 성립하는 규칙이면 각 조건을 따로 적고 combine 에 같은 group, min_count, simultaneous 를 적으세요.
5. evidence 는 입력에서 그대로 복사하세요 (지식그래프 입력이면 해당 코드 줄들을 그대로). 요약·번역·합성 금지.
6. 지식그래프 입력이면: 임계값이 붙은 개념, 결과(Death/Sepsis 등)와 연결된 개념만 명세로 옮기세요. 속성 선언(domain/range)만 있고 조건이 없는 것은 옮기지 마세요. 결과 개념 자체(Death, Outcome, Patient 등)는 옮기지 마세요.
7. consequent.object 는 입력이 말하는 결과를 그대로 쓰세요 (입력이 Sepsis 라고 하면 Death 로 바꾸지 마세요).

## 입력
{text}
"""

for key, (desc, text) in CHUNKS.items():
    out = ROOT / "tools" / f"grounding_prompt_{key}.txt"
    out.write_text(TEMPLATE.format(desc=desc, fields=fields, catalog=catalog, text=text), encoding="utf-8")
    (ROOT / "tools" / f"grounding_chunk_{key}.txt").write_text(text, encoding="utf-8")
    print(key, len(text), "chars →", out.name)
