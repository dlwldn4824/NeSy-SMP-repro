# -*- coding: utf-8 -*-
"""MIMIC-IV 코호트 지문 — 서로 다른 PC 의 MIMIC 이 같은 숫자를 내는지 맞춰 본다.

왜 필요한가
    2026-11-17 회의: "MIMIC-IV 를 새로 받아 사용했고, 기존 보유 데이터와 차이가 있을 수 있어
    재현 가능성 확인이 필요하다." 코호트 수가 다르면 이후 모든 비교가 어긋난다.

무엇을 재나
    `delirium/44_padis_delirium_model.py` 의 추출·앵커 코드를 **그대로 불러다** 쓴다.
    정의를 다시 적지 않으므로 모델이 보는 숫자와 어긋날 수 없다.

    원본 테이블   icustays · patients · admissions 행 수
    항목 기록     CAM-ICU(228332) · RASS(228096) 행 수와 stay 수
    코호트        성인(>=18) · ICU 재원 1일 이상 stay 수
    앵커          입실 후 0~240h 의 CAM-ICU 기록 수, 라벨(이후 24h 확정평가) 수, 양성률
    분할          환자 단위 70/20/30 으로 나눈 train · val · test 앵커 수

사용
    python NeSy-SMP/tools/audit/cohort_fingerprint.py --db <MIMIC sqlite> --work <캐시폴더>
    python NeSy-SMP/tools/audit/cohort_fingerprint.py --compare a.json b.json

캐시 폴더에 44_ 의 추출 결과가 이미 있으면 재사용한다(빠름). 없으면 DB 에서 새로 뽑는다(수 분).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODEL = ROOT / "delirium" / "44_padis_delirium_model.py"


def load_model_module(db, work):
    """44_ 를 모듈로 올린다 (main 은 실행되지 않는다)."""
    src = MODEL.read_text(encoding="utf-8")
    src = src.replace('MIMIC_DB = "C:/path/to/MIMIC4-hosp-icu.db"', f'MIMIC_DB = r"{db}"')
    src = src.replace('WORK_DIR = "padis_work"', f'WORK_DIR = r"{work}"')
    ns = {"__name__": "cohort_fingerprint_model", "__file__": str(MODEL)}
    exec(compile(src, str(MODEL), "exec"), ns)      # noqa: S102
    return ns


def table_counts(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = {}
    for t in ("icustays", "patients", "admissions"):
        out[t] = con.execute(f"select count(*) from {t}").fetchone()[0]
    for name, itemid in (("CAM-ICU(228332)", 228332), ("RASS(228096)", 228096)):
        n, s = con.execute("select count(*), count(distinct stay_id) from chartevents "
                           "where itemid = ?", (itemid,)).fetchone()
        out[name] = {"행": n, "stay": s}
    con.close()
    return out


def fingerprint(db, work):
    import numpy as np
    m = load_model_module(db, work)
    print("[1/3] 원본 테이블 세는 중…", flush=True)
    fp = {"db": str(db), "원본 테이블": table_counts(db)}

    print("[2/3] 추출·앵커 만드는 중…", flush=True)
    raw = m["extract_mimic"]()
    cam, cohort, intime, h, first, cnt = m["build_anchors"](raw)
    L = cam.labeled.to_numpy()
    fp["코호트"] = {"stay": int(len(cohort)), "환자": int(cohort.subject_id.nunique())}
    fp["앵커"] = {"전체": int(len(cam)), "라벨 있음": int(L.sum()),
                  "양성률%": round(100 * float(cam.y[L].mean()), 2),
                  "환자": int(cam.subject_id.nunique()),
                  "앵커값 P/N/U": {k: int(v) for k, v in cam.v.value_counts().items()}}

    print("[3/3] 분할 세는 중…", flush=True)
    rng = np.random.default_rng(m["SPLIT_SEED"])
    pats = cam.iloc[np.where(L)[0]].subject_id.unique(); rng.shuffle(pats)
    tr_all = set(pats[:int(len(pats) * 0.70)])
    rng2 = np.random.default_rng(m["SPLIT_SEED"] + 1)
    tr_list = np.array(sorted(tr_all)); rng2.shuffle(tr_list)
    va = set(tr_list[:int(len(tr_list) * 0.20)])
    subj = cam["subject_id"].to_numpy()
    fp["분할"] = {"train": int((np.isin(subj, list(tr_all - va)) & L).sum()),
                  "val": int((np.isin(subj, list(va)) & L).sum()),
                  "test": int((~np.isin(subj, list(tr_all)) & L).sum())}
    return fp


def show(fp):
    print(json.dumps(fp, ensure_ascii=False, indent=2))


def compare(a_path, b_path):
    a = json.loads(Path(a_path).read_text(encoding="utf-8"))
    b = json.loads(Path(b_path).read_text(encoding="utf-8"))
    diff = []

    def walk(x, y, path=""):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in dict.fromkeys(list(x) + list(y)):
                walk(x.get(k), y.get(k), f"{path}/{k}" if path else k)
        elif x != y:
            diff.append((path, x, y))

    walk({k: v for k, v in a.items() if k != "db"}, {k: v for k, v in b.items() if k != "db"})
    print(f"A {a.get('db')}\nB {b.get('db')}\n")
    if not diff:
        print("두 DB 의 코호트 지문이 **완전히 같다** — 이후 비교를 그대로 진행해도 된다.")
        return
    print(f"다른 항목 {len(diff)}개")
    for p, x, y in diff:
        d = ""
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and x:
            d = f"  ({100 * (y - x) / x:+.2f}%)"
        print(f"  {p:28s} A={x}  B={y}{d}")
    print("\n앵커·분할 수가 다르면 test set 이 달라진다 → 기존 결과와 숫자를 직접 비교하면 안 된다.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", help="MIMIC-IV sqlite 파일")
    ap.add_argument("--work", default="padis_work", help="44_ 추출 캐시 폴더")
    ap.add_argument("--out", help="지문을 JSON 으로 저장할 경로")
    ap.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"))
    a = ap.parse_args()
    if a.compare:
        compare(*a.compare)
        return
    if not a.db:
        sys.exit("--db 또는 --compare 중 하나가 필요하다")
    fp = fingerprint(a.db, a.work)
    show(fp)
    if a.out:
        Path(a.out).write_text(json.dumps(fp, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n-> {a.out}")


if __name__ == "__main__":
    main()
