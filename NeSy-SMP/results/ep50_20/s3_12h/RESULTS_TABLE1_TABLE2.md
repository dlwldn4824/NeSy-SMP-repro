# Phase 3 — Table 1 vs Table 2 Reproduction

- CSV: `C:\data\mimic-iv-derived\events_12h_wide_s3.csv`
- seed=42, epochs=50/20, device=cuda
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
| BiLSTM | Acc | 83.53 | 88.23±0.39 | +4.70 |
| BiLSTM | F1 | 76.82 | 80.07±0.99 | +3.25 |
| BiLSTM | Prec | 77.91 | 81.00±0.87 | +3.09 |
| BiLSTM | Rec | 76.22 | 79.42±1.96 | +3.20 |
| BiLSTM | AUC | 85.35 | 90.91±0.30 | +5.56 |
| LTN | Acc | 85.65 | 88.53±0.37 | +2.88 |
| LTN | F1 | 79.20 | 80.40±0.82 | +1.20 |
| LTN | Prec | 80.63 | 81.67±0.98 | +1.04 |
| LTN | Rec | 78.06 | 79.46±1.72 | +1.40 |
| LTN | AUC | 88.10 | 90.92±0.41 | +2.82 |
| NeSy-SMP | Acc | 86.45 | 88.14±0.60 | +1.69 |
| NeSy-SMP | F1 | 80.35 | 80.58±0.85 | +0.23 |
| NeSy-SMP | Prec | 81.86 | 80.38±1.04 | -1.48 |
| NeSy-SMP | Rec | 79.14 | 80.83±0.90 | +1.69 |
| NeSy-SMP | AUC | 88.33 | 90.93±0.45 | +2.60 |
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
- point binary F1=67.40 | pooled macro F1=80.11
- boot binary F1 67.37 [66.10, 68.65]
- boot macro F1 80.09 [79.37, 80.84]

### LTN
- point binary F1=67.84 | pooled macro F1=80.43
- boot binary F1 67.81 [66.55, 69.13]
- boot macro F1 80.42 [79.68, 81.18]

### NeSy-SMP
- point binary F1=68.47 | pooled macro F1=80.58
- boot binary F1 68.42 [67.15, 69.73]
- boot macro F1 80.56 [79.82, 81.33]

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
| Our T1 F1 (macro fold mean) | 80.58 |
| Our pooled binary F1 | 68.47 |
| Our pooled macro F1 | 80.58 |

Interpretation: T1–T2 gap is largely **macro (fold) vs binary (pooled)** under class imbalance, not necessarily a training bug.