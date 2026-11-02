# -*- coding: utf-8 -*-
# ============================================================================
# PADIS 섬망 예측 — 데이터 추출부터 학습까지 한 파일
#
#   이 파일 하나만 있으면 된다. 아래 두 줄(MIMIC_DB, WORK_DIR)만 고치고 실행한다.
#       python 43_padis_delirium_all.py
#   이미 끝난 단계는 START 를 바꿔 건너뛴다 (예: START = "22").
#
#   단계 (각 단계 원본 코드를 그대로 넣었다 — delirium/ 의 같은 이름 파일과 동일)
#     00  00_extract.py                      MIMIC → ICU 기본 테이블 · CAM-ICU 라벨 · RASS/진정제
#     24  24_extract_mobility_pain_gcs.py    거동 · 통증 · GCS
#     25  25_extract_axiom_gaps.py           치매 · 외상 · 고혈압 · 수혈 (공리 개념)
#     22  22_stage2_xgb.py                   XGBoost 기준선 (23 결과표가 읽는다)
#     23  23_stage34_bilstm_cbm.py           BiLSTM · CBM · LTN(PADIS 공리) 학습
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
print(f"[설정] 데이터 폴더 {os.environ['EDA_DATA']} · 결과 "
      f"{os.environ.get('EDA_OUT') or os.path.join(os.environ['EDA_DATA'], 'out_split')} · START={START}"
      + (f" · KG_JSON={KG_JSON}" if KG_JSON else ""), flush=True)


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
    print(f"[KG] {KG_JSON} -> 공리 {len(AXIOMS)}개 사용 (변환 {len(_ax)} · 섬망 모델에 없는 개념/출력 제외)")
    for _a in AXIOMS:
        print("   ", _a[0], _a[6])
"""
_AX_LINE = "AX_W = torch.tensor([GRADE_W[a[6]] for a in AXIOMS], dtype=torch.float32)"


def _step(name, src):
    """단계마다 새 이름공간에서 실행한다 — 단계끼리 변수가 섞이지 않는다."""
    print(f"\n===== [{name}] =====", flush=True)
    t0 = time.time()
    if name.startswith("23_"):
        assert src.count(_AX_LINE) == 1
        src = src.replace(_AX_LINE, _KG_HOOK + _AX_LINE)
    exec(compile(src, name, "exec"), {"__name__": "__main__", "__file__": __file__, "KG_JSON": KG_JSON})
    print(f"===== [{name}] 완료 {time.time() - t0:.0f}s =====", flush=True)

# ============================================================================
# 보조 모듈: delirium/_extra_features.py
# ============================================================================
_module('_extra_features', r'''# -*- coding: utf-8 -*-
"""_extra_values.parquet (24_ 산출물) 을 앵커별 시계열 채널로 만든다.

22_(XGB) 와 23_(BiLSTM/CBM) 이 같은 정의를 쓰도록 여기 한 군데에 둔다.
요약 피처는 이 텐서에서 파생하므로 두 단계의 입력 정의가 어긋날 일이 없다.

24_ 출력에서 itemid 별 척도를 확인한 뒤 쓸 것만 골랐다:
  GCS      220739 eye(1-4) · 223900 verbal(1-5) · 223901 motor(1-6)   커버 100%
  MOBILITY 224057 Braden 이동성(1-4, stay 99.9%) · 229321 JH-HLM(1-8, stay 55%)
           229633 은 값이 16~57 로 다른 측정이라 제외. 228697/229319/229742 는 표본 과소.
  PAIN     223791 + 224409 의 valuenum(0-10)만 NRS 로 본다.
           223794 "Yes/Tolerable" 는 다른 구성개념이라 값이 아니라 관측 플래그로만.
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

# (이름, itemid 목록) — 값 채널
FEATS = [
    ("gcs_eye", [220739]),
    ("gcs_verbal", [223900]),
    ("gcs_motor", [223901]),
    ("mob_braden", [224057]),
    ("mob_jhhlm", [229321]),
    ("pain_nrs", [223791, 224409]),
]
PAIN_CAT = [223794, 230144]          # 값 없이 '통증 평가 시도' 관측 플래그로만


def build_extra_channels(data_dir, stay_ids, anchor_hr, first, cnt, nbin=24, lookback=24.0):
    """앵커별 (n, nbin, C) 텐서를 만든다.

    채널 순서: 각 FEATS 마다 [값 평균, 관측여부] 2개, 마지막에 통증평가시도 1개.
    stay_ids/anchor_hr 는 stay 별로 정렬돼 있어야 하고 first/cnt 은 그 블록 인덱스다.
    파일이 없으면 (None, []) 를 돌려준다 — 호출부가 건너뛸 수 있게.
    """
    path = os.path.join(data_dir, "_extra_values.parquet")
    if not os.path.exists(path):
        return None, []

    d = pd.read_parquet(path, columns=["stay_id", "itemid", "hr", "valuenum"])
    d = d[d.valuenum.notna()]
    n_anchor = len(anchor_hr)
    C = len(FEATS) * 2 + 1
    X = np.zeros((n_anchor, nbin, C), dtype=np.float32)
    edges = np.linspace(-lookback, 0.0, nbin + 1)

    names = []
    for nm, _ in FEATS:
        names += [nm, f"{nm}_obs"]
    names.append("pain_attempt")

    def _per_stay(sub):
        g = {}
        for k, gg in sub.groupby("stay_id", sort=False):
            gg = gg.sort_values("hr")
            g[k] = (gg["hr"].to_numpy(np.float64), gg["valuenum"].to_numpy(np.float64))
        return g

    banks = [_per_stay(d[d.itemid.isin(ids)]) for _, ids in FEATS]

    dp = pd.read_parquet(path, columns=["stay_id", "itemid", "hr"])
    dp = dp[dp.itemid.isin(PAIN_CAT)]
    bank_pain = {}
    for k, gg in dp.groupby("stay_id", sort=False):
        bank_pain[k] = np.sort(gg["hr"].to_numpy(np.float64))

    for a, n in zip(first, cnt):
        sid = stay_ids[a]
        hh = anchor_hr[a:a + n]
        rel = hh[:, None] + edges[None, :]
        for fi, bank in enumerate(banks):
            got = bank.get(sid)
            if got is None:
                continue
            hs, vs = got
            csum = np.concatenate([[0.0], np.cumsum(vs)])
            bnd = np.searchsorted(hs, rel, side="left")
            lo, hi = bnd[:, :-1], bnd[:, 1:]
            k_ = hi - lo
            with np.errstate(invalid="ignore", divide="ignore"):
                mean = np.where(k_ > 0, (csum[hi] - csum[lo]) / np.maximum(k_, 1), 0.0)
            X[a:a + n, :, fi * 2] = mean
            X[a:a + n, :, fi * 2 + 1] = (k_ > 0)
        hs = bank_pain.get(sid)
        if hs is not None:
            bnd = np.searchsorted(hs, rel, side="left")
            X[a:a + n, :, -1] = (bnd[:, 1:] - bnd[:, :-1]) > 0
    return X, names


def summarize(X, names):
    """(n, nbin, C) 텐서에서 XGB 용 요약 피처를 만든다. 관측 없는 칸은 제외하고 집계."""
    out, cols = [], []
    n_val = (len(names) - 1) // 2
    for fi in range(n_val):
        nm = names[fi * 2]
        v = X[:, :, fi * 2]
        m = X[:, :, fi * 2 + 1] > 0
        cnt = m.sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(cnt > 0, (v * m).sum(1) / np.maximum(cnt, 1), np.nan)
        vmin = np.where(m, v, np.inf).min(1)
        vmax = np.where(m, v, -np.inf).max(1)
        vmin[~np.isfinite(vmin)] = np.nan
        vmax[~np.isfinite(vmax)] = np.nan
        # last: 관측이 있는 마지막 칸
        idx = np.where(m.any(1), nbin_last(m), -1)
        last = np.where(idx >= 0, v[np.arange(len(v)), np.maximum(idx, 0)], np.nan)
        out += [mean, vmin, vmax, last, cnt.astype(np.float32)]
        cols += [f"{nm}_mean", f"{nm}_min", f"{nm}_max", f"{nm}_last", f"{nm}_n"]
    out.append(X[:, :, -1].max(1))
    cols.append("pain_attempt_any")
    return np.stack(out, 1).astype(np.float32), cols


def nbin_last(m):
    """행마다 True 인 마지막 열 인덱스."""
    nb = m.shape[1]
    return nb - 1 - np.argmax(m[:, ::-1], axis=1)
