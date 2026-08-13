"""Phase-3 Table 1 (fold macro mean±std) + Table 2 (pooled OOF bootstrap).

Mirrors stratified_main.py APIs (LSTMModel, SepsisDataset, LTN predicates).
"""
from __future__ import annotations

import argparse
import math
import random
import statistics
from pathlib import Path

import ltn
import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from torch.utils.data import DataLoader
from xgboost import XGBClassifier

from data.dataset import ModelConfig, SepsisDataset
from data.preprocessing import preprocess_eventlog
from model.models import LSTMModel, MLP, SimpleMLP, SimpleMLPAge

PAPER_T1 = {
    "RF": {"Acc": 84.78, "F1": 74.77, "Prec": 83.07, "Rec": 71.48, "AUC": 88.11},
    "XGBoost": {"Acc": 85.31, "F1": 77.86, "Prec": 80.90, "Rec": 75.86, "AUC": 88.56},
    "BiLSTM": {"Acc": 83.53, "F1": 76.82, "Prec": 77.91, "Rec": 76.22, "AUC": 85.35},
    "LTN": {"Acc": 85.65, "F1": 79.20, "Prec": 80.63, "Rec": 78.06, "AUC": 88.10},
    "NeSy-SMP": {"Acc": 86.45, "F1": 80.35, "Prec": 81.86, "Rec": 79.14, "AUC": 88.33},
}
PAPER_T2_NESY_F1 = 68.51


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def mean_excluding_zeros(values):
    nz = [v for v in values if v != 0.0]
    return sum(nz) / len(nz) if nz else 0.0


def std_excluding_zeros(values):
    nz = [v for v in values if v != 0.0]
    if not nz:
        return 0.0
    m = sum(nz) / len(nz)
    return math.sqrt(sum((v - m) ** 2 for v in nz) / len(nz))


def flat_xy(Xs, ys):
    Xf, yf = [], []
    for x, y in zip(Xs, ys):
        feats = [lst for i, lst in enumerate(x[0]) if i not in (0, 1, 2, 3)]
        feats = [mean_excluding_zeros(lst) for lst in feats] + [std_excluding_zeros(lst) for lst in feats]
        Xf.append(np.array(feats))
        yf.append(y)
    return np.asarray(Xf), np.asarray(yf)


def metric_bundle(y_true, y_pred, y_prob, average="macro"):
    return {
        "Acc": 100 * accuracy_score(y_true, y_pred),
        "F1": 100 * f1_score(y_true, y_pred, average=average, zero_division=0),
        "Prec": 100 * precision_score(y_true, y_pred, average=average, zero_division=0),
        "Rec": 100 * recall_score(y_true, y_pred, average=average, zero_division=0),
        "AUC": 100 * roc_auc_score(y_true, y_prob),
    }


@torch.no_grad()
def predict_loader(model, loader, device):
    model.eval()
    y_true, y_pred, y_prob, hadms = [], [], [], []
    for x, y, c_id in loader:
        x = x.to(device)
        out = model(x).detach().cpu().numpy().reshape(-1)
        pred = (out > 0.5).astype(float)
        for i in range(len(y)):
            y_true.append(float(y[i]))
            y_pred.append(pred[i])
            y_prob.append(float(out[i]))
            hadms.append(c_id[i])
    return np.asarray(y_true), np.asarray(y_pred), np.asarray(y_prob), hadms


def train_bilstm(train_loader, val_loader, vocab_sizes, config, feature_names, device):
    model = LSTMModel(vocab_sizes, config, 1, feature_names).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    crit = torch.nn.BCELoss()
    best_f1, best_state, bad = -1.0, None, 0
    for epoch in range(config.num_epochs):
        model.train()
        losses = []
        for x, y, _ in train_loader:
            x = x.to(device)
            opt.zero_grad()
            out = model(x)
            loss = crit(out.squeeze(1).cpu(), y.float())
            loss.backward()
            opt.step()
            losses.append(loss.item())
        yt, yp, _, _ = predict_loader(model, val_loader, device)
        f1 = f1_score(yt, yp, average="macro", zero_division=0)
        print(f"  BiLSTM ep {epoch+1}/{config.num_epochs} loss={statistics.mean(losses):.4f} val_f1={f1:.4f}")
        if f1 > best_f1:
            best_f1 = f1
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            bad = 0
        else:
            bad += 1
            if epoch >= 10 and bad > 15:
                print("  BiLSTM early stop")
                break
    if best_state:
        model.load_state_dict(best_state)
    return model


