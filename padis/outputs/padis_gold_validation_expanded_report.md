# Gold validation (expanded set)

- total gold items: 55

## Overall
- exact match: 50/55 (0.91)
- source_type accuracy: 52/55 (0.95)
- subject accuracy: 55/55 (1.00)
- object accuracy: 55/55 (1.00)
- negation_present accuracy: 53/55 (0.96)
- source_page accuracy: 55/55 (1.00)
- relation accuracy: 12/13 (0.92)
- mismatches: G-046, G-048, G-049, G-050, G-054
  - G-046 (null_effect_negation): source_type: exp='evidence' got='risk_factor_statement'
  - G-048 (null_effect_negation): negation_present: exp=True got=False
  - G-049 (no_recommendation): source_type: exp='no_recommendation' got='evidence'
  - G-050 (recommendation): negation_present: exp=True got=False
  - G-054 (evidence): source_type: exp='evidence' got='pending'; relation: exp='increasesRiskOf' got='pending'

## Original smoke (15)
- exact match: 15/15 (1.00)
- source_type accuracy: 15/15 (1.00)
- subject accuracy: 15/15 (1.00)
- object accuracy: 15/15 (1.00)
- negation_present accuracy: 15/15 (1.00)
- source_page accuracy: 15/15 (1.00)
- relation accuracy: 7/7 (1.00)

## New gold (40)
- exact match: 35/40 (0.88)
- source_type accuracy: 37/40 (0.93)
- subject accuracy: 40/40 (1.00)
- object accuracy: 40/40 (1.00)
- negation_present accuracy: 38/40 (0.95)
- source_page accuracy: 40/40 (1.00)
- relation accuracy: 5/6 (0.83)
- mismatches: G-046, G-048, G-049, G-050, G-054
  - G-046 (null_effect_negation): source_type: exp='evidence' got='risk_factor_statement'
  - G-048 (null_effect_negation): negation_present: exp=True got=False
  - G-049 (no_recommendation): source_type: exp='no_recommendation' got='evidence'
  - G-050 (recommendation): negation_present: exp=True got=False
  - G-054 (evidence): source_type: exp='evidence' got='pending'; relation: exp='increasesRiskOf' got='pending'

## By sentence_category
- comparative_outcome: 8/8 (1.00)
- evidence: 13/14 (0.93)
- no_recommendation: 1/2 (0.50)
- null_effect_negation: 8/10 (0.80)
- pending_correct: 2/2 (1.00)
- recommendation: 7/8 (0.88)
- research_gap: 10/10 (1.00)
- risk_factor_statement: 1/1 (1.00)
