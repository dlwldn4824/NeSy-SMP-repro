"""Sepsis 사망 예측 — 시점(window) 단위 데이터셋.

원본 설계(입원당 1개: 사망자는 사망 lead h 전 24h 창, 생존자는 무작위 24h 창)를 대신해
ICU 재원 중 여러 예측 시점을 만든다.

    예측 시점  t = ICU 입실 + 24h + stride·k   (t < min(ICU 퇴실, 입실+cap, 사망))
    입력      [t−24h, t] 이벤트 — long_to_wide / preprocess_eventlog 와 같은 변수·같은 가공
    타깃      t 이후 horizon 시간 안에 원내 사망

전처리는 data/preprocessing.py::preprocess_eventlog 를 그대로 따르되, 인스턴스가 많아
create_training_data 의 파이썬 리스트(샘플×변수×길이) 대신 텐서를 바로 만든다.
출력: 인스턴스 텐서(.pt) + 메타(.csv). 학습은 rolling_tables.py.

사용:
  python data/make_rolling_windows.py --events C:/data/mimic-iv-derived/dataset_gcs_s3.csv \
      --cohort C:/data/mimic-iv-derived/cohort_sepsis3_paperlike.csv \
      --como C:/data/mimic-iv-derived/comorbidities_icd_wide.csv \
      --out C:/data/mimic-iv-derived/rolling_s3_icd_s12_h24.pt
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import MinMaxScaler

from long_to_wide import CONCEPT_MAP, COMORBIDITIES, NUMERIC_COLS
from preprocessing import COMORBIDITY_COLS

T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def load_events(path: Path, hadms: set) -> pd.DataFrame:
    cols = ["hadm_id", "time:timestamp", "concept:name", "value"]
    parts = []
    for ch in pd.read_csv(path, usecols=cols, chunksize=4_000_000, low_memory=False):
        ch = ch[ch["hadm_id"].isin(hadms) & ch["concept:name"].isin(CONCEPT_MAP.keys())]
        ch["concept:name"] = ch["concept:name"].map(CONCEPT_MAP).astype("category")
        parts.append(ch)
        log(f"  read chunk → kept {sum(len(p) for p in parts):,}")
    ev = pd.concat(parts, ignore_index=True)
    ev["concept:name"] = ev["concept:name"].astype(str)
    ev["time:timestamp"] = pd.to_datetime(ev["time:timestamp"])
    return ev


def to_wide_rows(ev: pd.DataFrame) -> pd.DataFrame:
    """long_to_wide 와 같다: (hadm, 시각) 한 행, 개념별 마지막 값, concept:name = 그 시각 마지막 개념."""
    ev = ev.reset_index(drop=True)
    ev["_ord"] = np.arange(len(ev))
    ev = ev.sort_values(["hadm_id", "time:timestamp", "_ord"], kind="mergesort")
    last_val = ev.drop_duplicates(["hadm_id", "time:timestamp", "concept:name"], keep="last")
    wide = last_val.pivot(index=["hadm_id", "time:timestamp"], columns="concept:name", values="value")
    last_concept = ev.drop_duplicates(["hadm_id", "time:timestamp"], keep="last").set_index(
        ["hadm_id", "time:timestamp"])["concept:name"]
    wide["concept:name"] = last_concept
    return wide.reset_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=Path, required=True)
    ap.add_argument("--cohort", type=Path, required=True)
    ap.add_argument("--como", type=Path, default=None, help="동반질환 wide CSV (없으면 0)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--stride", type=float, default=12.0)
    ap.add_argument("--horizon", type=float, default=24.0)
    ap.add_argument("--obs", type=float, default=24.0, help="관찰 창 길이(h)")
    ap.add_argument("--cap", type=float, default=240.0, help="입실 후 최대 예측 시점(h)")
    ap.add_argument("--seq-cap", type=int, default=64, help="창당 최대 이벤트 행 수(최근 것 유지)")
    ap.add_argument("--limit-hadm", type=int, default=0, help="점검용: 앞 N 입원만")
    args = ap.parse_args()

    co = pd.read_csv(args.cohort, parse_dates=["icu_intime", "icu_outtime", "deathtime"])
    co = co.drop_duplicates("hadm_id")
    if args.limit_hadm:
        co = co.head(args.limit_hadm)
    log(f"cohort hadm={len(co):,} subj={co.subject_id.nunique():,}")

    ev = load_events(args.events, set(co.hadm_id))
    log(f"events rows={len(ev):,}")
    rows = to_wide_rows(ev)
    del ev
    log(f"timestamp rows={len(rows):,}")

    rows = rows.merge(co[["hadm_id", "icu_intime", "icu_outtime", "deathtime", "age", "admission_location"]],
                      on="hadm_id", how="left")
    h = (rows["time:timestamp"] - rows["icu_intime"]).dt.total_seconds() / 3600
    los = (rows["icu_outtime"] - rows["icu_intime"]).dt.total_seconds() / 3600
    hd = (rows["deathtime"] - rows["icu_intime"]).dt.total_seconds() / 3600
    # 시점 t_k = obs + stride·k. 행 시각 h 가 [t_k − obs, t_k] 에 들면 인스턴스 k 에 속한다.
    k_lo = np.ceil((h - args.obs) / args.stride).clip(lower=0)  # t_k >= h  ⇔  k >= (h-obs)/stride
    k_hi = np.floor(h / args.stride)                             # t_k - obs <= h ⇔ k <= h/stride
    t_max = np.minimum(np.minimum(los, args.cap), hd.fillna(np.inf))
    k_max = np.ceil((t_max - args.obs) / args.stride) - 1          # t_k < t_max
    k_hi = np.minimum(k_hi, k_max)
    ok = (h >= 0) & (k_hi >= k_lo)
    rows, k_lo, k_hi = rows[ok].reset_index(drop=True), k_lo[ok].to_numpy(int), k_hi[ok].to_numpy(int)
    n_rep = k_hi - k_lo + 1
    idx = np.repeat(np.arange(len(rows)), n_rep)
    k = np.concatenate([np.arange(a, b + 1) for a, b in zip(k_lo, k_hi)]) if len(rows) else np.array([], int)
    rows = rows.iloc[idx].reset_index(drop=True)
    rows["k"] = k
    log(f"window rows (with overlap)={len(rows):,}")

    rows["t_h"] = args.obs + args.stride * rows["k"]
    rows["inst"] = rows["hadm_id"].astype("int64") * 1000 + rows["k"].astype("int64")  # hadm·1000 + k
    hd = (rows["deathtime"] - rows["icu_intime"]).dt.total_seconds() / 3600
    rows["hospital_expire_flag"] = ((hd > rows["t_h"]) & (hd <= rows["t_h"] + args.horizon)).astype(int)

    # 동반질환 (merge_comorbidities.py 와 같게: 없는 hadm 은 0)
    if args.como is not None:
        como = pd.read_csv(args.como)
        keep = ["hadm_id"] + [c for c in COMORBIDITIES if c in como.columns]
        rows = rows.merge(como[keep], on="hadm_id", how="left")
    for c in COMORBIDITIES:
        if c not in rows.columns:
            rows[c] = 0
        rows[c] = rows[c].fillna(0).astype(int)

    # long_to_wide 의 고정 열
    for c in NUMERIC_COLS:
        if c not in rows.columns:
            rows[c] = np.nan
    rows["anchor_age"] = rows["age"]
    rows["admission_type"] = "unknown"
    rows["medication"] = "unknown"
    rows = rows.sort_values(["inst", "time:timestamp"], kind="mergesort").reset_index(drop=True)

    # ---- preprocess_eventlog 와 같은 가공 ----
    data = rows
    data = data[~data["concept:name"].isin(["Urine output", "Death", "Discharge from hospital"])]
    data = data[~data["concept:name"].astype(str).str.contains("std", case=False, na=False)].copy()
    data["concept:name"] = pd.Categorical(data["concept:name"].fillna("unknown"))
    data["concept:name"] = data["concept:name"].cat.codes + 1
    vocab_sizes = {"concept:name": int(data["concept:name"].max())}
    for c in ["admission_type", "admission_location", "medication"]:
        data[c] = pd.Categorical(data[c].ffill().bfill().fillna("unknown"))
        data[c] = data[c].cat.codes + 1
        vocab_sizes[c] = int(data[c].max())
    g = data.groupby("inst", sort=False)
    scalers = {}
    num_list = [c for c in NUMERIC_COLS]
    for c in num_list:
        data[c] = g[c].ffill()
        if c == "anchor_age":
            data[c] = data.groupby("inst", sort=False)[c].bfill()
        data[c] = data[c].fillna(0)
        sc = MinMaxScaler()
        data[c] = sc.fit_transform(data[[c]])
        scalers[c] = sc
    log("scaled numeric")

    feat_cols = ["concept:name", "admission_type", "admission_location", "medication"] + \
        [c for c in num_list if c != "anchor_age"] + ["anchor_age"] + list(COMORBIDITY_COLS)
    assert len(COMORBIDITY_COLS) == 23, "note_missing 은 이 스크립트에서 쓰지 않는다"

    sizes = data.groupby("inst", sort=False).size()
    max_group = int(sizes.max())
    keep_inst = sizes[sizes > 4].index
    q = sizes.quantile([0.5, 0.9, 0.95, 0.99]).to_dict()
    log(f"rows/instance median {q[0.5]:.0f} p90 {q[0.9]:.0f} p95 {q[0.95]:.0f} p99 {q[0.99]:.0f} max {max_group}"
        f" | >{args.seq_cap}: {(sizes > args.seq_cap).mean():.2%} | <=4 dropped {(sizes <= 4).sum():,}")
    data = data[data["inst"].isin(keep_inst)]
    L = min(max_group, args.seq_cap)

    # 인스턴스별 마지막 L 행, 뒤쪽 0 패딩 (create_training_data 와 같음)
    inst_codes, inst_names = pd.factorize(data["inst"], sort=False)
    data = data.assign(_i=inst_codes)
    n_rows = data.groupby("_i").cumcount(ascending=False).to_numpy()   # 끝에서부터 0,1,2..
    tail = n_rows < L
    d = data[tail]
    pos = d.groupby("_i").cumcount().to_numpy()
    N, F = len(inst_names), len(feat_cols)
    X = torch.zeros((N, F, L), dtype=torch.float32)
    vals = torch.tensor(d[feat_cols].to_numpy(dtype=np.float32))
    X[torch.tensor(d["_i"].to_numpy()), :, torch.tensor(pos)] = vals
    first = data.drop_duplicates("_i").sort_values("_i")
    como_first = torch.tensor(first[list(COMORBIDITY_COLS)].to_numpy(dtype=np.float32))
    X = torch.cat([X.reshape(N, F * L), como_first], dim=1)
    log(f"tensor X {tuple(X.shape)} ~ {X.numel() * 4 / 1e9:.2f} GB")

    last = data.groupby("_i").tail(1).sort_values("_i")
    meta = pd.DataFrame({
        "inst": inst_names,
        "hadm_id": first["hadm_id"].to_numpy(),
        "t_h": first["t_h"].to_numpy(),
        "y": last["hospital_expire_flag"].to_numpy().astype(int),
    }).merge(co[["hadm_id", "subject_id", "hospital_expire_flag", "icu_intime", "deathtime"]], on="hadm_id", how="left")
    meta["hours_to_death"] = (meta["deathtime"] - meta["icu_intime"]).dt.total_seconds() / 3600 - meta["t_h"]
    meta = meta.drop(columns=["icu_intime", "deathtime"])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "X": X, "y": torch.tensor(meta["y"].to_numpy()), "feature_names": feat_cols, "vocab_sizes": vocab_sizes,
        "scalers": scalers, "sequence_length": L, "args": vars(args),
    }, args.out)
    meta.to_csv(args.out.with_suffix(".meta.csv"), index=False)
    log(f"saved {args.out} | instances {N:,} | stays {meta.hadm_id.nunique():,} | subjects {meta.subject_id.nunique():,}"
        f" | positive {meta.y.mean():.2%} | L={L}")


if __name__ == "__main__":
    main()
