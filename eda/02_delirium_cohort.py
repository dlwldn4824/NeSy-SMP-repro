# -*- coding: utf-8 -*-
"""랩미팅 §3 스펙 그대로의 Delirium cohort (①~⑦) + attrition + 확인항목 EDA."""
import pandas as pd, numpy as np, json

OUT = "notes/eda"
b = pd.read_pickle(f"{OUT}/_icu_base.pkl")
b["era"] = b["anchor_year_group"].str.replace(" ", "", regex=False)
v = pd.read_parquet(f"{OUT}/_label_values.parquet")

# --- CAM-ICU 결과 필드 = itemid 228332 'Delirium assessment' (Positive/Negative/UTA)
dl = v[v.itemid == 228332][["stay_id", "charttime", "value"]].copy()
dl["charttime"] = pd.to_datetime(dl["charttime"])
# --- RASS (UTA 원인 분석용)
rs = v[v.itemid == 228096][["stay_id", "charttime", "value"]].copy()
rs["charttime"] = pd.to_datetime(rs["charttime"])
rs["rass"] = rs["value"].str.extract(r"^\s*([+-]?\d)").astype(float)

intime = b.set_index("stay_id")["intime"]
outtime = b.set_index("stay_id")["outtime"]
dl["hr"] = (dl["charttime"] - dl["stay_id"].map(intime)).dt.total_seconds()/3600
rs["hr"] = (rs["charttime"] - rs["stay_id"].map(intime)).dt.total_seconds()/3600
dl = dl[dl["hr"].notna()]
rs = rs[rs["hr"].notna()]

W = 24.0
obs = dl[(dl.hr >= 0) & (dl.hr < W)]          # ④ observation window
fut = dl[dl.hr >= W]                           # ⑥⑦ outcome window

def agg(d, pre):
    g = d.groupby("stay_id")["value"]
    return pd.DataFrame({
        f"{pre}_n":   g.size(),
        f"{pre}_pos": g.apply(lambda s: (s == "Positive").sum()),
        f"{pre}_neg": g.apply(lambda s: (s == "Negative").sum()),
        f"{pre}_uta": g.apply(lambda s: (s == "UTA").sum()),
    })

A = agg(obs, "obs").reindex(b.stay_id.values).fillna(0)
B = agg(fut, "fut").reindex(b.stay_id.values).fillna(0)
d = b.set_index("stay_id").join(A).join(B)

# ---------------- ①~⑦ attrition ----------------
steps = []
def rec(lbl, x): steps.append((lbl, len(x), x["subject_id"].nunique()))

x = d.copy();                                      rec("0. 전체 ICU stay", x)
x = x[x.age >= 18];                                rec("① 성인 (age>=18)", x)
x = x[x.icu_seq_in_subject == 1];                  rec("② 환자당 첫 ICU stay", x)
x = x[x.los >= 1.0];                               rec("③ ICU LOS >= 24h", x)
# ④ observation window는 필터가 아니라 정의 (첫 24h)
x = x[x.obs_pos == 0];                             rec("⑤ 첫 24h CAM-ICU Positive 제외", x)
x = x[(x.fut_pos + x.fut_neg) >= 1];               rec("⑥ 24h 이후 assessable 기록 >=1", x)
x["delirium"] = (x.fut_pos > 0).astype(int);       rec("⑦ label 부여 (Unknown 제외 완료)", x)

att = pd.DataFrame(steps, columns=["step", "stays", "patients"])
att["kept_pct_of_prev"] = (att["stays"]/att["stays"].shift(1)*100).round(1)
att.to_csv(f"{OUT}/delirium_attrition.csv", index=False, encoding="utf-8-sig")
print("=== ①~⑦ ATTRITION ==="); print(att.to_string(index=False))

coh = x.copy()
print(f"\n최종 코호트 {len(coh)} stays / delirium=1 {coh.delirium.sum()} ({100*coh.delirium.mean():.1f}%)")

# ⑤/⑥에서 빠진 사람이 누구인지 (버려지는 집단의 성격)
base3 = d[(d.age >= 18) & (d.icu_seq_in_subject == 1) & (d.los >= 1.0)].copy()
base3["drop_reason"] = np.where(base3.obs_pos > 0, "⑤ prevalent delirium",
                        np.where((base3.fut_pos + base3.fut_neg) >= 1, "included",
                        np.where(base3.fut_uta > 0, "⑥ 24h이후 UTA만 (Unknown)",
                                 "⑥ 24h이후 기록 없음")))
drop = base3.groupby("drop_reason").agg(
    stays=("subject_id","size"), hosp_mort=("hospital_expire_flag","mean"),
    los=("los","median"), age=("age","median"),
    obs_uta_frac=("obs_uta", lambda s: s.mean())).round(3)
drop["hosp_mort"] = (100*drop["hosp_mort"]).round(1)
drop.to_csv(f"{OUT}/delirium_drop_reasons.csv", encoding="utf-8-sig")
print("\n=== ③ 이후 누가 왜 빠지나 ==="); print(drop.to_string())

coh.reset_index().to_csv(f"{OUT}/delirium_cohort_stays.csv", index=False, encoding="utf-8-sig")
coh.to_pickle(f"{OUT}/_delirium_cohort.pkl")
base3.to_pickle(f"{OUT}/_base3.pkl")
