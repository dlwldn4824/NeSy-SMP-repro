# Phase 3 — Table 1 vs Table 2 Reproduction

- CSV: `C:\data\mimic-iv-derived\events_48h_wide_s3.csv`
- seed=42, epochs=50/20, device=cuda
- n=18200, mortality=15.6%, seq_window=230
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
| BiLSTM | Acc | 83.53 | 87.52±0.49 | +3.99 |
| BiLSTM | F1 | 76.82 | 74.15±0.54 | -2.67 |
| BiLSTM | Prec | 77.91 | 76.83±1.29 | -1.08 |
| BiLSTM | Rec | 76.22 | 72.28±0.83 | -3.94 |
| BiLSTM | AUC | 85.35 | 87.76±0.35 | +2.41 |
| LTN | Acc | 85.65 | 86.17±0.27 | +0.52 |
| LTN | F1 | 79.20 | 75.16±0.53 | -4.04 |
| LTN | Prec | 80.63 | 73.93±0.48 | -6.70 |
| LTN | Rec | 78.06 | 76.69±0.81 | -1.37 |
| LTN | AUC | 88.10 | 87.83±0.29 | -0.27 |
| NeSy-SMP | Acc | 86.45 | 84.96±1.54 | -1.49 |
| NeSy-SMP | F1 | 80.35 | 74.32±1.13 | -6.03 |
| NeSy-SMP | Prec | 81.86 | 72.66±1.60 | -9.20 |
| NeSy-SMP | Rec | 79.14 | 77.29±1.72 | -1.85 |
| NeSy-SMP | AUC | 88.33 | 87.51±0.70 | -0.82 |
| RF | Acc | 84.78 | 87.46±0.20 | +2.68 |
| RF | F1 | 74.77 | 66.05±0.83 | -8.72 |
| RF | Prec | 83.07 | 83.96±0.98 | +0.89 |
| RF | Rec | 71.48 | 62.34±0.64 | -9.14 |
| RF | AUC | 88.11 | 87.30±0.44 | -0.81 |
| XGBoost | Acc | 85.31 | 88.16±0.28 | +2.85 |
| XGBoost | F1 | 77.86 | 74.20±0.71 | -3.66 |
| XGBoost | Prec | 80.90 | 79.00±0.97 | -1.90 |
| XGBoost | Rec | 75.86 | 71.36±0.98 | -4.50 |
| XGBoost | AUC | 88.56 | 88.91±0.42 | +0.35 |

## Table 2 pooled OOF (binary vs macro + bootstrap)

### BiLSTM
- point binary F1=55.57 | pooled macro F1=74.16
- boot binary F1 55.58 [53.88, 57.18]
- boot macro F1 74.16 [73.21, 75.05]

### LTN
- point binary F1=58.62 | pooled macro F1=75.16
- boot binary F1 58.63 [57.12, 60.15]
- boot macro F1 75.17 [74.33, 76.05]

### NeSy-SMP
- point binary F1=57.79 | pooled macro F1=74.32
- boot binary F1 57.80 [56.35, 59.28]
- boot macro F1 74.32 [73.49, 75.19]

### RF
- point binary F1=39.10 | pooled macro F1=66.06
- boot binary F1 39.08 [37.07, 40.95]
- boot macro F1 66.04 [65.01, 67.06]

### XGBoost
- point binary F1=55.26 | pooled macro F1=74.22
- boot binary F1 55.23 [53.46, 56.84]
- boot macro F1 74.21 [73.24, 75.09]

## NeSy-SMP T1 vs T2 discrepancy

| | Value |
|---|---:|
| Paper T1 F1 (macro fold) | 80.35 |
| Paper T2 F1 | 68.51 |
| Our T1 F1 (macro fold mean) | 74.32 |
| Our pooled binary F1 | 57.79 |
| Our pooled macro F1 | 74.32 |

Interpretation: T1–T2 gap is largely **macro (fold) vs binary (pooled)** under class imbalance, not necessarily a training bug.