def train_ltn_variant(
    train_loader,
    val_loader,
    vocab_sizes,
    config,
    feature_names,
    scalers,
    sequence_length,
    device,
    epochs_nesy,
    with_knowledge: bool,
):
    Forall = ltn.Quantifier(ltn.fuzzy_ops.AggregPMeanError(p=2), quantifier="f")
    Not = ltn.Connective(ltn.fuzzy_ops.NotStandard())
    Implies = ltn.Connective(ltn.fuzzy_ops.ImpliesReichenbach())
    SatAgg = ltn.fuzzy_ops.SatAgg()

    features_dict = {s: i for i, s in enumerate(feature_names, start=1)}
    lstm = LSTMModel(vocab_sizes, config, 1, feature_names).to(device)
    P = ltn.Predicate(lstm).to(device)

    model_lactate = MLP(sequence_length, 64).to(device)
    LactateRisk = ltn.Predicate(model_lactate).to(device)
    model_bil = MLP(sequence_length, 64).to(device)
    HighBilirubin = ltn.Predicate(model_bil).to(device)
    model_plt = MLP(sequence_length, 64).to(device)
    PlateletLow = ltn.Predicate(model_plt).to(device)
    model_map = MLP(sequence_length, 64).to(device)
    MAPRisk = ltn.Predicate(model_map).to(device)
    model_wbc = MLP(sequence_length, 64).to(device)
    WBCRisk = ltn.Predicate(model_wbc).to(device)
    model_crp = MLP(sequence_length, 64).to(device)
    CRPRisk = ltn.Predicate(model_crp).to(device)
    model_age = SimpleMLPAge(24, 64).to(device)  # age(1)+comorbidities(23)
    AgeRisk = ltn.Predicate(model_age).to(device)
    model_chr = SimpleMLP(23, 64).to(device)
    Chronic = ltn.Predicate(model_chr).to(device)

    params = list(lstm.parameters())
    for m in [model_lactate, model_bil, model_plt, model_map, model_wbc, model_crp, model_age, model_chr]:
        params += list(m.parameters())
    opt = torch.optim.Adam(params, lr=config.learning_rate)

    def feat(name):
        i = features_dict[name]
        return lambda x: x[:, (i * sequence_length - sequence_length) : (i * sequence_length)]

    lactate_f = ltn.Function(func=lambda x: feat("Lactate")(x))
    bil_f = ltn.Function(func=lambda x: feat("Total Bilirubin")(x))
    plt_f = ltn.Function(func=lambda x: feat("Platelet Count")(x))
    map_f = ltn.Function(func=lambda x: feat("Arterial Blood Pressure mean")(x))
    wbc_f = ltn.Function(func=lambda x: feat("White Blood Cells")(x))
    crp_f = ltn.Function(func=lambda x: feat("C-Reactive Protein")(x))
    age_s = ltn.Function(func=lambda x: feat("anchor_age")(x)[:, 0])
    como_f = ltn.Function(func=lambda x: x[:, -23:])

    thr = {
        "Lactate": scalers["Lactate"].transform([[4.0]])[0][0],
        "Total Bilirubin": scalers["Total Bilirubin"].transform([[2.0]])[0][0],
        "Platelet Count": scalers["Platelet Count"].transform([[50.0]])[0][0],
        "Arterial Blood Pressure mean": scalers["Arterial Blood Pressure mean"].transform([[65.0]])[0][0],
        "White Blood Cells": scalers["White Blood Cells"].transform([[12.0]])[0][0],
        "C-Reactive Protein": scalers["C-Reactive Protein"].transform([[100.0]])[0][0],
        "anchor_age": scalers["anchor_age"].transform([[65.0]])[0][0],
    }
    w_D, w_K = 0.8, 0.2
    best_f1, best_state = -1.0, None

    for epoch in range(epochs_nesy):
        lstm.train()
        train_loss = 0.0
        n_batches = 0
        for x, y, _ in train_loader:
            x = x.to(device)
            y = y.to(device)
            opt.zero_grad()
            x_D = ltn.Variable("x_D", x[y == 1])
            x_nD = ltn.Variable("x_not_D", x[y == 0])
            formulas = []
            if x_D.value.numel() > 0:
                formulas.append(Forall(x_D, P(x_D)).value)
            if x_nD.value.numel() > 0:
                formulas.append(Forall(x_nD, Not(P(x_nD)), p=6).value)
            if not formulas:
                continue
            sat_D = SatAgg(*formulas)
            if with_knowledge:
                know = []
                # Weak anchoring (D): threshold subset → Forall Pred(...)
                m = (feat("Lactate")(x) > thr["Lactate"]).all(dim=1)
                if m.any():
                    xv = ltn.Variable("x_lac", x[m])
                    know.append(Forall(xv, LactateRisk(lactate_f(xv), como_f(xv), age_s(xv))).value)
                m = (feat("Total Bilirubin")(x) >= thr["Total Bilirubin"]).any(dim=1)
                if m.any():
                    xv = ltn.Variable("x_bil", x[m])
                    know.append(Forall(xv, HighBilirubin(bil_f(xv), como_f(xv), age_s(xv))).value)
                m = ((feat("Platelet Count")(x) < thr["Platelet Count"]) & (feat("Platelet Count")(x) > 0)).any(dim=1)
                if m.any():
                    xv = ltn.Variable("x_plt", x[m])
                    know.append(Forall(xv, PlateletLow(plt_f(xv), como_f(xv), age_s(xv))).value)
                m = (feat("Arterial Blood Pressure mean")(x) < thr["Arterial Blood Pressure mean"]).any(dim=1)
                if m.any():
                    xv = ltn.Variable("x_map", x[m])
                    know.append(Forall(xv, MAPRisk(map_f(xv), como_f(xv), age_s(xv))).value)
                m = (feat("White Blood Cells")(x) > thr["White Blood Cells"]).any(dim=1)
                if m.any():
                    xv = ltn.Variable("x_wbc", x[m])
                    know.append(Forall(xv, WBCRisk(wbc_f(xv), como_f(xv), age_s(xv))).value)
                m = (feat("C-Reactive Protein")(x) > thr["C-Reactive Protein"]).any(dim=1)
                if m.any():
                    xv = ltn.Variable("x_crp", x[m])
                    know.append(Forall(xv, CRPRisk(crp_f(xv), como_f(xv), age_s(xv))).value)
                m = feat("anchor_age")(x)[:, 0] > thr["anchor_age"]
                if m.any():
                    xv = ltn.Variable("x_age", x[m])
                    know.append(Forall(xv, AgeRisk(age_s(xv), como_f(xv))).value)
                x_all = ltn.Variable("x_all", x)
                know.extend(
                    [
                        Forall(x_all, Implies(LactateRisk(lactate_f(x_all), como_f(x_all), age_s(x_all)), P(x_all))).value,
                        Forall(x_all, Implies(HighBilirubin(bil_f(x_all), como_f(x_all), age_s(x_all)), P(x_all))).value,
                        Forall(x_all, Implies(PlateletLow(plt_f(x_all), como_f(x_all), age_s(x_all)), P(x_all))).value,
                        Forall(x_all, Implies(MAPRisk(map_f(x_all), como_f(x_all), age_s(x_all)), P(x_all))).value,
                        Forall(x_all, Implies(WBCRisk(wbc_f(x_all), como_f(x_all), age_s(x_all)), P(x_all))).value,
                        Forall(x_all, Implies(AgeRisk(age_s(x_all), como_f(x_all)), P(x_all))).value,
                        Forall(x_all, Implies(Chronic(como_f(x_all)), P(x_all))).value,
                    ]
                )
                sat_K = SatAgg(*know) if know else sat_D
                loss = 1 - (w_D * sat_D + w_K * sat_K)
            else:
                loss = 1 - sat_D
            loss.backward()
            opt.step()
            train_loss += float(loss.detach().cpu())
            n_batches += 1
        yt, yp, _, _ = predict_loader(lstm, val_loader, device)
        f1 = f1_score(yt, yp, average="macro", zero_division=0)
        tag = "NeSy" if with_knowledge else "LTN"
        print(f"  {tag} ep {epoch+1}/{epochs_nesy} loss={train_loss/max(n_batches,1):.4f} val_f1={f1:.4f}")
        if f1 > best_f1:
            best_f1 = f1
            best_state = {k: v.detach().cpu().clone() for k, v in lstm.state_dict().items()}
    if best_state:
        lstm.load_state_dict(best_state)
    return lstm


