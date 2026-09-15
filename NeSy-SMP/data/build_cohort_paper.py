"""논문 §5.1 코호트 — MIMIC-IV Sepsis-3 (mimic-code 공식 concept 을 로컬 SQLite 로 그대로 옮김).

논문 원문 (De Santis et al., EAAI 2026, §5.1):
  "all adult patients (age >= 18 years) who met the Sepsis-3 criteria, defined as a suspected or documented
   infection and an acute increase in the SOFA score of >= 2 points. Patients were excluded if (1) ICU length of
   stay less than 24 h, (2) Multiple ICU admissions during the hospital stay, or (3) Absence of significant clinical
   data required for the analysis. The final cohort comprised 19,328 patients ... mortality rate of 18%."
  데이터: MIMIC-IV v2.2 (2008-2019).

Sepsis-3 는 MIT-LCP/mimic-code (mimic-iv/concepts) 의 다음 SQL 을 한 줄씩 옮겼다:
  medication/antibiotic.sql · sepsis/suspicion_of_infection.sql · score/sofa.sql · sepsis/sepsis3.sql
  입력: demographics/icustay_times · icustay_hourly · measurement/bg · gcs · vitalsign(mbp) · enzyme(bilirubin)
        · chemistry(creatinine) · complete_blood_count(platelet) · urine_output · urine_output_rate
        · treatment/ventilation (ventilator_setting · oxygen_delivery) · medication/{norepi,epi,dopamine,dobutamine}
BigQuery 의미를 따른 부분: DATETIME_DIFF(HOUR) = 시(hour) 경계 수 · NULL 비교는 거짓 · MAX 는 NULL 무시 · ASC 정렬 NULL 먼저.

v2.2 근사: 로컬 DB 는 2020-2022 가 들어간 v3.x 다. 환자별 anchor_year_group 과 입원 연도 이동으로 실제 연도 하한을
  추정해 2020 이후가 확실한 입원을 뺀다 (anchor_year_group 시작연도 + (입원연도 − anchor_year) ≥ 2020 → 제외).
제외 (3) '분석에 필요한 임상 데이터 없음' 은 원문에 정의가 없어 여기서 적용하지 않고, 이벤트·창 생성 단계
  (preprocess_eventlog 의 이벤트 5개 미만 제외 등)에서 자연히 걸리는 것으로 둔다.

사용:
  python data/build_cohort_paper.py --db C:/Users/dlwld/Downloads/MIMIC4-hosp-icu.db --out-dir C:/data/mimic-iv-derived
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
T0 = time.time()
H = pd.Timedelta(hours=1)


def log(m):
    print(f"[{time.time() - T0:7.0f}s] {m}", flush=True)


def ro(db):
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def cached(cache: Path, name: str, fn):
    p = cache / f"{name}.parquet"
    if p.exists():
        log(f"cache {name}")
        return pd.read_parquet(p)
    df = fn()
    df.to_parquet(p, index=False)
    log(f"saved {name} rows={len(df):,}")
    return df


def hour_floor(s):
    return s.dt.floor("h")


def hour_diff(a, b):
    """BigQuery DATETIME_DIFF(a, b, HOUR): 시 경계 수."""
    return (hour_floor(a) - hour_floor(b)) / H


# ---------------------------------------------------------------- antibiotic.sql
ABX_NAMES = """adoxa ala-tet alodox amikacin amikin amoxicill amphotericin anidulafungin ancef clavulanate ampicillin
augmentin avelox avidoxy azactam azithromycin aztreonam axetil bactocill bactrim bactroban bethkis biaxin
|bicillin l-a| cayston cefazolin cedax cefoxitin ceftazidime cefaclor cefadroxil cefdinir cefditoren cefepime cefotan
cefotetan cefotaxime ceftaroline cefpodoxime cefpirome cefprozil ceftibuten ceftin ceftriaxone cefuroxime cephalexin
cephalothin cephapririn chloramphenicol cipro ciprofloxacin claforan clarithromycin cleocin clindamycin cubicin
dicloxacillin dirithromycin doryx doxycy duricef dynacin ery-tab eryped eryc erythrocin erythromycin factive flagyl
fortaz furadantin garamycin gentamicin kanamycin keflex kefzol ketek levaquin levofloxacin lincocin linezolid macrobid
macrodantin maxipime mefoxin metronidazole meropenem methicillin minocin minocycline monodox monurol morgidox moxatag
moxifloxacin mupirocin myrac nafcillin neomycin |nicazel doxy 30| nitrofurantoin norfloxacin noroxin ocudox ofloxacin
omnicef oracea oraxyl oxacillin |pc pen vk| |pce dispertab| panixine pediazole penicillin periostat pfizerpen
piperacillin tazobactam primsol proquin raniclor rifadin rifampin rocephin smz-tmp septra |septra ds| solodyn
spectracef streptomycin sulfadiazine sulfamethoxazole trimethoprim sulfatrim sulfisoxazole suprax synercid tazicef
tetracycline timentin tobramycin unasyn vancocin vancomycin vantin vibativ vibra-tabs vibramycin zinacef zithromax
zosyn zyvox"""


def abx_patterns():
    pats, s = [], ABX_NAMES.replace("\n", " ")
    while s:
        s = s.strip()
        if not s:
            break
        if s[0] == "|":
            j = s.index("|", 1)
            pats.append(s[1:j]); s = s[j + 1:]
        else:
            k = s.find(" ")
            k = len(s) if k < 0 else k
            pats.append(s[:k]); s = s[k:]
    return pats


def build_antibiotic(db, icu):
    con = ro(db)
    pr = pd.read_sql("SELECT subject_id, hadm_id, drug_type, drug, route, starttime, stoptime FROM prescriptions", con)
    log(f"prescriptions rows={len(pr):,}")
    low = pr["drug"].str.lower()
    pats = abx_patterns()
    lowv = low.fillna("")
    uniq = pd.Series(lowv.unique())
    hit = np.zeros(len(uniq), bool)
    for p_ in pats:
        hit |= uniq.str.contains(p_, regex=False).to_numpy()
    is_abx = lowv.map(dict(zip(uniq, hit))).to_numpy()
    rl = pr["route"].str.lower()
    ok = (pr["drug_type"].notna() & (pr["drug_type"] != "BASE")
          & pr["route"].notna() & ~pr["route"].isin(["OU", "OS", "OD", "AU", "AS", "AD", "TP"])
          & ~rl.str.contains("ear", regex=False, na=False) & ~rl.str.contains("eye", regex=False, na=False)
          & low.notna()
          & ~lowv.str.contains("cream", regex=False) & ~lowv.str.contains("desensitization", regex=False)
          & ~lowv.str.contains("ophth oint", regex=False) & ~lowv.str.contains("gel", regex=False)
          & is_abx)
    pairs = pr.loc[ok, ["drug", "route"]].drop_duplicates()
    ab = pr.merge(pairs, on=["drug", "route"])            # INNER JOIN abx ON drug, route (drug_type 재검사 없음)
    ab["starttime"] = pd.to_datetime(ab["starttime"]); ab["stoptime"] = pd.to_datetime(ab["stoptime"])
    # LEFT JOIN icustays ON hadm_id AND starttime >= intime AND starttime < outtime
    m = ab.reset_index().merge(icu[["hadm_id", "stay_id", "intime", "outtime"]], on="hadm_id", how="left")
    m = m[(m.starttime >= m.intime) & (m.starttime < m.outtime)]
    ab = ab.reset_index().merge(m[["index", "stay_id"]], on="index", how="left").drop(columns="index")
    return ab.rename(columns={"drug": "antibiotic"})[["subject_id", "hadm_id", "stay_id", "antibiotic", "route",
                                                        "starttime", "stoptime"]]


# ---------------------------------------------------------------- suspicion_of_infection.sql
def build_suspicion(db, ab):
    con = ro(db)
    me = pd.read_sql("SELECT micro_specimen_id, subject_id, hadm_id, chartdate, charttime, spec_type_desc, org_name, "
                     "org_itemid FROM microbiologyevents", con)
    pos = (me.org_name.notna() & me.org_itemid.notna() & ~me.org_itemid.isin([90856, 90760]) & (me.org_name != "")
           & (me.org_name != "CANCELLED")).astype(int)
    me = me.assign(pos=pos)
    me["chartdate"] = pd.to_datetime(me["chartdate"]).dt.normalize()
    me["charttime"] = pd.to_datetime(me["charttime"])
    me = me.groupby("micro_specimen_id").agg(subject_id=("subject_id", "max"), chartdate=("chartdate", "max"),
                                             charttime=("charttime", "max"), spec=("spec_type_desc", "max"),
                                             pos=("pos", "max")).reset_index()
    log(f"micro specimens={len(me):,}")
    ab = ab.sort_values(["subject_id", "starttime", "stoptime", "antibiotic", "hadm_id", "stay_id"],
                        na_position="first").reset_index(drop=True)
    ab["ab_id"] = ab.groupby("subject_id").cumcount() + 1
    ab["antibiotic_date"] = ab["starttime"].dt.normalize()
    ab = ab[ab.stay_id.notna()].copy()        # sepsis3 은 stay_id 있는 행만 쓴다 (결과 동일, 계산량 절감)
    mm = me[me.subject_id.isin(ab.subject_id.unique())]
    j = ab[["subject_id", "ab_id", "starttime", "antibiotic_date"]].merge(mm, on="subject_id")
    ct, at, ad, cd = j.charttime, j.starttime, j.antibiotic_date, j.chartdate
    has_ct = ct.notna()
    c72 = (has_ct & (at > ct) & (at <= ct + 72 * H)) | (~has_ct & (ad >= cd) & (ad <= cd + pd.Timedelta(days=3)))
    c24 = (has_ct & (at >= ct - 24 * H) & (at < ct)) | (~has_ct & (ad >= cd - pd.Timedelta(days=1)) & (ad <= cd))

    def first(sel):
        s = j[sel].copy()
        s["ct_null"] = s.charttime.isna()
        s = s.sort_values(["subject_id", "ab_id", "chartdate", "ct_null", "charttime", "pos", "micro_specimen_id"],
                          ascending=[True, True, True, True, True, False, True])
        s = s.drop_duplicates(["subject_id", "ab_id"])
        s["ct_eff"] = s.charttime.fillna(s.chartdate)
        return s[["subject_id", "ab_id", "ct_eff", "pos", "spec"]]

    m72 = first(c72).rename(columns={"ct_eff": "last72_charttime", "pos": "pos72", "spec": "spec72"})
    m24 = first(c24).rename(columns={"ct_eff": "next24_charttime", "pos": "pos24", "spec": "spec24"})
    s = ab.merge(m24, on=["subject_id", "ab_id"], how="left").merge(m72, on=["subject_id", "ab_id"], how="left")
    s["suspected_infection"] = (~(s.spec72.isna() & s.spec24.isna())).astype(int)
    s["suspected_infection_time"] = np.where(s.suspected_infection == 1,
                                             s.last72_charttime.fillna(s.starttime), pd.NaT)
    s["suspected_infection_time"] = pd.to_datetime(s["suspected_infection_time"])
    s["culture_time"] = s.last72_charttime.fillna(s.next24_charttime)
    s = s.rename(columns={"starttime": "antibiotic_time"})
    return s[["subject_id", "hadm_id", "stay_id", "ab_id", "antibiotic", "antibiotic_time", "suspected_infection",
              "suspected_infection_time", "culture_time"]]


# ---------------------------------------------------------------- chartevents 입력 (후보 stay 로 제한, 1회 스캔)
CE_ITEMS = [220045, 220052, 220181, 225312, 223900, 223901, 220739, 223849, 229314,
            223834, 227582, 227287, 226732, 223835]


def load_chartevents(db, stays, subjects):
    con = ro(db)
    q = (f"SELECT subject_id, stay_id, charttime, storetime, itemid, value, valuenum FROM chartevents "
         f"WHERE itemid IN ({','.join(map(str, CE_ITEMS))})")
    parts = []
    TEXT = [223900, 223849, 229314, 226732]           # 문자열 값이 필요한 항목
    STORE = [223834, 227582, 227287, 226732]          # storetime 정렬이 필요한 항목
    for ch in pd.read_sql(q, con, chunksize=5_000_000):
        keep = ch.stay_id.isin(stays) | ((ch.itemid == 223835) & ch.subject_id.isin(subjects))
        ch = ch[keep].copy()
        ch["has_value"] = ch["value"].notna()
        ch["value"] = ch["value"].where(ch.itemid.isin(TEXT))
        ch["storetime"] = pd.to_datetime(ch["storetime"].where(ch.itemid.isin(STORE)), format="%Y-%m-%d %H:%M:%S")
        ch["charttime"] = pd.to_datetime(ch["charttime"], format="%Y-%m-%d %H:%M:%S")
        ch["stay_id"] = ch["stay_id"].astype("Int64")
        ch["valuenum"] = ch["valuenum"].astype("float64")
        parts.append(ch)
        log(f"  chartevents chunk kept {sum(len(p) for p in parts):,}")
    return pd.concat(parts, ignore_index=True)


def load_labs(db, subjects):
    con = ro(db)
    q = ("SELECT specimen_id, subject_id, hadm_id, itemid, charttime, value, valuenum FROM labevents "
         "WHERE itemid IN (50885, 50912, 51265, 52033, 50816, 50821)")
    parts = []
    for ch in pd.read_sql(q, con, chunksize=5_000_000):
        ch = ch[ch.subject_id.isin(subjects)]
        ch["charttime"] = pd.to_datetime(ch["charttime"])
        parts.append(ch)
    df = pd.concat(parts, ignore_index=True)
    log(f"labevents rows={len(df):,}")
    return df


# ---------------------------------------------------------------- icustay_times / icustay_hourly
def build_hourly(icu, ce):
    hr = ce[ce.itemid == 220045].groupby("stay_id").charttime.agg(intime_hr="min", outtime_hr="max")
    t = icu.merge(hr, left_on="stay_id", right_index=True, how="inner")
    e0 = t.intime_hr.dt.ceil("h")
    n = hour_diff(t.outtime_hr, t.intime_hr).astype(int)
    cnt = n + 25
    rows = pd.DataFrame({"stay_id": np.repeat(t.stay_id.to_numpy(), cnt),
                         "hadm_id": np.repeat(t.hadm_id.to_numpy(), cnt),
                         "e0": np.repeat(e0.to_numpy(), cnt)})
    cc = cnt.to_numpy()
    rows["hr"] = np.arange(cc.sum()) - np.repeat(np.cumsum(cc) - cc, cc) - 24
    rows["endtime"] = rows.e0 + rows.hr.to_numpy() * H
    return t[["stay_id", "hadm_id", "subject_id", "intime", "outtime", "intime_hr"]], rows


def bin_points(grid_e0, df, key, time_col="charttime"):
    """(endtime-1h, endtime] 에 드는 시각 → hr 번호."""
    d = df.merge(grid_e0, on=key)
    delta = (d[time_col] - d.e0) / H
    d["hr"] = np.ceil(delta).astype("int64")
    return d


# ---------------------------------------------------------------- gcs.sql
def build_gcs(ce):
    g = ce[ce.itemid.isin([223900, 223901, 220739])].copy()
    g["motor"] = np.where(g.itemid == 223901, g.valuenum, np.nan)
    g["verbal"] = np.where((g.itemid == 223900) & (g.value == "No Response-ETT"), 0.0,
                           np.where(g.itemid == 223900, g.valuenum, np.nan))
    g["eyes"] = np.where(g.itemid == 220739, g.valuenum, np.nan)
    b = g.groupby(["subject_id", "stay_id", "charttime"]).agg(motor=("motor", "max"), verbal=("verbal", "max"),
                                                              eyes=("eyes", "max")).reset_index()
    b = b.sort_values(["stay_id", "charttime"]).reset_index(drop=True)
    b["stay_id"] = b["stay_id"].astype("int64")
    prev = b.groupby("stay_id")[["motor", "verbal", "eyes", "charttime"]].shift(1)
    within = prev.charttime > b.charttime - 6 * H
    pm, pv, pe = (prev[c].where(within) for c in ["motor", "verbal", "eyes"])
    has_prev = within.fillna(False)
    gcs = np.where(b.verbal == 0, 15,
          np.where(b.verbal.isna() & has_prev & (pv == 0), 15,
          np.where(has_prev & (pv == 0),
                   b.motor.fillna(6) + b.verbal.fillna(5) + b.eyes.fillna(4),
                   b.motor.fillna(pm).fillna(6) + b.verbal.fillna(pv).fillna(5) + b.eyes.fillna(pe).fillna(4))))
    return b.assign(gcs=gcs)[["stay_id", "charttime", "gcs"]]


# ---------------------------------------------------------------- ventilation.sql
TRACH = ["Tracheostomy tube", "Trach mask "]
INV_MODE = ["(S) CMV", "APRV", "APRV/Biphasic+ApnPress", "APRV/Biphasic+ApnVol", "APV (cmv)", "Ambient",
            "Apnea Ventilation", "CMV", "CMV/ASSIST", "CMV/ASSIST/AutoFlow", "CMV/AutoFlow", "CPAP/PPS", "CPAP/PSV",
            "CPAP/PSV+Apn TCPL", "CPAP/PSV+ApnPres", "CPAP/PSV+ApnVol", "MMV", "MMV/AutoFlow", "MMV/PSV",
            "MMV/PSV/AutoFlow", "P-CMV", "PCV+", "PCV+/PSV", "PCV+Assist", "PRES/AC", "PRVC/AC", "PRVC/SIMV",
            "PSV/SBT", "SIMV", "SIMV/AutoFlow", "SIMV/PRES", "SIMV/PSV", "SIMV/PSV/AutoFlow", "SIMV/VOL",
            "SYNCHRON MASTER", "SYNCHRON SLAVE", "VOL/AC"]
INV_HAM = ["APRV", "APV (cmv)", "Ambient", "(S) CMV", "P-CMV", "SIMV", "APV (simv)", "P-SIMV", "VS", "ASV"]
NIV_DEV = ["Bipap mask ", "CPAP mask "]
NIV_HAM = ["DuoPaP", "NIV", "NIV-ST"]
SUPP = ["Non-rebreather", "Face tent", "Aerosol-cool", "Venti mask ", "Medium conc mask ", "Ultrasonic neb",
        "Vapomist", "Oxymizer", "High flow neb", "Nasal cannula"]


def build_ventilation(ce):
    # ventilator_setting: value not null, stay not null, group by subject, charttime
    vs = ce[ce.itemid.isin([223849, 229314]) & ce.has_value & ce.stay_id.notna()]
    vs = vs.assign(vmode=vs.value.where(vs.itemid == 223849), ham=vs.value.where(vs.itemid == 229314))
    vs = vs.groupby(["subject_id", "charttime"]).agg(stay_id=("stay_id", "max"), vmode=("vmode", "max"),
                                                     ham=("ham", "max")).reset_index()
    # oxygen_delivery
    fl = ce[ce.itemid.isin([223834, 227582, 227287]) & ce.has_value].copy()
    fl["itemid"] = fl.itemid.replace({227582: 223834})
    fl = fl.sort_values(["subject_id", "charttime", "itemid", "storetime", "valuenum"], ascending=[1, 1, 1, 0, 0],
                        na_position="last").drop_duplicates(["subject_id", "charttime", "itemid"])
    o2 = ce[ce.itemid == 226732].copy()
    o2 = o2.sort_values(["subject_id", "charttime", "storetime", "value"], ascending=[1, 1, 0, 0], na_position="last")
    o2["rn"] = o2.groupby(["subject_id", "charttime"]).cumcount() + 1
    st = fl[["subject_id", "stay_id", "charttime"]].merge(
        o2[["subject_id", "stay_id", "charttime", "value", "rn"]].rename(columns={"stay_id": "stay_o2"}),
        on=["subject_id", "charttime"], how="left")       # WHERE ce.rn = 1 → ce 없는 o2 행은 빠진다
    st["stay_id"] = st.stay_id.fillna(st.stay_o2)
    for k in (1, 2, 3, 4):
        st[f"d{k}"] = st.value.where(st.rn == k)
    od = st.groupby(["subject_id", "charttime"]).agg(stay_id=("stay_id", "max"), d1=("d1", "max"), d2=("d2", "max"),
                                                     d3=("d3", "max"), d4=("d4", "max")).reset_index()
    tm = pd.concat([vs[["stay_id", "charttime"]], od[["stay_id", "charttime"]]]).dropna().drop_duplicates()
    v = tm.merge(vs[["stay_id", "charttime", "vmode", "ham"]], on=["stay_id", "charttime"], how="left") \
          .merge(od[["stay_id", "charttime", "d1", "d2", "d3", "d4"]], on=["stay_id", "charttime"], how="left")
    niv_any = v.d1.isin(NIV_DEV) | v.d2.isin(NIV_DEV) | v.d3.isin(NIV_DEV) | v.d4.isin(NIV_DEV) | v.ham.isin(NIV_HAM)
    v["status"] = np.select(
        [v.d1.isin(TRACH), v.d1.eq("Endotracheal tube") | v.vmode.isin(INV_MODE) | v.ham.isin(INV_HAM), niv_any,
         v.d1.eq("High flow nasal cannula"), v.d1.isin(SUPP), v.d1.eq("None")],
        ["Tracheostomy", "InvasiveVent", "NonInvasiveVent", "HFNC", "SupplementalOxygen", "None"], default=None)
    v = v[v.status.notna()].sort_values(["stay_id", "charttime"]).reset_index(drop=True)
    v["lag_same"] = v.groupby(["stay_id", "status"]).charttime.shift(1)
    v["lead"] = v.groupby("stay_id").charttime.shift(-1)
    v["status_lag"] = v.groupby("stay_id").status.shift(1)
    new = v.status_lag.isna() | (hour_diff(v.charttime, v.lag_same) >= 14).fillna(False) | \
        (v.status_lag.notna() & (v.status_lag != v.status))
    v["seq"] = new.astype(int).groupby(v.stay_id).cumsum()
    v["end_c"] = np.where(v.lead.isna() | (hour_diff(v.lead, v.charttime) >= 14).fillna(False), v.charttime, v.lead)
    v["end_c"] = pd.to_datetime(v["end_c"])
    ep = v.groupby(["stay_id", "seq"]).agg(starttime=("charttime", "min"), endtime=("end_c", "max"),
                                           ct_max=("charttime", "max"), status=("status", "max")).reset_index()
    ep = ep[ep.starttime != ep.ct_max]
    return ep[["stay_id", "starttime", "endtime", "status"]]


# ---------------------------------------------------------------- bg.sql → pafi
def build_pafi(labs, ce, ep, cand):
    bgl = labs[labs.itemid.isin([52033, 50816, 50821])].copy()
    bgl["specimen"] = bgl.value.where(bgl.itemid == 52033)
    fio2v = bgl.valuenum.where(bgl.itemid == 50816)
    bgl["fio2"] = np.where((fio2v > 20) & (fio2v <= 100), fio2v, np.where((fio2v > 0.2) & (fio2v <= 1.0), fio2v * 100, np.nan))
    bgl["po2"] = bgl.valuenum.where(bgl.itemid == 50821)
    bg = bgl.groupby("specimen_id").agg(subject_id=("subject_id", "max"), charttime=("charttime", "max"),
                                        specimen=("specimen", "max"), fio2=("fio2", "max"), po2=("po2", "max")).reset_index()
    bg = bg[bg.po2.notna()]
    f = ce[(ce.itemid == 223835) & (ce.valuenum > 0) & (ce.valuenum <= 100)].copy()
    f["fio2c"] = np.where((f.valuenum > 0.2) & (f.valuenum <= 1), f.valuenum * 100,
                          np.where((f.valuenum >= 20) & (f.valuenum <= 100), f.valuenum, np.nan))
    f = f.groupby(["subject_id", "charttime"]).fio2c.max().reset_index()
    f = f[f.fio2c > 0].sort_values("charttime")
    bg = bg.sort_values("charttime")
    bg = pd.merge_asof(bg, f.rename(columns={"charttime": "fct"}), left_on="charttime", right_on="fct",
                       by="subject_id", direction="backward", tolerance=4 * H)
    bg["pf"] = np.where(bg.fio2.notna(), 100 * bg.po2 / bg.fio2,
                        np.where(bg.fio2c.notna(), 100 * bg.po2 / bg.fio2c, np.nan))
    bg = bg[bg.specimen == "ART."]
    p = cand[["stay_id", "subject_id"]].merge(bg[["subject_id", "charttime", "pf"]], on="subject_id")
    iv = ep[ep.status == "InvasiveVent"]
    pv = p.reset_index().merge(iv, on="stay_id")
    pv = pv[(pv.charttime >= pv.starttime) & (pv.charttime <= pv.endtime)]
    p["vent"] = p.index.isin(pv["index"].unique())
    p["pf_novent"] = p.pf.where(~p.vent)
    p["pf_vent"] = p.pf.where(p.vent)
    return p[["stay_id", "charttime", "pf_novent", "pf_vent"]]


# ---------------------------------------------------------------- urine_output(_rate).sql
def build_uo(db, times, stays):
    con = ro(db)
    items = [226559, 226560, 226561, 226584, 226563, 226564, 226565, 226567, 226557, 226558, 227488, 227489]
    oe = pd.read_sql(f"SELECT stay_id, charttime, itemid, value FROM outputevents WHERE itemid IN ({','.join(map(str, items))})", con)
    oe = oe[oe.stay_id.isin(stays)]
    oe["charttime"] = pd.to_datetime(oe["charttime"])
    oe["uo"] = np.where((oe.itemid == 227488) & (oe.value > 0), -oe.value, oe.value)
    uo = oe.groupby(["stay_id", "charttime"]).uo.sum(min_count=1).reset_index()
    tm = times[["stay_id", "intime", "outtime", "intime_hr"]]
    uo = uo.merge(tm, on="stay_id")            # INNER JOIN tm (HR 있는 stay)
    uo = uo.sort_values(["stay_id", "charttime"]).reset_index(drop=True)
    prev = uo.groupby("stay_id").charttime.shift(1)
    uo["tm"] = np.where(prev.isna(), (uo.charttime - uo.intime_hr) / pd.Timedelta(minutes=1),
                        (uo.charttime - prev) / pd.Timedelta(minutes=1))
    out = []
    for sid, g in uo.groupby("stay_id", sort=False):
        t = g.charttime.to_numpy(); u = np.nan_to_num(g.uo.to_numpy(float)); m = g.tm.to_numpy(float)
        cu = np.concatenate([[0.0], np.cumsum(u)]); cm = np.concatenate([[0.0], np.cumsum(m)])
        lo = np.searchsorted(t, t - np.timedelta64(23, "h"), side="left")
        idx = np.arange(len(t)) + 1
        out.append(pd.DataFrame({"stay_id": sid, "charttime": t, "uo24": cu[idx] - cu[lo],
                                 "uo_tm24": np.round((cm[idx] - cm[lo]) / 60.0, 6)}))
    r = pd.concat(out, ignore_index=True)
    r["uo_24hr"] = np.where((r.uo_tm24 >= 22) & (r.uo_tm24 <= 30), r.uo24 / r.uo_tm24 * 24, np.nan)
    return r[["stay_id", "charttime", "uo_24hr"]]


# ---------------------------------------------------------------- sofa.sql
def build_sofa(db, icu, cand, ce, labs, cache):
    times, grid = build_hourly(cand, ce)
    log(f"hourly grid rows={len(grid):,} stays={grid.stay_id.nunique():,}")
    e0 = grid.drop_duplicates("stay_id")[["stay_id", "e0"]]
    e0h = grid.drop_duplicates("stay_id")[["stay_id", "hadm_id", "e0"]]
    key = ["stay_id", "hr"]
    comp = grid[["stay_id", "hr", "endtime"]].copy()

    def agg_into(df, col, how, name):
        nonlocal comp
        d = df.groupby(key)[col].agg(how).rename(name).reset_index()
        comp = comp.merge(d, on=key, how="left")

    # vitalsign mbp: AVG per (subject, stay, charttime) of valid values, then MIN per hour
    mb = ce[ce.itemid.isin([220052, 220181, 225312]) & (ce.valuenum > 0) & (ce.valuenum < 300)]
    mb = mb.groupby(["stay_id", "charttime"]).valuenum.mean().reset_index()
    agg_into(bin_points(e0, mb, "stay_id"), "valuenum", "min", "meanbp_min")
    agg_into(bin_points(e0, build_gcs(ce), "stay_id"), "gcs", "min", "gcs_min")
    log("mbp · gcs")

    def lab_series(itemid, cond):
        l = labs[(labs.itemid == itemid) & labs.valuenum.notna() & cond(labs.valuenum)]
        l = l.groupby("specimen_id").agg(hadm_id=("hadm_id", "max"), charttime=("charttime", "max"),
                                         v=("valuenum", "max")).reset_index()
        l = l.dropna(subset=["hadm_id"])
        l["hadm_id"] = l["hadm_id"].astype("int64")
        return l
    b = bin_points(e0h[["hadm_id", "stay_id", "e0"]], lab_series(50885, lambda x: x > 0), "hadm_id")
    agg_into(b, "v", "max", "bilirubin_max")
    c = bin_points(e0h[["hadm_id", "stay_id", "e0"]], lab_series(50912, lambda x: (x > 0) & (x <= 150)), "hadm_id")
    agg_into(c, "v", "max", "creatinine_max")
    p = bin_points(e0h[["hadm_id", "stay_id", "e0"]], lab_series(51265, lambda x: x > 0), "hadm_id")
    agg_into(p, "v", "min", "platelet_min")
    log("labs")

    ep = cached(cache, "ventilation", lambda: build_ventilation(ce))
    pf = build_pafi(labs, ce, ep, times)
    pfb = bin_points(e0, pf, "stay_id")
    agg_into(pfb, "pf_novent", "min", "pf_novent")
    agg_into(pfb, "pf_vent", "min", "pf_vent")
    log("pafi")

    uo = build_uo(db, times, set(times.stay_id))
    agg_into(bin_points(e0, uo, "stay_id"), "uo_24hr", "max", "uo_24hr")
    log("urine output")

    con = ro(db)
    ie = pd.read_sql("SELECT stay_id, itemid, rate, rateuom, patientweight, starttime, endtime FROM inputevents "
                     "WHERE itemid IN (221906, 221289, 221662, 221653)", con)
    ie = ie[ie.stay_id.isin(set(times.stay_id))]
    ie["starttime"] = pd.to_datetime(ie["starttime"]); ie["endtime"] = pd.to_datetime(ie["endtime"])
    ie["vr"] = np.where((ie.itemid == 221906) & (ie.rateuom == "mg/kg/min") & (ie.patientweight == 1), ie.rate,
                np.where((ie.itemid == 221906) & (ie.rateuom == "mg/kg/min"), ie.rate * 1000.0, ie.rate))
    ie = ie.merge(e0, on="stay_id")
    kmin = np.floor((ie.starttime - ie.e0) / H).astype("int64") + 1      # endtime_k > starttime
    kmax = np.floor((ie.endtime - ie.e0) / H).astype("int64")            # endtime_k <= endtime
    n = (kmax - kmin + 1).clip(lower=0)
    ex = pd.DataFrame({"stay_id": np.repeat(ie.stay_id.to_numpy(), n), "itemid": np.repeat(ie.itemid.to_numpy(), n),
                       "vr": np.repeat(ie.vr.to_numpy(), n)})
    nn = n.to_numpy(); starts = np.repeat(kmin.to_numpy(), nn)
    offs = np.arange(nn.sum()) - np.repeat(np.cumsum(nn) - nn, nn)
    ex["hr"] = starts + offs
    for it, nm in [(221289, "rate_epinephrine"), (221906, "rate_norepinephrine"), (221662, "rate_dopamine"),
                   (221653, "rate_dobutamine")]:
        agg_into(ex[ex.itemid == it], "vr", "max", nm)
    log("vasopressors")

    c_ = comp
    vent, novent = c_.pf_vent, c_.pf_novent
    c_["respiration"] = np.select([vent < 100, vent < 200, novent < 300, vent < 300, novent < 400, vent < 400,
                                   vent.isna() & novent.isna()], [4, 3, 2, 2, 1, 1, np.nan], default=0)
    pl = c_.platelet_min
    c_["coagulation"] = np.select([pl < 20, pl < 50, pl < 100, pl < 150, pl.isna()], [4, 3, 2, 1, np.nan], default=0)
    bi = c_.bilirubin_max
    c_["liver"] = np.select([bi >= 12, bi >= 6, bi >= 2, bi >= 1.2, bi.isna()], [4, 3, 2, 1, np.nan], default=0)
    dop, dob, epi, nor, mbp = c_.rate_dopamine, c_.rate_dobutamine, c_.rate_epinephrine, c_.rate_norepinephrine, c_.meanbp_min
    c_["cardiovascular"] = np.select(
        [(dop > 15) | (epi > 0.1) | (nor > 0.1), (dop > 5) | (epi <= 0.1) | (nor <= 0.1), (dop > 0) | (dob > 0),
         mbp < 70, mbp.isna() & dop.isna() & dob.isna() & epi.isna() & nor.isna()], [4, 3, 2, 1, np.nan], default=0)
    g = c_.gcs_min
    c_["cns"] = np.select([(g >= 13) & (g <= 14), (g >= 10) & (g <= 12), (g >= 6) & (g <= 9), g < 6, g.isna()],
                          [1, 2, 3, 4, np.nan], default=0)
    cr, u = c_.creatinine_max, c_.uo_24hr
    c_["renal"] = np.select([cr >= 5, u < 200, (cr >= 3.5) & (cr < 5), u < 500, (cr >= 2) & (cr < 3.5),
                             (cr >= 1.2) & (cr < 2), cr.isna() & u.isna()], [4, 4, 3, 3, 2, 1, np.nan], default=0)
    c_ = c_.sort_values(["stay_id", "hr"]).reset_index(drop=True)
    comps = ["respiration", "coagulation", "liver", "cardiovascular", "cns", "renal"]
    r = c_.groupby("stay_id")[comps].rolling(24, min_periods=1).max().reset_index(level=0, drop=True)
    for k in comps:
        c_[f"{k}_24hours"] = r[k].fillna(0)
    c_["sofa_24hours"] = sum(c_[f"{k}_24hours"] for k in comps)
    return c_[c_.hr >= 0]


# ---------------------------------------------------------------- sepsis3.sql
def build_sepsis3(soi, sofa):
    s = sofa[sofa.sofa_24hours >= 2][["stay_id", "endtime", "sofa_24hours"] + [f"{k}_24hours" for k in
            ["respiration", "coagulation", "liver", "cardiovascular", "cns", "renal"]]]
    q = soi[soi.stay_id.notna() & soi.suspected_infection_time.notna()].copy()
    q["stay_id"] = q["stay_id"].astype("int64")
    q["lo"] = q.suspected_infection_time - 48 * H
    q = q.sort_values("lo"); s = s.sort_values("endtime")
    m = pd.merge_asof(q, s, left_on="lo", right_on="endtime", by="stay_id", direction="forward")
    m = m[m.endtime.notna() & (m.endtime <= m.suspected_infection_time + 24 * H)]
    m = m.sort_values(["stay_id", "suspected_infection_time", "antibiotic_time", "culture_time", "endtime"],
                      na_position="first").drop_duplicates("stay_id")
    return m.rename(columns={"endtime": "sofa_time", "sofa_24hours": "sofa_score"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    cache = args.out_dir / "_cache_paper"
    cache.mkdir(parents=True, exist_ok=True)
    con = ro(args.db)

    icu = pd.read_sql("SELECT subject_id, hadm_id, stay_id, intime, outtime, los FROM icustays", con)
    icu["intime"] = pd.to_datetime(icu["intime"]); icu["outtime"] = pd.to_datetime(icu["outtime"])
    ab = cached(cache, "antibiotic", lambda: build_antibiotic(args.db, icu))
    soi = cached(cache, "suspicion", lambda: build_suspicion(args.db, ab))
    cand_ids = set(soi.loc[soi.stay_id.notna() & (soi.suspected_infection == 1), "stay_id"].astype("int64"))
    cand = icu[icu.stay_id.isin(cand_ids)]
    log(f"stays with in-ICU suspected infection: {len(cand):,}")
    subj = set(cand.subject_id)

    def _sofa():
        ce = cached(cache, "chartevents_raw", lambda: load_chartevents(args.db, cand_ids, subj))
        labs = cached(cache, "labevents_raw", lambda: load_labs(args.db, subj))
        return build_sofa(args.db, icu, cand, ce, labs, cache)
    sofa = cached(cache, "sofa", _sofa)
    s3 = build_sepsis3(soi, sofa)
    log(f"sepsis3 stays={len(s3):,}")

    adm = pd.read_sql("SELECT hadm_id, admittime, dischtime, deathtime, admission_location, hospital_expire_flag "
                      "FROM admissions", con)
    pat = pd.read_sql("SELECT subject_id, gender, anchor_age, anchor_year, anchor_year_group FROM patients", con)
    n_icu = icu.groupby("hadm_id").stay_id.size().rename("n_icu")
    s3["stay_id"] = s3["stay_id"].astype("int64")
    c = s3[["stay_id", "suspected_infection_time", "antibiotic_time", "culture_time", "sofa_time", "sofa_score"]] \
        .merge(icu, on="stay_id").merge(adm, on="hadm_id").merge(pat, on="subject_id").merge(n_icu, on="hadm_id")
    c["admittime"] = pd.to_datetime(c["admittime"])
    c["age"] = c.anchor_age + (c.admittime.dt.year - c.anchor_year)          # mimic-code age.sql
    gs = c.anchor_year_group.str[:4].astype(int)
    c["year_lb"] = gs + (c.admittime.dt.year - c.anchor_year)
    steps = [("Sepsis-3 (mimic-code)", np.ones(len(c), bool))]
    steps.append(("age >= 18", c.age >= 18))
    steps.append(("v2.2 기간 (추정 입원연도 하한 < 2020)", c.year_lb < 2020))
    steps.append(("ICU LOS >= 24h", c.los >= 1.0))
    steps.append(("입원 중 ICU 1회", c.n_icu == 1))
    keep = np.ones(len(c), bool)
    rows = []
    for nm, m in steps:
        keep &= np.asarray(m)
        rows.append({"단계": nm, "n": int(keep.sum()), "사망률%": round(100 * c.hospital_expire_flag[keep].mean(), 1)})
    flow = pd.DataFrame(rows)
    print(flow.to_string(index=False))
    out = c[keep].rename(columns={"intime": "icu_intime", "outtime": "icu_outtime", "los": "icu_los_days"})
    out = out[["subject_id", "hadm_id", "stay_id", "gender", "age", "admittime", "dischtime", "deathtime",
               "admission_location", "hospital_expire_flag", "icu_intime", "icu_outtime", "icu_los_days",
               "suspected_infection_time", "antibiotic_time", "culture_time", "sofa_time", "sofa_score",
               "anchor_year_group"]]
    out.to_csv(args.out_dir / "cohort_sepsis3_paper.csv", index=False)
    flow.to_csv(args.out_dir / "cohort_sepsis3_paper_flow.csv", index=False)
    log(f"saved cohort_sepsis3_paper.csv n={len(out):,} mortality={out.hospital_expire_flag.mean():.1%} "
        f"(논문 19,328 / 18%)")


if __name__ == "__main__":
    main()
