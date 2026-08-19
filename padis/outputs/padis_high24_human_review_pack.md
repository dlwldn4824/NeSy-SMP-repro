# PADIS Human Review Pack — High Priority (24 items)

- Generated: 2026-08-20T00:37:05
- Source: `C:/Users/dlwld/OneDrive/Desktop/학연생/NeSy-SMP-repro/padis/outputs/padis_rules_human_review.csv`
- Filter: `review_priority = high`
- Count: 24

Instructions:
1. Compare each `source_text` against PADIS PDF original.
2. Fill reviewer fields only — **do not auto-approve in code**.
3. Use `reviewer_decision`: approve | revise_approve | reject | defer
4. Set `direct_kg_edge`: yes | no | defer (only for approve/revise_approve)

---

## 1. D-012 (page 7)

### Auto extraction
- **rule_id**: `D-012`
- **source_page**: 7
- **auto_source_type**: `recommendation`
- **auto_subject**: `OpioidExposure`
- **auto_relation**: `pending`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `no`
- **in_gold_set**: `yes`

### PADIS source_text

> If available, nefopam could be used to reduce the opioid consumption and opioid-associated side effects, such as nausea, after an evalua- tion of the risk-to-benefit ratio of all available analgesic options and patient reassessment for potential side effects (tachycardia, glaucoma, seizure, and delirium) (89–92).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 2. D-014 (page 9)

### Auto extraction
- **rule_id**: `D-014`
- **source_page**: 9
- **auto_source_type**: `pending`
- **auto_subject**: `OpioidExposure`
- **auto_relation**: `associatedWith`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `no`
- **in_gold_set**: `no`

### PADIS source_text

> The outcomes asso- ciated with opioid safety concerns such as ileus, duration of mechanical ventilation, immunosuppression, healthcare- associated infections, delirium, and both ICU and hospital LOS must be evaluated carefully.

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 3. D-015 (page 9)

### Auto extraction
- **rule_id**: `D-015`
- **source_page**: 9
- **auto_source_type**: `pending`
- **auto_subject**: `Sedation`
- **auto_relation**: `associatedWith`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `no`
- **in_gold_set**: `no`

### PADIS source_text

> This includes analysis of liver and renal toxicities secondary to acetaminophen (all routes), hemodynamic instability second- ary to IV acetaminophen (85), risk of bleeding secondary to non-COX-1–selective NSAIDs, delirium, and neurotoxicity associated with ketamine (105), and hemodynamic alterations with IV lidocaine (100).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 4. D-017 (page 14)

### Auto extraction
- **rule_id**: `D-017`
- **source_page**: 14
- **auto_source_type**: `evidence`
- **auto_subject**: `Sedation`
- **auto_relation**: `increasesRiskOf`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `yes`

### PADIS source_text

> One recent cohort study not considered in the guideline evidence demonstrates that sedation intensity (sum of negative RASS measurements by number of assessments) independently, in an escalating dose-dependent relationship, predicts increased risk of death, delirium, and delayed time to extubation (177).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 5. D-019 (page 15)

### Auto extraction
- **rule_id**: `D-019`
- **source_page**: 15
- **auto_source_type**: `recommendation`
- **auto_subject**: `BenzodiazepineExposure`
- **auto_relation**: `preferredOver`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `yes`

### PADIS source_text

> The 2013 PAD guidelines suggest (in a conditional recommendation) that nonbenzodiazepine sedatives (either propofol or dexmedetomidine) are preferable to benzodiaz- epine sedatives (either midazolam or lorazepam) in critically ill, mechanically ventilated adults because of improved short- term outcomes such as ICU LOS, duration of mechanical ventilation, and delirium (1).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 6. D-022 (page 16)

### Auto extraction
- **rule_id**: `D-022`
- **source_page**: 16
- **auto_source_type**: `evidence`
- **auto_subject**: `BenzodiazepineExposure`
- **auto_relation**: `increasesRiskOf`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `yes`

