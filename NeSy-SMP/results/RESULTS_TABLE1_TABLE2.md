# Phase 3 — Table 1 vs Table 2 Reproduction

- CSV: `C:\data\mimic-iv-derived\events_6h_wide.csv`
- seed=42, epochs=30/15, device=cuda
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
| BiLSTM | Acc | 83.53 | 86.28±0.51 | +2.75 |
| BiLSTM | F1 | 76.82 | 81.72±0.75 | +4.90 |
| BiLSTM | Prec | 77.91 | 82.87±0.68 | +4.96 |
| BiLSTM | Rec | 76.22 | 80.80±0.90 | +4.58 |
| BiLSTM | AUC | 85.35 | 89.37±1.13 | +4.02 |
| LTN | Acc | 85.65 | 85.93±0.69 | +0.28 |
| LTN | F1 | 79.20 | 81.45±1.23 | +2.25 |
| LTN | Prec | 80.63 | 82.27±1.03 | +1.64 |
| LTN | Rec | 78.06 | 80.94±1.96 | +2.88 |
| LTN | AUC | 88.10 | 89.24±1.19 | +1.14 |
| NeSy-SMP | Acc | 86.45 | 85.95±0.73 | -0.50 |
| NeSy-SMP | F1 | 80.35 | 81.54±0.98 | +1.19 |
| NeSy-SMP | Prec | 81.86 | 82.18±1.10 | +0.32 |
| NeSy-SMP | Rec | 79.14 | 81.04±1.23 | +1.90 |
| NeSy-SMP | AUC | 88.33 | 89.15±1.18 | +0.82 |
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
- point binary F1=72.60 | pooled macro F1=81.73
- boot binary F1 72.63 [71.17, 74.07]
- boot macro F1 81.75 [80.86, 82.67]

### LTN
- point binary F1=72.44 | pooled macro F1=81.50
- boot binary F1 72.45 [71.12, 73.87]
- boot macro F1 81.50 [80.62, 82.44]

### NeSy-SMP
- point binary F1=72.54 | pooled macro F1=81.55
- boot binary F1 72.55 [71.16, 73.92]
- boot macro F1 81.56 [80.66, 82.48]

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
| Our T1 F1 (macro fold mean) | 81.54 |
| Our pooled binary F1 | 72.54 |
| Our pooled macro F1 | 81.55 |

Interpretation: T1–T2 gap is largely **macro (fold) vs binary (pooled)** under class imbalance, not necessarily a training bug.