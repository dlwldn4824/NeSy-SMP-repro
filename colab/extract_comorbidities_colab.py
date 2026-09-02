# -*- coding: utf-8 -*-
"""
동반질환 23개 추출 — Colab용.

원 논문 extract_comorbidities.py 와 동일한 규칙/로직을 쓰되 두 가지만 고쳤다.
  1) list.index() 루프 제거      원본은 노트 1건마다 전체 리스트를 훑어 O(n^2) 다.
                                 33만 건이면 사실상 끝나지 않는다. dict 조회로 바꿨다.
  2) nlp.pipe() 배치 처리        건별 nlp() 호출보다 크게 빠르다.
추출 규칙(TargetRule)과 context 필터(NEGATED_EXISTENCE / FAMILY 제외)는 원본 그대로다.

Colab 셀에 순서대로 붙여넣어 실행한다.
"""

# ===========================================================================
# [셀 1] 설치  — 약 2분. 설치 후 런타임 재시작 요구하면 재시작하고 셀 2부터.
# ===========================================================================
# !pip install -q medspacy

# ===========================================================================
# [셀 2] 드라이브 마운트 + 경로 설정
# ===========================================================================
"""
from google.colab import drive
drive.mount('/content/drive')

# 업로드한 파일 위치로 바꾼다
NOTES = '/content/drive/MyDrive/discharge_icu.csv.gz'
OUT   = '/content/drive/MyDrive/comorbidities.csv'
"""

# ===========================================================================
# [셀 3] 추출 — 아래를 통째로 붙여넣는다
# ===========================================================================
import time
import pandas as pd
import medspacy
from medspacy.ner import TargetRule

NOTES = '/content/drive/MyDrive/discharge_icu.csv.gz'
OUT = '/content/drive/MyDrive/comorbidities.csv'
CHECKPOINT_EVERY = 5000          # 중간 저장 간격 (건)

# ---- 원본과 동일한 파이프라인 ----
nlp = medspacy.load(medspacy_enable=[
    'medspacy_pyrush', 'medspacy_target_matcher',
    'medspacy_context', 'medspacy_sectionizer'])
print('pipes:', nlp.pipe_names)

# ---- 원본 extract_comorbidities.py 의 TargetRule 목록 그대로 ----
TERMS = [
    "cancer", "pneumonia", "cirrhosis", "dementia", "kidney disease",
    "kidney failure", "leukemia", "hypertension", "HIV", "COPD",
    "Chronic Obstructive Pulmonary Disease", "diabetes", "diabetes mellitus",
    "trauma", "coronary artery disease", "Coronary Artery Disease", "cad",
    "heart failure", "atrial fibrillation", "acute kidney injury",
    "peptic ulcer disease", "cerebrovascular accident", "metastatic disease",
    "metastatic cancer", "lymphoma", "AIDS",
]
nlp.get_pipe("medspacy_target_matcher").add(
    [TargetRule(t, "PROBLEM") for t in TERMS])

# ---- 노트 로드 ----
notes = pd.read_csv(NOTES, compression='gzip', low_memory=False)
notes = notes[notes.hadm_id.notna()].copy()
notes['hadm_id'] = notes['hadm_id'].astype('int64')
print(f'노트 {len(notes):,}건 / {notes.hadm_id.nunique():,} hadm')

# ---- 원본의 list.index() 대신 dict (여기가 O(n^2) 였던 곳) ----
hadm2subject = dict(zip(notes.hadm_id, notes.subject_id))

# age 는 patients 테이블에서 온다. 없으면 공란으로 두고 나중에 조인한다.
# (원본은 patients.anchor_age 를 썼다)
hadm2age = {}
try:
    pat = pd.read_csv('/content/drive/MyDrive/patients.csv.gz', compression='gzip',
                      usecols=['subject_id', 'anchor_age'])
    s2age = dict(zip(pat.subject_id, pat.anchor_age))
    hadm2age = {h: s2age.get(s, '') for h, s in hadm2subject.items()}
    print('age 조인 완료')
except Exception as e:
    print(f'[주의] patients 없음 ({type(e).__name__}). age 는 공란으로 둔다.')

texts = notes['text'].astype(str).tolist()
hadms = notes['hadm_id'].tolist()

# ---- 추출 ----
t0 = time.time()
rows = []
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('subject_id,hadm_id,age,comorbidity\n')
    for i, (hadm, doc) in enumerate(zip(hadms, nlp.pipe(texts, batch_size=20)), 1):
        # 원본과 동일: 부정/가족력 modifier 가 붙은 건 제외
        ents = {tg.text.lower() for tg, md in doc._.context_graph.edges
                if md.rule.category not in ("NEGATED_EXISTENCE", "FAMILY")}
        sid = hadm2subject[hadm]
        age = hadm2age.get(hadm, '')
        for e in ents:
            # 원본과 동일한 정규화
            if e == "chronic obstructive pulmonary disease":
                e = "copd"
            elif e == "coronary artery disease":
                e = "cad"
            f.write(f'{sid},{hadm},{age},{e}\n')
        if i % CHECKPOINT_EVERY == 0:
            f.flush()
            el = time.time() - t0
            print(f'  {i:,}/{len(texts):,}  {el/60:.1f}분 경과  '
                  f'남은 예상 {(len(texts)-i)*el/i/60:.0f}분', flush=True)
print(f'완료 {(time.time()-t0)/60:.1f}분  ->  {OUT}')

# ===========================================================================
# [셀 4] long -> wide (모델 입력 형태). 원 저장소 merge_comorbidities.py 와 호환
# ===========================================================================
"""
long = pd.read_csv(OUT)
wide = (long.assign(v=1)
            .pivot_table(index=['subject_id','hadm_id'], columns='comorbidity',
                         values='v', aggfunc='max', fill_value=0)
            .reset_index())
wide.to_csv('/content/drive/MyDrive/comorbidities_wide.csv', index=False)
print(wide.shape)
print(wide.drop(columns=['subject_id','hadm_id']).mean().sort_values(ascending=False))
"""
