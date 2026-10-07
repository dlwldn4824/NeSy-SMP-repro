# -*- coding: utf-8 -*-
"""[실험 D5] 원본 패혈증 코드에서 지식 공리가 사망 예측까지 닿는지 gradient 로 재는 감사 스크립트.

학습은 하지 않는다. 이미 학습된 체크포인트(`ltn_w_k.pth`)를 올리고, 원본 코드가 만드는 공리를
**그대로** 재구성해 공리별로 backward 를 한 번씩 돌려 다음을 센다.

  1) ||∂(공리 만족도) / ∂θ_P||   — 사망 예측 모델(LSTM, 원본에서 `P = ltn.Predicate(lstm)`) 로 가는 gradient
  2) ||∂(공리 만족도) / ∂θ_own|| — 그 공리의 위험 술어 MLP 로 가는 gradient
  3) 데이터 공리(∀x⁺ P · ∀x⁻ ¬P) 의 θ_P gradient — 비교 기준
  4) 논문 손실 1 − (0.8·SatAgg(D) + 0.2·SatAgg(K)) 에서 지식 항이 θ_P 에 주는 몫

읽는 방법 — Anchor 공리(조건 → 위험 술어)는 머리가 위험 술어이므로 θ_P gradient 가 **구조적으로 0** 이고,
Implication 공리(위험 술어 → P)만 θ_P 로 흐른다. 섬망 쪽 eda/38 과 같은 질문을 원저자 코드에서 재는 것이다.

한 가지 한계 — 원본 코드는 **위험 술어 MLP 를 저장하지 않는다**(`torch.save(lstm.state_dict())` 뿐).
따라서 위험 술어는 같은 구조로 새로 초기화한 상태에서 잰다. 0/비0 (경로가 있느냐) 판정은 정확하고,
크기는 "학습 종료 시점" 값이 아니라 "초기값에서의" 크기로 읽어야 한다. `--seed-pred` 로 여러 번 재서
크기의 흔들림을 볼 수 있다.

사용:
  python NeSy-SMP/tools/audit/grad_path_sepsis.py \
      --variant C:/dev/NeSy-SMP-repro/NeSy-SMP/upstream_faithful \
      --ckpt    C:/dev/NeSy-SMP-repro/NeSy-SMP/results_paper_6h/ltn_w_k.pth \
      --data    C:/data/mimic-iv-derived/paper_leads/events_6h_wide_paper_como.csv \
      --out     C:/data/mimic-iv-derived/audit/grad_sepsis_6h --batches 20
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--variant", required=True, help="원본 실행본 폴더 (stratified_main.py 가 있는 곳)")
    p.add_argument("--ckpt", required=True, help="학습된 사망 모델 체크포인트 (ltn_w_k.pth)")
    p.add_argument("--data", required=True, help="입력 CSV (NESY_DATA 와 같은 파일)")
    p.add_argument("--out", required=True, help="결과를 쓸 폴더")
    p.add_argument("--fold", type=int, default=1, help="몇 번째 fold 로 재나 (1-base)")
    p.add_argument("--batches", type=int, default=20, help="평균낼 배치 수")
    p.add_argument("--seed-pred", type=int, default=0, help="위험 술어 초기화 시드")
    return p.parse_args()


def main():
    a = parse()
    var = Path(a.variant).resolve()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(var))
    os.environ["NESY_DATA"] = a.data

    src = (var / "stratified_main.py").read_text(encoding="utf-8", errors="replace")
    lines = src.splitlines(keepends=True)

    def line_of(pred, start=0):
        for i in range(start, len(lines)):
            if pred(lines[i]):
                return i
        raise RuntimeError("못 찾음")

    # ---- 1) 원본 전처리부만 실행 (fold 루프 시작 직전까지)
    i_loop = line_of(lambda s: s.startswith("for i, (train_index, test_index)"))
    g = {"__name__": "__upstream_prefix__", "__file__": str(var / "stratified_main.py")}
    sys.argv = [str(var / "stratified_main.py")]
    exec(compile("".join(lines[:i_loop]), "upstream_prefix", "exec"), g)   # noqa: S102
    print(f"[1] 전처리 완료 — 샘플 {len(g['X_all']):,} · 변수 {len(g['feature_names'])} · 길이 {g['sequence_length']}",
          flush=True)

    import ltn
    import torch
    from model.models import LSTMModel, MLP, SimpleMLP, SimpleMLPAge   # noqa: F401
    from data.dataset import SepsisDataset
    from torch.utils.data import DataLoader
    from sklearn.model_selection import train_test_split

    X_all, y_all, seed = g["X_all"], g["y_all"], g["seed"]
    device, config = g["device"], g["config"]

    # ---- 2) 원본과 같은 방식으로 fold 분할
    splits = list(g["skf"].split(X_all, y_all))
    train_index, test_index = splits[a.fold - 1]
    X_train = [X_all[i] for i in train_index]; y_train = [y_all[i] for i in train_index]
    X_train, _X_val, y_train, _y_val = train_test_split(
        X_train, y_train, test_size=0.20, stratify=y_train, random_state=seed)
    train_loader = DataLoader(SepsisDataset(X_train, y_train, g["feature_names"]),
                              batch_size=32, shuffle=False)
    print(f"[2] fold {a.fold} 학습 배치 {len(train_loader):,}", flush=True)

    # ---- 3) 학습된 사망 모델 올리기
    lstm = LSTMModel(g["vocab_sizes"], config, 1, g["feature_names"]).to(device)
    lstm.load_state_dict(torch.load(a.ckpt, map_location=device))
    lstm.eval()
    print(f"[3] 체크포인트 적재 {a.ckpt}", flush=True)

    # ---- 4) 원본의 술어·함수·임계값 정의 블록을 **원문 그대로** 실행
    i_P = line_of(lambda s: s.strip() == "P = ltn.Predicate(lstm).to(device)",
                  line_of(lambda s: s.strip().startswith("lstm.load_state_dict(torch.load(\"ltn_w_o_k.pth\")")))
    i_w = line_of(lambda s: s.strip() == "w_data = 0.8", i_P)
    block = "".join(l[4:] if l.startswith("    ") else l for l in lines[i_P:i_w])
    torch.manual_seed(a.seed_pred); np.random.seed(a.seed_pred)
    ns = dict(g); ns.update({"lstm": lstm, "ltn": ltn, "torch": torch, "np": np,
                             "MLP": MLP, "SimpleMLP": SimpleMLP, "SimpleMLPAge": SimpleMLPAge,
                             "device": device, "features_dict": g["features_dict"],
                             "sequence_length": g["sequence_length"], "scalers": g["scalers"]})
    exec(compile(block, "upstream_predicates", "exec"), ns)              # noqa: S102
    # 양화사·결합자(원본 "# Knowledge Theory" 블록) 도 원문 그대로
    i_kt = line_of(lambda s_: s_.strip().startswith("Forall = ltn.Quantifier("))
    i_kt_end = line_of(lambda s_: s_.strip().startswith("Implies = ltn.Connective("), i_kt) + 1
    exec(compile("".join(l[4:] if l.startswith("    ") else l for l in lines[i_kt:i_kt_end]),
                 "upstream_ops", "exec"), ns)                            # noqa: S102
    # 감사는 같은 입력에 같은 값이 나와야 하므로 드롭아웃을 끈다 (원본 학습 루프는 train() 모드)
    for _k, _v in list(ns.items()):
        if _k.startswith("model_") and hasattr(_v, "eval"):
            _v.eval()
    print(f"[4] 술어·임계값 블록 실행 (원문 {i_P + 1}~{i_w} 행) · 연산자 {i_kt + 1}~{i_kt_end} 행", flush=True)

    # 공리별 '자기 술어' 파라미터
    own = {"anchor:GCS<8": "model_gcs", "anchor:Lactate>4": "model_lactate",
           "anchor:Platelet<50": "model_platelet", "anchor:LactateNotClearing": "model_lactate_not_clearing",
           "anchor:LactateClearing(neg)": "model_lactate_not_clearing", "anchor:Bilirubin>=2": "model_birulin",
           "anchor:RR": "model_respiratory_rate", "anchor:SBP<=100": "model_abps",
           "anchor:Creatinine>=1.5": "model_creatinine", "anchor:CRP>=100": "model_crp",
           "anchor:Chronic": "model_cronic_conditions", "anchor:Glucose>100": "model_glucose",
           "anchor:WBC>30": "model_wbc", "anchor:Age>65": "model_age",
           "impl:Lactate": "model_lactate", "impl:Bilirubin": "model_birulin",
           "impl:Platelet": "model_platelet", "impl:LactateNotClearing": "model_lactate_not_clearing",
           "impl:CRP": "model_crp", "impl:Chronic": "model_cronic_conditions",
           "impl:WBC": "model_wbc", "impl:Age": "model_age",
           "impl:GCS": "model_gcs", "impl:SBP": "model_abps", "impl:RR": "model_respiratory_rate",
           "impl:Creatinine": "model_creatinine", "impl:Glucose": "model_glucose",
           "impl:MAP": "model_map"}

    # ---- 5) 공리 구성 블록도 원문 그대로 (배치마다)
    i_f0 = line_of(lambda s: s.strip() == "formulas = []", i_w)
    i_f1 = line_of(lambda s: s.strip() == "sat_agg = SatAgg(*formulas)", i_f0)
    fblock = compile("".join(l[12:] if l.startswith(" " * 12) else l for l in lines[i_f0:i_f1]),
                     "upstream_formulas", "exec")
    vblock = compile("".join(l[12:] if l.startswith(" " * 12) else l for l in
                             lines[line_of(lambda s: s.strip().startswith('x_D = ltn.Variable("x_D"'), i_w):i_f0]),
                     "upstream_vars", "exec")

    P_params = [p for p in lstm.parameters() if p.requires_grad]
    SatAgg = ns["SatAgg"]
    acc = {}        # name -> [gP, gOwn, sat, n]
    data_gP, n_data, kn_gP, n_kn = 0.0, 0, 0.0, 0

    def gnorm(y, params):
        """||∂y/∂params||. 경로가 전혀 없으면 grad 가 모두 None 이고, 그때는 정확히 0 이다."""
        if not params:
            return 0.0
        gs = torch.autograd.grad(y, params, retain_graph=True, allow_unused=True)
        tot = sum((gg.detach() ** 2).sum() for gg in gs if gg is not None)
        return float(tot.sqrt()) if torch.is_tensor(tot) else 0.0

    for bi, (x, y, _c) in enumerate(train_loader):
        if bi >= a.batches:
            break
        local = dict(ns); local.update({"x": x, "y": y})
        exec(vblock, local)                                              # noqa: S102
        exec(fblock, local)                                              # noqa: S102
        fk, fd = local["formulas_knowledge"], local["formulas"]

        # 원본 P6 패치와 같은 순서로 이름 붙이기
        names = []
        for n_, v_ in (("GCS<8", local["x_below_gcs"]), ("Lactate>4", local["x_above_lactate"]),
                       ("Platelet<50", local["x_below_platelet"]),
                       ("LactateNotClearing", local["x_lactate_not_clear"]),
                       ("LactateClearing(neg)", local["x_lactate_clearing"]),
                       ("Bilirubin>=2", local["x_above_bilirubin"])):
            if v_.value.numel() > 0:
                names.append("anchor:" + n_)
        if local["x_risk_respiratory_rate"].value.numel() > 0 and local["x_risk_pressure_systolic"].value.numel() > 0:
            names += ["anchor:RR", "anchor:SBP<=100"]
        for n_, v_ in (("Creatinine>=1.5", local["x_above_creatinine"]), ("CRP>=100", local["x_above_crp"]),
                       ("Chronic", local["x_cronic_condition"]), ("Glucose>100", local["x_above_glucose"]),
                       ("WBC>30", local["x_above_wbc"]), ("Age>65", local["x_above_age"])):
            if v_.value.numel() > 0:
                names.append("anchor:" + n_)
        n_impl = len(fk) - len(names)
        base_impl = ["Lactate", "Bilirubin", "Platelet", "LactateNotClearing", "CRP", "Chronic", "WBC", "Age"]
        extra = ["GCS", "SBP", "RR", "Creatinine", "Glucose", "MAP"]
        names += ["impl:" + n_ for n_ in (base_impl + extra)[:n_impl]]
        assert len(names) == len(fk), (len(names), len(fk))

        for n_, f_ in zip(names, fk):
            op = [p for p in ns[own[n_]].parameters()] if n_ in own else []
            r = acc.setdefault(n_, [0.0, 0.0, 0.0, 0])
            r[0] += gnorm(f_, P_params)
            r[1] += gnorm(f_, op) if op else 0.0
            r[2] += float(f_.detach()); r[3] += 1
        if fd:
            data_gP += gnorm(SatAgg(*fd), P_params); n_data += 1
        if fk:
            kn_gP += gnorm(SatAgg(*fk), P_params); n_kn += 1
        if (bi + 1) % 5 == 0:
            print(f"  배치 {bi + 1}/{a.batches}", flush=True)

    # ---- 6) 정리
    rows = []
    for n_, (gp, go, s_, c_) in sorted(acc.items(), key=lambda kv: (not kv[0].startswith("impl"), kv[0])):
        rows.append({"공리": n_, "종류": "함축" if n_.startswith("impl") else "앵커",
                     "배치수": c_, "만족도": round(s_ / c_, 4),
                     "사망모델 gradient": round(gp / c_, 8),
                     "자기술어 gradient": round(go / c_, 6)})
    d_mean = data_gP / max(n_data, 1); k_mean = kn_gP / max(n_kn, 1)
    summary = {"변형": var.name, "체크포인트": a.ckpt, "fold": a.fold, "배치": a.batches,
               "술어초기화시드": a.seed_pred,
               "데이터공리 gradient(θ_P)": round(d_mean, 6),
               "지식공리 gradient(θ_P)": round(k_mean, 6),
               "논문손실 기준 지식 몫": round((0.2 * k_mean) / (0.2 * k_mean + 0.8 * d_mean + 1e-12), 6),
               "θ_P gradient 가 0 인 공리 수": sum(1 for r in rows if r["사망모델 gradient"] == 0),
               "공리 수": len(rows)}

    import pandas as pd
    T = pd.DataFrame(rows)
    T.to_csv(out / "grad_path_sepsis.csv", index=False, encoding="utf-8-sig")
    (out / "grad_path_sepsis.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + T.to_string(index=False))
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
