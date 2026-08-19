# Phase 3 — Table 1 vs Table 2 Reproduction

- CSV: `C:\data\mimic-iv-derived\events_24h_wide_s3.csv`
- seed=42, epochs=50/20, device=cuda
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
| BiLSTM | Acc | 83.53 | 87.85±0.33 | +4.32 |
| BiLSTM | F1 | 76.82 | 78.21±0.51 | +1.39 |
| BiLSTM | Prec | 77.91 | 80.27±0.87 | +2.36 |
| BiLSTM | Rec | 76.22 | 76.62±0.70 | +0.40 |
| BiLSTM | AUC | 85.35 | 89.56±0.69 | +4.21 |
| LTN | Acc | 85.65 | 87.32±0.27 | +1.67 |
| LTN | F1 | 79.20 | 78.61±0.61 | -0.59 |
| LTN | Prec | 80.63 | 78.66±0.60 | -1.97 |
| LTN | Rec | 78.06 | 78.66±1.42 | +0.60 |
| LTN | AUC | 88.10 | 89.67±0.67 | +1.57 |
| NeSy-SMP | Acc | 86.45 | 86.43±0.52 | -0.02 |
| NeSy-SMP | F1 | 80.35 | 78.14±0.63 | -2.21 |
| NeSy-SMP | Prec | 81.86 | 77.05±0.82 | -4.81 |
| NeSy-SMP | Rec | 79.14 | 79.52±0.98 | +0.38 |
| NeSy-SMP | AUC | 88.33 | 89.34±0.70 | +1.01 |
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
- point binary F1=63.72 | pooled macro F1=78.21
- boot binary F1 63.73 [62.35, 65.16]
- boot macro F1 78.22 [77.44, 79.05]

### LTN
- point binary F1=65.00 | pooled macro F1=78.63
- boot binary F1 64.99 [63.58, 66.35]
- boot macro F1 78.63 [77.83, 79.42]

### NeSy-SMP
- point binary F1=64.68 | pooled macro F1=78.14
- boot binary F1 64.68 [63.36, 65.99]
- boot macro F1 78.14 [77.38, 78.93]

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
| Our T1 F1 (macro fold mean) | 78.14 |
| Our pooled binary F1 | 64.68 |
| Our pooled macro F1 | 78.14 |

Interpretation: T1–T2 gap is largely **macro (fold) vs binary (pooled)** under class imbalance, not necessarily a training bug.