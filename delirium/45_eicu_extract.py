# -*- coding: utf-8 -*-
"""eICU-CRD 2.0 추출 — 섬망 예측에 필요한 기록만 뽑고 코호트 규모를 보고한다.

왜
    2026-11-17 회의: "EICU 실험 설계". MIMIC 으로 얻은 결론(공리 효과는 변동 범위 안 ·
    저데이터에서만 +2.9 · SeverePain 공리는 데이터와 방향이 반대)이 다른 병원에서도
    버티는지 보려면 같은 과제를 eICU 에서 다시 만들어야 한다.

무엇을
    zip 을 풀지 않고 스트리밍으로 읽는다 (5GB 디스크 절약).
    `nurseCharting` 1.5억 행을 **한 번만** 훑어 필요한 항목만 parquet 으로 남긴다.
    그 뒤로는 parquet 만 읽으면 되므로 다시 스캔하지 않는다.

    delirium.parquet   CAM-ICU 평가      (stay, offset, 척도, 값)
    sedation.parquet   RASS 진정 점수     (stay, offset, 척도, 값)
    gcs.parquet        GCS 총점·구성요소   (stay, offset, 항목, 값)
    pain.parquet       통증 점수          (stay, offset, 값)
    patient.parquet    환자·재원 정보      (patient 테이블 그대로)

MIMIC 과 다른 점 (코드에 반영돼 있다)
    · 시각이 절대시간이 아니라 **입실 기준 분 오프셋** → hr = offset / 60
    · 나이가 '> 89' 같은 문자열 → 89 로 둔다
    · ICU 재원시간은 unitdischargeoffset(분) → LOS(일) = /1440
    · 섬망 척도가 CAM-ICU 외에 ICDSC 등도 섞여 있다 → CAM-ICU 만 쓴다
    · 진정 척도가 RASS 외에 SAS(1~7) 도 섞여 있다 → RASS 만 쓴다

사용
    python delirium/45_eicu_extract.py --zip <eicu...2.0.zip> --out C:/data/eicu_cache
    python delirium/45_eicu_extract.py --out C:/data/eicu_cache --report-only
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HORIZON_H = 24.0        # 앵커 이후 이 시간 안의 확정 평가로 라벨을 만든다 (44_ 와 동일)
ANCHOR_MAX_H = 240.0    # 입실 후 이 시간 안의 평가만 앵커로 쓴다 (44_ 와 동일)
MIN_LOS_DAY = 1.0
MIN_AGE = 18
T0 = time.time()

# nurseCharting 에서 가져올 항목 — (분류, 라벨) → 우리 이름
WANTED = {
    ("Scores", "Delirium Scale/Score"): "delirium",
    ("Scores", "Sedation Scale/Score/Goal"): "sedation",
    ("Scores", "Glasgow coma score"): "gcs",
    ("Scores", "Pain Score/Goal"): "pain",
}


def log(m):
    print(f"[{time.time() - T0:6.0f}s] {m}", flush=True)


def member(z, name):
    return [i.filename for i in z.infolist()
            if i.filename.endswith("/" + name) and "/._" not in i.filename][0]


def read_table(z, name, usecols=None):
    with z.open(member(z, name)) as fh, gzip.open(fh, "rt", newline="") as g:
        return pd.read_csv(g, usecols=usecols, low_memory=False)


def scan_nursecharting(z, out):
    """1.5억 행을 한 번 훑어 필요한 항목만 모은다."""
    buf = {k: [] for k in set(WANTED.values())}
    n = tot = 0
    with z.open(member(z, "nurseCharting.csv.gz")) as fh, gzip.open(fh, "rt", newline="") as g:
        r = csv.reader(g)
        hdr = next(r)
        si, oi = hdr.index("patientunitstayid"), hdr.index("nursingchartoffset")
        ci, li = hdr.index("nursingchartcelltypecat"), hdr.index("nursingchartcelltypevallabel")
        vi, xi = hdr.index("nursingchartcelltypevalname"), hdr.index("nursingchartvalue")
        for row in r:
            tot += 1
            key = WANTED.get((row[ci], row[li]))
            if key is not None:
                buf[key].append((int(row[si]), int(row[oi]), row[vi], row[xi]))
                n += 1
            if tot % 20_000_000 == 0:
                log(f"  {tot:,}행 훑음 · 보관 {n:,}")
    log(f"nurseCharting {tot:,}행 → 보관 {n:,}")
    for k, rows in buf.items():
        df = pd.DataFrame(rows, columns=["stay", "offset", "item", "value"])
        df.to_parquet(out / f"{k}.parquet", index=False)
        log(f"  {k}.parquet {len(df):,}행")


# 공리 개념에 필요한 약물·진단 — 문자열로 찾는다 (eICU 는 itemid 가 없다)
DRUG_PAT = {
    "benzo": ("lorazepam", "midazolam", "diazepam", "ativan", "versed"),
    "propofol": ("propofol", "diprivan"),
    "dexmedetomidine": ("dexmedetomidine", "precedex"),
}
DX_PAT = {
    "Dementia": ("dementia", "alzheimer"),
    "Trauma": ("trauma|",),                 # eICU diagnosisstring 의 최상위 범주
    "Hypertension": ("hypertension",),      # 폐고혈압은 아래에서 제외한다
}
DX_EXCLUDE = ("pulmonary hypertension", "portal hypertension", "intracranial hypertension")
TRANSFUSION_PAT = ("transfusion", "packed red blood cell", "blood product")


def _match(text, pats):
    t = text.lower()
    return any(p in t for p in pats)


def scan_extra(z, out):
    """진정제 투여 · 동반질환 · 수혈 — 공리 개념에 쓰는 것만 뽑는다."""
    rows = []
    for tbl, off_col, name_col in (("infusionDrug", "infusionoffset", "drugname"),
                                   ("medication", "drugstartoffset", "drugname")):
        with z.open(member(z, tbl + ".csv.gz")) as fh, gzip.open(fh, "rt", newline="") as g:
            r = csv.reader(g); hdr = next(r)
            si, oi, ni = (hdr.index("patientunitstayid"), hdr.index(off_col), hdr.index(name_col))
            n = 0
            for row in r:
                for cls, pats in DRUG_PAT.items():
                    if _match(row[ni], pats):
                        try:
                            rows.append((int(row[si]), int(row[oi] or 0), cls, tbl))
                        except ValueError:
                            break
                        n += 1
                        break
        log(f"  {tbl}: 진정제 {n:,}행")
    pd.DataFrame(rows, columns=["stay", "offset", "drug", "src"]).to_parquet(
        out / "drugs.parquet", index=False)

    dx = []
    for tbl, off_col, txt_cols in (("diagnosis", "diagnosisoffset", ("diagnosisstring",)),
                                   ("pastHistory", "pasthistoryoffset", ("pasthistorypath",
                                                                         "pasthistoryvalue"))):
        with z.open(member(z, tbl + ".csv.gz")) as fh, gzip.open(fh, "rt", newline="") as g:
            r = csv.reader(g); hdr = next(r)
            si, oi = hdr.index("patientunitstayid"), hdr.index(off_col)
            ti = [hdr.index(c) for c in txt_cols]
            n = 0
            for row in r:
                text = " ".join(row[i] for i in ti)
                if _match(text, DX_EXCLUDE):
                    continue
                for cond, pats in DX_PAT.items():
                    if _match(text, pats):
                        try:
                            dx.append((int(row[si]), int(row[oi] or 0), cond, tbl))
                        except ValueError:
                            break
                        n += 1
                        break
        log(f"  {tbl}: 동반질환 {n:,}행")
    pd.DataFrame(dx, columns=["stay", "offset", "cond", "src"]).to_parquet(
        out / "dx.parquet", index=False)

    tr = []
    with z.open(member(z, "treatment.csv.gz")) as fh, gzip.open(fh, "rt", newline="") as g:
        r = csv.reader(g); hdr = next(r)
        si, oi, ti = (hdr.index("patientunitstayid"), hdr.index("treatmentoffset"),
                      hdr.index("treatmentstring"))
        for row in r:
            if _match(row[ti], TRANSFUSION_PAT):
                tr.append((int(row[si]), int(row[oi] or 0)))
    log(f"  treatment: 수혈 {len(tr):,}행")
    pd.DataFrame(tr, columns=["stay", "offset"]).to_parquet(out / "transfusion.parquet", index=False)


def cohort_report(out):
    pat = pd.read_parquet(out / "patient.parquet")
    pat["age_n"] = pd.to_numeric(pat["age"].replace("> 89", "89"), errors="coerce")
    pat["los_day"] = pat["unitdischargeoffset"] / 1440.0
    cohort = pat[(pat.age_n >= MIN_AGE) & (pat.los_day >= MIN_LOS_DAY)]
    print(f"\n{'=' * 78}\neICU 코호트\n{'=' * 78}")
    print(f"ICU 재원 전체        {len(pat):,} · 환자 {pat.uniquepid.nunique():,} · 병원 {pat.hospitalid.nunique()}")
    print(f"성인·LOS>=1일        {len(cohort):,} · 환자 {cohort.uniquepid.nunique():,} "
          f"· 병원 {cohort.hospitalid.nunique()}")

    d = pd.read_parquet(out / "delirium.parquet")
    scale = d[d.item == "Delirium Scale"][["stay", "offset", "value"]].rename(columns={"value": "scale"})
    score = d[d.item == "Delirium Score"][["stay", "offset", "value"]].rename(columns={"value": "score"})
    cam = score.merge(scale, on=["stay", "offset"], how="left")
    print(f"\n섬망 평가 전체        {len(score):,}  (척도 표기 있는 것 {cam.scale.notna().sum():,})")
    print("  척도 분포:", cam.scale.value_counts(dropna=False).head(5).to_dict())
    cam = cam[cam.scale == "CAM-ICU"]
    print(f"CAM-ICU 만            {len(cam):,} · stay {cam.stay.nunique():,}")

    cam = cam[cam.stay.isin(set(cohort.patientunitstayid))].copy()
    cam["hr"] = cam["offset"] / 60.0
    cam = cam[(cam.hr >= 0) & (cam.hr <= ANCHOR_MAX_H)]
    code = {"No": "N", "Yes": "P", "N/A": "U", "Unable to Assess": "U"}
    cam["v"] = cam["score"].map(code)
    cam = cam[cam.v.notna()].sort_values(["stay", "hr"]).reset_index(drop=True)
    print(f"\n{'=' * 78}\n앵커 (코호트 안 · 입실 후 0~240h)\n{'=' * 78}")
    print(f"앵커 {len(cam):,} · stay {cam.stay.nunique():,} · 값 분포 {cam.v.value_counts().to_dict()}")

    # 라벨: 앵커 이후 24h 안에 확정 평가(P/N)가 있나 — 44_ 의 build_anchors 와 같은 계산
    h = cam["hr"].to_numpy(float)
    conf = (cam["v"] != "U").to_numpy()
    pos = (cam["v"] == "P").to_numpy()
    cum_c = np.concatenate([[0], conf.cumsum()])
    cum_p = np.concatenate([[0], (conf & pos).cumsum()])
    _, first, cnt = np.unique(cam["stay"].to_numpy(), return_index=True, return_counts=True)
    labeled = np.zeros(len(cam), bool); y = np.zeros(len(cam), bool)
    for a, n in zip(first, cnt):
        hh, idx = h[a:a + n], np.arange(n)
        j = np.searchsorted(hh, hh + HORIZON_H, side="right")
        labeled[a:a + n] = (cum_c[a + j] - cum_c[a + idx + 1]) > 0
        y[a:a + n] = (cum_p[a + j] - cum_p[a + idx + 1]) > 0
    print(f"라벨 있는 앵커 {labeled.sum():,} ({100 * labeled.mean():.1f}%) · "
          f"양성률 {100 * y[labeled].mean():.1f}%")
    print(f"\nMIMIC 비교 — 앵커 486,344 / 라벨 345,505 / 양성 31.3%")
    print(f"           eICU {len(cam):,} / {labeled.sum():,} / {100 * y[labeled].mean():.1f}%  "
          f"(앵커 기준 {100 * len(cam) / 486344:.0f}% 규모)")

    # 병원별 — CAM-ICU 를 쓰는 병원이 몇 곳인지 (일반화 가능성과 직결된다)
    hp = cohort.set_index("patientunitstayid")["hospitalid"]
    cam["hospital"] = cam["stay"].map(hp)
    per = cam.groupby("hospital").size().sort_values(ascending=False)
    print(f"\nCAM-ICU 기록이 있는 병원 {len(per)}곳 / 코호트 전체 {cohort.hospitalid.nunique()}곳")
    print(f"  상위 5곳이 전체 앵커의 {100 * per.head(5).sum() / per.sum():.0f}% · "
          f"상위 1곳 {100 * per.iloc[0] / per.sum():.0f}%")

    for nm, f in (("sedation", "sedation.parquet"), ("gcs", "gcs.parquet"), ("pain", "pain.parquet")):
        t = pd.read_parquet(out / f)
        t = t[t.stay.isin(set(cam.stay))]
        print(f"{nm:9s} 앵커 stay 안 기록 {len(t):,} · stay {t.stay.nunique():,}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", help="eicu-collaborative-research-database-2.0.zip")
    ap.add_argument("--out", required=True)
    ap.add_argument("--report-only", action="store_true", help="이미 뽑아 둔 parquet 으로 보고만")
    ap.add_argument("--extra-only", action="store_true", help="약물·진단·수혈만 추가로 뽑는다")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    if a.extra_only:
        log("약물·진단·수혈 추출")
        scan_extra(zipfile.ZipFile(a.zip), out)
        log(f"완료 -> {out}")
        return
    if not a.report_only:
        if not a.zip:
            sys.exit("--zip 이 필요하다 (또는 --report-only)")
        z = zipfile.ZipFile(a.zip)
        log("patient 테이블")
        read_table(z, "patient.csv.gz").to_parquet(out / "patient.parquet", index=False)
        log("nurseCharting 스캔 (1.5억 행, 10~15분)")
        scan_nursecharting(z, out)
        log("약물·진단·수혈 추출")
        scan_extra(z, out)
    cohort_report(out)
    log(f"완료 -> {out}")


if __name__ == "__main__":
    main()