''')

# ============================================================================
# 보조 모듈: NeSy-SMP/data/build_comorbidities_icd.py
# ============================================================================
_module('build_comorbidities_icd', r'''"""Build comorbidities one-hot from MIMIC diagnoses_icd (ICD proxy).

Paper uses notes NLP (spaCy/medspaCy). Local hosp-icu DB has no note tables and
notes zip is not present, so we map ICD-9/10 codes (+ diagnosis titles) onto the
same 23 comorbidity labels expected by preprocessing.py / models.py.

Output long format compatible with upstream extract_comorbidities.py:
  subject_id,hadm_id,age,comorbidity
and a wide one-hot CSV for easy merge into events_*_wide CSV.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

import pandas as pd

COMORBIDITIES = [
    "acute kidney injury",
    "aids",
    "atrial fibrillation",
    "cad",
    "cancer",
    "cerebrovascular accident",
    "cirrhosis",
    "copd",
    "dementia",
    "diabetes",
    "diabetes mellitus",
    "heart failure",
    "hiv",
    "hypertension",
    "kidney disease",
    "kidney failure",
    "leukemia",
    "lymphoma",
    "metastatic cancer",
    "metastatic disease",
    "peptic ulcer disease",
    "pneumonia",
    "trauma",
]

# (label, icd10 prefixes, icd9 prefixes/codes, title keywords)
RULES: list[tuple[str, list[str], list[str], list[str]]] = [
    ("acute kidney injury", ["N17"], ["584"], ["acute kidney injury", "acute renal failure"]),
    ("kidney failure", ["N18", "N19"], ["585", "586"], ["chronic kidney", "end stage renal", "renal failure"]),
    ("kidney disease", ["N18", "N19", "N28"], ["585", "586", "593"], ["kidney disease", "renal disease", "ckd"]),
    ("aids", ["B20"], ["042"], ["aids", "acquired immune deficiency"]),
    ("hiv", ["B20", "Z21", "B97.35"], ["042", "V08"], ["human immunodeficiency", "hiv"]),
    ("atrial fibrillation", ["I48"], ["4273"], ["atrial fibrillation", "atrial flutter"]),
    ("cad", ["I20", "I21", "I22", "I23", "I24", "I25"], ["410", "411", "412", "413", "414"], ["coronary", "atherosclerotic heart", "cad"]),
    ("heart failure", ["I50"], ["428"], ["heart failure", "congestive heart"]),
    ("hypertension", ["I10", "I11", "I12", "I13", "I15", "I16"], ["401", "402", "403", "404", "405"], ["hypertension", "hypertensive"]),
    ("cirrhosis", ["K74", "K70.3"], ["5712", "5715", "5716"], ["cirrhosis"]),
    ("copd", ["J44"], ["491", "492", "496"], ["copd", "chronic obstructive"]),
    ("dementia", ["F01", "F02", "F03", "G30"], ["290", "2941", "3310"], ["dementia", "alzheimer"]),
    ("diabetes mellitus", ["E10", "E11", "E13"], ["250"], ["diabetes mellitus"]),
    ("diabetes", ["E10", "E11", "E13"], ["250"], ["diabetes"]),
    ("cerebrovascular accident", ["I60", "I61", "I62", "I63", "I64", "I65", "I66", "I67", "I69"], ["430", "431", "432", "433", "434", "435", "436", "437", "438"], ["stroke", "cerebrovascular", "cerebral infarction", "cva"]),
    ("peptic ulcer disease", ["K25", "K26", "K27", "K28"], ["531", "532", "533", "534"], ["peptic ulcer", "gastric ulcer", "duodenal ulcer"]),
    ("pneumonia", ["J12", "J13", "J14", "J15", "J16", "J17", "J18"], ["480", "481", "482", "483", "484", "485", "486"], ["pneumonia"]),
    ("leukemia", ["C91", "C92", "C93", "C94", "C95"], ["204", "205", "206", "207", "208"], ["leukemia"]),
    ("lymphoma", ["C81", "C82", "C83", "C84", "C85", "C86"], ["200", "201", "202"], ["lymphoma"]),
    ("metastatic cancer", ["C77", "C78", "C79"], ["196", "197", "198"], ["secondary malignant", "metastasis", "metastatic"]),
    ("metastatic disease", ["C77", "C78", "C79"], ["196", "197", "198"], ["secondary malignant", "metastasis", "metastatic"]),
    ("cancer", ["C"], ["14", "15", "16", "17", "18", "19", "20", "21"], ["malignant neoplasm", "cancer", "carcinoma"]),
    # trauma: injury chapter only (no bare "fracture" — that hits osteoporosis M81 etc.)
    ("trauma", [], [], ["traumatic injury", "multiple trauma", "traumatic fracture"]),
]


def connect_ro(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=600)


def norm_code(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(code)).upper()


def is_trauma_code(icd_version: int, code: str) -> bool:
    """Acute injury codes only; exclude late effects / personal history / pathologic fx."""
    c = norm_code(code)
    if int(icd_version) == 9:
        if not c.isdigit() or len(c) < 3:
            return False
        stem = int(c[:3])
        # ICD-9 injury 800-904 (exclude 905-909 late effects, 910-959 often superficial/toxic)
        return 800 <= stem <= 904
    # ICD-10: S00-S99, T07, T14, T79; exclude Z87 history, M80 pathologic fracture
    if c.startswith("Z87") or c.startswith("M80") or c.startswith("M81"):
        return False
    if c.startswith("S") and len(c) >= 3:
        try:
            return 0 <= int(c[1:3]) <= 99
        except ValueError:
            return False
    return c.startswith(("T07", "T14", "T79"))


def match_label(icd_version: int, code: str, title: str) -> set[str]:
    c = norm_code(code)
    t = (title or "").lower()
    hit: set[str] = set()

    if is_trauma_code(int(icd_version), code):
        hit.add("trauma")
    # title keywords alone for trauma (avoid bare "fracture")
    if any(k in t for k in ["traumatic injury", "multiple trauma", "traumatic fracture"]):
        if "pathologic" not in t and "osteoporosis" not in t:
            hit.add("trauma")

    for label, p10, p9, kws in RULES:
        if label == "trauma":
            continue
        if any(k in t for k in kws):
            hit.add(label)
            continue
        prefs = p10 if int(icd_version) == 10 else p9
        for p in prefs:
            pn = norm_code(p)
            if c.startswith(pn):
                # avoid overly broad cancer 'C' catching everything: require C00-C97-ish
                if label == "cancer" and int(icd_version) == 10:
                    if c.startswith("C") and len(c) >= 3:
                        try:
                            num = int(c[1:3])
                        except ValueError:
                            continue
                        if 0 <= num <= 96 and not c.startswith(("C77", "C78", "C79")):
                            hit.add(label)
                else:
                    hit.add(label)
                break
    return hit


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--cohort", type=Path, required=True, help="cohort CSV with hadm_id,subject_id,age")
    ap.add_argument("--out-long", type=Path, required=True)
    ap.add_argument("--out-wide", type=Path, required=True)
    args = ap.parse_args()

    cohort = pd.read_csv(args.cohort)
    hadm = set(cohort["hadm_id"].astype(int))
    print(f"cohort hadm={len(hadm):,}")

    con = connect_ro(args.db)
    try:
        dx = pd.read_sql(
            """
            SELECT d.subject_id, d.hadm_id, d.icd_code, d.icd_version,
                   COALESCE(t.long_title, '') AS long_title
            FROM diagnoses_icd d
            LEFT JOIN d_icd_diagnoses t
              ON d.icd_code = t.icd_code AND d.icd_version = t.icd_version
            """,
            con,
        )
    finally:
        con.close()

    dx["hadm_id"] = dx["hadm_id"].astype(int)
    dx = dx[dx["hadm_id"].isin(hadm)].copy()
    print(f"diagnoses rows in cohort: {len(dx):,}")

    rows = []
    for _, r in dx.iterrows():
        labels = match_label(int(r["icd_version"]), r["icd_code"], r["long_title"])
        for lab in labels:
            rows.append(
                {
                    "subject_id": int(r["subject_id"]),
                    "hadm_id": int(r["hadm_id"]),
                    "comorbidity": lab,
                }
            )
    long_df = pd.DataFrame(rows).drop_duplicates()
    # attach age from cohort
    age_col = "age" if "age" in cohort.columns else "anchor_age"
    long_df = long_df.merge(
        cohort[["hadm_id", "subject_id", age_col]].rename(columns={age_col: "age"}),
        on=["hadm_id", "subject_id"],
        how="left",
    )
    args.out_long.parent.mkdir(parents=True, exist_ok=True)
    long_df[["subject_id", "hadm_id", "age", "comorbidity"]].to_csv(args.out_long, index=False)
    print(f"wrote long {args.out_long} rows={len(long_df):,} hadm={long_df['hadm_id'].nunique():,}")

    # wide one-hot for all cohort hadm
    wide = cohort[["subject_id", "hadm_id"]].drop_duplicates().copy()
    for c in COMORBIDITIES:
        wide[c] = 0
    if len(long_df):
        for hadm_id, g in long_df.groupby("hadm_id"):
            labs = set(g["comorbidity"])
            idx = wide.index[wide["hadm_id"] == hadm_id]
            for lab in labs:
                if lab in COMORBIDITIES:
                    wide.loc[idx, lab] = 1
    args.out_wide.parent.mkdir(parents=True, exist_ok=True)
    wide.to_csv(args.out_wide, index=False)
    rates = {c: float(wide[c].mean()) for c in COMORBIDITIES}
    top = sorted(rates.items(), key=lambda x: -x[1])[:8]
    print(f"wrote wide {args.out_wide} n={len(wide):,}")
    print("top prevalence:", ", ".join(f"{k}={v:.1%}" for k, v in top))
    print(f"any comorbidity: {(wide[COMORBIDITIES].sum(axis=1) > 0).mean():.1%}")


if __name__ == "__main__":
    main()
''')

# ============================================================================
# 보조 모듈: delirium/42_kg_to_axioms.py
# ============================================================================
_module('_kg_to_axioms', r'''# -*- coding: utf-8 -*-
# ============================================================================
# KG 트리플 JSON → PADIS 공리 (33_kg_variants_v2.py 의 compile_kg 만 떼어낸 것)
#
#   입력: [{"subject", "predicate", "object"}, ...] 형식 JSON 파일 1개 이상 (여러 개면 합집합)
#   출력: 공리 목록 JSON + 23_stage34_bilstm_cbm.py 의 AXIOMS 자리에 붙여 넣을 코드
#
#   변환 규칙은 33_ 과 같다.
#     1. hasNoEffectOn 은 공리로 만들지 않고, 같은 (주어, 목적어) 쌍의 다른 트리플을 기각한다.
#     2. 주어는 MAPPING 으로 MIMIC 개념·임계값에, 목적어는 HEADS 로 모델 출력에 대응시킨다.
#        대응이 없으면 미매핑으로 버린다.
#     3. 근거 등급은 술어로 정한다 (PRED_W). 가중치는 GRADE_W 를 합 1 로 정규화한 값.
#
#   MIMIC 데이터 없이 돈다. 임계값은 원 단위로 내보내고, 표준화(z)는 23_ 의 _zthr 가 한다.
#   PhysicalRestraint · MechanicalVentilation · OpioidUse · Melatonin 은 33_ 에서 회수한 개념이라
#   23_ 에는 없다 — 23_ 에 붙일 때는 이 4개 공리를 빼거나 개념을 먼저 추가해야 한다.
#
# 사용: python delirium/42_kg_to_axioms.py triples_one.json [triples_few.json ...] [-o axioms.json]
# ============================================================================
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# 개념 이름 -> (모델 개념, 방향(+1: 임계 이상이 참), 원 단위 임계, 이진 여부)
MAPPING = {
    "Benzodiazepine": ("BenzoFrac", +1, 1e-6, False),
    "DeepSedation": ("RASSmin", -1, -4.0, False),
    "SedationIntensity": ("RASSnegmean", -1, -2.0, False),
    "SeverePain": ("PainNRSmax", +1, 4.0, False),
    "Age": ("Age", +1, 65.0, False),
    "Dexmedetomidine": ("DexmedFrac", +1, 1e-6, False),
    "EarlyMobility": ("MobJHHLM", +1, 4.0, False),
    "Immobility": ("MobJHHLM", -1, 3.0, False),
    "BloodTransfusion": ("BloodTransfusion", +1, 0.5, True),
    "Dementia": ("Dementia", +1, 0.5, True),
    "Trauma": ("Trauma", +1, 0.5, True),
    "Hypertension": ("Hypertension", +1, 0.5, True),
    # 33_ 에서 회수한 개념 (23_ 에는 없음)
    "PhysicalRestraint": ("PhysicalRestraint", +1, 0.5, True),
    "MechanicalVentilation": ("MechanicalVentilation", +1, 0.5, True),
    "OpioidUse": ("OpioidUse", +1, 0.5, True),
    "Melatonin": ("Melatonin", +1, 0.5, True),
}
RECOVERED = {"PhysicalRestraint", "MechanicalVentilation", "OpioidUse", "Melatonin"}
HEADS = {"Delirium": "Delirium", "Death": "Death", "UnableToAssess": "CurrentUTA",
         "Assessable": "Assessable", "Immobility": "MobJHHLM"}
PRED_W = {"increasesRiskOf": "strong", "decreasesRiskOf": "moderate",
          "associatedWith": "low", "precludes": "derived"}
GRADE_W = {"strong": 1.0, "moderate": 0.6, "low": 0.3, "cohort": 0.3, "derived": 0.5,
           "inconclusive": 0.2}


def load_triples(paths):
    s = set()
    for p in paths:
        for t in json.loads(Path(p).read_text(encoding="utf-8")):
            s.add((t["subject"], t["predicate"], t["object"]))
    return s


def compile_kg(triples):
    no_effect = {(s, o) for s, p, o in triples if p == "hasNoEffectOn"}
    ax, dropped, unmapped = [], [], []
    for s, p, o in sorted(triples):
        if p == "hasNoEffectOn":
            continue
        if (s, o) in no_effect:
            dropped.append(f"{s}-{p}->{o}"); continue
        if p not in PRED_W or s not in MAPPING:
            unmapped.append(f"{s}-{p}->{o}"); continue
        head = "CurrentUTA" if p == "precludes" and o in ("Assessable", "UnableToAssess") \
            else HEADS.get(o)
        if head is None:
            unmapped.append(f"{s}-{p}->{o}"); continue
        cn, sgn, raw, is_bin = MAPPING[s]
        ax.append({"name": f"{s}-{p}->{o}", "concept": cn, "sign": sgn,
                   "threshold": 0.5 if is_bin else raw, "binary": is_bin, "head": head,
                   "negated_head": p == "decreasesRiskOf", "grade": PRED_W[p],
                   "recovered_concept": s in RECOVERED})
    tot = sum(GRADE_W[a["grade"]] for a in ax)
    for a in ax:
        a["weight"] = round(GRADE_W[a["grade"]] / tot, 4)
    return ax, dropped, unmapped


def as_23_code(ax):
    """23_ 의 AXIOMS 튜플 형식: (이름, 개념, 방향, 임계z, head, head 부정, GRADE).

    23_ 은 섬망 예측 모델이라 Death 출력이 없고, 회수 개념 4개도 없다 — 둘 다 주석으로 뺀다.
    """
    lines = ["AXIOMS = ["]
    for a in ax:
        thr = "0.5" if a["binary"] else f'_zthr("{a["concept"]}", {a["threshold"]})'
        row = (f'("{a["name"]}", "{a["concept"]}", {a["sign"]:+d}, {thr}, '
               f'"{a["head"]}", {a["negated_head"]}, "{a["grade"]}"),')
        if a["head"] == "Death":
            lines.append(f"    # {row}  # 23_ 에 Death 출력 없음")
        elif a["recovered_concept"]:
            lines.append(f"    # {row}  # 23_ 에 없는 개념")
        else:
            lines.append(f"    {row}")
    lines.append("]")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("triples", nargs="+", help="트리플 JSON 파일 (여러 개면 합집합)")
    ap.add_argument("-o", "--out", default="axioms.json")
    args = ap.parse_args()

    tr = load_triples(args.triples)
    ax, dropped, unmapped = compile_kg(tr)
    Path(args.out).write_text(json.dumps(
        {"inputs": args.triples, "n_triples": len(tr), "axioms": ax,
         "dropped_by_no_effect": dropped, "unmapped": unmapped},
        ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"트리플 {len(tr)} -> 공리 {len(ax)} (효과없음 기각 {len(dropped)} · 미매핑 {len(unmapped)})")
    for a in ax:
        print(f"  {a['name']:45s} {a['grade']:9s} w={a['weight']}")
    if dropped:
        print("기각:", ", ".join(dropped))
    print(f"\n저장: {args.out}\n\n# --- 23_stage34_bilstm_cbm.py 에 붙여 넣을 코드 ---")
    print(as_23_code(ax))


if __name__ == "__main__":
    main()
''')

_SRC = {}

# ============================================================================
# [00] delirium/00_extract.py — MIMIC → ICU 기본 테이블 · CAM-ICU 라벨 · RASS/진정제
# ============================================================================
_SRC['00'] = ('00_extract.py', r'''# -*- coding: utf-8 -*-
"""09b_remaining_eda.py 가 읽는 중간 파일 4개를 원본에서 만든다.

  _icu_base.pkl / .parquet             ICU stay 기본 테이블
  _label_values.parquet                섬망평가(228332) + RASS(228096) 원본 기록
  _padis_item_stay_counts.parquet      stay x itemid 기록수 + 첫/마지막 시각
  _padis_stay_group_counts.parquet     stay x 항목군 기록수
  _step1_sed.parquet                   진정제 투여(inputevents)

