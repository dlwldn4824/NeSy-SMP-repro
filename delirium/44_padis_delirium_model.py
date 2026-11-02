# -*- coding: utf-8 -*-
"""
PADIS 섬망 예측 — 뉴로심볼릭(LTN) 모델 학습·평가

예측 과제
    CAM-ICU 평가 시점(앵커)마다, 이후 24시간 안에 CAM-ICU 양성이 나오는지 예측한다.
    입력은 앵커 이전 24시간의 시계열(RASS · 진정제 · GCS · 거동 · 통증)과 정적·이력 정보.

비교 모델 (모두 같은 test set)
    XGBoost   요약 피처 벡터
    BiLSTM    시계열 + 정적 정보, 개념·공리 없음
    CBM       BiLSTM 표현 → 임상 개념(병목) → 섬망. 공리 없음
    LTN       CBM + PADIS 가이드라인 공리 손실 (뉴로심볼릭)

공리 (LTN 을 공리 세트마다 따로 학습해 비교한다)
    기본       PADIS 2018 위험인자 공리 12개 (사람이 정리한 KG)
    one-shot   LLM 이 예시 1개를 보고 PADIS 원문에서 추출한 KG
    few-shot   LLM 이 예시 2개를 보고 추출한 KG
    추출 KG 의 트리플은 이 파일 안(KG_TRIPLES)에 들어 있고, 실행할 때 공리로 변환된다.

실행
    아래 [설정] 을 고친 뒤  python 44_padis_delirium_model.py
    MIMIC 추출 결과는 WORK_DIR 에 저장해 두고, 다시 실행하면 추출을 건너뛴다.
    결과 표는 WORK_DIR/results/ 에 저장된다.

필요 패키지: numpy pandas pyarrow scikit-learn xgboost torch

delirium/00 · 23 · 24 · 25 단계 코드와 계산이 같다(실험용 변형 모델만 뺐다).
"""
import os
import sqlite3
import sys
import time

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import average_precision_score, roc_auc_score
from xgboost import XGBClassifier

# =============================================================================
# [설정]
# =============================================================================
MIMIC_DB = "C:/path/to/MIMIC4-hosp-icu.db"    # MIMIC-IV sqlite 파일
WORK_DIR = "padis_work"                       # 추출 캐시·결과 폴더
AXIOM_SETS = ["기본", "one-shot", "few-shot"]   # LTN 을 돌릴 공리 세트
SEEDS = [42]                                # 여러 개면 평균 ± 표준편차. 예: [42, 7, 2024]
W_AXIOM = 0.2                                 # LTN 공리 손실 가중치

EPOCHS, BATCH, LR = 10, 2048, 1e-3
SPLIT_SEED = 42                               # 환자 단위 분할 시드 (모델 시드와 별개)
HORIZON_H = 24.0                              # 예측 구간: 앵커 이후 24h
LOOKBACK_H, NBIN = 24.0, 24                   # 입력 구간: 앵커 이전 24h, 1h 간격
ANCHOR_MAX_H = 240.0                          # 입실 후 240h 안의 CAM-ICU 만 앵커로 쓴다

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
DEV = "cuda" if torch.cuda.is_available() else "cpu"
RESULT_DIR = os.path.join(WORK_DIR, "results")
os.makedirs(RESULT_DIR, exist_ok=True)
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.0f}s] {msg}", flush=True)


def section(title):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}", flush=True)


# =============================================================================
# 1. MIMIC-IV 추출
# =============================================================================
ITEM_CAM, ITEM_RASS = 228332, 228096
EXTRA_ITEMS = {                                    # 거동 · 통증 · GCS
    "PAIN_NRS": [223791, 223794, 224409, 229702, 230144],
    "MOBILITY": [229319, 229321, 229633, 229742, 228697, 224057],
    "GCS": [220739, 223900, 223901],
}
SEDATIVES = {225150: "dexmedetomidine", 229420: "dexmedetomidine", 221385: "lorazepam",
             221668: "midazolam", 222168: "propofol", 221623: "diazepam"}
BLOOD_RBC = [225168, 226368, 227070, 220996, 221013, 226370]       # 적혈구
BLOOD_ANY = BLOOD_RBC + [220970, 225170, 226369, 227071, 220971]   # + FFP · 혈소판
EXTRA_MAX_H = ANCHOR_MAX_H + LOOKBACK_H

CACHE = {k: os.path.join(WORK_DIR, f"{k}.parquet")
         for k in ["base", "cam_rass", "extra", "sedative", "transfusion", "diagnosis"]}


def build_base(con):
    """ICU stay 기본 테이블. 나이는 MIMIC 의 날짜 시프트를 보정한 입실 시 나이."""
    icu = pd.read_sql("select subject_id, hadm_id, stay_id, first_careunit, intime, los "
                      "from icustays", con)
    pat = pd.read_sql("select subject_id, gender, anchor_age, anchor_year, anchor_year_group "
                      "from patients", con)
    adm = pd.read_sql("select hadm_id from admissions", con)
    b = icu.merge(pat, on="subject_id").merge(adm, on="hadm_id")
    b["intime"] = pd.to_datetime(b["intime"], errors="coerce")
    b["age"] = b["anchor_age"] + (b["intime"].dt.year - b["anchor_year"])
    return b


