# Phase 3 — Table 1 vs Table 2 Reproduction

- CSV: `C:\data\mimic-iv-derived\events_24h_wide_s3.csv`
- seed=42, epochs=30/15, device=cuda
- n=18759, mortality=18.1%, seq_window=230
- comorbidities: **zeros** (notes NLP not merged yet)

## Code grounding

| Question | Finding | Location |
|---|---|---|
| Weak anchoring | **D**: FOL Forall on threshold subsets (not init / not MSE) | `reproduce_tables.py` + `stratified_main.py:519-648` |
| w_D / w_K | Hardcoded **0.8 / 0.2** train loss | `reproduce_tables.py`; `stratified_main.py:539-540` |
| Risk MLP input | concept seq + comorbidities(23) + age | `model/models.py` MLP.forward |
| Survivor window seed | Fixed seed=32 in `make_leadtime_csvs.py` (upstream extract_before_death unseeded) | |
| Table 1 | fold macro mean±std | this script |
| Table 2 | pooled OOF + 1000 bootstrap (binary & macro) | this script |

## Table 1 (5-fold macro) vs Paper

| Model | Metric | Paper | Reproduced | Diff |
|---|---|---:|---:|---:|
| BiLSTM | Acc | 83.53 | 87.96±0.39 | +4.43 |
| BiLSTM | F1 | 76.82 | 78.03±1.13 | +1.21 |
| BiLSTM | Prec | 77.91 | 80.75±0.51 | +2.84 |
| BiLSTM | Rec | 76.22 | 76.08±1.54 | -0.14 |
| BiLSTM | AUC | 85.35 | 89.59±0.73 | +4.24 |
| LTN | Acc | 85.65 | 87.10±0.31 | +1.45 |
| LTN | F1 | 79.20 | 78.16±0.85 | -1.04 |
| LTN | Prec | 80.63 | 78.25±0.41 | -2.38 |
| LTN | Rec | 78.06 | 78.09±1.29 | +0.03 |
| LTN | AUC | 88.10 | 89.08±0.56 | +0.98 |
| NeSy-SMP | Acc | 86.45 | 87.06±0.72 | +0.61 |
| NeSy-SMP | F1 | 80.35 | 78.22±1.11 | -2.13 |
| NeSy-SMP | Prec | 81.86 | 78.32±1.56 | -3.54 |
| NeSy-SMP | Rec | 79.14 | 78.37±2.00 | -0.77 |
| NeSy-SMP | AUC | 88.33 | 89.49±0.93 | +1.16 |
| RF | Acc | 84.78 | 87.50±0.35 | +2.72 |
| RF | F1 | 74.77 | 72.69±1.37 | -2.08 |
| RF | Prec | 83.07 | 85.73±0.39 | +2.66 |
| RF | Rec | 71.48 | 68.38±1.33 | -3.10 |
| RF | AUC | 88.11 | 89.53±0.95 | +1.42 |
| XGBoost | Acc | 85.31 | 88.51±0.36 | +3.20 |
| XGBoost | F1 | 77.86 | 78.68±0.94 | +0.82 |
| XGBoost | Prec | 80.90 | 82.29±0.90 | +1.39 |
| XGBoost | Rec | 75.86 | 76.27±1.41 | +0.41 |
| XGBoost | AUC | 88.56 | 90.86±0.89 | +2.30 |

## Table 2 pooled OOF (binary vs macro + bootstrap)

### BiLSTM
- point binary F1=63.32 | pooled macro F1=78.06
- boot binary F1 63.31 [61.94, 64.68]
- boot macro F1 78.06 [77.24, 78.85]

### LTN
- point binary F1=64.21 | pooled macro F1=78.17
- boot binary F1 64.20 [62.91, 65.57]
- boot macro F1 78.17 [77.41, 78.96]

### NeSy-SMP
- point binary F1=64.41 | pooled macro F1=78.25
- boot binary F1 64.41 [63.07, 65.73]
- boot macro F1 78.25 [77.52, 79.02]

### RF
- point binary F1=52.65 | pooled macro F1=72.73
- boot binary F1 52.67 [51.03, 54.37]
- boot macro F1 72.74 [71.81, 73.65]

### XGBoost
- point binary F1=64.26 | pooled macro F1=78.71
- boot binary F1 64.27 [62.83, 65.61]
- boot macro F1 78.71 [77.90, 79.49]

## NeSy-SMP T1 vs T2 discrepancy

| | Value |
|---|---:|
| Paper T1 F1 (macro fold) | 80.35 |
| Paper T2 F1 | 68.51 |
| Our T1 F1 (macro fold mean) | 78.22 |
| Our pooled binary F1 | 64.41 |
| Our pooled macro F1 | 78.25 |

Interpretation: T1–T2 gap is largely **macro (fold) vs binary (pooled)** under class imbalance, not necessarily a training bug.