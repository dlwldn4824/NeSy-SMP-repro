# MIMIC feasibility (smoke)

This is a *light* feasibility check using the current repo's feature schema (from `NeSy-SMP/data/preprocessing.py`), not full cohort coverage.

## Counts (by rule)
- yes: 0
- partial: 0
- no: 11
- undecided: 0

## Notes
- If PADIS variables (CAM-ICU/RASS/sedatives) are absent from current schema, rules will be marked `no` or `partial`.
- After full mapping + coverage, this report should be replaced by a true cohort-level coverage analysis.
