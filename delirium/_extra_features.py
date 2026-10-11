# -*- coding: utf-8 -*-
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