### PADIS source_text

> The study with the lowest risk of bias (n = 366), Safety and Efficacy of Dexmedetomidine Compared With Midazolam (SEDCOM), had the greatest benefit for the time to extubation (MD, –1.90 d; 95% CI, –2.32 to –1.48) and delirium (RR, 0.71; 95% CI, 0.61–0.83) with dexmedetomidine compared with a benzodiazepine infusion, and influenced how the evidence was graded when developing this recommendation (167).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 7. D-023 (page 16)

### Auto extraction
- **rule_id**: `D-023`
- **source_page**: 16
- **auto_source_type**: `evidence`
- **auto_subject**: `BenzodiazepineExposure`
- **auto_relation**: `decreasesRiskOf`
- **auto_object**: `Delirium`
- **auto_negation_present**: `True`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `yes`

### PADIS source_text

> Although the study by Xu et al (205) also showed reduced delirium with dexmedetomidine use, and the Dexmedetomidine V ersus Midazolam for Continuous Sedation in the ICU (MIDEX) study (203) demonstrated a shorter duration of mechanical ventilation with dexmedetomidine over a benzodiazepine infusion, pooled analysis of all evalu- ated studies did not show a significant benefit of dexmedeto- midine compared with a benzodiazepine infusion for duration of mechanical ventilation extubation (MD, –0.71

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 8. D-025 (page 16)

### Auto extraction
- **rule_id**: `D-025`
- **source_page**: 16
- **auto_source_type**: `evidence`
- **auto_subject**: `PropofolExposure`
- **auto_relation**: `decreasesRiskOf`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `yes`

### PADIS source_text

> A single RCT, the Propofol V ersus Dexmedetomidine for Continuous Sedation in the ICU (PRODEX) study, showed a decreased incidence of delirium with dexmedetomidine at the single time point of 48 hours after sedation cessation (203).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 9. D-027 (page 18)

### Auto extraction
- **rule_id**: `D-027`
- **source_page**: 18
- **auto_source_type**: `risk_factor_statement`
- **auto_subject**: `BenzodiazepineExposure`
- **auto_relation**: `increasesRiskOf`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `yes`

### PADIS source_text

> These events include more unplanned extubations and frequent reintubations (245, 247, 267, 268); greater unintentional device removal (268); longer ICU LOS (245); increased agitation; higher benzodiazepine, opioid, and antipsychotic medication use (244, 268); and increased risk for delirium or disorientation (257, 259, 268, 270, 271).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 10. D-030 (page 18)

### Auto extraction
- **rule_id**: `D-030`
- **source_page**: 18
- **auto_source_type**: `evidence`
- **auto_subject**: `BenzodiazepineExposure`
- **auto_relation**: `associatedWith`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `yes`

### PADIS source_text

> Ungraded Statement: For the following risk factors, strong evidence indicates that these are associated with delirium in critically ill adults: “modifiable”—benzodiazepine use and blood transfusions, and “nonmodifiable”—greater

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 11. D-031 (page 19)

### Auto extraction
- **rule_id**: `D-031`
- **source_page**: 19
- **auto_source_type**: `evidence`
- **auto_subject**: `BenzodiazepineExposure`
- **auto_relation**: `associatedWith`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `yes`

### PADIS source_text

> Benzodiazepine use and blood transfusion administration are the only two modifiable factors with strong evidence for an asso- ciation with delirium detected by screening tools (Supplemental T able 22, Supplemental Digital Content 30, http://links.lww.

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 12. D-039 (page 20)

### Auto extraction
- **rule_id**: `D-039`
- **source_page**: 20
- **auto_source_type**: `evidence`
- **auto_subject**: `CAM_ICU`
- **auto_relation**: `decreasesRiskOf`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `yes`

### PADIS source_text

> The CAM-ICU arm had a signifi- cantly lower proportion of nursing shifts with delirium and a shorter duration of delirium when compared with the period of unstructured assessments.

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 13. D-041 (page 20)

### Auto extraction
- **rule_id**: `D-041`
- **source_page**: 20
- **auto_source_type**: `recommendation`
- **auto_subject**: `CAM_ICU`
- **auto_relation**: `pending`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `no`
- **in_gold_set**: `yes`

### PADIS source_text

> In the context of the criteria needed to generate a best prac- tice statement, we felt that the benefits of widespread delirium assessment with the CAM-ICU or the ICDSC far outweigh any potential disadvantages.

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 14. D-052 (page 21)

### Auto extraction
- **rule_id**: `D-052`
- **source_page**: 21
- **auto_source_type**: `recommendation`
- **auto_subject**: `DexmedetomidineExposure`
- **auto_relation**: `pending`
- **auto_object**: `Delirium`
- **auto_negation_present**: `True`
- **kg_edge_candidate**: `no`
- **in_gold_set**: `yes`

### PADIS source_text

> Recommendation: We suggest not using haloperidol, an atypical antipsychotic, dexmedetomidine, a β-Hydroxy β-methylglutaryl-Coenzyme A (HMG-CoA) reductase inhibi- tor (i.e., statin), or ketamine to prevent delirium in all critically ill adults (conditional recommendation, very low to low qual- ity of evidence).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 15. D-054 (page 21)

### Auto extraction
- **rule_id**: `D-054`
- **source_page**: 21
- **auto_source_type**: `evidence`
- **auto_subject**: `DexmedetomidineExposure`
- **auto_relation**: `decreasesRiskOf`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `yes`

### PADIS source_text

> Each study reported a significant reduc- tion in delirium incidence favoring the pharmacologic agent: scheduled IV haloperidol (n = 457) after noncardiac surgery (RR, 0.66; 95% CI, 0.45–0.97; low quality) (366); a single dose of risperidone (n = 126) following elective cardiac surgery (RR, 0.35; 95% CI, 0.16–0.77; low quality) (366); and scheduled, low-dose dexmedetomidine (n = 700) after noncardiac surgery (odds ratio [OR], 0.35; 95% CI, 0.22–0.54; low quality) (368).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 16. D-056 (page 22)

### Auto extraction
- **rule_id**: `D-056`
- **source_page**: 22
- **auto_source_type**: `evidence`
- **auto_subject**: `DexmedetomidineExposure`
- **auto_relation**: `associatedWith`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `no`

### PADIS source_text

> Another sug- gested that nocturnal administration of low-dose dexmedeto- midine in critically ill adults with APACHE-II scores of 22 (sd, ± 7.8) was associated with a significantly greater proportion of patients who remained delirium free (80% vs 54%; p = 0.008) during their ICU stay (370).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 17. D-059 (page 22)

### Auto extraction
- **rule_id**: `D-059`
- **source_page**: 22
- **auto_source_type**: `recommendation`
- **auto_subject**: `Sedation`
- **auto_relation**: `pending`
- **auto_object**: `Delirium`
- **auto_negation_present**: `True`
- **kg_edge_candidate**: `no`
- **in_gold_set**: `no`

### PADIS source_text

> Recommendation: We suggest not using haloperidol or an atypical antipsychotic to treat subsyndromal delirium in criti- cally ill adults (conditional recommendations, very low to low quality of evidence).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 18. D-060 (page 22)

### Auto extraction
- **rule_id**: `D-060`
- **source_page**: 22
- **auto_source_type**: `evidence`
- **auto_subject**: `CAM_ICU`
- **auto_relation**: `increasesRiskOf`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `yes`

### PADIS source_text

> Duration of subsyndromal delirium when evaluated using the CAM-ICU is an independent predictor of increased odds of institutionalization (376).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 19. D-063 (page 22)

### Auto extraction
- **rule_id**: `D-063`
- **source_page**: 22
- **auto_source_type**: `evidence`
- **auto_subject**: `Sedation`
- **auto_relation**: `increasesRiskOf`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `no`

### PADIS source_text

> Risperidone (0.5 mg every 8 hr), when compared with placebo in 101 cardiac surgery patients, was associated with a reduced likelihood for a transition from subsyndromal to full- syndrome delirium (RR, 0.41; 95% CI, 0.02–0.86) (378).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 20. D-065 (page 22)

### Auto extraction
- **rule_id**: `D-065`
- **source_page**: 22
- **auto_source_type**: `recommendation`
- **auto_subject**: `Sedation`
- **auto_relation**: `pending`
- **auto_object**: `Delirium`
- **auto_negation_present**: `True`
- **kg_edge_candidate**: `no`
- **in_gold_set**: `yes`

### PADIS source_text

> Recommendation: We suggest not routinely using halo- peridol, an atypical antipsychotic, or a HMG-CoA reductase inhibitor (i.e., a statin) to treat delirium (conditional recom- mendation, low quality of evidence).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 21. D-071 (page 23)

### Auto extraction
- **rule_id**: `D-071`
- **source_page**: 23
- **auto_source_type**: `recommendation`
- **auto_subject**: `Sedation`
- **auto_relation**: `pending`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `no`
- **in_gold_set**: `yes`

### PADIS source_text

> Panel members judged that the undesirable consequences of using either haloperidol or an atypical antipsychotic far outweighed the potential benefits for most critically adults with delirium and thus issued a condi- tional recommendation against their routine use.

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 22. D-072 (page 23)

### Auto extraction
- **rule_id**: `D-072`
- **source_page**: 23
- **auto_source_type**: `recommendation`
- **auto_subject**: `DexmedetomidineExposure`
- **auto_relation**: `pending`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `no`
- **in_gold_set**: `yes`

### PADIS source_text

> Recommendation: We suggest using dexmedetomidine for delirium in mechanically ventilated adults where agitation is precluding weaning/extubation (conditional recommenda- tion, low quality of evidence).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 23. D-076 (page 24)

### Auto extraction
- **rule_id**: `D-076`
- **source_page**: 24
- **auto_source_type**: `evidence`
- **auto_subject**: `CAM_ICU`
- **auto_relation**: `decreasesRiskOf`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `maybe`
- **in_gold_set**: `yes`

### PADIS source_text

> When a revised and expanded ABCDEF bun- dle (which includes a focus on “F, ” Family engagement) was evaluated in a larger, multicenter, before-after, cohort study, and where delirium was also assessed using the CAM-ICU, an adjusted analysis showed that improvements in bundle com- pliance were significantly associated with reduced mortality and more ICU days without coma or delirium (9).

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## 24. D-078 (page 26)

### Auto extraction
- **rule_id**: `D-078`
- **source_page**: 26
- **auto_source_type**: `recommendation`
- **auto_subject**: `Sedation`
- **auto_relation**: `pending`
- **auto_object**: `Delirium`
- **auto_negation_present**: `False`
- **kg_edge_candidate**: `no`
- **in_gold_set**: `no`

### PADIS source_text

> The influence of patient condi- tions (e.g., pre-ICU functional status, delirium and sedation status, muscle wasting, and nerve and muscle dysfunction) on patient outcomes after rehabilitation/mobilization interven- tions should be examined.

### Reviewer (fill in)

- **reviewer_decision**: 
- **corrected_subject**: 
- **corrected_relation**: 
- **corrected_object**: 
- **direct_kg_edge**: 
- **reviewer_note**: 

---

## Summary tally (fill after review)

| reviewer_decision | count |
|-------------------|-------|
| approve | |
| revise_approve | |
| reject | |
| defer | |

| direct_kg_edge | count |
|----------------|-------|
| yes | |
| no | |
| defer | |
