"""delirium/ 의 단계 스크립트를 한 파일로 묶는다. 원본 코드는 한 글자도 바꾸지 않고 문자열로 넣는다."""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
OUT = ROOT / "delirium" / "43_padis_delirium_all.py"
MODULES = [("_extra_features", "delirium/_extra_features.py"),
           ("build_comorbidities_icd", "NeSy-SMP/data/build_comorbidities_icd.py"),
           ("_kg_to_axioms", "delirium/42_kg_to_axioms.py")]
STEPS = [("00", "delirium/00_extract.py", "MIMIC → ICU 기본 테이블 · CAM-ICU 라벨 · RASS/진정제"),
         ("24", "delirium/24_extract_mobility_pain_gcs.py", "거동 · 통증 · GCS"),
         ("25", "delirium/25_extract_axiom_gaps.py", "치매 · 외상 · 고혈압 · 수혈 (공리 개념)"),
         ("22", "delirium/22_stage2_xgb.py", "XGBoost 기준선 (23 결과표가 읽는다)"),
         ("23", "delirium/23_stage34_bilstm_cbm.py", "BiLSTM · CBM · LTN(PADIS 공리) 학습")]

HEAD = '''# -*- coding: utf-8 -*-
# ============================================================================
# PADIS 섬망 예측 — 데이터 추출부터 학습까지 한 파일
#
#   이 파일 하나만 있으면 된다. 아래 두 줄(MIMIC_DB, WORK_DIR)만 고치고 실행한다.
#       python 43_padis_delirium_all.py
#   이미 끝난 단계는 START 를 바꿔 건너뛴다 (예: START = "22").
#
#   단계 (각 단계 원본 코드를 그대로 넣었다 — delirium/ 의 같은 이름 파일과 동일)
{steps}
#
#   필요 패키지: numpy pandas pyarrow scikit-learn xgboost torch
#   결과: WORK_DIR/out_split/
#
#   이 파일은 생성물이다. 고칠 때는 원본 파일을 고치고 다시 묶는다: python delirium/_bundle_43.py .
# ============================================================================
import os
import sys
import time
import types

# ===== 여기만 고치세요 =====================================================
MIMIC_DB = "C:/path/to/MIMIC4-hosp-icu.db"    # MIMIC-IV sqlite 파일 (슬래시로)
WORK_DIR = "padis_work"                       # 중간 파일·결과를 쌓을 폴더
START = "00"                                  # 이 단계부터 실행: 00 24 25 22 23
KG_JSON = []                                  # 추출한 KG 트리플 JSON. 비우면 기본 공리 12개
                                              #   예: ["triples_one.json"] · 여러 개면 합집합
# ==========================================================================
# 파일을 고치지 않고 환경변수로도 지정할 수 있다 (생성물이라 가급적 이쪽을 쓴다):
#   START=23  KG_JSON="a.json;b.json"  EDA_DATA=<폴더>  EDA_SQLITE=<db>
START = os.environ.get("START", START)
KG_JSON = [p for p in os.environ.get("KG_JSON", "").split(";") if p] or KG_JSON

os.environ.setdefault("EDA_SRC_MODE", "sqlite")
os.environ.setdefault("EDA_SQLITE", MIMIC_DB)
os.environ.setdefault("EDA_DATA", WORK_DIR)
os.makedirs(os.environ["EDA_DATA"], exist_ok=True)
# EDA_DATA 가 셸에 이미 있으면 WORK_DIR 은 무시된다 — 실제로 쓰는 폴더를 찍어 둔다.
print(f"[설정] 데이터 폴더 {{os.environ['EDA_DATA']}} · 결과 "
      f"{{os.environ.get('EDA_OUT') or os.path.join(os.environ['EDA_DATA'], 'out_split')}} · START={{START}}"
      + (f" · KG_JSON={{KG_JSON}}" if KG_JSON else ""), flush=True)


def _module(name, src):
    """원본에서 import 하던 보조 모듈을 이 파일 안에서 만든다."""
    m = types.ModuleType(name)
    m.__file__ = __file__
    sys.modules[name] = m
    exec(compile(src, name + ".py", "exec"), m.__dict__)


# 23 단계의 공리 목록(AXIOMS)을 KG_JSON 에서 만든 공리로 바꾼다. 원본 코드는 그대로, 실행 직전에 끼운다.
_KG_HOOK = """
if KG_JSON:
    from _kg_to_axioms import load_triples, compile_kg
    _ax, _dr, _um = compile_kg(load_triples(KG_JSON))
    AXIOMS = [(a["name"], a["concept"], a["sign"],
               0.5 if a["binary"] else _zthr(a["concept"], a["threshold"]),
               a["head"], a["negated_head"], a["grade"])
              for a in _ax if a["concept"] in CI and (a["head"] == "Delirium" or a["head"] in CI)]
    print(f"[KG] {{KG_JSON}} -> 공리 {{len(AXIOMS)}}개 사용 (변환 {{len(_ax)}} · 섬망 모델에 없는 개념/출력 제외)")
    for _a in AXIOMS:
        print("   ", _a[0], _a[6])
"""
_AX_LINE = "AX_W = torch.tensor([GRADE_W[a[6]] for a in AXIOMS], dtype=torch.float32)"


def _step(name, src):
    """단계마다 새 이름공간에서 실행한다 — 단계끼리 변수가 섞이지 않는다."""
    print(f"\\n===== [{{name}}] =====", flush=True)
    t0 = time.time()
    if name.startswith("23_"):
        assert src.count(_AX_LINE) == 1
        src = src.replace(_AX_LINE, _KG_HOOK + _AX_LINE)
    exec(compile(src, name, "exec"), {{"__name__": "__main__", "__file__": __file__, "KG_JSON": KG_JSON}})
    print(f"===== [{{name}}] 완료 {{time.time() - t0:.0f}}s =====", flush=True)

'''

parts = [HEAD.format(steps="\n".join(f"#     {s}  {Path(p).name:34s} {d}" for s, p, d in STEPS))]
for name, path in MODULES:
    src = (ROOT / path).read_text(encoding="utf-8")
    assert "'''" not in src and not src.rstrip().endswith("\\")
    parts.append(f"# {'=' * 76}\n# 보조 모듈: {path}\n# {'=' * 76}\n"
                 f"_module({name!r}, r'''{src}''')\n\n")
parts.append("_SRC = {}\n\n")
for s, path, d in STEPS:
    src = (ROOT / path).read_text(encoding="utf-8")
    assert "'''" not in src and not src.rstrip().endswith("\\")
    parts.append(f"# {'=' * 76}\n# [{s}] {path} — {d}\n# {'=' * 76}\n"
                 f"_SRC[{s!r}] = ({Path(path).name!r}, r'''{src}''')\n\n")
parts.append('''# ============================================================================
# 실행
# ============================================================================
_ORDER = ["00", "24", "25", "22", "23"]
for _s in _ORDER[_ORDER.index(START):]:
    _step(*_SRC[_s])
print(f"\\n완료. 결과: {os.path.join(os.environ['EDA_DATA'], 'out_split')}")
''')
OUT.write_text("".join(parts), encoding="utf-8")
print(OUT, sum(p.count("\n") for p in parts), "lines")
