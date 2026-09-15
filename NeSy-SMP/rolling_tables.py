"""Sepsis 사망 예측 — 시점(window) 단위 설계 학습·평가.

입력: data/make_rolling_windows.py 가 만든 .pt (+ .meta.csv)

두 설계를 같은 환자 분할(subject 단위 70/15/15)에서 돌린다.
  rolling  : 모든 예측 시점. 타깃 = t 이후 horizon 안 원내 사망.
  paperlike: 원본식 샘플링 대조군. 입원당 1개 — 사망자는 사망 lead h 이상 전의 마지막 시점,
             생존자는 무작위 시점. 타깃 = 원내 사망. (같은 창·같은 변수, 샘플링만 원본식)

paperlike 로 학습한 모델은 rolling test 에서도 평가한다 — 원본식으로 학습한 모델이 실제 시점 예측에서 어떤지.

모델은 reproduce_tables.py 와 같다 (RF · XGBoost · BiLSTM · LTN · NeSy-SMP).
양성률이 낮아 checkpoint 는 val AUPRC 로 고른다 (--select). 주 지표는 AUROC · AUPRC.

사용:
  python rolling_tables.py --data C:/data/mimic-iv-derived/rolling_s3_icd_s12_h24.pt --out-dir results_rolling_s12_h24
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score
from torch.utils.data import DataLoader, Dataset
from xgboost import XGBClassifier

from data.dataset import ModelConfig
from reproduce_tables import predict_loader, set_seed, train_bilstm, train_ltn_variant

MODELS = ["RF", "XGBoost", "BiLSTM", "LTN", "NeSy-SMP"]


class TensorSet(Dataset):
    def __init__(self, X, y, ids):
        self.X, self.y, self.ids = X, y.float(), ids

    def __len__(self):
        return len(self.y)

    def __getitem__(self, i):
        return self.X[i], self.y[i], int(self.ids[i])


def flat_features(X, F, L):
    """reproduce_tables.flat_xy 와 같다: 범주 4열 제외, 변수별 0 제외 평균·표준편차(모표준편차)."""
    seq = X[:, : F * L].reshape(-1, F, L)[:, 4:, :]
    nz = (seq != 0).float()
    cnt = nz.sum(2)
    mean = (seq * nz).sum(2) / cnt.clamp(min=1)
    var = ((seq - mean.unsqueeze(2)) ** 2 * nz).sum(2) / cnt.clamp(min=1)
    mean = torch.where(cnt > 0, mean, torch.zeros_like(mean))
    std = torch.where(cnt > 0, var.sqrt(), torch.zeros_like(var))
    return torch.cat([mean, std], 1).numpy()


def split_subjects(meta, seed):
    subj = np.array(sorted(meta.subject_id.unique()))
    rng = np.random.default_rng(seed)
    rng.shuffle(subj)
    n = len(subj)
    tr, va = set(subj[: int(0.7 * n)]), set(subj[int(0.7 * n): int(0.85 * n)])
    return np.where(meta.subject_id.isin(tr), "train", np.where(meta.subject_id.isin(va), "val", "test"))


def paperlike_rows(meta, lead, seed):
    rng = np.random.default_rng(seed)
    pick = []
    for hadm, g in meta.groupby("hadm_id", sort=False):
        if g.hospital_expire_flag.iloc[0] == 1:
            ok = g[g.hours_to_death >= lead]
            if len(ok):
                pick.append(ok.t_h.idxmax())
        else:
            pick.append(rng.choice(g.index.to_numpy()))
    return np.array(sorted(pick))


def evaluate(y, prob):
    y = np.asarray(y)
    pred = (prob >= 0.5).astype(int)
    return {
        "n": len(y), "pos_rate": 100 * y.mean(),
        "AUROC": 100 * roc_auc_score(y, prob), "AUPRC": 100 * average_precision_score(y, prob),
        "F1_macro@0.5": 100 * f1_score(y, pred, average="macro", zero_division=0),
    }


def stay_level(meta_te, prob, val_neg_prob):
    """입원 단위: 최고 위험 점수 AUROC, val 음성 90% 분위 임계값 경보의 민감도·생존자 경보율·첫 경보~사망 시간."""
    d = meta_te.assign(p=prob)
    s = d.groupby("hadm_id").agg(p=("p", "max"), died=("hospital_expire_flag", "first"))
    thr = float(np.quantile(val_neg_prob, 0.90))
    d["alarm"] = d.p >= thr
    died = d[d.hospital_expire_flag == 1]
    first = died[died.alarm].groupby("hadm_id").t_h.min()
    death_h = died.groupby("hadm_id").apply(lambda g: (g.t_h + g.hours_to_death).iloc[0])
    lead = (death_h.reindex(first.index) - first)
    surv = d[d.hospital_expire_flag == 0].groupby("hadm_id").alarm.any()
    return {
        "stay_AUROC(max p)": 100 * roc_auc_score(s.died, s.p),
        "alarm_thr(val neg p90)": thr,
        "died_stays_alarmed%": 100 * died.groupby("hadm_id").alarm.any().mean(),
        "survivor_stays_alarmed%": 100 * surv.mean(),
        "median_h_first_alarm_to_death": float(lead.median()) if len(lead) else float("nan"),
    }


def run_models(tag, X, y, ids, idx_tr, idx_va, idx_te, d, args, device, extra_eval=None):
    F, L = len(d["feature_names"]), d["sequence_length"]
    fn, vocab, scalers = d["feature_names"], d["vocab_sizes"], d["scalers"]
    config = ModelConfig(hidden_size=128, num_layers=2, sequence_length=L, dropout_rate=0.1,
                         learning_rate=0.001, num_epochs=args.epochs)
    out = {}

    def loader(idx, shuffle):
        return DataLoader(TensorSet(X[idx], y[idx], ids[idx]), batch_size=args.batch_size, shuffle=shuffle)

    tr_l, va_l, te_l = loader(idx_tr, True), loader(idx_va, False), loader(idx_te, False)
    extra_l = {k: loader(v, False) for k, v in (extra_eval or {}).items()}

    Xf = flat_features(X, F, L)
    for name, mk in [
        ("RF", lambda: RandomForestClassifier(n_estimators=100, max_depth=10, random_state=args.seed, n_jobs=-1)),
        ("XGBoost", lambda: XGBClassifier(use_label_encoder=False, eval_metric="logloss", random_state=args.seed, n_jobs=-1)),
    ]:
        m = mk().fit(Xf[idx_tr], y[idx_tr].numpy())
        out[name] = {"val": m.predict_proba(Xf[idx_va])[:, 1], "test": m.predict_proba(Xf[idx_te])[:, 1],
                     **{k: m.predict_proba(Xf[v])[:, 1] for k, v in (extra_eval or {}).items()}}
        print(f"[{tag}] {name} test AUROC {100 * roc_auc_score(y[idx_te].numpy(), out[name]['test']):.2f}", flush=True)

    def dl_probs(model):
        r = {"val": predict_loader(model, va_l, device)[2], "test": predict_loader(model, te_l, device)[2]}
        r.update({k: predict_loader(model, l, device)[2] for k, l in extra_l.items()})
        return r

    set_seed(args.seed)
    out["BiLSTM"] = dl_probs(train_bilstm(tr_l, va_l, vocab, config, fn, device, select=args.select))
    set_seed(args.seed)
    out["LTN"] = dl_probs(train_ltn_variant(tr_l, va_l, vocab, config, fn, scalers, L, device, args.epochs_nesy,
                                            False, args.kb, args.select))
    set_seed(args.seed)
    out["NeSy-SMP"] = dl_probs(train_ltn_variant(tr_l, va_l, vocab, config, fn, scalers, L, device, args.epochs_nesy,
                                                 True, args.kb, args.select))
    for name in ["BiLSTM", "LTN", "NeSy-SMP"]:
        print(f"[{tag}] {name} test AUROC {100 * roc_auc_score(y[idx_te].numpy(), out[name]['test']):.2f}", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--epochs-nesy", type=int, default=15)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--select", choices=["f1", "auprc"], default="auprc")
    ap.add_argument("--kb", choices=["simple", "upstream"], default="upstream")
    ap.add_argument("--paper-lead", type=float, default=6.0, help="대조군 사망자 창: 사망 몇 h 이상 전")
    ap.add_argument("--skip-paperlike", action="store_true")
    args = ap.parse_args()

    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    d = torch.load(args.data, weights_only=False)
    meta = pd.read_csv(args.data.with_suffix(".meta.csv"))
    X, y = d["X"], d["y"].long()
    ids = np.arange(len(meta))
    assert len(meta) == len(X)
    meta["split"] = split_subjects(meta, args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    print(f"device {device} | instances {len(meta):,} | L={d['sequence_length']} | build {d['args']}")
    for s in ["train", "val", "test"]:
        g = meta[meta.split == s]
        print(f"  {s}: inst {len(g):,} stays {g.hadm_id.nunique():,} subj {g.subject_id.nunique():,} pos {g.y.mean():.2%}")

    rows, preds = [], []
    idx = {s: np.where(meta.split == s)[0] for s in ["train", "val", "test"]}
    val_neg = {}

    # ---- rolling ----
    res = run_models("rolling", X, y, ids, idx["train"], idx["val"], idx["test"], d, args, device)
    mte = meta.iloc[idx["test"]].reset_index(drop=True)
    for mname in MODELS:
        p_te, p_va = res[mname]["test"], res[mname]["val"]
        neg = p_va[meta.y.to_numpy()[idx["val"]] == 0]
        rows.append({"design": "rolling", "train_on": "rolling", "model": mname,
                     **evaluate(mte.y, p_te), **stay_level(mte, p_te, neg)})
        preds.append(mte[["inst", "hadm_id", "subject_id", "t_h", "y", "hours_to_death"]].assign(
            design="rolling", model=mname, prob=p_te))

    # ---- paperlike 대조군 ----
    if not args.skip_paperlike:
        pick = paperlike_rows(meta, args.paper_lead, seed=32)
        pm = meta.loc[pick]
        yp = torch.tensor(pm.hospital_expire_flag.to_numpy())
        y2 = y.clone()
        y2[pick] = yp
        pidx = {s: pick[pm.split.to_numpy() == s] for s in ["train", "val", "test"]}
        print(f"paperlike: stays {len(pick):,} mortality {pm.hospital_expire_flag.mean():.2%}")
        res = run_models("paperlike", X, y2, ids, pidx["train"], pidx["val"], pidx["test"], d, args, device,
                         extra_eval={"rolling_test": idx["test"]})
        pte = meta.loc[pidx["test"]].reset_index(drop=True)
        for mname in MODELS:
            rows.append({"design": "paperlike", "train_on": "paperlike", "model": mname,
                         **evaluate(pte.hospital_expire_flag, res[mname]["test"])})
            p_roll = res[mname]["rolling_test"]
            neg = res[mname]["val"][pm.set_index(pm.index).loc[pidx["val"]].hospital_expire_flag.to_numpy() == 0]
            rows.append({"design": "rolling", "train_on": "paperlike", "model": mname,
                         **evaluate(mte.y, p_roll), **stay_level(mte, p_roll, neg)})
            preds.append(pte[["inst", "hadm_id", "subject_id", "t_h", "hospital_expire_flag", "hours_to_death"]]
                         .rename(columns={"hospital_expire_flag": "y"}).assign(design="paperlike", model=mname,
                                                                                 prob=res[mname]["test"]))

    tab = pd.DataFrame(rows)
    tab.to_csv(args.out_dir / "metrics.csv", index=False)
    pd.concat(preds).to_csv(args.out_dir / "test_predictions.csv", index=False)
    with open(args.out_dir / "RESULTS.md", "w", encoding="utf-8") as f:
        f.write(f"# Sepsis 시점 단위 결과\n\n데이터 `{args.data.name}` · build {d['args']}\n\n")
        f.write(f"seed {args.seed} · epochs {args.epochs}/{args.epochs_nesy} · select {args.select} · kb {args.kb} · "
                f"환자 단위 70/15/15\n\n")
        cols = [c for c in tab.columns if c not in ("design", "train_on", "model")]
        for (des, tr), g in tab.groupby(["design", "train_on"], sort=False):
            f.write(f"## 평가 {des} · 학습 {tr}\n\n| model | " + " | ".join(cols) + " |\n|---|" + "---:|" * len(cols) + "\n")
            for _, r in g.iterrows():
                f.write(f"| {r.model} | " + " | ".join("" if pd.isna(r[c]) else f"{r[c]:.2f}" for c in cols) + " |\n")
            f.write("\n")
    print(tab.to_string())
    print(f"-> {args.out_dir}")


if __name__ == "__main__":
    main()
