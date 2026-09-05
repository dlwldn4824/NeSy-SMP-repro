# ===== 방식 B 전체 추출 — 설치부터 끝까지 한 셀 =====
# 원 논문 코드의 context_graph.edges 대신 doc.ents 를 쓴다.
# 200건 비교에서 B 가 A 의 2.8배, hypertension 10.0% -> 56.5% 로 확인됨.
# 출력은 comorbidities_B.csv 로 따로 저장한다 (A 결과를 덮지 않는다).
#
# 셀을 한 번 돌렸는데 import 에서 실패하면 그냥 같은 셀을 한 번 더 실행한다.

import importlib, subprocess, sys

if importlib.util.find_spec("medspacy") is None:
    print("medspacy 설치 중 ... 2분쯤 걸린다", flush=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "medspacy"], check=True)
    print("설치 완료", flush=True)

# ---- 로그 끄기 (PyRuSH 가 토큰마다 DEBUG 를 쏟는다) ----
try:
    from loguru import logger
    logger.remove()
except Exception:
    pass
import logging
for _n in ["PyRuSH", "medspacy", "spacy"]:
    logging.getLogger(_n).setLevel(logging.WARNING)

import os
import time
import pandas as pd
import medspacy
from medspacy.ner import TargetRule

# ---- 드라이브 ----
try:
    from google.colab import drive
    if not os.path.exists('/content/drive/MyDrive'):
        drive.mount('/content/drive')
except Exception as e:
    print("마운트 건너뜀:", e)

DRIVE = '/content/drive/MyDrive'
NOTES = f'{DRIVE}/discharge_icu.csv.gz'
OUT = f'{DRIVE}/comorbidities_B.csv'        # ★ A 결과와 별도
CHECKPOINT_EVERY = 2000
BATCH_SIZE = 20
N_PROCESS = 1                                # 2 로 올리면 빨라지나 가끔 실패한다
LIMIT = None                                 # 시험이면 200

print("NOTES 존재:", os.path.exists(NOTES))

# ---- 파이프라인 (원 논문과 동일) ----
nlp = medspacy.load(medspacy_enable=[
    'medspacy_pyrush', 'medspacy_target_matcher',
    'medspacy_context', 'medspacy_sectionizer'])

TERMS = ['cancer', 'pneumonia', 'cirrhosis', 'dementia', 'kidney disease',
         'kidney failure', 'leukemia', 'hypertension', 'HIV', 'COPD',
         'Chronic Obstructive Pulmonary Disease', 'diabetes', 'diabetes mellitus',
         'trauma', 'coronary artery disease', 'Coronary Artery Disease', 'cad',
         'heart failure', 'atrial fibrillation', 'acute kidney injury',
         'peptic ulcer disease', 'cerebrovascular accident', 'metastatic disease',
         'metastatic cancer', 'lymphoma', 'AIDS']
nlp.get_pipe('medspacy_target_matcher').add([TargetRule(t, 'PROBLEM') for t in TERMS])
print(f'TargetRule {len(TERMS)}개 등록')

notes = pd.read_csv(NOTES, compression='gzip', low_memory=False)
notes = notes[notes.hadm_id.notna()].copy()
notes['hadm_id'] = notes['hadm_id'].astype('int64')
if LIMIT:
    notes = notes.head(LIMIT)
hadm2subject = dict(zip(notes.hadm_id, notes.subject_id))
print(f'노트 {len(notes):,}건')

# ---- 이어하기 ----
done = set()
if os.path.exists(OUT):
    try:
        done = set(pd.read_csv(OUT, usecols=['hadm_id']).hadm_id.astype('int64'))
        print(f'이어하기: {len(done):,} hadm 완료됨')
    except Exception:
        pass

todo = notes[~notes.hadm_id.isin(done)]
texts = todo['text'].astype(str).tolist()
hadms = todo['hadm_id'].tolist()
print(f'처리할 노트 {len(texts):,}건\n')

# ---- 추출 (여기만 원본과 다르다) ----
t0 = time.time()
n_ent = 0
with open(OUT, 'a' if done else 'w', encoding='utf-8') as f:
    if not done:
        f.write('subject_id,hadm_id,age,comorbidity\n')
    for i, (hadm, doc) in enumerate(
            zip(hadms, nlp.pipe(texts, batch_size=BATCH_SIZE, n_process=N_PROCESS)), 1):

        # ★ 원본: doc._.context_graph.edges  (수식어 붙은 엔티티만)
        # ★ 수정: doc.ents 전부에서 부정/가족력만 제외
        ents = set()
        for e in doc.ents:
            if getattr(e._, 'is_negated', False) or getattr(e._, 'is_family', False):
                continue
            x = e.text.lower()
            if x == 'chronic obstructive pulmonary disease':
                x = 'copd'
            elif x == 'coronary artery disease':
                x = 'cad'
            ents.add(x)

        sid = hadm2subject[hadm]
        for x in ents:
            f.write(f'{sid},{hadm},,{x}\n')
            n_ent += 1

        if i % CHECKPOINT_EVERY == 0:
            f.flush()
            os.fsync(f.fileno())
            el = time.time() - t0
            print(f'  {i:,}/{len(texts):,}  경과 {el/60:.1f}분  '
                  f'남은예상 {(len(texts)-i)*el/i/60:.0f}분  엔티티 {n_ent:,}', flush=True)

print(f'\n완료 {(time.time()-t0)/60:.1f}분 · 엔티티 {n_ent:,}개 -> {OUT}')
