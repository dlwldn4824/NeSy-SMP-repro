# -*- coding: utf-8 -*-
"""상대적 관찰창 두 설계의 실현 가능성 비교.

  (A) event-anchored : case = onset - lead - W 직전 W시간. control = 무작위 창 (원 논문식)
  (B) landmark       : 매 t 마다 [t-W, t) 로 [t, t+H) 예측. stride 간격
"""
import sys; import pandas as pd, numpy as np
sys.stdout.reconfigure(encoding="utf-8"); pd.set_option("display.width",220)
D="notes/eda"
b=pd.read_parquet(f"{D}/_icu_base.parquet")
b["intime"]=pd.to_datetime(b.intime); b["outtime"]=pd.to_datetime(b.outtime)
v=pd.read_parquet(f"{D}/_label_values.parquet")
MAP={"Positive":"P","Negative":"N","UTA":"U"}
dl=v[v.itemid==228332][["stay_id","charttime","value"]].copy()
dl["charttime"]=pd.to_datetime(dl.charttime); dl["v"]=dl["value"].astype(str).str.strip().map(MAP)
dl=dl[dl.v.notna()]
base=b[(b.age>=18)&(b.icu_seq_in_subject==1)&(b.los>=0.5)].copy()   # 최소 12h
it=b.set_index("stay_id")["intime"]
dl=dl[dl.stay_id.isin(base.stay_id)].copy()
dl["hr"]=(dl.charttime-dl.stay_id.map(it)).dt.total_seconds()/3600
dl=dl[dl.hr>=0]
base["los_hr"]=base.los*24
onset=dl[dl.v=="P"].groupby("stay_id")["hr"].min()

print(f"대상(성인·환자당첫stay·LOS>=12h) {len(base):,} stays")
print(f"섬망 발생 {len(onset):,} ({100*len(onset)/len(base):.1f}%)  median {onset.median():.1f}h\n")

# ---------------- (A) event-anchored ----------------
print("="*74); print("[A] event-anchored (원 논문식)")
print("case 는 onset-lead-W 창, control 은 기준점이 없어 무작위 선택이 필요하다\n")
rows=[]
for W in [12,24]:
    for lead in [0,6,12,24]:
        need=lead+W
        ok=int((onset>=need).sum())
        rows.append(dict(관찰창=f"{W}h", lead=f"{lead}h", 필요onset=f"{need}h",
                         사용가능case=ok, case유지율=round(100*ok/len(onset),1)))
print(pd.DataFrame(rows).to_string(index=False))
noP=base[~base.stay_id.isin(onset.index)]
print(f"\ncontrol(섬망 없음) {len(noP):,} stays · LOS median {noP.los.median():.2f}일"
      f"  vs case {base[base.stay_id.isin(onset.index)].los.median():.2f}일")

# ---------------- (B) landmark ----------------
print("\n"+"="*74); print("[B] landmark (슬라이딩)")
print("매 t 마다 [t-W,t) 로 [t,t+H) 예측. 첫 발생 이후 시점은 제외\n")
g=dl.groupby("stay_id")
hrs={k:v.values for k,v in dl.groupby("stay_id")["hr"]}
vals={k:v.values for k,v in dl.groupby("stay_id")["v"]}
los=base.set_index("stay_id")["los_hr"].to_dict()
ons=onset.to_dict()

def landmark(W,H,stride):
    n_s=0; n_pos=0; pts=set()
    for sid,L in los.items():
        h=hrs.get(sid); vv=vals.get(sid)
        if h is None: continue
        o=ons.get(sid, np.inf)
        t=W
        while t+H<=L+1e-9:
            if t>o:            # 이미 발생한 뒤 시점은 제외
                break
            m=(h>=t)&(h<t+H)
            if m.any():
                w=vv[m]
                if ("P" in w) or ("N" in w):      # 판정 가능한 시점만
                    n_s+=1; pts.add(sid)
                    if "P" in w: n_pos+=1
            t+=stride
    return n_s,n_pos,len(pts)

rows=[]
for W,H,st in [(12,24,12),(24,24,12),(12,24,6),(24,48,24),(12,48,12)]:
    n,p,pt=landmark(W,H,st)
    rows.append(dict(관찰창=f"{W}h", 예측지평=f"{H}h", 간격=f"{st}h",
                     샘플수=n, 양성=p, 유병률=round(100*p/n,1) if n else None,
                     기여환자=pt, 환자당샘플=round(n/pt,2) if pt else None))
print(pd.DataFrame(rows).to_string(index=False))
print("\n참고: 고정창(첫24h->24~72h) 22,867 샘플 / 유병률 15.6% / 환자당 1개")