def extract_mimic():
    if all(os.path.exists(p) for p in CACHE.values()):
        log(f"추출 캐시 사용 ({WORK_DIR})")
        return {k: pd.read_parquet(p) for k, p in CACHE.items()}
    if not os.path.exists(MIMIC_DB):
        sys.exit(f"MIMIC DB 를 찾을 수 없다: {MIMIC_DB}  ([설정] 의 MIMIC_DB 를 고칠 것)")
    con = sqlite3.connect(f"file:{MIMIC_DB}?mode=ro", uri=True, timeout=600)
    con.execute("pragma cache_size=-400000")

    log("icustays · patients · admissions")
    base = build_base(con)
    cohort = base[(base.age >= 18) & (base.los >= 1.0)]
    intime = cohort.set_index("stay_id")["intime"]

    # chartevents 는 인덱스가 없어 풀스캔이다. 필요한 항목을 한 번에 읽는다.
    log("chartevents 스캔 (CAM-ICU · RASS · 거동 · 통증 · GCS) — 수 분 걸린다")
    extra_ids = sorted({i for ids in EXTRA_ITEMS.values() for i in ids})
    ids = ",".join(map(str, [ITEM_CAM, ITEM_RASS] + extra_ids))
    cam_rass, extra = [], []
    for ch in pd.read_sql(f"select stay_id, itemid, charttime, value, valuenum from chartevents "
                          f"where itemid in ({ids}) and stay_id is not null",
                          con, chunksize=4_000_000):
        cam_rass.append(ch[ch.itemid.isin([ITEM_CAM, ITEM_RASS])])
        e = ch[ch.itemid.isin(extra_ids)].copy()
        e["stay_id"] = e["stay_id"].astype("int64")
        e = e[e.stay_id.isin(intime.index)]
        e["hr"] = (pd.to_datetime(e["charttime"], errors="coerce")
                   - e["stay_id"].map(intime)).dt.total_seconds() / 3600
        e = e[(e.hr >= 0) & (e.hr <= EXTRA_MAX_H)]
        e["valuenum"] = pd.to_numeric(e["valuenum"], errors="coerce").astype("float32")
        e["hr"] = e["hr"].astype("float32")
        extra.append(e[["stay_id", "itemid", "hr", "valuenum"]])
        log(f"  누적 CAM/RASS {sum(map(len, cam_rass)):,} · 기타 {sum(map(len, extra)):,}")
    cam_rass = pd.concat(cam_rass, ignore_index=True)
    extra = pd.concat(extra, ignore_index=True)

    log("inputevents (진정제 · 수혈)")
    sedative = pd.read_sql(f"select stay_id, itemid, starttime, endtime from inputevents "
                           f"where itemid in ({','.join(map(str, SEDATIVES))})", con)
    sedative["drug"] = sedative["itemid"].map(SEDATIVES)
    tr = pd.read_sql(f"select stay_id, itemid, starttime from inputevents "
                     f"where itemid in ({','.join(map(str, BLOOD_ANY))}) and stay_id is not null", con)
    tr["stay_id"] = tr["stay_id"].astype("int64")
    tr = tr[tr.stay_id.isin(intime.index)].copy()
    tr["hr"] = (pd.to_datetime(tr["starttime"], errors="coerce")
                - tr["stay_id"].map(intime)).dt.total_seconds() / 3600
    tr = tr[(tr.hr >= 0) & (tr.hr <= EXTRA_MAX_H)].copy()
    tr["is_rbc"] = tr.itemid.isin(BLOOD_RBC).astype("int8")
    tr["hr"] = tr["hr"].astype("float32")
    transfusion = tr[["stay_id", "hr", "is_rbc"]]

    log("diagnoses_icd (치매 · 외상 · 고혈압)")
    dx = pd.read_sql("select d.hadm_id, d.icd_code, d.icd_version, t.long_title "
                     "from diagnoses_icd d left join d_icd_diagnoses t "
                     "on t.icd_code = d.icd_code and t.icd_version = d.icd_version", con)
    con.close()
    diagnosis = comorbidity_flags(dx, set(cohort.hadm_id.astype("int64")))

    out = dict(base=base, cam_rass=cam_rass, extra=extra, sedative=sedative,
               transfusion=transfusion, diagnosis=diagnosis)
    for k, df in out.items():
        df.to_parquet(CACHE[k], index=False)
    log(f"추출 완료 → {WORK_DIR}")
    return out


# 동반질환 판별 규칙 (NeSy-SMP/data/build_comorbidities_icd.py 의 match_label 과 같은 결과)
DX_RULES = {   # 라벨: (ICD-10 접두, ICD-9 접두, 진단명 키워드)
    "dementia": (["F01", "F02", "F03", "G30"], ["290", "2941", "3310"], ["dementia", "alzheimer"]),
    "hypertension": (["I10", "I11", "I12", "I13", "I15", "I16"], ["401", "402", "403", "404", "405"],
                     ["hypertension", "hypertensive"]),
}


def _norm_code(code):
    return "".join(ch for ch in str(code) if ch.isalnum()).upper()


def _is_trauma(version, code, title):
    """급성 손상 코드만 (후유증 · 과거력 · 병적 골절 제외)."""
    c = _norm_code(code)
    if any(k in title for k in ["traumatic injury", "multiple trauma", "traumatic fracture"]) \
            and "pathologic" not in title and "osteoporosis" not in title:
        return True
    if int(version) == 9:
        return c.isdigit() and len(c) >= 3 and 800 <= int(c[:3]) <= 904
    if c.startswith(("Z87", "M80", "M81")):
        return False
    if c.startswith("S") and len(c) >= 3:
        return c[1:3].isdigit()
    return c.startswith(("T07", "T14", "T79"))


def comorbidity_flags(dx, hadms):
    """hadm 별 치매 · 외상 · 고혈압 진단 여부. 진단은 퇴원 시 부여되는 입원 단위 정보다."""
    dx = dx.copy()
    dx["hadm_id"] = dx["hadm_id"].astype("int64")
    dx = dx[dx.hadm_id.isin(hadms)]
    hit = {w: set() for w in ["dementia", "trauma", "hypertension"]}
    for h, code, ver, title in zip(dx.hadm_id, dx.icd_code, dx.icd_version, dx.long_title):
        t = (title or "").lower()
        c = _norm_code(code)
        if _is_trauma(ver, code, t):
            hit["trauma"].add(h)
        for lab, (p10, p9, kws) in DX_RULES.items():
            prefixes = p10 if int(ver) == 10 else p9
            if any(k in t for k in kws) or any(c.startswith(p) for p in prefixes):
                hit[lab].add(h)
    out = pd.DataFrame({"hadm_id": sorted(hadms)})
    for w, s in hit.items():
        out[w] = out.hadm_id.isin(s).astype("int8")
    return out


