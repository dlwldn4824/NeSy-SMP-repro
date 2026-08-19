# Phase 3 — Table 1 vs Table 2 Reproduction

- CSV: `C:\data\mimic-iv-derived\events_6h_wide.csv`
- seed=42, epochs=50/20, device=cuda
- n=9959, mortality=26.2%, seq_window=230
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
| BiLSTM | Acc | 83.53 | 86.27±0.59 | +2.74 |
| BiLSTM | F1 | 76.82 | 81.78±0.80 | +4.96 |
| BiLSTM | Prec | 77.91 | 82.78±0.83 | +4.87 |
| BiLSTM | Rec | 76.22 | 80.95±0.87 | +4.73 |
| BiLSTM | AUC | 85.35 | 89.17±1.16 | +3.82 |
| LTN | Acc | 85.65 | 86.07±0.53 | +0.42 |
| LTN | F1 | 79.20 | 81.68±0.75 | +2.48 |
| LTN | Prec | 80.63 | 82.34±0.78 | +1.71 |
| LTN | Rec | 78.06 | 81.13±1.00 | +3.07 |
| LTN | AUC | 88.10 | 89.37±1.11 | +1.27 |
| NeSy-SMP | Acc | 86.45 | 85.70±0.65 | -0.75 |
| NeSy-SMP | F1 | 80.35 | 81.45±0.84 | +1.10 |
| NeSy-SMP | Prec | 81.86 | 81.73±1.18 | -0.13 |
| NeSy-SMP | Rec | 79.14 | 81.36±1.41 | +2.22 |
| NeSy-SMP | AUC | 88.33 | 88.96±1.02 | +0.63 |
| RF | Acc | 84.78 | 86.28±0.68 | +1.50 |
| RF | F1 | 74.77 | 79.85±1.08 | +5.08 |
| RF | Prec | 83.07 | 86.31±1.24 | +3.24 |
| RF | Rec | 71.48 | 76.78±1.05 | +5.30 |
| RF | AUC | 88.11 | 90.28±0.99 | +2.17 |
| XGBoost | Acc | 85.31 | 87.36±0.78 | +2.05 |
| XGBoost | F1 | 77.86 | 82.75±1.08 | +4.89 |
| XGBoost | Prec | 80.90 | 85.03±1.20 | +4.13 |
| XGBoost | Rec | 75.86 | 81.13±1.14 | +5.27 |
| XGBoost | AUC | 88.56 | 91.40±0.60 | +2.84 |

## Table 2 pooled OOF (binary vs macro + bootstrap)

### BiLSTM
- point binary F1=72.73 | pooled macro F1=81.78
- boot binary F1 72.75 [71.28, 74.24]
- boot macro F1 81.79 [80.84, 82.77]

### LTN
- point binary F1=72.72 | pooled macro F1=81.69
- boot binary F1 72.75 [71.37, 74.19]
- boot macro F1 81.70 [80.82, 82.58]

### NeSy-SMP
- point binary F1=72.62 | pooled macro F1=81.47
- boot binary F1 72.63 [71.29, 74.01]
- boot macro F1 81.48 [80.61, 82.39]

### RF
- point binary F1=68.48 | pooled macro F1=79.86
- boot binary F1 68.45 [66.90, 70.01]
- boot macro F1 79.84 [78.91, 80.84]

### XGBoost
- point binary F1=73.85 | pooled macro F1=82.76
- boot binary F1 73.85 [72.56, 75.23]
- boot macro F1 82.76 [81.94, 83.64]

## NeSy-SMP T1 vs T2 discrepancy

| | Value |
|---|---:|
| Paper T1 F1 (macro fold) | 80.35 |
| Paper T2 F1 | 68.51 |
| Our T1 F1 (macro fold mean) | 81.45 |
| Our pooled binary F1 | 72.62 |
| Our pooled macro F1 | 81.47 |

Interpretation: T1–T2 gap is largely **macro (fold) vs binary (pooled)** under class imbalance, not necessarily a training bug.