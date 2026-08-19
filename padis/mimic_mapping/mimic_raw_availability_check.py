from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


DEFAULT_DB_PATH = r"C:\Users\dlwld\Downloads\MIMIC4-hosp-icu.db"


@dataclass
class VarQuery:
    name: str
    # chartevents-based or prescriptions-based
    source: str  # "chartevents" | "prescriptions"
    # d_items label/abbrev patterns (chartevents only)
    item_label_patterns: List[str]
    # prescriptions.drug patterns (prescriptions only)
    drug_patterns: List[str]


def _lower_no_space(s: str) -> str:
    return re.sub(r"\s+", "", s.lower())


def _find_itemids(cur: sqlite3.Cursor, patterns: List[str]) -> List[int]:
    """
    Match item ids via d_items.label OR d_items.abbreviation using LIKE patterns.
    Patterns are treated as raw lower-substrings.
    """
    if not patterns:
        return []
    # Use OR chain in SQL for sqlite LIKE. Keep it simple & robust.
    ors = []
    params: List[str] = []
    for p in patterns:
        ors.append("(LOWER(label) LIKE ? OR LOWER(abbreviation) LIKE ?)")
        p2 = f"%{p.lower()}%"
        params.extend([p2, p2])
    q = "SELECT DISTINCT itemid FROM d_items WHERE " + " OR ".join(ors)
    cur.execute(q, params)
    rows = cur.fetchall()
    return [int(r[0]) for r in rows]


def _query_distinct_hadm_subject_from_chartevents(
    cur: sqlite3.Cursor, itemids: List[int], adult_hadm: Set[str]
) -> Tuple[Set[str], Set[str]]:
    if not itemids:
        return set(), set()
    # Avoid huge IN lists by chunking.
    hadm_ids: Set[str] = set()
    subject_ids: Set[str] = set()
    itemids = [int(x) for x in itemids]
    chunk = 400
    for i in range(0, len(itemids), chunk):
        part = itemids[i : i + chunk]
        placeholders = ",".join(["?"] * len(part))
        # hadm_id stored as text in sqlite (from other scripts) is unknown; use string compare by casting.
        cur.execute(
            f"""
            SELECT DISTINCT CAST(hadm_id AS TEXT), CAST(subject_id AS TEXT)
            FROM chartevents
            WHERE itemid IN ({placeholders})
            """,
            part,
        )
        for hadm_id, subject_id in cur.fetchall():
            if hadm_id in adult_hadm:
                hadm_ids.add(hadm_id)
                subject_ids.add(subject_id)
    return hadm_ids, subject_ids


def _query_distinct_hadm_subject_from_prescriptions(
    cur: sqlite3.Cursor, drug_patterns: List[str], adult_hadm: Set[str]
) -> Tuple[Set[str], Set[str], int]:
    if not drug_patterns:
        return set(), set(), 0
    ors = []
    params: List[str] = []
    for p in drug_patterns:
        ors.append("LOWER(drug) LIKE ?")
        params.append(f"%{p.lower()}%")
    # We'll use two queries: counts aggregated and sets.
    # First sets:
    cur.execute(
        "SELECT DISTINCT CAST(hadm_id AS TEXT), CAST(subject_id AS TEXT) FROM prescriptions WHERE "
        + " OR ".join(ors),
        params,
    )
    hadm_ids: Set[str] = set()
    subject_ids: Set[str] = set()
    for hadm_id, subject_id in cur.fetchall():
        if hadm_id in adult_hadm:
            hadm_ids.add(hadm_id)
            subject_ids.add(subject_id)
    # second count of rows matched (optional)
    cur.execute(
        "SELECT COUNT(*) FROM prescriptions WHERE " + " OR ".join(ors),
        params,
    )
    rows_matched = int(cur.fetchone()[0])
    return hadm_ids, subject_ids, rows_matched


