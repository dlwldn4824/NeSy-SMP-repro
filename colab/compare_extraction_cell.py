# ===== 추출 방식 비교 — Colab 새 셀에 통째로 붙여넣고 실행 (몇 분) =====
# 같은 노트 200건을 두 방식으로 뽑아 비교한다.
#   방식 A (현재/원논문) : context_graph.edges  — 수식어가 붙은 엔티티만
#   방식 B (대안)        : doc.ents            — 찾은 엔티티 전부에서 부정/가족력만 제외

from loguru import logger
logger.remove()
import logging
for n in ["PyRuSH", "medspacy", "spacy"]:
    logging.getLogger(n).setLevel(logging.WARNING)

import time
import collections
import pandas as pd
import medspacy
from medspacy.ner import TargetRule

NOTES = '/content/drive/MyDrive/discharge_icu.csv.gz'
N = 200

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

notes = pd.read_csv(NOTES, compression='gzip', low_memory=False).head(N)
texts = notes['text'].astype(str).tolist()
print(f'비교 대상 {len(texts)}건\n')


def norm(e):
    e = e.lower()
    if e == 'chronic obstructive pulmonary disease':
        return 'copd'
    if e == 'coronary artery disease':
        return 'cad'
    return e


t0 = time.time()
cntA = collections.Counter()   # 방식 A 가 잡은 것
cntB = collections.Counter()   # 방식 B 가 잡은 것
nA = nB = 0                    # 총 엔티티 수
zeroA = zeroB = 0              # 하나도 못 뽑은 노트 수
onlyB_ex = []                  # B 만 잡은 실제 문맥 예시

for doc in nlp.pipe(texts, batch_size=20):
    # --- 방식 A : 수식어가 붙은 엔티티만 ---
    A = {norm(tg.text) for tg, mod in doc._.context_graph.edges
         if mod.rule.category not in ('NEGATED_EXISTENCE', 'FAMILY')}

    # --- 방식 B : 찾은 엔티티 전부에서 부정/가족력만 제외 ---
    B = set()
    for e in doc.ents:
        neg = getattr(e._, 'is_negated', False)
        fam = getattr(e._, 'is_family', False)
        if not (neg or fam):
            B.add(norm(e.text))

    cntA.update(A); cntB.update(B)
    nA += len(A);   nB += len(B)
    if not A: zeroA += 1
    if not B: zeroB += 1

    # B 만 잡은 것의 문맥을 몇 개 모아둔다
    if len(onlyB_ex) < 8:
        for e in doc.ents:
            if norm(e.text) in (B - A):
                s = max(e.start_char - 60, 0)
                onlyB_ex.append(f"[{norm(e.text)}]  ...{doc.text[s:e.end_char+40]}...".replace('\n', ' '))
                break

print(f'처리 {time.time()-t0:.0f}초\n')
print('=' * 72)
print(f"{'':26s} {'방식 A (현재)':>14s} {'방식 B (대안)':>14s}")
print(f"{'노트당 평균 엔티티':26s} {nA/len(texts):>14.2f} {nB/len(texts):>14.2f}")
print(f"{'엔티티 0개인 노트':26s} {100*zeroA/len(texts):>13.1f}% {100*zeroB/len(texts):>13.1f}%")
print(f"{'고유 동반질환 종류':26s} {len(cntA):>14d} {len(cntB):>14d}")

print('\n' + '=' * 72)
print('동반질환별 보유 노트 비율 (%)   — 차이 큰 순')
rows = []
for k in sorted(set(cntA) | set(cntB)):
    a = 100 * cntA[k] / len(texts)
    b = 100 * cntB[k] / len(texts)
    rows.append((k, round(a, 1), round(b, 1), round(b - a, 1)))
df = pd.DataFrame(rows, columns=['동반질환', 'A_현재', 'B_대안', '차이']) \
       .sort_values('차이', ascending=False)
print(df.to_string(index=False))

print('\n' + '=' * 72)
print('B 만 잡은 엔티티의 실제 문맥 (A 가 놓친 것)')
for x in onlyB_ex:
    print('  ' + x[:150])

print('\n' + '=' * 72)
print('판정')
if nB > nA * 1.3:
    print(f'  B 가 A 의 {nB/max(nA,1):.1f}배. context_graph.edges 가 원인으로 확정.')
    print('  -> 추출 방식을 doc.ents 기준으로 바꾸고 재실행할 것.')
elif nB > nA * 1.05:
    print(f'  B 가 A 의 {nB/max(nA,1):.1f}배. 차이는 있으나 크지 않다.')
    print('  -> 낮은 유병률의 다른 원인도 함께 확인할 것.')
else:
    print('  두 방식이 비슷하다. context_graph.edges 는 원인이 아니다.')
    print('  -> TargetRule 매칭 자체 또는 노트 구조를 확인할 것.')
