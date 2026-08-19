import json
from pathlib import Path

repo = Path(r"c:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro")
gold_path = repo / 'padis/rules/gold_set_smoke.json'
rules_path = repo / 'padis/outputs/padis_rules_raw.json'

gold_doc = json.loads(gold_path.read_text(encoding='utf-8'))
gold = gold_doc['gold_set']
rules = {r['rule_id']: r for r in json.loads(rules_path.read_text(encoding='utf-8'))['rules']}

existing_ids = {g['gold_id'] for g in gold}
add = [
    ('G-041','null_effect_negation','D-037','MechanicalVentilation',None,'Delirium','evidence',True,False),
    ('G-042','recommendation','D-041','CAM_ICU',None,'Delirium','recommendation',False,False),
    ('G-043','evidence','D-044','Sedation',None,'Delirium','evidence',False,False),
    ('G-044','null_effect_negation','D-050','Sedation',None,'Delirium','evidence',True,False),
    ('G-045','pending_correct','D-053','MechanicalVentilation',None,'Delirium','pending',False,False),
    ('G-046','null_effect_negation','D-062','Sedation',None,'Delirium','evidence',True,False),
    ('G-047','recommendation','D-065','Sedation',None,'Delirium','recommendation',True,False),
    ('G-048','null_effect_negation','D-067','Sedation',None,'Delirium','evidence',True,False),
    ('G-049','no_recommendation','D-068','Sedation',None,'Delirium','no_recommendation',True,False),
    ('G-050','recommendation','D-071','Sedation',None,'Delirium','recommendation',True,False),
    ('G-051','pending_correct','D-077','Agitation',None,'Delirium','pending',False,False),
    ('G-052','research_gap','D-080','MechanicalVentilation',None,'Delirium','research_gap',False,False),
    ('G-053','risk_factor_statement','D-027','BenzodiazepineExposure','increasesRiskOf','Delirium','risk_factor_statement',False,False),
    ('G-054','evidence','D-033','Sedation','increasesRiskOf','Delirium','evidence',False,False),
    ('G-055','research_gap','D-086','MechanicalVentilation',None,'Delirium','research_gap',True,False),
]
for gid,cat,rid,subj,rel,obj,stype,neg,orig in add:
    if gid in existing_ids:
        continue
    r = rules[rid]
    gold.append({
        'gold_id': gid,
        'sentence': r['source_text'],
        'expected_subject': subj,
        'expected_relation': rel,
        'expected_object': obj,
        'expected_source_type': stype,
        'expected_negation_present': neg,
        'expected_source_page': int(r['source_page']),
        'smoke_original': orig,
        'sentence_category': cat,
    })

gold_doc['version'] = 'expanded_smoke_v2'
gold_doc['description'] = '55-item balanced gold set; includes more no_recommendation and pending-correct sentences.'
gold_path.write_text(json.dumps(gold_doc, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'[gold] appended -> {len(gold)} items')
