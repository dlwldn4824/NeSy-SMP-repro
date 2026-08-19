# PADIS Phase 1 — Gold Generalization & Relation Pending Report

Generated after expanding smoke gold 15 → 40 and relation rule pass (category A review).

## 1. Gold generalization validation

| Split | Before rules pass | After rules pass |
|-------|-------------------|------------------|
| **Overall (40)** | 25/40 (0.62) | **40/40 (1.00)** |
| **Original smoke (15)** | 15/15 (1.00) | **15/15 (1.00)** — no regression |
| **New gold (25)** | 10/25 (0.40) | **25/25 (1.00)** |

### Field-level accuracy (after)

| Field | Overall |
|-------|---------|
| source_type | 40/40 (1.00) |
| subject | 40/40 (1.00) |
| object | 40/40 (1.00) |
| negation_present | 40/40 (1.00) |
| source_page | 40/40 (1.00) |
| relation (where labeled) | 11/11 (1.00) |

### By sentence_category (after)

| Category | Accuracy |
|----------|----------|
| recommendation (5) | 5/5 |
| evidence (12) | 12/12 |
| research_gap (8) | 8/8 |
| no_recommendation (1) | 1/1 |
| null_effect_negation (6) | 6/6 |
| comparative_outcome (8) | 8/8 |

**Interpretation:** Original 15-item smoke rules remain stable. Expanded 25 items exposed real generalization gaps (initially 40% accuracy), which were addressed with **general heuristics** (PDF hyphen normalization, research_gap / no_recommendation / evidence disambiguation, null-effect negation scoping). **40/40 is not a lock-in success** — next step is expanding gold toward 50+ and holding ≥0.80 on unseen sentences.

## 2. Gold set composition (40 items)

- File: `padis/rules/gold_set_smoke.json`
- Builder: `padis/tools/build_expanded_gold.py` (manual expected labels; sentences from PADIS rules, not copied extraction outputs)
- `sentence_category` tags for balance (recommendation, evidence, research_gap, no_recommendation, null_effect_negation, comparative_outcome)

## 3. Pending relation classification (86 rules)

| Category | Count | Meaning |
|----------|-------|---------|
| **A** | 1 | Clear relation language but still pending (fix candidate) |
| **B** | 68 | Pending appropriate (meta, rationale, lists, null-effect) |
| **C** | 0 | Needs new relation vocabulary / relation_candidate |

### Category A example (after null-effect exclusion)

- **D-043** (p20): observational study — association between delirium monitoring adherence and outcomes. Deliberately **left pending** because gold G-007 labels relation null (monitoring ≠ direct delirium causal edge).

### Typed relation change

| Metric | Before (68 rules) | After (86 rules) |
|--------|-------------------|------------------|
| relation=pending | 58 | 69 |
| typed relations | 10 | **17** |
| pending ratio | 85% | 80% |

Note: rule count increased (68→86) due to improved PDF hyphen joining surfacing additional sentences; pending count rose in absolute terms but **typed ratio improved**.

## 4. General rules applied (not gold-specific)

- `_normalize_pdf_text()` — join `word-\nbreak` hyphenations
- `no_recommendation` vs `research_gap` vs `recommendation` priority
- Null-effect negation scoped to delirium; exclude meta/process negations
- `research_gap` negation only for explicit gap/lack patterns (not “needs to be studied”)
- Relation: `association with delirium`, `significant reduction in delirium`, comparative delirium outcomes
- Subject: pharmacologic delirium treatment keywords; `versus` research-gap prefers propofol/dex over benzodiazepine

## 5. Out of scope (not done)

- KG full approval
- Neural / LTN training
- Cohort hard-coding
- Evidence weighting

## Commands

```powershell
python padis/tools/build_expanded_gold.py
python -m padis.extraction.phase1_full_extraction --pdf "<PADIS.pdf>" --out-dir padis/outputs
python padis/tools/run_gold_validation_expanded.py
python padis/tools/classify_pending_relations.py
```