# =============================================================================
# 2. 코호트 · 앵커 · 라벨
# =============================================================================
def build_anchors(raw):
    """CAM-ICU 기록 1건 = 앵커 1개. 라벨은 앵커 이후 24h 안의 확정 평가(양성/음성)로 정한다."""
    base = raw["base"].copy()
    base["intime"] = pd.to_datetime(base["intime"])
    cohort = base[(base.age >= 18) & (base.los >= 1.0)].copy()      # 성인 · ICU 재원 1일 이상
    intime = base.set_index("stay_id")["intime"]

    v = raw["cam_rass"]
    code = {"Positive": "P", "Negative": "N", "UTA": "U",
            "Unable to Assess": "U", "Unable to assess": "U"}
    cam = v[v.itemid == ITEM_CAM][["stay_id", "charttime", "value"]].copy()
    cam["charttime"] = pd.to_datetime(cam["charttime"])
    cam["v"] = cam["value"].astype(str).str.strip().map(code)        # P 양성 · N 음성 · U 평가불가
    cam = cam[cam.v.notna() & cam.stay_id.isin(cohort.stay_id)].copy()
    cam["hr"] = (cam["charttime"] - cam["stay_id"].map(intime)).dt.total_seconds() / 3600
    cam = (cam[(cam.hr >= 0) & (cam.hr <= ANCHOR_MAX_H)]
           .sort_values(["stay_id", "hr"]).reset_index(drop=True))

    h = cam["hr"].to_numpy(float)
    confirmed = (cam["v"] != "U").to_numpy()
    positive = (cam["v"] == "P").to_numpy()
    cum_c = np.concatenate([[0], confirmed.cumsum()])
    cum_p = np.concatenate([[0], (confirmed & positive).cumsum()])
    cum_u = np.concatenate([[0], (~confirmed).cumsum()])
    _, first, cnt = np.unique(cam["stay_id"].to_numpy(), return_index=True, return_counts=True)

    labeled = np.zeros(len(cam), bool)       # 이후 24h 에 확정 평가가 있음 → 학습·평가 대상
    y = np.zeros(len(cam), bool)             # 이후 24h 에 양성이 있음
    n_prev_pos = np.zeros(len(cam), int)
    n_prev_uta = np.zeros(len(cam), int)
    for a, n in zip(first, cnt):
        hh, idx = h[a:a + n], np.arange(n)
        j = np.searchsorted(hh, hh + HORIZON_H, side="right")
        labeled[a:a + n] = (cum_c[a + j] - cum_c[a + idx + 1]) > 0
        y[a:a + n] = (cum_p[a + j] - cum_p[a + idx + 1]) > 0
        n_prev_pos[a:a + n] = cum_p[a + idx] - cum_p[a]
        n_prev_uta[a:a + n] = cum_u[a + idx] - cum_u[a]
    cam["labeled"], cam["y"] = labeled, y

    # 같은 stay 안의 이전 평가 이력
    cam["n_prev"] = cam.groupby("stay_id").cumcount()
    cam["n_prev_pos"], cam["n_prev_uta"] = n_prev_pos, n_prev_uta
    cam["uta_frac"] = np.where(cam.n_prev > 0, cam.n_prev_uta / cam.n_prev.clip(lower=1), 0.0)
    cam["prev_conf"] = cam["v"].where(cam.v != "U").groupby(cam.stay_id).ffill().shift()
    cam.loc[cam.groupby("stay_id").head(1).index, "prev_conf"] = np.nan
    cam["prev_conf"] = cam["prev_conf"].fillna("없음")
    last_conf = (cam["hr"].where(cam.v != "U").groupby(cam.stay_id).ffill()
                 .groupby(cam.stay_id).shift())
    cam["since_conf"] = (cam["hr"] - last_conf).fillna(-1)
    cam["since_prev"] = cam.groupby("stay_id")["hr"].diff().fillna(-1)

    # 정적 정보
    st = cohort.set_index("stay_id")
    cam["subject_id"] = cam["stay_id"].map(st["subject_id"])
    cam["hadm_id"] = cam["stay_id"].map(st["hadm_id"].astype("int64"))
    cam["age"] = cam["stay_id"].map(st["age"])
    cam["los"] = cam["stay_id"].map(st["los"])
    cam["is_male"] = (cam["stay_id"].map(st["gender"]) == "M").astype(float)
    cam["cu"] = cam["stay_id"].map(st["first_careunit"]).astype("category").cat.codes
    cam["era"] = cam["stay_id"].map(st["anchor_year_group"]).astype("category").cat.codes
    for a in ["N", "P", "U"]:
        cam[f"anchor_{a}"] = (cam.v == a).astype(float)
    for a, nm in [("N", "prev_N"), ("P", "prev_P"), ("없음", "prev_none")]:
        cam[nm] = (cam.prev_conf == a).astype(float)
    return cam, cohort, intime, h, first, cnt


# =============================================================================
# 3. 입력 피처 — 시계열 X (앵커 이전 24h × 채널)
# =============================================================================
EXTRA_FEATS = [                      # (채널 이름, itemid) — 값 평균 + 관측 여부 2채널씩
    ("gcs_eye", [220739]), ("gcs_verbal", [223900]), ("gcs_motor", [223901]),
    ("mob_braden", [224057]), ("mob_jhhlm", [229321]), ("pain_nrs", [223791, 224409]),
]
PAIN_ATTEMPT = [223794, 230144]     # 값 없이 '통증 평가 시도' 관측 플래그로만 쓴다
SED_CLASSES = ["benzo", "propofol", "dexmedetomidine"]


