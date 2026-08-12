"""Build events_{6,12,24,48}h_before_death_gcs.csv from dataset_gcs*.csv.

Logic mirrors extract_before_death.py with lead hours parameterized.
Survivor windows use a fixed RNG seed for reproducibility.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def get_events_before_death(group: pd.DataFrame, lead_hours: int, rng: np.random.Generator) -> pd.DataFrame:
    death_event = group[group["concept:name"] == "Death"]
    if not death_event.empty:
        death_time = death_event["time:timestamp"].iloc[0]
        start_cut = death_time - pd.Timedelta(hours=lead_hours)
        # Drop events inside lead window and at/after death (leakage guard)
        kept = group[group["time:timestamp"] < start_cut]
        if kept.empty:
            return kept
        last_t = kept["time:timestamp"].max()
        win_start = last_t - pd.Timedelta(hours=24)
        return kept[kept["time:timestamp"] >= win_start]

    # Survivors: random 24h window within available span
    if len(group) <= 1:
        return group
    min_t = group["time:timestamp"].min()
    max_t = group["time:timestamp"].max()
    window = pd.Timedelta(hours=24)
    if max_t - min_t <= window:
        return group
    latest_start = max_t - window
    span = (latest_start - min_t).total_seconds()
    offset = float(rng.uniform(0, max(span, 0.0)))
    start = min_t + pd.to_timedelta(offset, unit="s")
    return group[(group["time:timestamp"] >= start) & (group["time:timestamp"] <= start + window)]


def build_for_lead(df: pd.DataFrame, lead_hours: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Explicit loop: pandas 3 groupby.apply may drop grouping cols (include_groups=False).
    parts: list[pd.DataFrame] = []
    for _, g in df.groupby("hadm_id", sort=False):
        part = get_events_before_death(g, lead_hours, rng)
        if part is not None and len(part):
            parts.append(part)
    if not parts:
        return pd.DataFrame(columns=df.columns)
    out = pd.concat(parts, ignore_index=True)
    out["hospital_expire_flag"] = out.groupby("hadm_id")["hospital_expire_flag"].transform(
        lambda x: x.ffill().bfill()
    )
    out = out.dropna(subset=["hospital_expire_flag"])
    out["hospital_expire_flag"] = out["hospital_expire_flag"].astype(int)
    out = out.sort_values(["subject_id", "hadm_id", "time:timestamp"])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 6/12/24/48h observation-window CSVs")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to dataset_gcs_v1.csv (or dataset_gcs.csv)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Output directory (e.g. NeSy-SMP/data/subset)",
    )
    parser.add_argument(
        "--hours",
        type=int,
        nargs="+",
        default=[6, 12, 24, 48],
        help="Lead times in hours",
    )
    parser.add_argument("--seed", type=int, default=32)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input not found: {args.input}")

    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {args.input} ...")
    df = pd.read_csv(args.input, low_memory=False, dtype={"subject_id": str, "hadm_id": str})
    df["time:timestamp"] = pd.to_datetime(df["time:timestamp"])
    print(
        f"loaded rows={len(df):,} hadm={df['hadm_id'].nunique():,} "
        f"Death={(df['concept:name'] == 'Death').sum():,}"
    )

    for h in args.hours:
        print(f"\n=== lead={h}h (seed={args.seed}) ===")
        out = build_for_lead(df, h, args.seed)
        path = args.out_dir / f"events_{h}h_before_death_gcs.csv"
        out.to_csv(path, index=False)
        mort = out.drop_duplicates("hadm_id")["hospital_expire_flag"].mean()
        print(f"saved {path}")
        print(f"rows={len(out):,} hadm={out['hadm_id'].nunique():,} mortality={mort:.1%}")
        print(out["concept:name"].value_counts().head(10).to_string())


if __name__ == "__main__":
    main()