이 4개가 이미 있으면 이 스크립트는 돌릴 필요가 없다. 바로 09 를 돌리면 된다.
chartevents 는 인덱스가 없어 풀스캔 1회에 60~75초 (로컬 SSD 기준).
"""
import os
import sys
import time

import pandas as pd

# ============================================================================
# ===== 여기만 고치세요 =======================================================
# ============================================================================
# 원본을 어떤 형태로 갖고 있는지: "sqlite" 또는 "csvgz"
SRC_MODE = "sqlite"

# [sqlite 모드] MIMIC4-hosp-icu.db 경로.
#   윈도우는 역슬래시 대신 슬래시로 쓴다 (r"" 를 써도 URI 로 넘길 때 깨진다).
#   경로에 공백이 있으면 폴더째 공백 없는 곳으로 옮기는 편이 안전하다.
SQLITE_PATH = "C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db"

# 구글 드라이브에 마운트해서 쓰는 경우 True 로.
#   드라이브 FUSE 는 SQLite 가 요구하는 파일 잠금을 지원하지 않아
#   "unable to open database file" 이 난다. immutable=1 이면 잠금 없이 읽는다.
SQLITE_IMMUTABLE = False

# [csvgz 모드] physionet 원본 csv.gz 디렉터리 (duckdb 필요)
CSV_HOSP = "/content/mimiciv/hosp"
CSV_ICU = "/content/mimiciv/icu"

# 중간 파일을 저장할 곳. 09b_remaining_eda.py 의 DATA 와 같아야 한다.
OUT = "notes/eda"
# ============================================================================
# ===== 여기까지 =============================================================
# ============================================================================

# 환경변수로도 덮어쓸 수 있다 (코랩에서 편하다)
SRC_MODE = os.environ.get("EDA_SRC_MODE", SRC_MODE)
SQLITE_PATH = os.environ.get("EDA_SQLITE", SQLITE_PATH)
CSV_HOSP = os.environ.get("EDA_CSV_HOSP", CSV_HOSP)
CSV_ICU = os.environ.get("EDA_CSV_ICU", CSV_ICU)
OUT = os.environ.get("EDA_DATA", OUT)
SQLITE_IMMUTABLE = os.environ.get("EDA_SQLITE_IMMUTABLE", str(SQLITE_IMMUTABLE)).lower() in ("1", "true")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
os.makedirs(OUT, exist_ok=True)

# ---- itemid 목록 (01b_scan_padis_labels.py / 05_scan_step1.py 와 동일) ----
GROUPS = {
    "RASS":            [228096],
    "RASS_goal":       [228299],
    "CAMICU":          [228300, 228301, 228302, 228303, 228334, 228335, 228336, 228337,
                        229324, 229325, 229326],
    "DELIRIUM_ASSESS": [228332, 228688],
    "PAIN_NRS":        [223791, 223794, 224409, 229702, 230144],
    "CPOT":            [229689, 229690, 229691, 229692, 229694, 229695, 229696, 229697,
                        229698, 229699],
    "MOBILITY":        [229319, 229321, 229633, 229742, 228697, 224057],
    "RESTRAINT":       [227671, 227670, 224063, 227945, 227962, 224856],
    "GCS_total":       [220739, 223900, 223901],
}
ITEM2G = {i: g for g, xs in GROUPS.items() for i in xs}
ALL_IDS = sorted(ITEM2G)
# 값까지 원본 그대로 보관할 항목 (섬망평가 · RASS · CAM-ICU feature)
VALUE_IDS = [228332, 228096, 228300, 228301, 228302, 228303, 228334, 228335, 228336,
             228337, 229324, 229325, 229326]
# 3·4단계 시계열 입력으로 mobility / pain / GCS 값도 필요하다 (docs/delirium/DELIRIUM_SPLIT_SPEC.md §3 블로커).
# 이걸 빼면 _label_values 에 CAM·RASS 만 남아 BiLSTM 입력이 반쪽이 된다.
VALUE_IDS = sorted(set(VALUE_IDS)
                   | set(GROUPS["PAIN_NRS"])
                   | set(GROUPS["MOBILITY"])
                   | set(GROUPS["GCS_total"]))
SED = {225150: "dexmedetomidine", 229420: "dexmedetomidine", 221385: "lorazepam",
       221668: "midazolam", 222168: "propofol", 221623: "diazepam"}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def build_base(icustays, patients, admissions):
    b = (icustays.merge(patients, on="subject_id", how="inner")
                 .merge(admissions[["hadm_id", "admittime", "dischtime", "deathtime",
                                    "hospital_expire_flag"]], on="hadm_id", how="inner"))
    for c in ["intime", "outtime", "admittime", "dischtime", "dod"]:
        if c in b.columns:
            b[c] = pd.to_datetime(b[c], errors="coerce")
    # anchor_age 는 anchor_year 시점 나이. MIMIC-IV 는 환자별로 날짜가 시프트되어 있다.
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
    b = b.sort_values(["subject_id", "intime"])
    b["icu_seq_in_hadm"] = b.groupby("hadm_id")["intime"].rank(method="first").astype(int)
    b["icu_seq_in_subject"] = b.groupby("subject_id")["intime"].rank(method="first").astype(int)
    if "dod" in b.columns:
        d = (b["dod"] - b["outtime"]).dt.total_seconds() / 86400.0
        b["mort_30d"] = ((d <= 30) & (d >= -1)).astype(int)
        b["mort_1y"] = ((d <= 365) & (d >= -1)).astype(int)
    return b


def run_sqlite():
    import sqlite3
    if not os.path.exists(SQLITE_PATH):
        sys.exit(f"DB 를 못 찾음: {SQLITE_PATH}\n  -> 파일 상단 SQLITE_PATH 를 고치세요.")
    uri = f"file:{SQLITE_PATH}?" + ("immutable=1" if SQLITE_IMMUTABLE else "mode=ro")
    try:
        con = sqlite3.connect(uri, uri=True)
        con.execute("select 1")
    except sqlite3.OperationalError as e:
        sys.exit(f"DB 를 열지 못함: {e}\n"
                 f"  구글 드라이브에 마운트한 파일이면 SQLITE_IMMUTABLE = True 로 바꿔보세요.")
    con.execute("pragma cache_size=-400000")
    con.execute("pragma temp_store=MEMORY")

    log("icustays / patients / admissions")
    icustays = pd.read_sql("select subject_id,hadm_id,stay_id,first_careunit,last_careunit,"
                           "intime,outtime,los from icustays", con)
    patients = pd.read_sql("select subject_id,gender,anchor_age,anchor_year,"
                           "anchor_year_group,dod from patients", con)
    admissions = pd.read_sql("select hadm_id,admittime,dischtime,deathtime,"
                             "hospital_expire_flag from admissions", con)

    ids = ",".join(map(str, ALL_IDS))
    log("chartevents 스캔 1/2 (stay x itemid 집계) — 인덱스 없으면 풀스캔")
    t = time.time()
    cnt = pd.read_sql(f"""select stay_id, itemid, count(*) n,
                                 min(charttime) t0, max(charttime) t1
                          from chartevents
                          where itemid in ({ids}) and stay_id is not null
                          group by stay_id, itemid""", con)
    log(f"  {time.time()-t:.0f}s rows={len(cnt):,}")

    log("chartevents 스캔 2/2 (원본 값)")
    t = time.time()
    val = pd.read_sql(f"""select stay_id, itemid, charttime, value, valuenum
                          from chartevents
                          where itemid in ({','.join(map(str, VALUE_IDS))})
                            and stay_id is not null""", con)
    log(f"  {time.time()-t:.0f}s rows={len(val):,}")

    log("inputevents (진정제)")
    ie = pd.read_sql(f"""select stay_id,itemid,starttime,endtime,amount,amountuom
                         from inputevents
                         where itemid in ({','.join(map(str, SED))})""", con)
    return icustays, patients, admissions, cnt, val, ie


def run_csvgz():
    ce = os.path.join(CSV_ICU, "chartevents.csv.gz")
    if not os.path.exists(ce):
        sys.exit(f"chartevents 를 못 찾음: {ce}\n  -> 파일 상단 CSV_ICU 를 고치세요.")
    try:
        import duckdb
    except ImportError:
        sys.exit("csvgz 모드는 duckdb 가 필요하다:  pip install duckdb\n"
                 "  (.db 파일을 갖고 있다면 SRC_MODE = \"sqlite\" 로 바꾸면 duckdb 없이 된다)")
    con = duckdb.connect()
    con.execute("pragma threads=4")
    con.execute("pragma memory_limit='6GB'")     # 필터 결과가 수천만 행이라 메모리에 다 못 얹는다
    if os.path.isdir("/content"):
        os.makedirs("/content/duckdb_tmp", exist_ok=True)
        con.execute("pragma temp_directory='/content/duckdb_tmp'")

    def rd(path, cols):
        return con.execute(f"select {cols} from read_csv_auto('{path}', compression='gzip')").df()

    log("icustays / patients / admissions")
    icustays = rd(os.path.join(CSV_ICU, "icustays.csv.gz"),
                  "subject_id,hadm_id,stay_id,first_careunit,last_careunit,intime,outtime,los")
    patients = rd(os.path.join(CSV_HOSP, "patients.csv.gz"),
                  "subject_id,gender,anchor_age,anchor_year,anchor_year_group,dod")
    admissions = rd(os.path.join(CSV_HOSP, "admissions.csv.gz"),
                    "hadm_id,admittime,dischtime,deathtime,hospital_expire_flag")

    ids = ",".join(map(str, ALL_IDS))
    tmp = os.path.join(OUT, "_ce_filtered.parquet")
    log("chartevents 1회 스캔 -> parquet 으로 흘려보냄 (메모리에 안 얹는다)")
    t = time.time()
    con.execute(f"""copy (select stay_id, itemid, charttime, value, valuenum
                          from read_csv_auto('{ce}', compression='gzip')
                          where itemid in ({ids}) and stay_id is not null)
                    to '{tmp}' (format parquet)""")
    log(f"  {time.time()-t:.0f}s -> {tmp}")
    cnt = con.execute(f"""select stay_id, itemid, count(*) n,
                                 min(charttime) t0, max(charttime) t1
                          from read_parquet('{tmp}') group by stay_id, itemid""").df()
    val = con.execute(f"""select stay_id,itemid,charttime,value,valuenum
                          from read_parquet('{tmp}')
                          where itemid in ({','.join(map(str, VALUE_IDS))})""").df()
    log(f"  집계 {len(cnt):,} rows / 값 {len(val):,} rows")

    log("inputevents (진정제)")
    ie = con.execute(f"""select stay_id,itemid,starttime,endtime,amount,amountuom
                         from read_csv_auto(
                             '{os.path.join(CSV_ICU, "inputevents.csv.gz")}', compression='gzip')
                         where itemid in ({','.join(map(str, SED))})""").df()
    return icustays, patients, admissions, cnt, val, ie


if SRC_MODE == "sqlite":
    icustays, patients, admissions, cnt, val, ie = run_sqlite()
elif SRC_MODE == "csvgz":
    icustays, patients, admissions, cnt, val, ie = run_csvgz()
else:
    sys.exit(f"SRC_MODE 는 sqlite 또는 csvgz 여야 한다: {SRC_MODE}")

b = build_base(icustays, patients, admissions)
b.to_pickle(f"{OUT}/_icu_base.pkl")
b.to_parquet(f"{OUT}/_icu_base.parquet")     # pickle 은 pandas 버전이 다르면 못 읽는다
log(f"_icu_base  {len(b):,} stays")

cnt["grp"] = cnt["itemid"].map(ITEM2G)
cnt.to_parquet(f"{OUT}/_padis_item_stay_counts.parquet")
cnt.groupby(["stay_id", "grp"])["n"].sum().unstack(fill_value=0) \
   .to_parquet(f"{OUT}/_padis_stay_group_counts.parquet")
log(f"_padis_item_stay_counts  {len(cnt):,} rows")

val.to_parquet(f"{OUT}/_label_values.parquet")
log(f"_label_values  {len(val):,} rows")

ie["drug"] = ie["itemid"].map(SED)
ie.to_parquet(f"{OUT}/_step1_sed.parquet")
log(f"_step1_sed  {len(ie):,} rows")
log(f"완료. 출력 -> {OUT}/  이제 09b_remaining_eda.py 를 돌리면 된다.")
''')

# ============================================================================
# [24] delirium/24_extract_mobility_pain_gcs.py — 거동 · 통증 · GCS
# ============================================================================
_SRC['24'] = ('24_extract_mobility_pain_gcs.py', r'''# -*- coding: utf-8 -*-
# ============================================================================
# 00_extract.py 가 값으로 뽑지 않은 3개 항목군을 보충 추출한다.
#   MOBILITY · PAIN_NRS · GCS_total
#
# 왜 별도 스크립트인가: 00_extract.py 를 다시 돌리면 _icu_base 등 기존 중간파일을
# 전부 덮어써서, 이미 문서에 실은 수치의 재현성이 흔들린다. 기존 파일은 그대로 두고
# 새 파일 하나(_extra_values.parquet)만 만든다.
# (00_extract.py 의 VALUE_IDS 도 같이 넓혀 두었으니, 다음 전체 재추출부터는 자동 포함된다.)
#
# 앵커 관련 구간만 남긴다: 입실 후 0~264h (240h 캡 + lookback 24h)
# 사용: EDA_DATA=<notes/eda> EDA_SQLITE=<db> python delirium/24_extract_mobility_pain_gcs.py
# ============================================================================
import os, sys, time, sqlite3
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ.get("EDA_DATA", "notes/eda")
DB = os.environ.get("EDA_SQLITE", "C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db")
OUTF = os.path.join(DATA, "_extra_values.parquet")
HR_MAX = 264.0                      # 240h 캡 + lookback 24h
CHUNK = 4_000_000

GROUPS = {
    "PAIN_NRS": [223791, 223794, 224409, 229702, 230144],
    "MOBILITY": [229319, 229321, 229633, 229742, 228697, 224057],
    "GCS_total": [220739, 223900, 223901],
}
ITEM2G = {i: g for g, xs in GROUPS.items() for i in xs}
IDS = sorted(ITEM2G)


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


if not os.path.exists(DB):
    sys.exit(f"DB 없음: {DB}")
log(f"DB {os.path.getsize(DB)/1e9:.1f}GB · itemid {len(IDS)}개")

b = pd.read_pickle(f"{DATA}/_icu_base.pkl")
b["intime"] = pd.to_datetime(b["intime"])
if "age" not in b.columns:
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
DEN = b[(b.age >= 18) & (b.los >= 1.0)]
keep = set(DEN.stay_id.astype("int64"))
intime = DEN.set_index("stay_id")["intime"]
log(f"코호트 stay {len(keep):,}")

try:
    con = sqlite3.connect(f"file:{DB}?immutable=1", uri=True)
    con.execute("select 1")
except sqlite3.OperationalError:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.execute("pragma cache_size=-400000")

q = (f"select stay_id, itemid, charttime, value, valuenum from chartevents "
     f"where itemid in ({','.join(map(str, IDS))}) and stay_id is not null")
log("chartevents 스캔 시작 (인덱스 없으면 풀스캔)")

parts, seen, kept = [], 0, 0
t0 = time.time()
for ch in pd.read_sql(q, con, chunksize=CHUNK):
    seen += len(ch)
    ch["stay_id"] = ch["stay_id"].astype("int64")
    ch = ch[ch.stay_id.isin(keep)]
    if len(ch):
        ch["charttime"] = pd.to_datetime(ch["charttime"], errors="coerce")
        ch["hr"] = (ch["charttime"] - ch["stay_id"].map(intime)).dt.total_seconds() / 3600
        ch = ch[(ch.hr >= 0) & (ch.hr <= HR_MAX)]
    if len(ch):
        ch["grp"] = ch["itemid"].map(ITEM2G)
        ch["valuenum"] = pd.to_numeric(ch["valuenum"], errors="coerce").astype("float32")
        ch["hr"] = ch["hr"].astype("float32")
        parts.append(ch[["stay_id", "itemid", "grp", "hr", "value", "valuenum"]])
        kept += len(ch)
    log(f"  스캔 {seen:,} · 보존 {kept:,} · {time.time()-t0:.0f}s")
con.close()

if not parts:
    sys.exit("보존된 행이 없다 — itemid 나 코호트를 확인할 것")
val = pd.concat(parts, ignore_index=True)
del parts
log(f"합계 {len(val):,} 행 · {val.memory_usage(deep=True).sum()/1e6:.0f}MB")

print()
print(val.groupby("grp").agg(
    행수=("hr", "size"), stay수=("stay_id", "nunique"),
    valuenum있음=("valuenum", lambda s: f"{100*s.notna().mean():.1f}%")).to_string())
print("\n항목별 값 예시:")
for g in GROUPS:
    sub = val[val.grp == g]
    if not len(sub):
        continue
    ex = sub["value"].astype(str).value_counts().head(4)
    print(f"  {g}: " + " | ".join(f"{k}({v:,})" for k, v in ex.items()))

val.to_parquet(OUTF, index=False)
log(f"저장 -> {OUTF}  ({os.path.getsize(OUTF)/1e6:.0f}MB)")

cov = val.groupby("grp")["stay_id"].nunique() / len(keep) * 100
print("\n코호트 stay 대비 보유율:")
print(cov.round(1).to_string())
''')

# ============================================================================
# [25] delirium/25_extract_axiom_gaps.py — 치매 · 외상 · 고혈압 · 수혈 (공리 개념)
# ============================================================================
_SRC['25'] = ('25_extract_axiom_gaps.py', r'''# -*- coding: utf-8 -*-
# ============================================================================
# 강제하지 못하고 있던 PADIS 공리 4개의 입력을 뽑는다.
#   BloodTransfusion (strong)  <- inputevents · Blood Products/Colloids
#   Dementia (strong) · Trauma (strong) · Hypertension (moderate)  <- diagnoses_icd
#
# 동반질환 매핑은 NeSy-SMP/data/build_comorbidities_icd.py 의 match_label 을 그대로 쓴다
# (내가 ICD 규칙을 새로 지어내지 않는다).
#
# ⚠️ ICD 진단은 **퇴원 시점에 부여**되고 hadm 단위라 앵커 시점 정보가 아니다.
#    치매·고혈압 같은 만성질환은 무리가 없지만, 엄밀히는 앵커 이후 정보가 섞일 수 있다.
#    원 논문도 동반질환을 정적 피처로 쓰므로 재현 관점에서는 일관되지만 한계로 기록한다.
#    수혈은 시각이 있어 lookback 창 안으로 제한한다 — 이쪽은 누수가 없다.
#
# 사용: EDA_DATA=<notes/eda> EDA_SQLITE=<db> python delirium/25_extract_axiom_gaps.py
# ============================================================================
import os, sys, time, sqlite3
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "NeSy-SMP", "data"))
from build_comorbidities_icd import match_label          # noqa: E402

DATA = os.environ.get("EDA_DATA", "notes/eda")
DB = os.environ.get("EDA_SQLITE", "C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db")
HR_MAX = 264.0
# d_items category = 'Blood Products/Colloids' + 미사용 표기지만 데이터가 있는 것들
BLOOD_RBC = [225168, 226368, 227070, 220996, 221013, 226370]      # 적혈구 계열
BLOOD_ANY = BLOOD_RBC + [220970, 225170, 226369, 227071, 220971]  # + FFP·혈소판


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


b = pd.read_pickle(f"{DATA}/_icu_base.pkl")
b["intime"] = pd.to_datetime(b["intime"])
if "age" not in b.columns:
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
DEN = b[(b.age >= 18) & (b.los >= 1.0)].copy()
stays = set(DEN.stay_id.astype("int64"))
hadms = set(DEN.hadm_id.astype("int64"))
intime = DEN.set_index("stay_id")["intime"]
log(f"코호트 stay {len(stays):,} · hadm {len(hadms):,}")

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=600)
con.execute("pragma cache_size=-400000")

# ---------------------------------------------------------------- 1. 동반질환
log("diagnoses_icd 조회")
dx = pd.read_sql("""select d.hadm_id, d.icd_code, d.icd_version, t.long_title
                    from diagnoses_icd d
                    left join d_icd_diagnoses t
                      on t.icd_code = d.icd_code and t.icd_version = d.icd_version""", con)
dx["hadm_id"] = dx["hadm_id"].astype("int64")
dx = dx[dx.hadm_id.isin(hadms)]
log(f"  진단 {len(dx):,}행 / hadm {dx.hadm_id.nunique():,}")

WANT = ["dementia", "trauma", "hypertension"]
hit = {w: set() for w in WANT}
for h_, c_, v_, t_ in zip(dx.hadm_id.to_numpy(), dx.icd_code.to_numpy(),
                          dx.icd_version.to_numpy(), dx.long_title.to_numpy()):
    for lab in match_label(v_, c_, t_):
        if lab in hit:
            hit[lab].add(h_)
com = pd.DataFrame({"hadm_id": sorted(hadms)})
for w in WANT:
    com[w] = com.hadm_id.isin(hit[w]).astype("int8")
print()
print("동반질환 유병률 (hadm 기준):")
print((100 * com[WANT].mean()).round(1).to_string())
print(f"(참고: sepsis 코호트 값 — dementia 5.2% · trauma 9.6% · hypertension 70.9%)")

# ---------------------------------------------------------------- 2. 수혈
log("inputevents 조회 (혈액제제)")
ids = ",".join(map(str, BLOOD_ANY))
tr = pd.read_sql(f"""select stay_id, itemid, starttime from inputevents
                     where itemid in ({ids}) and stay_id is not null""", con)
con.close()
tr["stay_id"] = tr["stay_id"].astype("int64")
tr = tr[tr.stay_id.isin(stays)].copy()
tr["starttime"] = pd.to_datetime(tr["starttime"], errors="coerce")
tr["hr"] = (tr["starttime"] - tr["stay_id"].map(intime)).dt.total_seconds() / 3600
tr = tr[(tr.hr >= 0) & (tr.hr <= HR_MAX)].copy()
tr["is_rbc"] = tr.itemid.isin(BLOOD_RBC).astype("int8")
tr["hr"] = tr["hr"].astype("float32")
print()
print(f"수혈 기록 {len(tr):,}건 / stay {tr.stay_id.nunique():,} "
      f"({100*tr.stay_id.nunique()/len(stays):.1f}%)")
print(f"  적혈구 계열만: {int(tr.is_rbc.sum()):,}건 / stay {tr[tr.is_rbc==1].stay_id.nunique():,} "
      f"({100*tr[tr.is_rbc==1].stay_id.nunique()/len(stays):.1f}%)")
print("\n제제별:")
print(tr.groupby("itemid").agg(건수=("hr", "size"), stay=("stay_id", "nunique")).to_string())

com.to_parquet(f"{DATA}/_axiom_comorb.parquet", index=False)
tr[["stay_id", "hr", "is_rbc"]].to_parquet(f"{DATA}/_axiom_transfusion.parquet", index=False)
log(f"저장 -> _axiom_comorb.parquet · _axiom_transfusion.parquet")
''')

# ============================================================================
# [22] delirium/22_stage2_xgb.py — XGBoost 기준선 (23 결과표가 읽는다)
# ============================================================================
_SRC['22'] = ('22_stage2_xgb.py', r'''# -*- coding: utf-8 -*-
# ============================================================================
# 2단계 — XGBoost (요약 피처만). 1단계 lookup baseline 을 넘는지 본다.
#
# mobility / pain / GCS 는 24_extract_mobility_pain_gcs.py 가 뽑은 _extra_values.parquet 에서 붙는다.
# 그 파일이 없으면 자동으로 빼고 돌아간다.
#
# 분할·seed 는 20_baseline_carryforward.py 와 동일 (환자 단위 70/30, seed 42)
# 사용: EDA_DATA=<notes/eda> python delirium/22_stage2_xgb.py
# ============================================================================
import os, sys, time
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score
from xgboost import XGBClassifier

sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ.get("EDA_DATA", "/content/drive/MyDrive/mimic_eda")
OUT = os.environ.get("EDA_OUT", os.path.join(DATA, "out_split"))
os.makedirs(OUT, exist_ok=True)
SEED, CAM_ITEM, RASS_ITEM = 42, 228332, 228096
W_AHEAD, HR_CAP = 24.0, 240.0
pd.set_option("display.width", 220)


def head(t):
    print("\n" + "=" * 78); print(t); print("=" * 78)


t0 = time.time()
# ---------------------------------------------------------------- 앵커 + 라벨
b = pd.read_pickle(f"{DATA}/_icu_base.pkl")
v = pd.read_parquet(f"{DATA}/_label_values.parquet")
b["intime"] = pd.to_datetime(b["intime"])
if "age" not in b.columns:
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
DEN = b[(b.age >= 18) & (b.los >= 1.0)].copy()
intime = b.set_index("stay_id")["intime"]

MAP = {"Positive": "P", "Negative": "N", "UTA": "U",
       "Unable to Assess": "U", "Unable to assess": "U"}
cam = v[v.itemid == CAM_ITEM][["stay_id", "charttime", "value"]].copy()
cam["charttime"] = pd.to_datetime(cam["charttime"])
cam["v"] = cam["value"].astype(str).str.strip().map(MAP)
cam = cam[cam.v.notna() & cam.stay_id.isin(DEN.stay_id)].copy()
cam["hr"] = (cam["charttime"] - cam["stay_id"].map(intime)).dt.total_seconds() / 3600
cam = cam[(cam.hr >= 0) & (cam.hr <= HR_CAP)].sort_values(["stay_id", "hr"]).reset_index(drop=True)

h = cam["hr"].to_numpy(float)
isC = (cam["v"] != "U").to_numpy(); isP = (cam["v"] == "P").to_numpy()
cumC = np.concatenate([[0], isC.cumsum()]); cumP = np.concatenate([[0], (isC & isP).cumsum()])
cumU = np.concatenate([[0], (~isC).cumsum()])
_, first, cnt = np.unique(cam["stay_id"].to_numpy(), return_index=True, return_counts=True)
labeled = np.zeros(len(cam), bool); y = np.zeros(len(cam), bool)
for a, n in zip(first, cnt):
    hh = h[a:a + n]; idx = np.arange(n)
    j = np.searchsorted(hh, hh + W_AHEAD, side="right")
    labeled[a:a + n] = (cumC[a + j] - cumC[a + idx + 1]) > 0
    y[a:a + n] = (cumP[a + j] - cumP[a + idx + 1]) > 0
cam["labeled"], cam["y"] = labeled, y

# ---------------------------------------------------------------- 누적 피처
cam["n_prev"] = cam.groupby("stay_id").cumcount()
pos_in_stay = np.zeros(len(cam), int)   # 앵커 이전 P 횟수
uta_in_stay = np.zeros(len(cam), int)
for a, n in zip(first, cnt):
    idx = np.arange(n)
    pos_in_stay[a:a + n] = cumP[a + idx] - cumP[a]
    uta_in_stay[a:a + n] = cumU[a + idx] - cumU[a]
cam["n_prev_pos"], cam["n_prev_uta"] = pos_in_stay, uta_in_stay
cam["uta_frac"] = np.where(cam.n_prev > 0, cam.n_prev_uta / cam.n_prev.clip(lower=1), np.nan)
cam["prev_conf"] = cam["v"].where(cam.v != "U").groupby(cam.stay_id).ffill().shift()
cam.loc[cam.groupby("stay_id").head(1).index, "prev_conf"] = np.nan
cam["prev_conf"] = cam["prev_conf"].fillna("없음")
# 직전 확정 평가로부터 경과시간
last_conf_hr = (cam["hr"].where(cam.v != "U").groupby(cam.stay_id).ffill()
                .groupby(cam.stay_id).shift())   # A2: stay 안에서만 shift (첫 앵커 누출 방지)
cam["since_conf"] = cam["hr"] - last_conf_hr
cam["since_prev"] = cam.groupby("stay_id")["hr"].diff()

# ---------------------------------------------------------------- RASS
r = v[v.itemid == RASS_ITEM][["stay_id", "charttime", "valuenum"]].copy()
r["charttime"] = pd.to_datetime(r["charttime"])
r = r[r.stay_id.isin(DEN.stay_id)].copy()
r["hr"] = (r["charttime"] - r["stay_id"].map(intime)).dt.total_seconds() / 3600
r = r[r.hr >= 0].sort_values(["stay_id", "hr"])
rh = {k: g["hr"].to_numpy(float) for k, g in r.groupby("stay_id", sort=False)}
rv = {k: g["valuenum"].to_numpy(float) for k, g in r.groupby("stay_id", sort=False)}

cols = ["rass_last", "rass_min24", "rass_mean24", "rass_max24", "rass_n24", "rass_negmean24"]
F = {c: np.full(len(cam), np.nan) for c in cols}
for a, n in zip(first, cnt):
    sid = cam["stay_id"].iloc[a]
    arr = rh.get(sid)
    if arr is None:
        continue
    vals = rv[sid]; hh = h[a:a + n]
    hi = np.searchsorted(arr, hh, side="right")
    lo = np.searchsorted(arr, hh - 24.0, side="left")
    for k in range(n):
        seg = vals[lo[k]:hi[k]]
        seg = seg[~np.isnan(seg)]
        if seg.size:
            F["rass_last"][a + k] = seg[-1]
            F["rass_min24"][a + k] = seg.min()
            F["rass_max24"][a + k] = seg.max()
            F["rass_mean24"][a + k] = seg.mean()
            F["rass_negmean24"][a + k] = np.minimum(seg, 0).mean()
        F["rass_n24"][a + k] = hi[k] - lo[k]
for c in cols:
    cam[c] = F[c]
cam["deep_sed24"] = (cam.rass_min24 <= -4).astype(float)

# ---------------------------------------------------------------- 진정제
sed = pd.read_parquet(f"{DATA}/_step1_sed.parquet")
sed = sed[sed.stay_id.isin(DEN.stay_id)].copy()
for c in ["starttime", "endtime"]:
    sed[c] = pd.to_datetime(sed[c])
sed["s"] = (sed["starttime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
sed["e"] = (sed["endtime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
BENZO = {"lorazepam", "midazolam", "diazepam"}
sed["cls"] = np.where(sed.drug.isin(BENZO), "benzo", sed.drug)
sed_by = {k: (g["s"].to_numpy(float), g["e"].to_numpy(float), g["cls"].to_numpy())
          for k, g in sed.groupby("stay_id", sort=False)}
CLS = ["benzo", "propofol", "dexmedetomidine"]
S = {f"sed_{c}": np.zeros(len(cam)) for c in CLS}
S["sed_benzo_cum"] = np.zeros(len(cam))
for a, n in zip(first, cnt):
    g = sed_by.get(cam["stay_id"].iloc[a])
    if g is None:
        continue
    s_, e_, cl = g; hh = h[a:a + n]
    ov = (s_[None, :] < hh[:, None]) & (e_[None, :] > hh[:, None] - 24.0)
    before = s_[None, :] < hh[:, None]
    for c in CLS:
        S[f"sed_{c}"][a:a + n] = (ov & (cl == c)[None, :]).any(1)
    S["sed_benzo_cum"][a:a + n] = (before & (cl == "benzo")[None, :]).sum(1)
for k, arr in S.items():
    cam[k] = arr

# ---------------------------------------------------------------- mobility/pain/GCS
# 24_extract_mobility_pain_gcs.py 가 만든 _extra_values.parquet 이 있으면 붙인다.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _extra_features import build_extra_channels, summarize

EX, EXNAMES = build_extra_channels(DATA, cam["stay_id"].to_numpy(), h, first, cnt)
if EX is None:
    EXTRA_COLS = []
    print("[!] _extra_values.parquet 없음 — mobility/pain/GCS 없이 진행")
else:
    ESUM, EXTRA_COLS = summarize(EX, EXNAMES)
    for i, c in enumerate(EXTRA_COLS):
        cam[c] = ESUM[:, i]
    print(f"추가 피처 {len(EXTRA_COLS)}개 · 채널 {EX.shape[2]}")
    del EX

# ---------------------------------------------------------------- 정적
st = DEN.set_index("stay_id")
cam["subject_id"] = cam["stay_id"].map(st["subject_id"])
cam["age"] = cam["stay_id"].map(st["age"])
cam["los"] = cam["stay_id"].map(st["los"])
cam["is_male"] = (cam["stay_id"].map(st["gender"]) == "M").astype(float)
cam["cu"] = cam["stay_id"].map(st["first_careunit"]).astype("category").cat.codes
cam["era"] = cam["stay_id"].map(st["anchor_year_group"]).astype("category").cat.codes

d = cam[cam.labeled].copy()
print(f"instance {len(d):,} · 환자 {d.subject_id.nunique():,} · Positive {100*d.y.mean():.1f}% "
      f"· 피처 준비 {time.time()-t0:.0f}s")

# ---------------------------------------------------------------- 분할 (20_ 과 동일)
rng = np.random.default_rng(SEED)
pats = d.subject_id.unique(); rng.shuffle(pats)
tr_pat = set(pats[:int(len(pats) * 0.70)])
d["split"] = np.where(d.subject_id.isin(tr_pat), "train", "test")

FEATS = (["hr", "n_prev", "n_prev_pos", "n_prev_uta", "uta_frac", "since_conf", "since_prev"]
         + cols + ["deep_sed24"] + [f"sed_{c}" for c in CLS] + ["sed_benzo_cum"]
         + ["age", "los", "is_male", "cu", "era"]
         + ["anchor_N", "anchor_P", "anchor_U", "prev_N", "prev_P", "prev_none"]
         + EXTRA_COLS)
for a in ["N", "P", "U"]:
    d[f"anchor_{a}"] = (d.v == a).astype(float)
for a, nm in [("N", "prev_N"), ("P", "prev_P"), ("없음", "prev_none")]:
    d[nm] = (d.prev_conf == a).astype(float)

tr, te = d[d.split == "train"], d[d.split == "test"]
print(f"train {len(tr):,} / {tr.subject_id.nunique():,}명 · test {len(te):,} / {te.subject_id.nunique():,}명")
assert not (set(tr.subject_id) & set(te.subject_id))

head("[1] 2단계 XGBoost 학습")
clf = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.05,
                    subsample=0.8, colsample_bytree=0.8, eval_metric="aucpr",
                    random_state=SEED, n_jobs=-1, tree_method="hist")
clf.fit(tr[FEATS], tr.y.astype(int))
te = te.copy()
te["p"] = clf.predict_proba(te[FEATS])[:, 1]
# 1단계 B2 룩업 (동일 분할에서 재계산)
lut = tr.groupby(["prev_conf", "v"])["y"].mean()
te["b2"] = [lut.get((p_, a_), tr.y.mean()) for p_, a_ in zip(te.prev_conf, te.v)]
print(f"학습 완료 {time.time()-t0:.0f}s")

head("[2] 계층별 — 1단계(B2 lookup) vs 2단계(XGB)")
rows = []
for nm, sub in [("전체", te)] + [(f"앵커={a}", te[te.v == a]) for a in ["N", "P", "U"]]:
    yt = sub.y.astype(int).to_numpy()
    if yt.min() == yt.max():
        continue
    r_ = {"계층": nm, "n": len(sub), "기저%": round(100 * yt.mean(), 1),
          "B2 AUROC": round(100 * roc_auc_score(yt, sub.b2), 1),
          "XGB AUROC": round(100 * roc_auc_score(yt, sub.p), 1),
          "B2 AUPRC": round(100 * average_precision_score(yt, sub.b2), 1),
          "XGB AUPRC": round(100 * average_precision_score(yt, sub.p), 1)}
    r_["ΔAUROC"] = round(r_["XGB AUROC"] - r_["B2 AUROC"], 1)
    r_["ΔAUPRC"] = round(r_["XGB AUPRC"] - r_["B2 AUPRC"], 1)
    rows.append(r_)
t = pd.DataFrame(rows).set_index("계층")
print(t.to_string())
t.to_csv(os.path.join(OUT, "stage2_xgb.csv"), encoding="utf-8-sig")
print("  -> stage2_xgb.csv")

head("[3] 피처 중요도 상위 15")
imp = (pd.Series(clf.feature_importances_, index=FEATS)
       .sort_values(ascending=False).head(15) * 100).round(1)
print(imp.to_string())

head("[4] 피처군 ablation — 이득이 어디서 오나 (주 지표 = 앵커=N)")
G_STATE = ["anchor_N", "anchor_P", "anchor_U", "prev_N", "prev_P", "prev_none"]
G_HIST = ["hr", "n_prev", "n_prev_pos", "n_prev_uta", "uta_frac", "since_conf", "since_prev"]
G_RASS = cols + ["deep_sed24"]
G_MED = [f"sed_{c}" for c in CLS] + ["sed_benzo_cum"]
G_STATIC = ["age", "los", "is_male", "cu", "era"]
steps = [("A 상태만", G_STATE),
         ("B +이력", G_STATE + G_HIST),
         ("C +RASS", G_STATE + G_HIST + G_RASS),
         ("D +진정제", G_STATE + G_HIST + G_RASS + G_MED),
         ("E +정적", G_STATE + G_HIST + G_RASS + G_MED + G_STATIC)]
if EXTRA_COLS:
    steps.append(("F +mobility/pain/GCS (full)", FEATS))
teN = te[te.v == "N"]; ytN = teN.y.astype(int).to_numpy()
yt_all = te.y.astype(int).to_numpy()
rows = []
for nm, fs in steps:
    m = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.05,
                      subsample=0.8, colsample_bytree=0.8, eval_metric="aucpr",
                      random_state=SEED, n_jobs=-1, tree_method="hist")
    m.fit(tr[fs], tr.y.astype(int))
    pN = m.predict_proba(teN[fs])[:, 1]
    pA = m.predict_proba(te[fs])[:, 1]
    rows.append({"피처군": nm, "n_feat": len(fs),
                 "N AUPRC": round(100 * average_precision_score(ytN, pN), 1),
                 "N AUROC": round(100 * roc_auc_score(ytN, pN), 1),
                 "전체 AUPRC": round(100 * average_precision_score(yt_all, pA), 1)})
ab = pd.DataFrame(rows).set_index("피처군")
ab["N AUPRC 증분"] = ab["N AUPRC"].diff().round(1)
print(ab.to_string())
ab.to_csv(os.path.join(OUT, "stage2_ablation.csv"), encoding="utf-8-sig")
print("  -> stage2_ablation.csv")

head("[5] 판정")
n = t.loc["앵커=N"]
print(f"주 지표 (앵커=N AUPRC): {n['B2 AUPRC']} -> {n['XGB AUPRC']}  (Δ{n['ΔAUPRC']:+})")
print(f"        (앵커=N AUROC): {n['B2 AUROC']} -> {n['XGB AUROC']}  (Δ{n['ΔAUROC']:+})")
gain_hist = ab.loc["B +이력", "N AUPRC"] - ab.loc["A 상태만", "N AUPRC"]
gain_rass = ab.loc["C +RASS", "N AUPRC"] - ab.loc["B +이력", "N AUPRC"]
last_row = ab.index[-1]
print(f"\n이득 분해 — 이력 +{gain_hist:.1f} · RASS +{gain_rass:.1f} "
      f"· 진정제 {ab.loc['D +진정제','N AUPRC']-ab.loc['C +RASS','N AUPRC']:+.1f} "
      f"· 정적 {ab.loc['E +정적','N AUPRC']-ab.loc['D +진정제','N AUPRC']:+.1f}"
      + (f" · mobility/pain/GCS {ab.loc[last_row,'N AUPRC']-ab.loc['E +정적','N AUPRC']:+.1f}"
         if EXTRA_COLS else ""))
print("→ 마지막 증분이 크면 3단계(BiLSTM)로 원시 시계열을 넣을 근거가 생긴다.")
print("\n" + ("mobility/pain/GCS 포함본이다." if EXTRA_COLS
                else "[!] mobility/pain/GCS 미포함이다."))
''')

# ============================================================================
# [23] delirium/23_stage34_bilstm_cbm.py — BiLSTM · CBM · LTN(PADIS 공리) 학습
# ============================================================================
_SRC['23'] = ('23_stage34_bilstm_cbm.py', r'''# -*- coding: utf-8 -*-
# ============================================================================
# 3단계 BiLSTM · 4단계 CBM — 1·2단계와 동일한 test set 에서 비교
#
#   3    BiLSTM          원시 24h 시계열이 2단계의 요약 피처를 넘나
#   4    CBM             개념 병목(개념 5종)을 거치는 비용
#   4b   CBM + Assessable  라벨 미관찰 앵커(29.0%)를 Assessable 보조라벨로 재활용
#
# 시계열 채널: RASS + 진정제 + (24_ 추출분) GCS 3성분 · mobility 2종 · pain NRS.
#
# 분할: test 는 20_/22_ 와 완전히 동일(환자 단위 30%, seed 42).
#       val 은 train 환자 중 15%p 를 다시 뗀다.
# 사용: EDA_DATA=<notes/eda> python delirium/23_stage34_bilstm_cbm.py
# ============================================================================
import os, sys, time
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import roc_auc_score, average_precision_score

sys.stdout.reconfigure(encoding="utf-8")
DATA = os.environ.get("EDA_DATA", "/content/drive/MyDrive/mimic_eda")
OUT = os.environ.get("EDA_OUT", os.path.join(DATA, "out_split"))
os.makedirs(OUT, exist_ok=True)
SEED, CAM_ITEM, RASS_ITEM = 42, 228332, 228096
W_AHEAD, HR_CAP, NBIN = 24.0, 240.0, 24
DEV = "cuda" if torch.cuda.is_available() else "cpu"
torch.manual_seed(SEED); np.random.seed(SEED)
pd.set_option("display.width", 220)


def head(t):
    print("\n" + "=" * 78); print(t); print("=" * 78, flush=True)


t0 = time.time()
# ================================================================ 앵커·라벨
b = pd.read_pickle(f"{DATA}/_icu_base.pkl")
v = pd.read_parquet(f"{DATA}/_label_values.parquet")
b["intime"] = pd.to_datetime(b["intime"])
if "age" not in b.columns:
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
DEN = b[(b.age >= 18) & (b.los >= 1.0)].copy()
intime = b.set_index("stay_id")["intime"]

MAP = {"Positive": "P", "Negative": "N", "UTA": "U",
       "Unable to Assess": "U", "Unable to assess": "U"}
cam = v[v.itemid == CAM_ITEM][["stay_id", "charttime", "value"]].copy()
cam["charttime"] = pd.to_datetime(cam["charttime"])
cam["v"] = cam["value"].astype(str).str.strip().map(MAP)
cam = cam[cam.v.notna() & cam.stay_id.isin(DEN.stay_id)].copy()
cam["hr"] = (cam["charttime"] - cam["stay_id"].map(intime)).dt.total_seconds() / 3600
cam = cam[(cam.hr >= 0) & (cam.hr <= HR_CAP)].sort_values(["stay_id", "hr"]).reset_index(drop=True)

h = cam["hr"].to_numpy(float)
isC = (cam["v"] != "U").to_numpy(); isP = (cam["v"] == "P").to_numpy()
cumC = np.concatenate([[0], isC.cumsum()]); cumP = np.concatenate([[0], (isC & isP).cumsum()])
cumU = np.concatenate([[0], (~isC).cumsum()])
sids, first, cnt = np.unique(cam["stay_id"].to_numpy(), return_index=True, return_counts=True)
labeled = np.zeros(len(cam), bool); y = np.zeros(len(cam), bool)
for a, n in zip(first, cnt):
    hh = h[a:a + n]; idx = np.arange(n)
    j = np.searchsorted(hh, hh + W_AHEAD, side="right")
    labeled[a:a + n] = (cumC[a + j] - cumC[a + idx + 1]) > 0
    y[a:a + n] = (cumP[a + j] - cumP[a + idx + 1]) > 0
cam["labeled"], cam["y"] = labeled, y

cam["n_prev"] = cam.groupby("stay_id").cumcount()
pp = np.zeros(len(cam), int); pu = np.zeros(len(cam), int)
for a, n in zip(first, cnt):
    idx = np.arange(n)
    pp[a:a + n] = cumP[a + idx] - cumP[a]
    pu[a:a + n] = cumU[a + idx] - cumU[a]
cam["n_prev_pos"], cam["n_prev_uta"] = pp, pu
cam["uta_frac"] = np.where(cam.n_prev > 0, cam.n_prev_uta / cam.n_prev.clip(lower=1), 0.0)
cam["prev_conf"] = cam["v"].where(cam.v != "U").groupby(cam.stay_id).ffill().shift()
cam.loc[cam.groupby("stay_id").head(1).index, "prev_conf"] = np.nan
cam["prev_conf"] = cam["prev_conf"].fillna("없음")
lc = (cam["hr"].where(cam.v != "U").groupby(cam.stay_id).ffill()
      .groupby(cam.stay_id).shift())         # A2: stay 안에서만 shift (첫 앵커 누출 방지)
cam["since_conf"] = (cam["hr"] - lc).fillna(-1)
cam["since_prev"] = cam.groupby("stay_id")["hr"].diff().fillna(-1)

# ================================================================ 시계열 (24 x C)
r = v[v.itemid == RASS_ITEM][["stay_id", "charttime", "valuenum"]].copy()
r["charttime"] = pd.to_datetime(r["charttime"])
r = r[r.stay_id.isin(DEN.stay_id)].copy()
r["hr"] = (r["charttime"] - r["stay_id"].map(intime)).dt.total_seconds() / 3600
r = r[r.hr >= 0].sort_values(["stay_id", "hr"])
RH, RV = {}, {}
for k, g in r.groupby("stay_id", sort=False):
    RH[k] = g["hr"].to_numpy(float)
    RV[k] = np.nan_to_num(g["valuenum"].to_numpy(float), nan=0.0)

sed = pd.read_parquet(f"{DATA}/_step1_sed.parquet")
sed = sed[sed.stay_id.isin(DEN.stay_id)].copy()
for c in ["starttime", "endtime"]:
    sed[c] = pd.to_datetime(sed[c])
sed["s"] = (sed["starttime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
sed["e"] = (sed["endtime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
BENZO = {"lorazepam", "midazolam", "diazepam"}
sed["cls"] = np.where(sed.drug.isin(BENZO), "benzo", sed.drug)
CLS = ["benzo", "propofol", "dexmedetomidine"]
SED = {k: (g["s"].to_numpy(float), g["e"].to_numpy(float), g["cls"].to_numpy())
       for k, g in sed.groupby("stay_id", sort=False)}

# 채널: RASS mean · RASS min · 관측있음 · benzo · propofol · dexmed
NCH = 6
X = np.zeros((len(cam), NBIN, NCH), dtype=np.float32)
edges = np.linspace(-24.0, 0.0, NBIN + 1)          # 앵커 기준 상대시간
centers = (edges[:-1] + edges[1:]) / 2
for a, n in zip(first, cnt):
    sid = cam["stay_id"].iloc[a]
    hh = h[a:a + n]
    arr = RH.get(sid)
    if arr is not None:
        vals = RV[sid]
        csum = np.concatenate([[0.0], np.cumsum(vals)])
        cmin = vals  # min 은 구간별로 직접
        bnd = np.searchsorted(arr, hh[:, None] + edges[None, :], side="left")  # (n, NBIN+1)
        lo, hi = bnd[:, :-1], bnd[:, 1:]
        k_ = hi - lo
        sm = csum[hi] - csum[lo]
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(k_ > 0, sm / np.maximum(k_, 1), 0.0)
        X[a:a + n, :, 0] = mean
        X[a:a + n, :, 2] = (k_ > 0)
        # min: 구간이 있는 칸만 루프 (대부분 0~2개)
        for i in range(n):
            for jb in range(NBIN):
                if k_[i, jb] > 0:
                    X[a + i, jb, 1] = cmin[lo[i, jb]:hi[i, jb]].min()
    g = SED.get(sid)
    if g is not None:
        s_, e_, cl = g
        ct = hh[:, None, None] + centers[None, :, None]        # (n, NBIN, 1)
        cov = (s_[None, None, :] <= ct) & (e_[None, None, :] > ct)
        for ci, c in enumerate(CLS):
            X[a:a + n, :, 3 + ci] = (cov & (cl == c)[None, None, :]).any(2)
# ---- mobility / pain / GCS 채널 붙이기 ----
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _extra_features import build_extra_channels

EX, EXNAMES = build_extra_channels(DATA, cam["stay_id"].to_numpy(), h, first, cnt, nbin=NBIN)
EX_START = X.shape[2]
if EX is None:
    print("[!] _extra_values.parquet 없음 — RASS+진정제 채널만 쓴다")
else:
    EX_START = X.shape[2]
    X = np.concatenate([X, EX], axis=2)
    NCH = X.shape[2]
    del EX
    print(f"채널 확장 -> {NCH} ({', '.join(EXNAMES)})")

print(f"시계열 텐서 {X.shape} · {X.nbytes/1e6:.0f}MB · {time.time()-t0:.0f}s", flush=True)

# ---------------- 25_ 산출물: 동반질환 3종 + 수혈 ----------------
# 공리를 강제하려면 개념이 필요하고, 개념을 예측하려면 입력에도 있어야 한다. 셋 다 붙인다.
_cmb_p = f"{DATA}/_axiom_comorb.parquet"
_trf_p = f"{DATA}/_axiom_transfusion.parquet"
HAS_GAP = os.path.exists(_cmb_p) and os.path.exists(_trf_p)
if HAS_GAP:
    _hadm = DEN.set_index("stay_id")["hadm_id"].astype("int64")
    cam["hadm_id"] = cam["stay_id"].map(_hadm)
    _cmb = pd.read_parquet(_cmb_p).set_index("hadm_id")
    for _w in ["dementia", "trauma", "hypertension"]:
        cam[_w] = cam["hadm_id"].map(_cmb[_w]).fillna(0).astype(np.float32)
    _trf = pd.read_parquet(_trf_p)
    _tb = {k: (np.sort(g["hr"].to_numpy(np.float64)),
               g.sort_values("hr")["is_rbc"].to_numpy(np.float64))
           for k, g in _trf.groupby("stay_id", sort=False)}
    _tr24 = np.zeros(len(cam), np.float32)      # 이전 24h 안 수혈(적혈구)
    _trcum = np.zeros(len(cam), np.float32)     # 앵커까지 누적 수혈 건수
    for a_, n_ in zip(first, cnt):
        g_ = _tb.get(cam["stay_id"].iloc[a_])
        if g_ is None:
            continue
        hs_, rb_ = g_
        hh_ = h[a_:a_ + n_]
        hi_ = np.searchsorted(hs_, hh_, side="right")
        lo_ = np.searchsorted(hs_, hh_ - 24.0, side="left")
        crb = np.concatenate([[0.0], np.cumsum(rb_)])
        _tr24[a_:a_ + n_] = (crb[hi_] - crb[lo_]) > 0
        _trcum[a_:a_ + n_] = hi_
    cam["transfusion24"] = _tr24
    cam["transfusion_cum"] = _trcum
    print(f"공백 공리 입력 — dementia {100*cam.dementia.mean():.1f}% · "
          f"trauma {100*cam.trauma.mean():.1f}% · hypertension {100*cam.hypertension.mean():.1f}% · "
          f"수혈(24h) {100*(_tr24>0).mean():.1f}%")
else:
    print("[!] _axiom_comorb/_axiom_transfusion 없음 — 공리 8개로 진행 (delirium/25_ 를 먼저 돌릴 것)")

# ================================================================ 정적/이력 벡터
st = DEN.set_index("stay_id")
cam["subject_id"] = cam["stay_id"].map(st["subject_id"])
cam["age"] = cam["stay_id"].map(st["age"])
cam["los"] = cam["stay_id"].map(st["los"])
cam["is_male"] = (cam["stay_id"].map(st["gender"]) == "M").astype(float)
cam["cu"] = cam["stay_id"].map(st["first_careunit"]).astype("category").cat.codes
cam["era"] = cam["stay_id"].map(st["anchor_year_group"]).astype("category").cat.codes
for a_ in ["N", "P", "U"]:
    cam[f"anchor_{a_}"] = (cam.v == a_).astype(float)
for a_, nm in [("N", "prev_N"), ("P", "prev_P"), ("없음", "prev_none")]:
    cam[nm] = (cam.prev_conf == a_).astype(float)
SFEAT = ["hr", "n_prev", "n_prev_pos", "n_prev_uta", "uta_frac", "since_conf", "since_prev",
         "age", "los", "is_male", "cu", "era",
         "anchor_N", "anchor_P", "anchor_U", "prev_N", "prev_P", "prev_none"]
if HAS_GAP:
    SFEAT += ["dementia", "trauma", "hypertension", "transfusion24", "transfusion_cum"]
S = cam[SFEAT].to_numpy(np.float32)

# ---------------- 개념 라벨 ----------------
# 두 벌을 만든다.
#   BIN  : 이진 임계 (v2). 지금까지 쓰던 것.
#   CONT : 연속값 (v3). 같은 임상량을 임계 없이 그대로 개념으로 둔다.
# -10.1 의 병목 비용이 정의의 거칠기 탓인지 가리려면 둘을 같은 폭에서 비교해야 한다.
# 미관측(예: mobility 기록 없음)은 개념 손실에서 마스킹한다 — 중앙값으로 채우면 라벨 잡음이 된다.
#
# 채널(정규화 전 raw X): 0 rass_mean · 1 rass_binmin · 2 rass_obs · 3 benzo · 4 propofol
#   · 5 dexmed · 6/7 gcs_eye · 8/9 gcs_verbal · 10/11 gcs_motor · 12/13 mob_braden
#   · 14/15 mob_jhhlm · 16/17 pain_nrs · 18 pain_attempt
def _agg(vi, mi, how):
    v, m = X[:, :, vi], X[:, :, mi] > 0
    if how == "min":
        o = np.where(m, v, np.inf).min(1)
    else:
        o = np.where(m, v, -np.inf).max(1)
    ok = np.isfinite(o)
    return np.where(ok, o, 0.0).astype(np.float32), ok


_rm = X[:, :, 2] > 0
_rass_min = np.where(_rm, X[:, :, 1], np.inf).min(1)
_rass_ok = np.isfinite(_rass_min)
_rass_min = np.where(_rass_ok, _rass_min, 0.0).astype(np.float32)
_rass_negmean = (np.where(_rm, np.minimum(X[:, :, 0], 0), 0.0).sum(1)
                 / np.maximum(_rm.sum(1), 1)).astype(np.float32)
_one = np.ones(len(cam), bool)
_nb = X.shape[1]
_benzo_f = X[:, :, 3].mean(1); _prop_f = X[:, :, 4].mean(1); _dex_f = X[:, :, 5].mean(1)
_age = cam["age"].to_numpy(np.float32)
_male = (cam["is_male"].to_numpy() > 0)
_lab = cam["labeled"].to_numpy()
_curP = (cam.v.to_numpy() == "P")
_curU = (cam.v.to_numpy() == "U")
_npv = cam.n_prev.to_numpy(); _pf = cam.n_prev_pos.to_numpy() / np.maximum(_npv, 1)
_uf = cam.n_prev_uta.to_numpy() / np.maximum(_npv, 1)

if NCH > 6:
    _ge, _geo = _agg(6, 7, "min"); _gv, _gvo = _agg(8, 9, "min"); _gm, _gmo = _agg(10, 11, "min")
    _gcs = (_ge + _gv + _gm).astype(np.float32); _gcso = _geo & _gvo & _gmo
    _mb, _mbo = _agg(12, 13, "min")
    _mj, _mjo = _agg(14, 15, "min")
    _mjx, _mjxo = _agg(14, 15, "max")
    _pn, _pno = _agg(16, 17, "max")
    _pa = (X[:, :, 18].max(1) > 0)
else:
    _gcs = _gcso = _mb = _mbo = _mj = _mjo = _mjx = _mjxo = _pn = _pno = _pa = None

# (이름, 값, 마스크, 종류)
BIN_DEF = [("DeepSedation", (_rass_min <= -4), _one, "bin"),
           ("HighSedationIntensity", (_rass_negmean <= -2), _one, "bin"),
           ("BenzoExposure", (_benzo_f > 0), _one, "bin"),
           ("PropofolExposure", (_prop_f > 0), _one, "bin"),
           ("DexmedExposure", (_dex_f > 0), _one, "bin")]
CONT_DEF = [("RASSmin", _rass_min, _rass_ok, "cont"),
            ("RASSnegmean", _rass_negmean, _one, "cont"),
            ("BenzoFrac", _benzo_f, _one, "cont"),
            ("PropofolFrac", _prop_f, _one, "cont"),
            ("DexmedFrac", _dex_f, _one, "cont")]
if NCH > 6:
    BIN_DEF += [("LowGCS", (_gcs <= 8), _gcso, "bin"),
                ("Immobility", (_mb <= 2) | (_mj <= 2), _mbo | _mjo, "bin"),
                ("EarlyMobility", (_mjx >= 4), _mjxo, "bin"),
                ("SeverePain", (_pn >= 4), _pno, "bin"),
                ("PainUnassessable", _pa & ~_pno, _one, "bin")]
    CONT_DEF += [("GCStotal", _gcs, _gcso, "cont"),
                 ("MobBraden", _mb, _mbo, "cont"),
                 ("MobJHHLM", _mjx, _mjxo, "cont"),
                 ("PainNRSmax", _pn, _pno, "cont"),
                 ("PainUnassessable", _pa & ~_pno, _one, "bin")]
_TAIL = [("OlderAge", (_age >= 65), _one, "bin"), ("MaleSex", _male, _one, "bin"),
         ("Assessable", _lab, _one, "bin"), ("CurrentDelirium", _curP, _one, "bin"),
         ("PriorDelirium", (cam.n_prev_pos.to_numpy() > 0), _one, "bin")]
_TAILC = [("Age", _age, _one, "cont"), ("MaleSex", _male, _one, "bin"),
          ("Assessable", _lab, _one, "bin"), ("CurrentDelirium", _curP, _one, "bin"),
          ("CurrentUTA", _curU, _one, "bin"), ("PriorDeliriumFrac", _pf, _one, "cont"),
          ("PriorUTAFrac", _uf, _one, "cont")]
if HAS_GAP:
    _gap = [("Dementia", cam.dementia.to_numpy() > 0, _one, "bin"),
            ("Trauma", cam.trauma.to_numpy() > 0, _one, "bin"),
            ("Hypertension", cam.hypertension.to_numpy() > 0, _one, "bin"),
            ("BloodTransfusion", cam.transfusion24.to_numpy() > 0, _one, "bin")]
    BIN_DEF += _gap
    CONT_DEF += _gap
BIN_DEF += _TAIL
CONT_DEF += _TAILC


def _pack(defs):
    names = [d[0] for d in defs]
    arr = np.stack([np.asarray(d[1], dtype=np.float32) for d in defs], 1)
    msk = np.stack([np.asarray(d[2], dtype=np.float32) for d in defs], 1)
    typ = [d[3] for d in defs]
    # 연속 개념은 train 통계로 표준화한다 (MSE 스케일 통일)
    return names, arr, msk, typ


CONCEPTS, CARR, CMASK, CTYPE = _pack(BIN_DEF)
CONCEPTS_C, CARR_C, CMASK_C, CTYPE_C = _pack(CONT_DEF)
V1 = ["DeepSedation", "BenzoExposure", "Assessable", "CurrentDelirium", "PriorDelirium"]
CONCEPT_SETS = {"5 (v1)": [CONCEPTS.index(x) for x in V1]}
print(f"개념 세트 — 이진 {len(CONCEPTS)}개 / 연속 {len(CONCEPTS_C)}개"
      f" (연속 중 cont {sum(t=='cont' for t in CTYPE_C)}개)")

# ================================================================ 분할 (test 는 20_/22_ 와 동일)
lab_idx = np.where(cam.labeled.to_numpy())[0]
d_lab = cam.iloc[lab_idx]
rng = np.random.default_rng(SEED)
pats = d_lab.subject_id.unique(); rng.shuffle(pats)
tr_pat_all = set(pats[:int(len(pats) * 0.70)])
rng2 = np.random.default_rng(SEED + 1)
tr_list = np.array(sorted(tr_pat_all)); rng2.shuffle(tr_list)
val_pat = set(tr_list[:int(len(tr_list) * 0.20)])
tr_pat = tr_pat_all - val_pat

subj = cam["subject_id"].to_numpy()
in_tr = np.isin(subj, list(tr_pat)); in_val = np.isin(subj, list(val_pat))
in_te = ~np.isin(subj, list(tr_pat_all))
L = cam.labeled.to_numpy()
print(f"train {int((in_tr&L).sum()):,} · val {int((in_val&L).sum()):,} · test {int((in_te&L).sum()):,} (라벨 기준)")

# ---------------- 요약 벡터 Z — MLP/CBM/XGB 가 공유하는 입력 ----------------
# X(시계열)에서 그대로 파생한다. BiLSTM 과 입력 정보량이 같아야 backbone 비교가 성립한다.
def _summ(v, m):
    cnt = m.sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(cnt > 0, (v * m).sum(1) / np.maximum(cnt, 1), np.nan)
    vmin = np.where(m, v, np.inf).min(1); vmin[~np.isfinite(vmin)] = np.nan
    vmax = np.where(m, v, -np.inf).max(1); vmax[~np.isfinite(vmax)] = np.nan
    nb = m.shape[1]
    li = nb - 1 - np.argmax(m[:, ::-1], axis=1)
    last = np.where(cnt > 0, v[np.arange(len(v)), np.maximum(li, 0)], np.nan)
    return [mean, vmin, vmax, last, cnt.astype(np.float32)]


zc, zn = [], []
_m = X[:, :, 2] > 0
zc += _summ(X[:, :, 0], _m); zn += [f"rass_{k}" for k in ["mean", "min", "max", "last", "n"]]
_bmin = np.where(_m, X[:, :, 1], np.inf).min(1); _bmin[~np.isfinite(_bmin)] = np.nan
zc.append(_bmin); zn.append("rass_binmin")
zc.append((_bmin <= -4).astype(np.float32)); zn.append("deep_sed24")
for ci, c in enumerate(CLS):
    zc.append(X[:, :, 3 + ci].max(1)); zn.append(f"sed_{c}")
if EX_START < X.shape[2]:
    from _extra_features import summarize as _sm
    _z, _n = _sm(X[:, :, EX_START:], EXNAMES)
    zc += [_z[:, i] for i in range(_z.shape[1])]; zn += _n
Z = np.concatenate([S, np.stack(zc, 1).astype(np.float32)], 1)
ZCOLS = SFEAT + zn
# 결측은 train 중앙값으로 채운다 (관측 수 _n 피처가 결측 여부를 이미 담고 있다)
_med = np.nanmedian(Z[in_tr & L], axis=0)
_med = np.where(np.isfinite(_med), _med, 0.0)
Z = np.where(np.isfinite(Z), Z, _med[None, :]).astype(np.float32)
zmu, zsd = Z[in_tr & L].mean(0), Z[in_tr & L].std(0) + 1e-6
Z = (Z - zmu) / zsd
Zt = torch.from_numpy(Z)
print(f"요약 벡터 Z {Z.shape} ({len(ZCOLS)} 피처)")

mu, sd = S[in_tr & L].mean(0), S[in_tr & L].std(0) + 1e-6
S = (S - mu) / sd
xm = X[in_tr & L].reshape(-1, NCH).mean(0)
xs = X[in_tr & L].reshape(-1, NCH).std(0) + 1e-6
X = (X - xm) / xs

Xt = torch.from_numpy(X); St = torch.from_numpy(S)
Yt = torch.from_numpy(cam.y.to_numpy().astype(np.float32))
# 연속 개념은 train 통계로 표준화
_trm = (in_tr & L)
_cs = CARR_C.copy()
_cmu = np.zeros(_cs.shape[1], np.float32); _csd = np.ones(_cs.shape[1], np.float32)
for i, t_ in enumerate(CTYPE_C):
    if t_ == "cont":
        w = _trm & (CMASK_C[:, i] > 0)
        mu_, sd_ = _cs[w, i].mean(), _cs[w, i].std() + 1e-6
        _cmu[i], _csd[i] = mu_, sd_
        _cs[:, i] = (_cs[:, i] - mu_) / sd_
Ct = torch.from_numpy(CARR)
Mt = torch.from_numpy(CMASK)
CtC = torch.from_numpy(_cs)
MtC = torch.from_numpy(CMASK_C)
TYPE_B = torch.tensor([t == "bin" for t in CTYPE])
TYPE_C = torch.tensor([t == "bin" for t in CTYPE_C])
Lt = torch.from_numpy(L.astype(np.float32))


# ================================================================ PADIS 공리 (5단계)
# NeSy-SMP/pipeline/horn_to_ltn.py 가 컴파일한 19개 중 **데이터가 있는 8개**만 강제한다.
# BloodTransfusion · PhysicalRestraint · Dementia · Trauma · Hypertension · Melatonin ·
# OpioidExposure · MechanicalVentilation 은 미매핑이고, HighMortality 는 우리 출력이 아니다.
#
# 연속 개념 위에서 술어의 진리값이 필요하다 — 임계 기반 membership 으로 둔다.
# 이건 원 논문의 weak anchoring(stratified_main.py 519-537)이 있던 자리와 같다.
CI = {n: i for i, n in enumerate(CONCEPTS_C)}
TAU = 0.35          # membership 의 부드러움 (표준화 좌표)


RAW_THR = {}          # 공리 이름 -> (개념, 원 단위 임계). 역학 계산에 쓴다.


def _zthr(name, raw):
    i = CI[name]
    return float((raw - _cmu[i]) / _csd[i])


# (이름, 개념, 방향(+1: 임계 이상이 참), 임계z, head, head 부정, GRADE)
GRADE_W = {"strong": 1.0, "moderate": 0.6, "low": 0.3, "cohort": 0.3, "derived": 0.5,
           "inconclusive": 0.2}
AXIOMS = [
    ("Benzo→Delirium", "BenzoFrac", +1, _zthr("BenzoFrac", 1e-6), "Delirium", False, "strong"),
    ("DeepSedation→Delirium", "RASSmin", -1, _zthr("RASSmin", -4.0), "Delirium", False, "low"),
    ("SedationIntensity→Delirium", "RASSnegmean", -1, _zthr("RASSnegmean", -2.0),
     "Delirium", False, "cohort"),
    ("SeverePain→Delirium", "PainNRSmax", +1, _zthr("PainNRSmax", 4.0), "Delirium", False,
     "inconclusive"),
    ("OlderAge→Delirium", "Age", +1, _zthr("Age", 65.0), "Delirium", False, "strong"),
    ("Dexmed→¬Delirium", "DexmedFrac", +1, _zthr("DexmedFrac", 1e-6), "Delirium", True, "moderate"),
    ("EarlyMobility→¬Delirium", "MobJHHLM", +1, _zthr("MobJHHLM", 4.0), "Delirium", True, "low"),
    # precludes 는 '지금 평가가 불가능하다' 는 뜻이다. Assessable(=미래 24h 에 확정 기록이 있나)
    # 로 걸면 LTN 학습셋에서 정답이 상수 1 이라 개념 손실과 정면충돌한다. 현재 상태로 건다.
    ("DeepSedation→CurrentUTA", "RASSmin", -1, _zthr("RASSmin", -4.0), "CurrentUTA", False,
     "derived"),
]
if HAS_GAP:
    # delirium/25_ 로 회수한 4개. 전부 양의 방향이라 균형이 5:3 -> 9:3 으로 기운다 (collapse 주의)
    AXIOMS += [
        ("BloodTransfusion→Delirium", "BloodTransfusion", +1, 0.5, "Delirium", False, "strong"),
        ("Dementia→Delirium", "Dementia", +1, 0.5, "Delirium", False, "strong"),
        ("Trauma→Delirium", "Trauma", +1, 0.5, "Delirium", False, "strong"),
        ("Hypertension→Delirium", "Hypertension", +1, 0.5, "Delirium", False, "moderate"),
    ]
AX_W = torch.tensor([GRADE_W[a[6]] for a in AXIOMS], dtype=torch.float32)
AX_W = AX_W / AX_W.sum()
print(f"공리 {len(AXIOMS)}개 강제 (컴파일 19개 중 데이터 있는 것) · "
      f"양의 방향 {sum(1 for a in AXIOMS if not a[5])} · 음의 방향 {sum(1 for a in AXIOMS if a[5])}")


def axiom_sat(c, p_del, per_axiom=False):
    """공리별 만족도. 함축은 Reichenbach(1-a+ab), 전칭은 pMeanError(p=2)."""
    sats = []
    for nm, cn, sgn, thr, head, neg, _g in AXIOMS:
        z = c[:, CI[cn]]
        # 이진 개념은 헤드가 이미 확률을 내므로 sigmoid 만, 연속 개념은 임계 membership
        a = (torch.sigmoid(z) if CTYPE_C[CI[cn]] == "bin"
             else torch.sigmoid(sgn * (z - thr) / TAU))
        b = p_del if head == "Delirium" else torch.sigmoid(c[:, CI[head]])
        if neg:
            b = 1.0 - b
        sat = 1.0 - a + a * b                      # a -> b
        agg = 1.0 - torch.sqrt(torch.clamp(((1.0 - sat) ** 2).mean(), min=1e-9))
        sats.append(agg)
    st = torch.stack(sats)
    return st if per_axiom else (st * AX_W.to(st.device)).sum()


# ================================================================ 모델
class Net(nn.Module):
    """backbone='bilstm' 은 시계열 텐서를, 'mlp' 는 요약 벡터 Z 를 받는다."""

    def __init__(self, nch, nstat, hid=64, cbm=False, nconcept=15,
                 backbone="bilstm", nz=0):
        super().__init__()
        self.cbm, self.backbone = cbm, backbone
        if backbone == "bilstm":
            self.lstm = nn.LSTM(nch, hid, batch_first=True, bidirectional=True)
            self.att = nn.Linear(hid * 2, 1)
            self.stat = nn.Sequential(nn.Linear(nstat, hid), nn.ReLU())
            enc_in = hid * 3
        else:
            self.mlp = nn.Sequential(
                nn.Linear(nz, hid * 4), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(hid * 4, hid * 2), nn.ReLU(), nn.Dropout(0.1))
            enc_in = hid * 2
        self.enc = nn.Sequential(nn.Linear(enc_in, hid), nn.ReLU(), nn.Dropout(0.1))
        self.register_buffer('type_bin', torch.ones(nconcept, dtype=torch.bool))
        self.concept = nn.Linear(hid, nconcept)
        # CBM: 개념값만 통과시킨다 (병목). 비CBM: 표현 전체를 쓴다.
        self.out = nn.Linear(nconcept if cbm else hid, 1)

    def forward(self, x, s, z=None):
        if self.backbone == "bilstm":
            o, _ = self.lstm(x)
            w = torch.softmax(self.att(o), 1)
            h_ = torch.cat([(o * w).sum(1), self.stat(s)], 1)
        else:
            h_ = self.mlp(z)
        h_ = self.enc(h_)
        c = self.concept(h_)
        if not self.cbm:
            return self.out(h_).squeeze(1), c
        # 병목: 이진 개념은 sigmoid, 연속 개념은 예측값 그대로 통과
        tb = self.type_bin.to(c.device)
        z_ = torch.where(tb, torch.sigmoid(c), c)
        return self.out(z_).squeeze(1), c


def run(name, cbm, use_unlabeled, w_concept, epochs=10, bs=2048, backbone="bilstm",
        seed=SEED, quiet=False, cidx=None, cset="bin", w_axiom=0.0):
    torch.manual_seed(seed)
    np.random.seed(seed)
    _C, _M, _T = (Ct, Mt, TYPE_B) if cset == "bin" else (CtC, MtC, TYPE_C)
    cidx = list(range(_C.shape[1])) if cidx is None else cidx
    Csub, Msub, Tsub = _C[:, cidx], _M[:, cidx], _T[cidx]
    m = Net(NCH, len(SFEAT), cbm=cbm, nconcept=len(cidx),
            backbone=backbone, nz=Z.shape[1]).to(DEV)
    m.type_bin.copy_(Tsub.to(DEV))
    opt = torch.optim.Adam(m.parameters(), lr=1e-3)
    bce = nn.BCEWithLogitsLoss(reduction="none")
    tr_mask = in_tr if use_unlabeled else (in_tr & L)
    idx_tr = np.where(tr_mask)[0]
    idx_va = np.where(in_val & L)[0]
    idx_te = np.where(in_te & L)[0]
    best, best_state, bad = -1, None, 0
    for ep in range(epochs):
        m.train()
        perm = np.random.permutation(idx_tr)
        tot = 0.0
        for i in range(0, len(perm), bs):
            j = perm[i:i + bs]
            xb, sb = Xt[j].to(DEV), St[j].to(DEV)
            yb, cb, lb = Yt[j].to(DEV), Csub[j].to(DEV), Lt[j].to(DEV)
            mb_ = Msub[j].to(DEV); tb_ = Tsub.to(DEV)
            zb = Zt[j].to(DEV)
            logit, c = m(xb, sb, zb)
            ltask = (bce(logit, yb) * lb).sum() / lb.sum().clamp(min=1)
            if w_concept > 0:
                lb_ = torch.where(tb_.unsqueeze(0), bce(c, cb), (c - cb) ** 2)
                lcon = (lb_ * mb_).sum() / mb_.sum().clamp(min=1)
            else:
                lcon = torch.zeros((), device=DEV)
            loss = ltask + w_concept * lcon
            if w_axiom > 0:
                loss = loss + w_axiom * (1.0 - axiom_sat(c, torch.sigmoid(logit)))
            opt.zero_grad(); loss.backward(); opt.step()
            tot += float(loss.detach()) * len(j)
        m.eval()
        with torch.no_grad():
            pv = []
            for i in range(0, len(idx_va), 8192):
                j = idx_va[i:i + 8192]
                pv.append(torch.sigmoid(
                    m(Xt[j].to(DEV), St[j].to(DEV), Zt[j].to(DEV))[0]).cpu().numpy())
            pv = np.concatenate(pv)
        yv = cam.y.to_numpy()[idx_va].astype(int)
        vN = cam.v.to_numpy()[idx_va] == "N"
        ap = average_precision_score(yv[vN], pv[vN])       # 주 지표로 조기종료
        if not quiet:
            print(f"  {name} ep{ep+1} loss={tot/len(perm):.4f} valN_AUPRC={100*ap:.1f}", flush=True)
        if ap > best:
            best, best_state, bad = ap, {k: t.detach().clone() for k, t in m.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 2:
                if not quiet:
                    print("  early stop")
                break
    m.load_state_dict(best_state); m.eval()
    if cset == "cont" and not quiet and w_concept > 0:
        with torch.no_grad():
            _sat = []
            for i in range(0, len(idx_te), 8192):
                j = idx_te[i:i + 8192]
                _lg, _c = m(Xt[j].to(DEV), St[j].to(DEV), Zt[j].to(DEV))
                _sat.append(axiom_sat(_c, torch.sigmoid(_lg), per_axiom=True).cpu().numpy())
            AX_SAT[name] = np.mean(_sat, 0)
    with torch.no_grad():
        pt = []
        for i in range(0, len(idx_te), 8192):
            j = idx_te[i:i + 8192]
            pt.append(torch.sigmoid(
                m(Xt[j].to(DEV), St[j].to(DEV), Zt[j].to(DEV))[0]).cpu().numpy())
        pt = np.concatenate(pt)
    return idx_te, pt


AX_SAT = {}
head(f"[학습] device={DEV}")
res = {}
_I5 = CONCEPT_SETS["5 (v1)"]
res["3 BiLSTM"] = run("3 BiLSTM", cbm=False, use_unlabeled=False, w_concept=0.0)
res["4 CBM-5"] = run("4 CBM-5", cbm=True, use_unlabeled=False, w_concept=1.0, cidx=_I5)
res[f"4x CBM-{len(CONCEPTS)} 이진"] = run("4x 이진", cbm=True, use_unlabeled=False, w_concept=1.0)
res[f"4c CBM-{len(CONCEPTS_C)} 연속"] = run("4c 연속", cbm=True, use_unlabeled=False,
                                            w_concept=1.0, cset="cont")
res[f"4f free-{len(CONCEPTS_C)}"] = run("4f free", cbm=True, use_unlabeled=False,
                                        w_concept=0.0, cset="cont")
res["5 LTN (w_K=0.2)"] = run("5 LTN", cbm=True, use_unlabeled=False, w_concept=1.0,
                             cset="cont", w_axiom=0.2)
res["5 LTN (w_K=0.5)"] = run("5 LTN .5", cbm=True, use_unlabeled=False, w_concept=1.0,
                             cset="cont", w_axiom=0.5)

# 같은 Z 위의 XGBoost — backbone 비교의 상한 기준
from xgboost import XGBClassifier
_xi_tr, _xi_te = np.where(in_tr & L)[0], np.where(in_te & L)[0]
_x = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.05, subsample=0.8,
                   colsample_bytree=0.8, eval_metric="aucpr", random_state=SEED,
                   n_jobs=-1, tree_method="hist")
_x.fit(Z[_xi_tr], cam.y.to_numpy()[_xi_tr].astype(int))
res["2z XGB(같은 Z)"] = (_xi_te, _x.predict_proba(Z[_xi_te])[:, 1])

head("[결과] 1~4단계 — 동일 test set")
# 22_ 를 건너뛰고 23_ 만 돌리면 stage2_xgb.csv 가 없다. 학습을 다 끝낸 뒤 여기서 멈추지 않도록
# 1·2단계 열만 빼고 표를 만든다.
_prev_p = os.path.join(OUT, "stage2_xgb.csv")
_has_prev = os.path.exists(_prev_p)
if _has_prev:
    prev = pd.read_csv(_prev_p)
    prev = prev.set_index(prev.columns[0])
else:
    print(f"[!] {_prev_p} 없음 — 1 lookup · 2 XGB 열을 빼고 표를 만든다 (22_ 를 돌리면 채워진다)")
idx_te = res["3 BiLSTM"][0]
vte = cam.v.to_numpy()[idx_te]; yte = cam.y.to_numpy()[idx_te].astype(int)
rows = []
for strat in ["전체", "앵커=N", "앵커=P", "앵커=U"]:
    sel = np.ones(len(idx_te), bool) if strat == "전체" else (vte == strat[-1])
    r_ = {"계층": strat, "n": int(sel.sum())}
    if _has_prev:
        r_["1 lookup"] = prev.loc[strat, "B2 AUPRC"]
        r_["2 XGB"] = prev.loc[strat, "XGB AUPRC"]
    for nm, (_, p) in res.items():
        r_[nm] = round(100 * average_precision_score(yte[sel], p[sel]), 1)
    rows.append(r_)
t = pd.DataFrame(rows).set_index("계층")
print("AUPRC")
print(t.to_string())
t.to_csv(os.path.join(OUT, "stage34.csv"), encoding="utf-8-sig")

rows = []
for strat in ["전체", "앵커=N", "앵커=P", "앵커=U"]:
    sel = np.ones(len(idx_te), bool) if strat == "전체" else (vte == strat[-1])
    r_ = {"계층": strat}
    if _has_prev:
        r_["1 lookup"] = prev.loc[strat, "B2 AUROC"]
        r_["2 XGB"] = prev.loc[strat, "XGB AUROC"]
    for nm, (_, p) in res.items():
        r_[nm] = round(100 * roc_auc_score(yte[sel], p[sel]), 1)
    rows.append(r_)
ta = pd.DataFrame(rows).set_index("계층")
print("\nAUROC")
print(ta.to_string())
ta.to_csv(os.path.join(OUT, "stage34_auroc.csv"), encoding="utf-8-sig")

# AUPRC 의 무작위 예측 값은 곧 그 계층의 기저율이다. 계층끼리 원값으로 비교하면
# 기저 78% 인 앵커=P 가 저절로 높아 보인다. 기저 대비로 정규화해서 같이 본다.
head("[기저 보정] 계층끼리 비교하려면 AUPRC 를 기저 대비로")
_rows = []
for _st in ["전체", "앵커=N", "앵커=P", "앵커=U"]:
    if _st not in t.index:
        continue
    _sel = np.ones(len(idx_te), bool) if _st == "전체" else (vte == _st[-1])
    _b = 100 * yte[_sel].mean()
    _r = {"계층": _st, "기저%": round(_b, 1)}
    for _c in t.columns:
        if _c != "n":
            _r[_c] = round(100 * (t.loc[_st, _c] - _b) / (100 - _b), 1)
    _rows.append(_r)
tn = pd.DataFrame(_rows).set_index("계층")
print("정규화 AUPRC = (AUPRC − 기저) / (100 − 기저) · 0=무작위 · 100=완전")
print(tn.to_string())
tn.to_csv(os.path.join(OUT, "stage34_auprc_norm.csv"), encoding="utf-8-sig")

head("[시드 3개] 앵커=N AUPRC — backbone 결론을 단일 시드로 내리지 않는다")
SEEDS = [42, 7, 2024]
VARIANTS = [
    ("3  BiLSTM", dict(cbm=False, use_unlabeled=False, w_concept=0.0)),
    ("4  CBM-5", dict(cbm=True, use_unlabeled=False, w_concept=1.0, cidx=_I5)),
    (f"4x 이진-{len(CONCEPTS)}", dict(cbm=True, use_unlabeled=False, w_concept=1.0)),
    (f"4c 연속-{len(CONCEPTS_C)}", dict(cbm=True, use_unlabeled=False, w_concept=1.0, cset="cont")),
    (f"4f free-{len(CONCEPTS_C)}", dict(cbm=True, use_unlabeled=False, w_concept=0.0, cset="cont")),
    ("5  LTN w_K=0.2", dict(cbm=True, use_unlabeled=False, w_concept=1.0,
                           cset="cont", w_axiom=0.2)),
    ("5  LTN w_K=0.5", dict(cbm=True, use_unlabeled=False, w_concept=1.0,
                           cset="cont", w_axiom=0.5)),
]
_teN = cam.v.to_numpy()[res["3 BiLSTM"][0]] == "N"
_ytN = cam.y.to_numpy()[res["3 BiLSTM"][0]].astype(int)[_teN]
rows = []
for nm, kw in VARIANTS:
    vals = []
    for sd_ in SEEDS:
        _, pp = run(nm, seed=sd_, quiet=True, **kw)
        vals.append(100 * average_precision_score(_ytN, pp[_teN]))
    rows.append({"모델": nm, "평균": round(float(np.mean(vals)), 1),
                 "표준편차": round(float(np.std(vals)), 1),
                 "최소": round(min(vals), 1), "최대": round(max(vals), 1),
                 "시드별": " / ".join(f"{v:.1f}" for v in vals)})
    print(f"  {nm:14s} {rows[-1]['평균']:5.1f} ± {rows[-1]['표준편차']:.1f}   ({rows[-1]['시드별']})",
          flush=True)
sv = pd.DataFrame(rows).set_index("모델")
sv.to_csv(os.path.join(OUT, "stage34_seeds.csv"), encoding="utf-8-sig")
print("  -> stage34_seeds.csv")
_b = sv.loc[f"4x 이진-{len(CONCEPTS)}", "평균"]
_cc = sv.loc[f"4c 연속-{len(CONCEPTS_C)}", "평균"]
_f = sv.loc[f"4f free-{len(CONCEPTS_C)}", "평균"]
_n = sv.loc["3  BiLSTM", "평균"]
print(f"\n연속 - 이진               {_cc-_b:+.1f}   <- 정의를 다듬어 줄어드나")
print(f"연속 개념의 남은 비용      {_cc-_f:+.1f}   (같은 폭 자유 병목 대비)")
print(f"자유 병목 자체의 비용      {_f-_n:+.1f}")
print("\n연속-이진 차이가 SD 보다 작으면 '정의가 거칠어서'는 기각된다.")
_l2 = sv.loc["5  LTN w_K=0.2", "평균"]; _l5 = sv.loc["5  LTN w_K=0.5", "평균"]
print(f"\n5단계 LTN - 4단계 CBM : w_K=0.2 {_l2-_cc:+.1f} · w_K=0.5 {_l5-_cc:+.1f}")

if AX_SAT:
    head("[공리 만족도] test set · 1.0 = 완전 만족")
    _sat = pd.DataFrame(AX_SAT, index=[a[0] for a in AXIOMS]).round(3)
    _sat["GRADE"] = [a[6] for a in AXIOMS]
    print("모델 정합성 (같은 집계 p=2, 모델 예측값 기준). 4단계 -> 5단계 변화만 읽을 것.")
    print(_sat.to_string())
    _sat.to_csv(os.path.join(OUT, "stage5_axiom_sat.csv"), encoding="utf-8-sig")

    # ---- 데이터 자체가 규칙을 지지하는가: 모델을 거치지 않고 실제 라벨로만 잰다 ----
    head("[데이터 일치도] 규칙이 이 코호트에서 성립하나 — 모델 무관, 실제 라벨만")
    _teL = np.where(in_te & L)[0]
    _yv = cam.y.to_numpy()[_teL].astype(float)
    _rows = []
    for _nm, _cn, _sg, _thz, _hd, _ng, _g in AXIOMS:
        _i = CI[_cn]
        if CTYPE_C[_i] == "bin":
            A = CARR_C[_teL, _i] > 0.5
        else:
            A = (np.sign(_sg) * (_cs[_teL, _i] - _thz)) > 0     # 표준화 좌표에서 동일 임계
        if _hd == "Delirium":
            B = _yv > 0.5
        else:
            B = CARR_C[_teL, CI[_hd]] > 0.5
        if _ng:
            B = ~B
        nA = int(A.sum())
        if nA == 0 or nA == len(A):
            _rows.append({"공리": _nm, "GRADE": _g, "n(A)": nA, "P(B|A)": np.nan,
                          "P(B|¬A)": np.nan, "위험차": np.nan, "위험비": np.nan})
            continue
        pBA, pBnA = float(B[A].mean()), float(B[~A].mean())
        # 모델 정합성과 같은 집계(p=2)로 데이터 자체의 만족도도 낸다 -> 같은 자로 비교 가능
        _dis = A.astype(float) * (1.0 - B.astype(float))
        _satD = 1.0 - float(np.sqrt((_dis ** 2).mean()))
        _rows.append({"공리": _nm, "GRADE": _g, "n(A)": nA,
                      "P(B|A)": round(100 * pBA, 1), "P(B|¬A)": round(100 * pBnA, 1),
                      "위험차": round(100 * (pBA - pBnA), 1),
                      "위험비": round(pBA / pBnA, 2) if pBnA > 0 else np.nan,
                      "데이터 만족도": round(_satD, 3),
                      "모델(4단계)": _sat.iloc[len(_rows), 0] if len(_sat.columns) else np.nan})
    _ep = pd.DataFrame(_rows).set_index("공리")
    _ep["모델−데이터"] = (_ep["모델(4단계)"] - _ep["데이터 만족도"]).round(3)
    _ep = _ep.sort_values("위험차")
    print(_ep.to_string())
    _ep.to_csv(os.path.join(OUT, "stage5_axiom_data.csv"), encoding="utf-8-sig")
    print()
    print("위험차 = P(B|A) − P(B|¬A). 규칙이 맞으면 양수여야 한다. 음수면 데이터가 반대다.")
    print("\n'데이터 만족도'는 모델 정합성과 같은 집계(p=2)·하드 라벨로 낸 것이라 직접 비교된다.")
    print("'모델−데이터'가 음수면 데이터보다 모델이 규칙을 덜 지킨다는 뜻이다.")
    print("  -> stage5_axiom_data.csv · stage5_axiom_sat.csv")

head("[판정] 앵커=N AUPRC (단일 시드)")
n = t.loc["앵커=N"]
for k in t.columns:
    if k != "n":
        print(f"  {k:22s} {n[k]}")

print(f"\n총 {time.time()-t0:.0f}s")
print("\n" + ("mobility/pain/GCS 포함본이다 — 3단계 판정은 확정이다."
                if NCH > 6 else "[!] mobility/pain/GCS 미포함 — 하한이다."))
''')

# ============================================================================
# 실행
# ============================================================================
_ORDER = ["00", "24", "25", "22", "23"]
for _s in _ORDER[_ORDER.index(START):]:
    _step(*_SRC[_s])
print(f"\n완료. 결과: {os.environ.get('EDA_OUT') or os.path.join(os.environ['EDA_DATA'], 'out_split')}")
