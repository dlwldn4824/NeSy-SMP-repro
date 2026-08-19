from __future__ import annotations

import os
import sqlite3
from typing import List


DB_PATH = r"C:\Users\dlwld\Downloads\MIMIC4-hosp-icu.db"


def main() -> None:
    print("DB exists:", os.path.exists(DB_PATH))
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    names = [r[0] for r in cur.fetchall()]
    print("num tables:", len(names))

    keywords = ["d_items", "chartevents", "labevents", "icustays", "inputevents", "procedures", "prescriptions", "drugs", "admissions"]
    cand = [t for t in names if any(k in t.lower() for k in keywords)]
    print("candidate tables:", cand)

    tables_to_check: List[str] = [
        "d_items",
        "chartevents",
        "labevents",
        "icustays",
        "patients",
        "admissions",
        "inputevents_mv",
        "inputevents_cv",
        "procedures_icd",
        "prescriptions",
        "drgcodes",
    ]

    for table in tables_to_check:
        if table in names:
            cur.execute(f"PRAGMA table_info({table});")
            cols = [c[1] for c in cur.fetchall()]
            print(f"\n{table} columns (first 60):", cols[:60])
        else:
            # print only not found briefly
            print(f"\n{table} NOT FOUND")


if __name__ == "__main__":
    main()

