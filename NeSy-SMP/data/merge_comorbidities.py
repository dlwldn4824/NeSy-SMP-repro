"""Merge comorbidity one-hot columns into a wide events CSV (by hadm_id)."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from long_to_wide import COMORBIDITIES


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wide", type=Path, required=True)
    ap.add_argument("--como-wide", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    wide = pd.read_csv(args.wide, low_memory=False)
    como = pd.read_csv(args.como_wide)
    print(f"wide rows={len(wide):,} hadm={wide['hadm_id'].nunique():,}")
    print(f"como n={len(como):,}")

    # drop existing zero como cols then merge
    drop = [c for c in COMORBIDITIES if c in wide.columns]
    wide = wide.drop(columns=drop)
    keep = ["hadm_id"] + [c for c in COMORBIDITIES if c in como.columns]
    merged = wide.merge(como[keep], on="hadm_id", how="left")
    for c in COMORBIDITIES:
        if c not in merged.columns:
            merged[c] = 0
        merged[c] = merged[c].fillna(0).astype(int)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.output, index=False)
    any_rate = (merged.groupby("hadm_id")[COMORBIDITIES].max().sum(axis=1) > 0).mean()
    print(f"saved {args.output} rows={len(merged):,} hadm_with_any_como={any_rate:.1%}")


if __name__ == "__main__":
    main()
