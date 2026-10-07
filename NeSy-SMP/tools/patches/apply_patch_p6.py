"""[PATCH P6] 기록 전용 — LTN w/ knowledge(NeSy-SMP) 학습 중 규칙별 activation · satisfaction 기록.

학습 계산은 바꾸지 않는다 (formula 값을 detach 해서 읽기만 함).
epoch 마다 p6_knowledge_log.jsonl 에 한 줄:
  fold · epoch · val_f1 · is_best(이번 epoch 이 val F1 최고 → 체크포인트 저장)
  sat_data / sat_knowledge : 학습 batch 평균 SatAgg
  activation[규칙]        : 코드 판정으로 켜진 환자 비율 (학습 batch 전체)
  axiom_sat[공리]         : 공리 formula 값의 batch 평균 · axiom_batches: 그 공리가 들어간 batch 수
사용: python apply_patch_p6.py <stratified_main.py>  (제자리 수정, 이미 적용됐으면 건너뜀)
"""
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
if "[PATCH P6]" in s:
    sys.exit(f"skip (already patched): {p}")
k0 = s.index("w_knowledge = 0.2")
head, body = s[:k0], s[k0:]


def once(text, old, new):
    assert text.count(old) == 1, (old[:60], text.count(old))
    return text.replace(old, new)


body = once(body, "        sa_knowledge = 0\n",
            "        sa_knowledge = 0\n"
            "        _p6_act, _p6_sat, _p6_n, _p6_sd, _p6_sk, _p6_b = {}, {}, 0, 0.0, 0.0, 0   # [PATCH P6]\n")

body = once(body, """                Forall(x_All, Implies(AgeRisk(age(x_All), comorbidities(x_All)), P(x_All))).value,
            ])
""", """                Forall(x_All, Implies(AgeRisk(age(x_All), comorbidities(x_All)), P(x_All))).value,
            ])
            # [PATCH P6] 기록 전용 — formula 순서대로 이름을 붙이고 값을 읽기만 한다
            _names = []
            for _n, _v in (("GCS<8", x_below_gcs), ("Lactate>4", x_above_lactate), ("Platelet<50", x_below_platelet),
                           ("LactateNotClearing", x_lactate_not_clear), ("LactateClearing(neg)", x_lactate_clearing),
                           ("Bilirubin>=2", x_above_bilirubin)):
                if _v.value.numel() > 0: _names.append("anchor:" + _n)
            if x_risk_respiratory_rate.value.numel()>0 and x_risk_pressure_systolic.value.numel()>0:
                _names += ["anchor:RR", "anchor:SBP<=100"]
            for _n, _v in (("Creatinine>=1.5", x_above_creatinine), ("CRP>=100", x_above_crp), ("Chronic", x_cronic_condition),
                           ("Glucose>100", x_above_glucose), ("WBC>30", x_above_wbc), ("Age>65", x_above_age)):
                if _v.value.numel() > 0: _names.append("anchor:" + _n)
            _names += ["impl:" + _n for _n in ("Lactate", "Bilirubin", "Platelet", "LactateNotClearing", "CRP", "Chronic", "WBC", "Age")]
            assert len(_names) == len(formulas_knowledge), (len(_names), len(formulas_knowledge))
            for _n, _v in (("GCS<8", x_below_gcs), ("Lactate>4", x_above_lactate), ("Platelet<50", x_below_platelet),
                           ("LactateNotClearing", x_lactate_not_clear), ("Bilirubin>=2", x_above_bilirubin), ("RR", x_risk_respiratory_rate),
                           ("SBP<=100", x_risk_pressure_systolic), ("Creatinine>=1.5", x_above_creatinine), ("CRP>=100", x_above_crp),
                           ("Chronic", x_cronic_condition), ("Glucose>100", x_above_glucose), ("WBC>30", x_above_wbc),
                           ("Age>65", x_above_age), ("MAP<65", x_below_map)):
                _p6_act[_n] = _p6_act.get(_n, 0) + (int(_v.value.shape[0]) if _v.value.numel() > 0 else 0)
            _p6_n += int(x.shape[0])
            for _n, _f in zip(_names, formulas_knowledge):
                _s6 = _p6_sat.setdefault(_n, [0.0, 0]); _s6[0] += float(_f.detach()); _s6[1] += 1
""")

body = once(body, """                loss = 1 - sat_agg
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
""", """                loss = 1 - sat_agg
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
            _p6_sd += float(sat_agg.detach()); _p6_b += 1   # [PATCH P6]
            _p6_sk += float(sat_agg_knowledge.detach()) if len(formulas_knowledge) > 0 else 0.0
""")

body = once(body, """        f1_val = compute_accuracy(val_loader)
        if f1_val > best_f1_val:
            best_f1_val = f1_val
            torch.save(lstm.state_dict(), "ltn_w_k.pth")
""", """        f1_val = compute_accuracy(val_loader)
        _p6_rec = {"fold": len(ltn_log_roc_aucs) + 1, "epoch": epoch + 1, "val_f1": float(f1_val),   # [PATCH P6]
                   "is_best": bool(f1_val > best_f1_val), "sat_data": _p6_sd / max(_p6_b, 1), "sat_knowledge": _p6_sk / max(_p6_b, 1),
                   "activation": {k: v / max(_p6_n, 1) for k, v in _p6_act.items()},
                   "axiom_sat": {k: v[0] / v[1] for k, v in _p6_sat.items()}, "axiom_batches": {k: v[1] for k, v in _p6_sat.items()}}
        print("[P6]", json.dumps(_p6_rec))
        with open("p6_knowledge_log.jsonl", "a") as _fp6:
            _fp6.write(json.dumps(_p6_rec) + "\\n")
        if f1_val > best_f1_val:
            best_f1_val = f1_val
            torch.save(lstm.state_dict(), "ltn_w_k.pth")
""")
p.write_text(head + body, encoding="utf-8")
print("patched:", p)
