# Phase 3 — Table 1 vs Table 2 Reproduction

- CSV: `C:\data\mimic-iv-derived\events_6h_wide_s3.csv`
- seed=42, epochs=50/20, device=cuda
- n=18887, mortality=18.6%, seq_window=230
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
| BiLSTM | Acc | 83.53 | 90.03±0.73 | +6.50 |
| BiLSTM | F1 | 76.82 | 83.03±1.01 | +6.21 |
| BiLSTM | Prec | 77.91 | 84.29±1.71 | +6.38 |
| BiLSTM | Rec | 76.22 | 81.97±0.72 | +5.75 |
| BiLSTM | AUC | 85.35 | 92.23±0.57 | +6.88 |
| LTN | Acc | 85.65 | 90.05±0.57 | +4.40 |
| LTN | F1 | 79.20 | 82.81±0.71 | +3.61 |
| LTN | Prec | 80.63 | 84.64±1.44 | +4.01 |
| LTN | Rec | 78.06 | 81.33±0.50 | +3.27 |
| LTN | AUC | 88.10 | 92.27±0.58 | +4.17 |
| NeSy-SMP | Acc | 86.45 | 89.71±0.46 | +3.26 |
| NeSy-SMP | F1 | 80.35 | 82.88±0.60 | +2.53 |
| NeSy-SMP | Prec | 81.86 | 83.22±0.96 | +1.36 |
| NeSy-SMP | Rec | 79.14 | 82.57±0.34 | +3.43 |
| NeSy-SMP | AUC | 88.33 | 92.27±0.42 | +3.94 |
| RF | Acc | 84.78 | 89.17±0.34 | +4.39 |
| RF | F1 | 74.77 | 78.27±0.70 | +3.50 |
| RF | Prec | 83.07 | 88.25±1.02 | +5.18 |
| RF | Rec | 71.48 | 73.78±0.65 | +2.30 |
| RF | AUC | 88.11 | 91.49±0.52 | +3.38 |
| XGBoost | Acc | 85.31 | 90.13±0.26 | +4.82 |
| XGBoost | F1 | 77.86 | 82.36±0.38 | +4.50 |
| XGBoost | Prec | 80.90 | 85.65±0.69 | +4.75 |
| XGBoost | Rec | 75.86 | 79.96±0.33 | +4.10 |
| XGBoost | AUC | 88.56 | 92.87±0.31 | +4.31 |

## Table 2 pooled OOF (binary vs macro + bootstrap)

### BiLSTM
- point binary F1=72.10 | pooled macro F1=83.02
- boot binary F1 72.08 [70.85, 73.18]
- boot macro F1 83.01 [82.31, 83.66]

### LTN
- point binary F1=71.64 | pooled macro F1=82.80
- boot binary F1 71.64 [70.31, 72.81]
- boot macro F1 82.81 [82.03, 83.51]

### NeSy-SMP
- point binary F1=72.06 | pooled macro F1=82.88
- boot binary F1 72.06 [70.83, 73.26]
- boot macro F1 82.88 [82.15, 83.57]

### RF
- point binary F1=62.89 | pooled macro F1=78.28
- boot binary F1 62.90 [61.32, 64.34]
- boot macro F1 78.29 [77.38, 79.11]

### XGBoost
- point binary F1=70.64 | pooled macro F1=82.35
- boot binary F1 70.66 [69.46, 71.91]
- boot macro F1 82.37 [81.65, 83.09]

## NeSy-SMP T1 vs T2 discrepancy

| | Value |
|---|---:|
| Paper T1 F1 (macro fold) | 80.35 |
| Paper T2 F1 | 68.51 |
| Our T1 F1 (macro fold mean) | 82.88 |
| Our pooled binary F1 | 72.06 |
| Our pooled macro F1 | 82.88 |

Interpretation: T1–T2 gap is largely **macro (fold) vs binary (pooled)** under class imbalance, not necessarily a training bug.