def bootstrap_ci(y_true, y_pred, y_prob, n_boot=1000, seed=42):
    rng = np.random.default_rng(seed)
    rows = []
    n = len(y_true)
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        yt, yp, ypr = y_true[idx], y_pred[idx], y_prob[idx]
        if len(np.unique(yt)) < 2:
            continue
        rows.append(
            {
                **{f"bin_{k}": v for k, v in metric_bundle(yt, yp, ypr, "binary").items()},
                **{f"mac_{k}": v for k, v in metric_bundle(yt, yp, ypr, "macro").items()},
            }
        )
    df = pd.DataFrame(rows)
    return {
        c: {"mean": float(df[c].mean()), "lo": float(df[c].quantile(0.025)), "hi": float(df[c].quantile(0.975))}
        for c in df.columns
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=Path("results"))
    ap.add_argument("--seed", type=int, default=42)
    # Match stratified_main.py / GitHub defaults: BiLSTM 50, LTN/NeSy 20
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--epochs-nesy", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--skip-nesy", action="store_true")
    args = ap.parse_args()

    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    print("device", device)

    data = pd.read_csv(args.csv, dtype={"hadm_id": str, "subject_id": str}, low_memory=False)
    (X_all, y_all, feature_names), vocab_sizes, scalers, sequence_length = preprocess_eventlog(
        data, args.seed, False
    )
    y_all = list(y_all)
    print(f"n={len(y_all)} mort={np.mean(y_all):.3f} seq={sequence_length} n_feat={len(feature_names)}")

    config = ModelConfig(
        hidden_size=128,
        num_layers=2,
        sequence_length=sequence_length,
        dropout_rate=0.1,
        learning_rate=0.001,
        num_epochs=args.epochs,
    )
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=args.seed)
    fold_rows, oof_rows = [], []

    for fold, (tr, te) in enumerate(skf.split(np.zeros(len(y_all)), y_all), 1):
        print(f"\n===== Fold {fold}/5 =====")
        X_train = [X_all[i] for i in tr]
        X_test = [X_all[i] for i in te]
        y_train = [y_all[i] for i in tr]
        y_test = [y_all[i] for i in te]
        X_train, X_val, y_train, y_val = train_test_split(
            X_train, y_train, test_size=0.2, stratify=y_train, random_state=args.seed
        )

        Xtr, ytr = flat_xy(X_train, y_train)
        Xte, yte = flat_xy(X_test, y_test)

        rf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=args.seed, n_jobs=-1)
        rf.fit(Xtr, ytr)
        prob = rf.predict_proba(Xte)[:, 1]
        pred = (prob >= 0.5).astype(int)
        m = metric_bundle(yte, pred, prob, "macro")
        fold_rows.append({"fold": fold, "model": "RF", **m})
        for i in range(len(yte)):
            oof_rows.append(
                {"fold": fold, "model": "RF", "hadm_id": X_test[i][2], "y_true": int(yte[i]), "y_prob": float(prob[i]), "y_pred": int(pred[i])}
            )

        xgb = XGBClassifier(use_label_encoder=False, eval_metric="logloss", random_state=args.seed, n_jobs=-1)
        xgb.fit(Xtr, ytr)
        prob = xgb.predict_proba(Xte)[:, 1]
        pred = (prob >= 0.5).astype(int)
        m = metric_bundle(yte, pred, prob, "macro")
        fold_rows.append({"fold": fold, "model": "XGBoost", **m})
        for i in range(len(yte)):
            oof_rows.append(
                {
                    "fold": fold,
                    "model": "XGBoost",
                    "hadm_id": X_test[i][2],
                    "y_true": int(yte[i]),
                    "y_prob": float(prob[i]),
                    "y_pred": int(pred[i]),
                }
            )

        train_loader = DataLoader(SepsisDataset(X_train, y_train, feature_names), batch_size=args.batch_size, shuffle=True)
        val_loader = DataLoader(SepsisDataset(X_val, y_val, feature_names), batch_size=args.batch_size)
        test_loader = DataLoader(SepsisDataset(X_test, y_test, feature_names), batch_size=args.batch_size)

        bilstm = train_bilstm(train_loader, val_loader, vocab_sizes, config, feature_names, device)
        yt, yp, ypr, hadms = predict_loader(bilstm, test_loader, device)
        m = metric_bundle(yt, yp, ypr, "macro")
        fold_rows.append({"fold": fold, "model": "BiLSTM", **m})
        for i in range(len(yt)):
            oof_rows.append(
                {"fold": fold, "model": "BiLSTM", "hadm_id": hadms[i], "y_true": int(yt[i]), "y_prob": float(ypr[i]), "y_pred": int(yp[i])}
            )

        if not args.skip_nesy:
            ltn_m = train_ltn_variant(
                train_loader, val_loader, vocab_sizes, config, feature_names, scalers, sequence_length, device, args.epochs_nesy, False
            )
            yt, yp, ypr, hadms = predict_loader(ltn_m, test_loader, device)
            m = metric_bundle(yt, yp, ypr, "macro")
            fold_rows.append({"fold": fold, "model": "LTN", **m})
            for i in range(len(yt)):
                oof_rows.append(
                    {"fold": fold, "model": "LTN", "hadm_id": hadms[i], "y_true": int(yt[i]), "y_prob": float(ypr[i]), "y_pred": int(yp[i])}
                )

            nesy = train_ltn_variant(
                train_loader, val_loader, vocab_sizes, config, feature_names, scalers, sequence_length, device, args.epochs_nesy, True
            )
            yt, yp, ypr, hadms = predict_loader(nesy, test_loader, device)
            m = metric_bundle(yt, yp, ypr, "macro")
            fold_rows.append({"fold": fold, "model": "NeSy-SMP", **m})
            for i in range(len(yt)):
                oof_rows.append(
                    {
                        "fold": fold,
                        "model": "NeSy-SMP",
                        "hadm_id": hadms[i],
                        "y_true": int(yt[i]),
                        "y_prob": float(ypr[i]),
                        "y_pred": int(yp[i]),
                    }
                )

    fold_df = pd.DataFrame(fold_rows)
    oof_df = pd.DataFrame(oof_rows)
    fold_df.to_csv(args.out_dir / "table1_fold_metrics.csv", index=False)
    oof_df.to_csv(args.out_dir / "oof_predictions.csv", index=False)

    t1_rows = []
    for model, g in fold_df.groupby("model"):
        row = {"model": model}
        for mname in ["Acc", "F1", "Prec", "Rec", "AUC"]:
            row[f"{mname}_mean"] = g[mname].mean()
            row[f"{mname}_std"] = g[mname].std(ddof=0)
            if model in PAPER_T1:
                row[f"{mname}_paper"] = PAPER_T1[model][mname]
                row[f"{mname}_diff"] = row[f"{mname}_mean"] - PAPER_T1[model][mname]
        t1_rows.append(row)
    t1 = pd.DataFrame(t1_rows)
    t1.to_csv(args.out_dir / "table1_summary.csv", index=False)

    t2_rows = []
    for model, g in oof_df.groupby("model"):
        yt, yp, ypr = g["y_true"].to_numpy(), g["y_pred"].to_numpy(), g["y_prob"].to_numpy()
        point_bin = metric_bundle(yt, yp, ypr, "binary")
        point_mac = metric_bundle(yt, yp, ypr, "macro")
        boot = bootstrap_ci(yt, yp, ypr, 1000, args.seed)
        t2_rows.append(
            {
                "model": model,
                **{f"point_bin_{k}": v for k, v in point_bin.items()},
                **{f"point_mac_{k}": v for k, v in point_mac.items()},
                **{f"boot_{k}_mean": v["mean"] for k, v in boot.items()},
                **{f"boot_{k}_lo": v["lo"] for k, v in boot.items()},
                **{f"boot_{k}_hi": v["hi"] for k, v in boot.items()},
            }
        )
    t2 = pd.DataFrame(t2_rows)
    t2.to_csv(args.out_dir / "table2_bootstrap.csv", index=False)

    lines = [
        "# Phase 3 — Table 1 vs Table 2 Reproduction",
        "",
        f"- CSV: `{args.csv}`",
        f"- seed={args.seed}, epochs={args.epochs}/{args.epochs_nesy}, device={device}",
        f"- n={len(y_all)}, mortality={np.mean(y_all):.1%}, seq_window={sequence_length}",
        "- comorbidities: **zeros** (notes NLP not merged yet)",
        "",
        "## Code grounding",
        "",
        "| Question | Finding | Location |",
        "|---|---|---|",
        "| Weak anchoring | **D**: FOL Forall on threshold subsets (not init / not MSE) | `reproduce_tables.py` + `stratified_main.py:519-648` |",
        "| w_D / w_K | Hardcoded **0.8 / 0.2** train loss | `reproduce_tables.py`; `stratified_main.py:539-540` |",
        "| Risk MLP input | concept seq + comorbidities(23) + age | `model/models.py` MLP.forward |",
        "| Survivor window seed | Fixed seed=32 in `make_leadtime_csvs.py` (upstream extract_before_death unseeded) | |",
        "| Table 1 | fold macro mean±std | this script |",
        "| Table 2 | pooled OOF + 1000 bootstrap (binary & macro) | this script |",
        "",
        "## Table 1 (5-fold macro) vs Paper",
        "",
        "| Model | Metric | Paper | Reproduced | Diff |",
        "|---|---|---:|---:|---:|",
    ]
    for _, r in t1.iterrows():
        for mname in ["Acc", "F1", "Prec", "Rec", "AUC"]:
            paper = r.get(f"{mname}_paper", float("nan"))
            lines.append(
                f"| {r['model']} | {mname} | {paper:.2f} | {r[f'{mname}_mean']:.2f}±{r[f'{mname}_std']:.2f} | {r.get(f'{mname}_diff', float('nan')):+.2f} |"
            )
    lines += ["", "## Table 2 pooled OOF (binary vs macro + bootstrap)", ""]
    for _, r in t2.iterrows():
        lines += [
            f"### {r['model']}",
            f"- point binary F1={r['point_bin_F1']:.2f} | pooled macro F1={r['point_mac_F1']:.2f}",
            f"- boot binary F1 {r['boot_bin_F1_mean']:.2f} [{r['boot_bin_F1_lo']:.2f}, {r['boot_bin_F1_hi']:.2f}]",
            f"- boot macro F1 {r['boot_mac_F1_mean']:.2f} [{r['boot_mac_F1_lo']:.2f}, {r['boot_mac_F1_hi']:.2f}]",
            "",
        ]
    if (t2["model"] == "NeSy-SMP").any() and (t1["model"] == "NeSy-SMP").any():
        nesy = t2[t2["model"] == "NeSy-SMP"].iloc[0]
        t1n = t1[t1["model"] == "NeSy-SMP"].iloc[0]
        lines += [
            "## NeSy-SMP T1 vs T2 discrepancy",
            "",
            f"| | Value |",
            f"|---|---:|",
            f"| Paper T1 F1 (macro fold) | {PAPER_T1['NeSy-SMP']['F1']:.2f} |",
            f"| Paper T2 F1 | {PAPER_T2_NESY_F1:.2f} |",
            f"| Our T1 F1 (macro fold mean) | {t1n['F1_mean']:.2f} |",
            f"| Our pooled binary F1 | {nesy['point_bin_F1']:.2f} |",
            f"| Our pooled macro F1 | {nesy['point_mac_F1']:.2f} |",
            "",
            "Interpretation: T1–T2 gap is largely **macro (fold) vs binary (pooled)** under class imbalance, not necessarily a training bug.",
        ]
    (args.out_dir / "RESULTS_TABLE1_TABLE2.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", args.out_dir / "RESULTS_TABLE1_TABLE2.md")


if __name__ == "__main__":
    main()