def _make_adult_icu_hadm_set(cur: sqlite3.Cursor) -> Set[str]:
    """
    Adult ICU admissions (hadm_id) based on icustays join patients anchor_age >= 18.
    """
    cur.execute(
        """
        SELECT DISTINCT CAST(i.hadm_id AS TEXT)
        FROM icustays i
        JOIN patients p ON p.subject_id = i.subject_id
        WHERE p.anchor_age >= 18
        """
    )
    return {str(r[0]) for r in cur.fetchall()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=Path(DEFAULT_DB_PATH))
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(args.db))
    cur = conn.cursor()

    adult_hadm = _make_adult_icu_hadm_set(cur)

    total_admissions = len(adult_hadm)

    # Variable definitions (small, Phase1)
    vars_to_check: List[VarQuery] = [
        VarQuery(
            name="RASS",
            source="chartevents",
            item_label_patterns=["rass"],
            drug_patterns=[],
        ),
        VarQuery(
            name="CAM-ICU",
            source="chartevents",
            item_label_patterns=["cam-icu", "camicu", "cam"],
            drug_patterns=[],
        ),
        VarQuery(
            name="MechanicalVentilation",
            source="chartevents",
            item_label_patterns=["mechanical ventilation", "ventilator", "ventilation"],
            drug_patterns=[],
        ),
        VarQuery(
            name="Propofol",
            source="prescriptions",
            item_label_patterns=[],
            drug_patterns=["propofol"],
        ),
        VarQuery(
            name="Dexmedetomidine",
            source="prescriptions",
            item_label_patterns=[],
            drug_patterns=["dexmedetomidine", "dexmed", "precedex"],
        ),
        VarQuery(
            name="Benzodiazepines",
            source="prescriptions",
            item_label_patterns=[],
            drug_patterns=["lorazepam", "midazolam", "diazepam", "benzodiazep"],
        ),
        VarQuery(
            name="Opioids",
            source="prescriptions",
            item_label_patterns=[],
            drug_patterns=["morphine", "fentanyl", "hydromorphone", "opioid"],
        ),
        VarQuery(
            name="HR",
            source="chartevents",
            item_label_patterns=["heart rate"],
            drug_patterns=[],
        ),
        VarQuery(
            name="RR",
            source="chartevents",
            item_label_patterns=["respiratory rate", "rr"],
            drug_patterns=[],
        ),
        VarQuery(
            name="SpO2",
            source="chartevents",
            item_label_patterns=["spo2", "oxygen saturation", "o2 sat"],
            drug_patterns=[],
        ),
        VarQuery(
            name="BP",
            source="chartevents",
            item_label_patterns=["arterial blood pressure mean", "mean arterial pressure", "arterial blood pressure", "systolic", "diastolic"],
            drug_patterns=[],
        ),
    ]

    # Compute availability sets.
    hadm_sets: Dict[str, Set[str]] = {}
    subject_sets: Dict[str, Set[str]] = {}
    details: Dict[str, dict] = {}

    for v in vars_to_check:
        if v.source == "chartevents":
            itemids = _find_itemids(cur, v.item_label_patterns)
            hadm_ids, subject_ids = _query_distinct_hadm_subject_from_chartevents(cur, itemids, adult_hadm)
            hadm_sets[v.name] = hadm_ids
            subject_sets[v.name] = subject_ids
            details[v.name] = {
                "source": v.source,
                "itemids_found": len(itemids),
                "itemids_sample": itemids[:10],
                "distinct_hadm_with_records": len(hadm_ids),
                "distinct_subject_with_records": len(subject_ids),
                "availability": "unknown",
            }
        else:
            hadm_ids, subject_ids, rows_matched = _query_distinct_hadm_subject_from_prescriptions(cur, v.drug_patterns, adult_hadm)
            hadm_sets[v.name] = hadm_ids
            subject_sets[v.name] = subject_ids
            details[v.name] = {
                "source": v.source,
                "drug_patterns": v.drug_patterns,
                "rows_matched": rows_matched,
                "distinct_hadm_with_exposure": len(hadm_ids),
                "distinct_subject_with_exposure": len(subject_ids),
                "availability": "unknown",
            }

    def _avail(hadm_count: int) -> str:
        if hadm_count == 0:
            return "unavailable"
        return "available_in_raw_mimic"

    for k, d in details.items():
        hadm_count = (
            d.get("distinct_hadm_with_records")
            if "distinct_hadm_with_records" in d
            else d.get("distinct_hadm_with_exposure")
        )
        d["availability"] = _avail(int(hadm_count or 0))

    # Intersections
    def inter(name_a: str, name_b: str) -> Set[str]:
        return hadm_sets.get(name_a, set()) & hadm_sets.get(name_b, set())

    def inter3(a: str, b: str, c: str) -> Set[str]:
        return hadm_sets.get(a, set()) & hadm_sets.get(b, set()) & hadm_sets.get(c, set())

    def inter4(a: str, b: str, c: str, d_: str) -> Set[str]:
        return hadm_sets.get(a, set()) & hadm_sets.get(b, set()) & hadm_sets.get(c, set()) & hadm_sets.get(d_, set())

    ventilation = hadm_sets.get("MechanicalVentilation", set())
    rass = hadm_sets.get("RASS", set())
    cam = hadm_sets.get("CAM-ICU", set())
    sedative = set().union(
        hadm_sets.get("Propofol", set()),
        hadm_sets.get("Dexmedetomidine", set()),
        hadm_sets.get("Benzodiazepines", set()),
    )
    sedative_with_opioid = set().union(sedative, hadm_sets.get("Opioids", set()))

    def _ratio(x: int) -> float:
        return x / max(1, total_admissions)

    coverage_summary = {
        "total_adult_icu_admissions": total_admissions,
        "mechanically_ventilated_hadm": len(ventilation),
        "mechanically_ventilated_ratio": _ratio(len(ventilation)),
        "rass_hadm": len(rass),
        "rass_ratio": _ratio(len(rass)),
        "cam_icu_hadm": len(cam),
        "cam_icu_ratio": _ratio(len(cam)),
        "ventilation_and_rass_and_cam_hadm": len(inter3("MechanicalVentilation", "RASS", "CAM-ICU")),
        "ventilation_and_rass_and_cam_ratio": _ratio(len(inter3("MechanicalVentilation", "RASS", "CAM-ICU"))),
        "sedative_exposure_hadm": len(sedative),
        "sedative_exposure_ratio": _ratio(len(sedative)),
        "ventilation_and_rass_and_cam_and_sedative_hadm": len(
            inter4("MechanicalVentilation", "RASS", "CAM-ICU", "Propofol")  # placeholder; intersections computed below
        ),
        # Compute correct final intersection using sets:
        "ventilation_and_rass_and_cam_and_sedative_any_hadm": len(ventilation & rass & cam & sedative),
        "ventilation_and_rass_and_cam_and_sedative_any_ratio": _ratio(len(ventilation & rass & cam & sedative)),
        "ventilation_and_rass_and_cam_and_sedative_plus_opioid_hadm": len(ventilation & rass & cam & sedative_with_opioid),
        "ventilation_and_rass_and_cam_and_sedative_plus_opioid_ratio": _ratio(
            len(ventilation & rass & cam & sedative_with_opioid)
        ),
    }

    out_json = args.out_dir / "mimic_raw_availability.json"
    out_md = args.out_dir / "mimic_raw_availability_report.md"

    out_json.write_text(json.dumps({"coverage_summary": coverage_summary, "details": details}, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        "# MIMIC-IV raw availability (Phase 1)",
        "",
        f"DB: `{args.db}`",
        "",
        "## Coverage summary (adult ICU admissions, based on `icustays` + `patients.anchor_age>=18`)",
    ]
    for k, v in coverage_summary.items():
        md.append(f"- {k}: {v}")
    md.append("")
    md.append("## Per-variable availability")
    for name, d in details.items():
        md.append(f"- {name}: availability={d['availability']} (hadm={d.get('distinct_hadm_with_records', d.get('distinct_hadm_with_exposure'))})")
        if "itemids_sample" in d:
            md.append(f"  - itemids_found={d['itemids_found']} sample={d['itemids_sample']}")
        if "rows_matched" in d:
            md.append(f"  - rows_matched={d['rows_matched']} drug_patterns={d['drug_patterns']}")
    md.append("")

    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"[PADIS mimic raw] wrote: {out_md} and {out_json}")


if __name__ == "__main__":
    main()

