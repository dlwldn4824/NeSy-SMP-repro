# Phase 3 — Table 1 vs Table 2 Reproduction

- CSV: `C:\data\mimic-iv-derived\events_12h_wide_s3.csv`
- seed=42, epochs=30/15, device=cuda
- n=18881, mortality=18.6%, seq_window=230
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
| BiLSTM | Acc | 83.53 | 88.60±0.73 | +5.07 |
| BiLSTM | F1 | 76.82 | 80.34±1.13 | +3.52 |
| BiLSTM | Prec | 77.91 | 81.90±1.46 | +3.99 |
| BiLSTM | Rec | 76.22 | 79.05±1.02 | +2.83 |
| BiLSTM | AUC | 85.35 | 91.03±0.47 | +5.68 |
| LTN | Acc | 85.65 | 88.23±0.56 | +2.58 |
| LTN | F1 | 79.20 | 80.47±0.97 | +1.27 |
| LTN | Prec | 80.63 | 80.72±1.16 | +0.09 |
| LTN | Rec | 78.06 | 80.35±1.61 | +2.29 |
| LTN | AUC | 88.10 | 90.79±0.53 | +2.69 |
| NeSy-SMP | Acc | 86.45 | 87.86±0.77 | +1.41 |
| NeSy-SMP | F1 | 80.35 | 80.41±0.86 | +0.06 |
| NeSy-SMP | Prec | 81.86 | 79.85±1.29 | -2.01 |
| NeSy-SMP | Rec | 79.14 | 81.07±0.55 | +1.93 |
| NeSy-SMP | AUC | 88.33 | 90.71±0.43 | +2.38 |
| RF | Acc | 84.78 | 88.51±0.14 | +3.73 |
| RF | F1 | 74.77 | 76.35±0.34 | +1.58 |
| RF | Prec | 83.07 | 87.76±0.74 | +4.69 |
| RF | Rec | 71.48 | 71.79±0.37 | +0.31 |
| RF | AUC | 88.11 | 90.63±0.51 | +2.52 |
| XGBoost | Acc | 85.31 | 89.34±0.26 | +4.03 |
| XGBoost | F1 | 77.86 | 80.94±0.42 | +3.08 |
| XGBoost | Prec | 80.90 | 84.06±0.66 | +3.16 |
| XGBoost | Rec | 75.86 | 78.67±0.47 | +2.81 |
| XGBoost | AUC | 88.56 | 92.12±0.36 | +3.56 |

## Table 2 pooled OOF (binary vs macro + bootstrap)

### BiLSTM
- point binary F1=67.58 | pooled macro F1=80.33
- boot binary F1 67.53 [66.24, 68.86]
- boot macro F1 80.31 [79.56, 81.08]

### LTN
- point binary F1=68.19 | pooled macro F1=80.49
- boot binary F1 68.16 [66.99, 69.41]
- boot macro F1 80.47 [79.76, 81.21]

### NeSy-SMP
- point binary F1=68.30 | pooled macro F1=80.40
- boot binary F1 68.25 [67.05, 69.56]
- boot macro F1 80.37 [79.65, 81.15]

### RF
- point binary F1=59.40 | pooled macro F1=76.36
- boot binary F1 59.37 [57.91, 60.93]
- boot macro F1 76.34 [75.53, 77.20]

### XGBoost
- point binary F1=68.28 | pooled macro F1=80.94
- boot binary F1 68.27 [66.83, 69.64]
- boot macro F1 80.93 [80.11, 81.73]

## NeSy-SMP T1 vs T2 discrepancy

| | Value |
|---|---:|
| Paper T1 F1 (macro fold) | 80.35 |
| Paper T2 F1 | 68.51 |
| Our T1 F1 (macro fold mean) | 80.41 |
| Our pooled binary F1 | 68.30 |
| Our pooled macro F1 | 80.40 |

Interpretation: T1–T2 gap is largely **macro (fold) vs binary (pooled)** under class imbalance, not necessarily a training bug.