def build_timeseries(raw, cam, cohort, intime, h, first, cnt):
    """채널 0 RASS 평균 · 1 RASS 최솟값 · 2 RASS 관측 · 3~5 진정제(벤조 · 프로포폴 · 덱스) 투여 중
       · 6~17 GCS 3성분 · 거동 2종 · 통증 NRS (각 값 + 관측) · 18 통증 평가 시도"""
    edges = np.linspace(-LOOKBACK_H, 0.0, NBIN + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    sids = cam["stay_id"].to_numpy()

    v = raw["cam_rass"]
    r = v[v.itemid == ITEM_RASS][["stay_id", "charttime", "valuenum"]].copy()
    r["charttime"] = pd.to_datetime(r["charttime"])
    r = r[r.stay_id.isin(cohort.stay_id)].copy()
    r["hr"] = (r["charttime"] - r["stay_id"].map(intime)).dt.total_seconds() / 3600
    r = r[r.hr >= 0].sort_values(["stay_id", "hr"])
    rass = {k: (g["hr"].to_numpy(float), np.nan_to_num(g["valuenum"].to_numpy(float), nan=0.0))
            for k, g in r.groupby("stay_id", sort=False)}

    sed = raw["sedative"]
    sed = sed[sed.stay_id.isin(cohort.stay_id)].copy()
    for c in ["starttime", "endtime"]:
        sed[c] = pd.to_datetime(sed[c])
    sed["s"] = (sed["starttime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
    sed["e"] = (sed["endtime"] - sed["stay_id"].map(intime)).dt.total_seconds() / 3600
    sed["cls"] = np.where(sed.drug.isin({"lorazepam", "midazolam", "diazepam"}), "benzo", sed.drug)
    sed_by = {k: (g["s"].to_numpy(float), g["e"].to_numpy(float), g["cls"].to_numpy())
              for k, g in sed.groupby("stay_id", sort=False)}

    X = np.zeros((len(cam), NBIN, 6 + 2 * len(EXTRA_FEATS) + 1), dtype=np.float32)
    for a, n in zip(first, cnt):
        sid, hh = sids[a], h[a:a + n]
        if sid in rass:                                        # RASS: 1h 칸별 평균 · 최솟값
            rh, rv = rass[sid]
            csum = np.concatenate([[0.0], np.cumsum(rv)])
            bnd = np.searchsorted(rh, hh[:, None] + edges[None, :], side="left")
            lo, hi = bnd[:, :-1], bnd[:, 1:]
            k = hi - lo
            with np.errstate(invalid="ignore", divide="ignore"):
                X[a:a + n, :, 0] = np.where(k > 0, (csum[hi] - csum[lo]) / np.maximum(k, 1), 0.0)
            X[a:a + n, :, 2] = k > 0
            for i, jb in zip(*np.nonzero(k)):
                X[a + i, jb, 1] = rv[lo[i, jb]:hi[i, jb]].min()
        if sid in sed_by:                                      # 진정제: 칸 중앙 시각에 투여 중인가
            s_, e_, cl = sed_by[sid]
            ct = hh[:, None, None] + centers[None, :, None]
            on = (s_[None, None, :] <= ct) & (e_[None, None, :] > ct)
            for ci, c in enumerate(SED_CLASSES):
                X[a:a + n, :, 3 + ci] = (on & (cl == c)[None, None, :]).any(2)

    # GCS · 거동 · 통증: 1h 칸별 평균 + 관측 여부
    ex = raw["extra"]
    exv = ex[ex.valuenum.notna()]
    banks = []
    for _, ids in EXTRA_FEATS:
        sub = exv[exv.itemid.isin(ids)]
        bank = {}
        for k, g in sub.groupby("stay_id", sort=False):
            g = g.sort_values("hr")
            bank[k] = (g["hr"].to_numpy(np.float64), g["valuenum"].to_numpy(np.float64))
        banks.append(bank)
    pain = ex[ex.itemid.isin(PAIN_ATTEMPT)]
    bank_pain = {k: np.sort(g["hr"].to_numpy(np.float64)) for k, g in pain.groupby("stay_id", sort=False)}
    for a, n in zip(first, cnt):
        sid = sids[a]
        rel = h[a:a + n][:, None] + edges[None, :]
        for fi, bank in enumerate(banks):
            if sid not in bank:
                continue
            hs, vs = bank[sid]
            csum = np.concatenate([[0.0], np.cumsum(vs)])
            bnd = np.searchsorted(hs, rel, side="left")
            lo, hi = bnd[:, :-1], bnd[:, 1:]
            k = hi - lo
            with np.errstate(invalid="ignore", divide="ignore"):
                X[a:a + n, :, 6 + fi * 2] = np.where(k > 0, (csum[hi] - csum[lo]) / np.maximum(k, 1), 0.0)
            X[a:a + n, :, 7 + fi * 2] = k > 0
        if sid in bank_pain:
            bnd = np.searchsorted(bank_pain[sid], rel, side="left")
            X[a:a + n, :, -1] = (bnd[:, 1:] - bnd[:, :-1]) > 0
    return X


def add_comorbidity_transfusion(raw, cam, h, first, cnt):
    """치매 · 외상 · 고혈압(입원 진단) · 수혈(앵커 이전 24h 적혈구, 누적 건수)."""
    dx = raw["diagnosis"].set_index("hadm_id")
    for w in ["dementia", "trauma", "hypertension"]:
        cam[w] = cam["hadm_id"].map(dx[w]).fillna(0).astype(np.float32)
    tb = {k: (np.sort(g["hr"].to_numpy(np.float64)), g.sort_values("hr")["is_rbc"].to_numpy(np.float64))
          for k, g in raw["transfusion"].groupby("stay_id", sort=False)}
    tr24 = np.zeros(len(cam), np.float32)
    trcum = np.zeros(len(cam), np.float32)
    sids = cam["stay_id"].to_numpy()
    for a, n in zip(first, cnt):
        if sids[a] not in tb:
            continue
        hs, rbc = tb[sids[a]]
        hh = h[a:a + n]
        hi = np.searchsorted(hs, hh, side="right")
        lo = np.searchsorted(hs, hh - 24.0, side="left")
        c = np.concatenate([[0.0], np.cumsum(rbc)])
        tr24[a:a + n] = (c[hi] - c[lo]) > 0
        trcum[a:a + n] = hi
    cam["transfusion24"], cam["transfusion_cum"] = tr24, trcum


STATIC_COLS = ["hr", "n_prev", "n_prev_pos", "n_prev_uta", "uta_frac", "since_conf", "since_prev",
               "age", "los", "is_male", "cu", "era",
               "anchor_N", "anchor_P", "anchor_U", "prev_N", "prev_P", "prev_none",
               "dementia", "trauma", "hypertension", "transfusion24", "transfusion_cum"]


# =============================================================================
# 4. 임상 개념 — CBM 병목이자 공리가 걸리는 술어
# =============================================================================
def build_concepts(X, cam):
    """(이름, 값, 관측 마스크, 종류). 연속 개념은 값 그대로, 이진 개념은 0/1.
    관측이 없는 개념(예: 거동 기록 없음)은 개념 손실에서 마스킹한다."""
    def agg(vi, mi, how):
        val, obs = X[:, :, vi], X[:, :, mi] > 0
        o = (np.where(obs, val, np.inf).min(1) if how == "min"
             else np.where(obs, val, -np.inf).max(1))
        ok = np.isfinite(o)
        return np.where(ok, o, 0.0).astype(np.float32), ok

    rass_obs = X[:, :, 2] > 0
    rass_min = np.where(rass_obs, X[:, :, 1], np.inf).min(1)
    rass_ok = np.isfinite(rass_min)
    rass_min = np.where(rass_ok, rass_min, 0.0).astype(np.float32)
    rass_negmean = (np.where(rass_obs, np.minimum(X[:, :, 0], 0), 0.0).sum(1)
                    / np.maximum(rass_obs.sum(1), 1)).astype(np.float32)   # 진정 강도
    ge, geo = agg(6, 7, "min"); gv, gvo = agg(8, 9, "min"); gm, gmo = agg(10, 11, "min")
    braden, braden_ok = agg(12, 13, "min")
    jhhlm, jhhlm_ok = agg(14, 15, "max")
    pain, pain_ok = agg(16, 17, "max")
    pain_attempt = X[:, :, 18].max(1) > 0
    one = np.ones(len(cam), bool)
    n_prev = cam.n_prev.to_numpy()

    defs = [("RASSmin", rass_min, rass_ok, "cont"),
            ("RASSnegmean", rass_negmean, one, "cont"),
            ("BenzoFrac", X[:, :, 3].mean(1), one, "cont"),          # 24h 중 투여 시간 비율
            ("PropofolFrac", X[:, :, 4].mean(1), one, "cont"),
            ("DexmedFrac", X[:, :, 5].mean(1), one, "cont"),
            ("GCStotal", ge + gv + gm, geo & gvo & gmo, "cont"),
            ("MobBraden", braden, braden_ok, "cont"),
            ("MobJHHLM", jhhlm, jhhlm_ok, "cont"),
            ("PainNRSmax", pain, pain_ok, "cont"),
            ("PainUnassessable", pain_attempt & ~pain_ok, one, "bin"),
            ("Dementia", cam.dementia.to_numpy() > 0, one, "bin"),
            ("Trauma", cam.trauma.to_numpy() > 0, one, "bin"),
            ("Hypertension", cam.hypertension.to_numpy() > 0, one, "bin"),
            ("BloodTransfusion", cam.transfusion24.to_numpy() > 0, one, "bin"),
            ("Age", cam["age"].to_numpy(np.float32), one, "cont"),
            ("MaleSex", cam["is_male"].to_numpy() > 0, one, "bin"),
            ("Assessable", cam["labeled"].to_numpy(), one, "bin"),
            ("CurrentDelirium", cam.v.to_numpy() == "P", one, "bin"),
            ("CurrentUTA", cam.v.to_numpy() == "U", one, "bin"),
            ("PriorDeliriumFrac", cam.n_prev_pos.to_numpy() / np.maximum(n_prev, 1), one, "cont"),
            ("PriorUTAFrac", cam.n_prev_uta.to_numpy() / np.maximum(n_prev, 1), one, "cont")]
    names = [d[0] for d in defs]
    values = np.stack([np.asarray(d[1], np.float32) for d in defs], 1)
    mask = np.stack([np.asarray(d[2], np.float32) for d in defs], 1)
    is_bin = np.array([d[3] == "bin" for d in defs])
    return names, values, mask, is_bin


def summary_vector(X, S):
    """XGBoost 입력: 정적·이력 S + 시계열 채널별 요약(평균 · 최소 · 최대 · 마지막 · 관측 수)."""
    def summ(val, obs):
        n = obs.sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(n > 0, (val * obs).sum(1) / np.maximum(n, 1), np.nan)
        vmin = np.where(obs, val, np.inf).min(1); vmin[~np.isfinite(vmin)] = np.nan
        vmax = np.where(obs, val, -np.inf).max(1); vmax[~np.isfinite(vmax)] = np.nan
        last_i = obs.shape[1] - 1 - np.argmax(obs[:, ::-1], axis=1)
        last = np.where(n > 0, val[np.arange(len(val)), np.maximum(last_i, 0)], np.nan)
        return [mean, vmin, vmax, last, n.astype(np.float32)]

    rass_obs = X[:, :, 2] > 0
    cols = summ(X[:, :, 0], rass_obs)
    binmin = np.where(rass_obs, X[:, :, 1], np.inf).min(1); binmin[~np.isfinite(binmin)] = np.nan
    cols += [binmin, (binmin <= -4).astype(np.float32)]
    cols += [X[:, :, 3 + ci].max(1) for ci in range(len(SED_CLASSES))]
    for fi in range(len(EXTRA_FEATS)):
        cols += summ(X[:, :, 6 + fi * 2], X[:, :, 7 + fi * 2] > 0)
    cols.append(X[:, :, 18].max(1))
    return np.concatenate([S, np.stack(cols, 1).astype(np.float32)], 1)


# =============================================================================
# 5. PADIS 공리
# =============================================================================
# 공리 a → b 하나 = (이름, 개념, 방향, 임계값(원 단위), 결론, 결론 부정, 근거 등급)
#   방향 +1: 개념값이 임계 이상이면 앞조건 참 · -1: 이하이면 참
#   결론 부정 True: "위험 감소" 공리 (a → ¬섬망)
DEFAULT_AXIOMS = [   # PADIS 2018 위험인자 · 2018/2025 중재 근거
    ("Benzo→Delirium", "BenzoFrac", +1, 1e-6, "Delirium", False, "strong"),
    ("DeepSedation→Delirium", "RASSmin", -1, -4.0, "Delirium", False, "low"),
    ("SedationIntensity→Delirium", "RASSnegmean", -1, -2.0, "Delirium", False, "cohort"),
    ("SeverePain→Delirium", "PainNRSmax", +1, 4.0, "Delirium", False, "inconclusive"),
    ("OlderAge→Delirium", "Age", +1, 65.0, "Delirium", False, "strong"),
    ("Dexmed→¬Delirium", "DexmedFrac", +1, 1e-6, "Delirium", True, "moderate"),
    ("EarlyMobility→¬Delirium", "MobJHHLM", +1, 4.0, "Delirium", True, "low"),
    ("DeepSedation→CurrentUTA", "RASSmin", -1, -4.0, "CurrentUTA", False, "derived"),
    ("BloodTransfusion→Delirium", "BloodTransfusion", +1, 0.5, "Delirium", False, "strong"),
    ("Dementia→Delirium", "Dementia", +1, 0.5, "Delirium", False, "strong"),
    ("Trauma→Delirium", "Trauma", +1, 0.5, "Delirium", False, "strong"),
    ("Hypertension→Delirium", "Hypertension", +1, 0.5, "Delirium", False, "moderate"),
]
GRADE_W = {"strong": 1.0, "moderate": 0.6, "low": 0.3, "cohort": 0.3, "derived": 0.5,
           "inconclusive": 0.2}

# KG 트리플 → 공리 (delirium/42_kg_to_axioms.py 와 같은 규칙)
KG_SUBJECT = {   # KG 개념 → (모델 개념, 방향, 임계값)
    "Benzodiazepine": ("BenzoFrac", +1, 1e-6), "DeepSedation": ("RASSmin", -1, -4.0),
    "SedationIntensity": ("RASSnegmean", -1, -2.0), "SeverePain": ("PainNRSmax", +1, 4.0),
    "Age": ("Age", +1, 65.0), "Dexmedetomidine": ("DexmedFrac", +1, 1e-6),
    "EarlyMobility": ("MobJHHLM", +1, 4.0), "Immobility": ("MobJHHLM", -1, 3.0),
    "BloodTransfusion": ("BloodTransfusion", +1, 0.5), "Dementia": ("Dementia", +1, 0.5),
    "Trauma": ("Trauma", +1, 0.5), "Hypertension": ("Hypertension", +1, 0.5),
}
KG_OBJECT = {"Delirium": "Delirium", "UnableToAssess": "CurrentUTA", "Assessable": "Assessable",
             "Immobility": "MobJHHLM"}
KG_GRADE = {"increasesRiskOf": "strong", "decreasesRiskOf": "moderate",
            "associatedWith": "low", "precludes": "derived"}


# PADIS 2018 · 2025 원문에서 LLM 으로 추출한 KG (윤연서, 2026-09-17).
# (주어, 관계, 목적어). 공리가 될 수 없는 것(사망 결론 · MIMIC 에 없는 개념)도 원본 그대로 둔다.
_KG_COMMON = [
    ("Age", "associatedWith", "Delirium"), ("Benzodiazepine", "associatedWith", "Delirium"),
    ("BloodTransfusion", "associatedWith", "Delirium"), ("Dementia", "associatedWith", "Delirium"),
    ("Dexmedetomidine", "decreasesRiskOf", "Delirium"), ("Hypertension", "associatedWith", "Delirium"),
    ("MechanicalVentilation", "hasNoEffectOn", "Delirium"), ("Melatonin", "decreasesRiskOf", "Delirium"),
    ("OpioidUse", "hasNoEffectOn", "Delirium"), ("PatientSex", "hasNoEffectOn", "Delirium"),
    ("SedationIntensity", "associatedWith", "Death"), ("SedationIntensity", "associatedWith", "Delirium"),
    ("Trauma", "associatedWith", "Delirium"),
]
KG_TRIPLES = {
    "one-shot": _KG_COMMON,                                                   # 13개
    "few-shot": _KG_COMMON + [("EarlyMobility", "hasNoEffectOn", "Death")],   # 14개
}


def axioms_from_kg(triples):
    """트리플 → 공리. '영향 없음' 트리플은 같은 쌍의 다른 트리플을 기각한다.
    이 모델에 없는 개념·결론(사망, 멜라토닌 등)은 버린다."""
    triples = set(triples)
    no_effect = {(s, o) for s, p, o in triples if p == "hasNoEffectOn"}
    axioms, skipped = [], []
    for s, p, o in sorted(triples):
        if p == "hasNoEffectOn":
            continue
        # "평가 불가능하게 한다(precludes)" 는 지금 평가 불가 상태(CurrentUTA)로 건다
        head = ("CurrentUTA" if p == "precludes" and o in ("Assessable", "UnableToAssess")
                else KG_OBJECT.get(o))
        if (s, o) in no_effect or p not in KG_GRADE or s not in KG_SUBJECT or head is None:
            skipped.append(f"{s}-{p}->{o}")
            continue
        concept, sign, thr = KG_SUBJECT[s]
        axioms.append((f"{s}-{p}->{o}", concept, sign, thr, head, p == "decreasesRiskOf", KG_GRADE[p]))
    return axioms


class AxiomSet:
    """공리 만족도 계산. 함축은 Reichenbach(1 − a + a·b), 환자 전체 집계는 pMeanError(p=2)."""
    TAU = 0.35      # 연속 개념 임계의 부드러움 (표준화 좌표)

    def __init__(self, axioms, cidx, is_bin, mu, sd):
        self.axioms = axioms
        self.rows = []
        for nm, concept, sign, raw_thr, head, neg, grade in axioms:
            i = cidx[concept]
            thr = (raw_thr - mu[i]) / sd[i]
            self.rows.append((i, sign, float(thr), bool(is_bin[i]),
                              None if head == "Delirium" else cidx[head], neg))
        w = torch.tensor([GRADE_W[a[6]] for a in axioms], dtype=torch.float32)
        self.w = w / w.sum()

    def satisfaction(self, c, p_delirium, per_axiom=False):
        sats = []
        for i, sign, thr, binary, head, neg in self.rows:
            z = c[:, i]
            a = torch.sigmoid(z) if binary else torch.sigmoid(sign * (z - thr) / self.TAU)
            b = p_delirium if head is None else torch.sigmoid(c[:, head])
            if neg:
                b = 1.0 - b
            sat = 1.0 - a + a * b
            sats.append(1.0 - torch.sqrt(torch.clamp(((1.0 - sat) ** 2).mean(), min=1e-9)))
        st = torch.stack(sats)
        return st if per_axiom else (st * self.w.to(st.device)).sum()


# =============================================================================
# 6. 모델
# =============================================================================
class DeliriumNet(nn.Module):
    """BiLSTM(+주의집중) 시계열 인코더 + 정적 정보 → 표현 h → 개념 c → 섬망 로짓.
    cbm=True 면 섬망은 개념값만 보고 예측한다(병목). False 면 표현 h 전체를 쓴다."""

    def __init__(self, nch, nstat, nconcept, is_bin, cbm, hid=64):
        super().__init__()
        self.cbm = cbm
        self.lstm = nn.LSTM(nch, hid, batch_first=True, bidirectional=True)
        self.att = nn.Linear(hid * 2, 1)
        self.stat = nn.Sequential(nn.Linear(nstat, hid), nn.ReLU())
        self.enc = nn.Sequential(nn.Linear(hid * 3, hid), nn.ReLU(), nn.Dropout(0.1))
        self.register_buffer("is_bin", torch.as_tensor(is_bin, dtype=torch.bool))
        self.concept = nn.Linear(hid, nconcept)
        self.out = nn.Linear(nconcept if cbm else hid, 1)

    def forward(self, x, s):
        o, _ = self.lstm(x)
        w = torch.softmax(self.att(o), 1)
        h = self.enc(torch.cat([(o * w).sum(1), self.stat(s)], 1))
        c = self.concept(h)
        if not self.cbm:
            return self.out(h).squeeze(1), c
        z = torch.where(self.is_bin, torch.sigmoid(c), c)   # 이진 개념은 확률, 연속 개념은 값 그대로
        return self.out(z).squeeze(1), c


BILSTM_CONCEPT_DIM = 19   # BiLSTM 은 개념 출력을 쓰지 않는다. 원본(23_)과 같은 초기화를 위해 크기만 맞춘다


def train_net(D, seed, cbm, w_concept, axioms=None, w_axiom=0.0):
    """학습 후 test 예측과 공리별 만족도를 돌려준다. 조기종료 기준은 val 의 앵커=음성 AUPRC."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    nconcept = D["C"].shape[1] if cbm else BILSTM_CONCEPT_DIM
    is_bin = D["is_bin"] if cbm else np.ones(nconcept, bool)
    m = DeliriumNet(D["X"].shape[2], D["S"].shape[1], nconcept, is_bin, cbm).to(DEV)
    opt = torch.optim.Adam(m.parameters(), lr=LR)
    bce = nn.BCEWithLogitsLoss(reduction="none")
    bin_mask = torch.as_tensor(D["is_bin"]).to(DEV)

    def predict(idx):
        m.eval()
        out_p, out_c = [], []
        with torch.no_grad():
            for i in range(0, len(idx), 8192):
                j = idx[i:i + 8192]
                lg, c = m(D["X"][j].to(DEV), D["S"][j].to(DEV))
                out_p.append(torch.sigmoid(lg))
                out_c.append(c)
        return torch.cat(out_p), torch.cat(out_c)

    best, best_state, bad = -1.0, None, 0
    for ep in range(EPOCHS):
        m.train()
        perm = np.random.permutation(D["idx_tr"])
        for i in range(0, len(perm), BATCH):
            j = perm[i:i + BATCH]
            logit, c = m(D["X"][j].to(DEV), D["S"][j].to(DEV))
            loss = bce(logit, D["Y"][j].to(DEV)).mean()
            if w_concept > 0:                                   # 개념이 실제 임상값을 맞히도록
                cb, mb = D["C"][j].to(DEV), D["M"][j].to(DEV)
                lc = torch.where(bin_mask.unsqueeze(0), bce(c, cb), (c - cb) ** 2)
                loss = loss + w_concept * (lc * mb).sum() / mb.sum().clamp(min=1)
            if w_axiom > 0:                                     # 공리를 어길수록 손실 증가
                loss = loss + w_axiom * (1.0 - axioms.satisfaction(c, torch.sigmoid(logit)))
            opt.zero_grad(); loss.backward(); opt.step()
        pv, _ = predict(D["idx_va"])
        neg = D["v"][D["idx_va"]] == "N"
        ap = average_precision_score(D["y"][D["idx_va"]][neg], pv.cpu().numpy()[neg])
        if ap > best:
            best, best_state, bad = ap, {k: t.detach().clone() for k, t in m.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= 2:
                break
    m.load_state_dict(best_state)
    return predict(D["idx_te"])          # test 섬망 확률, 개념 출력


# =============================================================================
# 7. 실행
# =============================================================================
def main():
    section("1. MIMIC-IV 추출")
    raw = extract_mimic()

    section("2. 앵커 · 라벨 · 입력 피처")
    cam, cohort, intime, h, first, cnt = build_anchors(raw)
    X = build_timeseries(raw, cam, cohort, intime, h, first, cnt)
    add_comorbidity_transfusion(raw, cam, h, first, cnt)
    S = cam[STATIC_COLS].to_numpy(np.float32)
    cnames, C, M, is_bin = build_concepts(X, cam)
    L = cam.labeled.to_numpy()
    log(f"앵커 {len(cam):,} (라벨 있음 {L.sum():,}) · 양성 {100 * cam.y[L].mean():.1f}% · "
        f"시계열 {X.shape} · 개념 {len(cnames)}개")

    # 환자 단위 분할: test 30% · 나머지에서 val 20% (같은 환자가 두 집합에 들어가지 않는다)
    rng = np.random.default_rng(SPLIT_SEED)
    pats = cam.iloc[np.where(L)[0]].subject_id.unique(); rng.shuffle(pats)
    tr_all = set(pats[:int(len(pats) * 0.70)])
    rng2 = np.random.default_rng(SPLIT_SEED + 1)
    tr_list = np.array(sorted(tr_all)); rng2.shuffle(tr_list)
    va = set(tr_list[:int(len(tr_list) * 0.20)])
    subj = cam["subject_id"].to_numpy()
    in_tr = np.isin(subj, list(tr_all - va)) & L
    in_va = np.isin(subj, list(va)) & L
    in_te = ~np.isin(subj, list(tr_all)) & L
    log(f"train {in_tr.sum():,} · val {in_va.sum():,} · test {in_te.sum():,}")

    # 정규화 (train 통계만 사용)
    Z = summary_vector(X, S)
    med = np.nanmedian(Z[in_tr], axis=0)
    Z = np.where(np.isfinite(Z), Z, np.where(np.isfinite(med), med, 0.0)[None, :]).astype(np.float32)
    Z = (Z - Z[in_tr].mean(0)) / (Z[in_tr].std(0) + 1e-6)
    S = (S - S[in_tr].mean(0)) / (S[in_tr].std(0) + 1e-6)
    nch = X.shape[2]
    X = (X - X[in_tr].reshape(-1, nch).mean(0)) / (X[in_tr].reshape(-1, nch).std(0) + 1e-6)
    c_mu, c_sd = np.zeros(len(cnames), np.float32), np.ones(len(cnames), np.float32)
    for i in np.where(~is_bin)[0]:
        w = in_tr & (M[:, i] > 0)
        c_mu[i], c_sd[i] = C[w, i].mean(), C[w, i].std() + 1e-6
    Cz = (C - c_mu) / c_sd

    D = dict(X=torch.from_numpy(X.astype(np.float32)), S=torch.from_numpy(S.astype(np.float32)),
             Y=torch.from_numpy(cam.y.to_numpy().astype(np.float32)),
             C=torch.from_numpy(Cz.astype(np.float32)), M=torch.from_numpy(M), is_bin=is_bin,
             y=cam.y.to_numpy().astype(int), v=cam.v.to_numpy(),
             idx_tr=np.where(in_tr)[0], idx_va=np.where(in_va)[0], idx_te=np.where(in_te)[0])

    section("3. 공리 세트")
    cidx = {n: i for i, n in enumerate(cnames)}
    usable = lambda ax: [a for a in ax if a[1] in cidx and (a[4] == "Delirium" or a[4] in cidx)]
    axiom_sets = {}
    for name in AXIOM_SETS:
        raw_ax = DEFAULT_AXIOMS if name == "기본" else axioms_from_kg(KG_TRIPLES[name])
        ax = usable(raw_ax)
        axiom_sets[name] = (ax, AxiomSet(ax, cidx, is_bin, c_mu, c_sd))
        src = "PADIS 기본" if name == "기본" else f"KG 트리플 {len(KG_TRIPLES[name])}개"
        print(f"[{name}] {src} → 공리 {len(ax)}개")
        for a in ax:
            print(f"    {a[0]:45s} {a[6]}")
    names = {n: tuple(a[0] for a in axiom_sets[n][0]) for n in AXIOM_SETS}
    for i, a in enumerate(AXIOM_SETS):
        for b in AXIOM_SETS[i + 1:]:
            if names[a] == names[b]:
                print(f"※ [{a}] · [{b}] 공리가 같다 → 두 LTN 결과도 같게 나온다")

    section(f"4. 학습 · 평가 (시드 {SEEDS}, device={DEV})")
    te = D["idx_te"]
    y_te, v_te = D["y"][te], D["v"][te]
    strata = {"전체": np.ones(len(te), bool), "앵커=음성": v_te == "N",
              "앵커=양성": v_te == "P", "앵커=평가불가": v_te == "U"}
    rows, sat_rows = [], []
    for seed in SEEDS:
        preds = {}
        xgb = XGBClassifier(n_estimators=400, max_depth=6, learning_rate=0.05, subsample=0.8,
                            colsample_bytree=0.8, eval_metric="aucpr", random_state=seed,
                            n_jobs=-1, tree_method="hist")
        xgb.fit(Z[D["idx_tr"]], D["y"][D["idx_tr"]])
        preds["XGBoost"] = xgb.predict_proba(Z[te])[:, 1]
        log(f"seed {seed} · XGBoost")
        p, _ = train_net(D, seed, cbm=False, w_concept=0.0)
        preds["BiLSTM"] = p.cpu().numpy()
        log(f"seed {seed} · BiLSTM")
        p_cbm, c_cbm = train_net(D, seed, cbm=True, w_concept=1.0)
        preds["CBM"] = p_cbm.cpu().numpy()
        log(f"seed {seed} · CBM")
        for name, (ax, axset) in axiom_sets.items():
            p, c = train_net(D, seed, cbm=True, w_concept=1.0, axioms=axset, w_axiom=W_AXIOM)
            preds[f"LTN {name}"] = p.cpu().numpy()
            log(f"seed {seed} · LTN {name}")
            with torch.no_grad():   # 공리별 만족도: 공리 없이 학습한 CBM 과 비교
                s_cbm = axset.satisfaction(c_cbm, p_cbm, per_axiom=True).cpu().numpy()
                s_ltn = axset.satisfaction(c, p, per_axiom=True).cpu().numpy()
            for a, s1, s2 in zip(ax, s_cbm, s_ltn):
                sat_rows.append(dict(seed=seed, 세트=name, 공리=a[0], CBM=s1, LTN=s2))
        for model, p in preds.items():
            for st, sel in strata.items():
                if y_te[sel].min() == y_te[sel].max():
                    continue
                rows.append(dict(seed=seed, 모델=model, 계층=st, n=int(sel.sum()),
                                 AUROC=100 * roc_auc_score(y_te[sel], p[sel]),
                                 AUPRC=100 * average_precision_score(y_te[sel], p[sel])))

    res = pd.DataFrame(rows)
    order = list(dict.fromkeys(res["모델"]))
    summary = (res.groupby(["계층", "모델"], sort=False)[["AUROC", "AUPRC"]]
               .agg(["mean", "std"]).round(2))
    print(summary.to_string())
    res.to_csv(os.path.join(RESULT_DIR, "metrics_by_seed.csv"), index=False, encoding="utf-8-sig")
    summary.to_csv(os.path.join(RESULT_DIR, "metrics.csv"), encoding="utf-8-sig")
    main_tbl = res[res["계층"] == "전체"].groupby("모델")["AUROC"].mean().reindex(order)
    print(f"\n전체 AUROC — " + " · ".join(f"{k} {v:.2f}" for k, v in main_tbl.items()))

    section("5. 공리 점검 (test set)")
    sat = pd.DataFrame(sat_rows).groupby(["세트", "공리"], sort=False)[["CBM", "LTN"]].mean()
    # 데이터가 공리를 지지하는가: 모델 없이 실제 개념값과 라벨만으로 잰다
    audit = []
    for name, (ax, _) in axiom_sets.items():
        for nm, concept, sign, raw_thr, head, neg, grade in ax:
            i = cidx[concept]
            A = C[te, i] > 0.5 if is_bin[i] else sign * (C[te, i] - raw_thr) > 0
            B = (y_te > 0) if head == "Delirium" else (C[te, cidx[head]] > 0.5)
            B = ~B if neg else B
            dis = A.astype(float) * (1.0 - B.astype(float))
            row = {"세트": name, "공리": nm, "등급": grade, "활성화%": round(100 * A.mean(), 1),
                   "데이터 만족도": round(1.0 - float(np.sqrt((dis ** 2).mean())), 3)}
            if 0 < A.sum() < len(A):
                row["P(결론|활성)%"] = round(100 * B[A].mean(), 1)
                row["P(결론|비활성)%"] = round(100 * B[~A].mean(), 1)
            audit.append(row)
    audit = (pd.DataFrame(audit).set_index(["세트", "공리"])
             .join(sat.round(3).add_prefix("모델 만족도 ")))
    print(audit.to_string())
    print("\n활성화% = 앞조건이 켜진 환자 비율. 공리가 맞다면 P(결론|활성) > P(결론|비활성).")
    print("만족도는 1 − a + a·b 의 집계라, 앞조건이 거의 안 켜지는 공리는 저절로 1 에 가깝다.")
    audit.to_csv(os.path.join(RESULT_DIR, "axiom_audit.csv"), encoding="utf-8-sig")
    log(f"완료 → {RESULT_DIR}")


if __name__ == "__main__":
    main()
