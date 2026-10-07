# ===== comorbidities_B.csv 결과 분석 — Colab 새 셀에 통째로 붙여넣기 (1~2분) =====
# 방식 B(doc.ents) 전체 추출이 끝난 뒤 실행한다.
#   1) 커버리지 / 유병률
#   2) 방식 A(원논문 context_graph.edges, 이미 돌린 결과)와 나란히 비교
#   3) 임상 통상 범위와 대조 -> 문제 해결됐는지 판정
#   4) comorbidities_B_wide.csv 저장 (merge_comorbidities.py 입력)

import os
import pandas as pd

DRIVE = '/content/drive/MyDrive'
NOTES = f'{DRIVE}/discharge_icu.csv.gz'
B     = f'{DRIVE}/comorbidities_B.csv'
WIDE  = f'{DRIVE}/comorbidities_B_wide.csv'

COMORBIDITIES = [
    'acute kidney injury', 'aids', 'atrial fibrillation', 'cad', 'cancer',
    'cerebrovascular accident', 'cirrhosis', 'copd', 'dementia', 'diabetes',
    'diabetes mellitus', 'heart failure', 'hiv', 'hypertension',
    'kidney disease', 'kidney failure', 'leukemia', 'lymphoma',
    'metastatic cancer', 'metastatic disease', 'peptic ulcer disease',
    'pneumonia', 'trauma',
]

# 방식 A 결과 (docs/repro/REPRO_COMORBIDITY_EXTRACTION.md 2절) — 분모는 '엔티티 1개 이상인 hadm' 28,744
A_PREV = {
    'pneumonia': 25.6, 'cad': 24.9, 'hypertension': 24.6, 'cancer': 20.0,
    'copd': 12.7, 'diabetes': 10.7, 'atrial fibrillation': 9.8, 'cirrhosis': 8.6,
    'heart failure': 7.8, 'dementia': 5.2, 'trauma': 3.7, 'diabetes mellitus': 3.3,
    'lymphoma': 2.9, 'metastatic disease': 2.7, 'kidney disease': 2.4, 'hiv': 2.0,
    'leukemia': 0.9, 'acute kidney injury': 0.5, 'peptic ulcer disease': 0.4,
    'kidney failure': 0.4, 'cerebrovascular accident': 0.4, 'aids': 0.3,
    'metastatic cancer': 0.2,
}
A_HADM_ANY, A_HADM_TOTAL, A_ENTS = 28744, None, 49137

# 임상 통상 범위 (ICU) — 문제 판정용
CLINICAL = {
    'hypertension': '50~60', 'diabetes(+mellitus)': '30~40',
    'heart failure': '20~30', 'cerebrovascular accident': '5~10',
    'acute kidney injury': '20~50',
}

# ---- 1. 로드 ----
print('B 존재:', os.path.exists(B))
b = pd.read_csv(B)
b['comorbidity'] = b['comorbidity'].str.strip().str.lower()
b = b.drop_duplicates(['hadm_id', 'comorbidity'])          # 안전장치 (이어하기 중복)

hadm_all = pd.read_csv(NOTES, compression='gzip', usecols=['hadm_id'], low_memory=False)
hadm_all = hadm_all[hadm_all.hadm_id.notna()].hadm_id.astype('int64')
N_HADM = hadm_all.nunique()
A_HADM_TOTAL = N_HADM

n_hadm_any = b.hadm_id.nunique()
print()
print('=' * 74)
print('1. 커버리지')
print('=' * 74)
print(f"{'노트 안의 고유 hadm':32s} {N_HADM:>10,}")
print(f"{'엔티티 1개 이상 hadm  (B)':32s} {n_hadm_any:>10,}  ({100*n_hadm_any/N_HADM:.1f}%)")
print(f"{'엔티티 1개 이상 hadm  (A)':32s} {A_HADM_ANY:>10,}  ({100*A_HADM_ANY/N_HADM:.1f}%)")
print(f"{'추출 엔티티 (B)':32s} {len(b):>10,}")
print(f"{'추출 엔티티 (A)':32s} {A_ENTS:>10,}   -> B/A = {len(b)/A_ENTS:.2f}배")
print(f"{'hadm 당 평균 (B, any 기준)':32s} {len(b)/max(n_hadm_any,1):>10.2f}")
print(f"{'hadm 당 평균 (A, any 기준)':32s} {A_ENTS/A_HADM_ANY:>10.2f}")
print(f"{'동반질환 하나도 없는 hadm (B)':32s} {N_HADM-n_hadm_any:>10,}  ({100*(N_HADM-n_hadm_any)/N_HADM:.1f}%)")
print(f"{'동반질환 하나도 없는 hadm (A)':32s} {N_HADM-A_HADM_ANY:>10,}  ({100*(N_HADM-A_HADM_ANY)/N_HADM:.1f}%)")

# ---- 2. 유병률 A vs B ----
cnt = b.groupby('comorbidity').hadm_id.nunique()
rows = []
for k in sorted(set(COMORBIDITIES) | set(cnt.index)):
    n = int(cnt.get(k, 0))
    rows.append({
        '동반질환': k,
        'n(B)': n,
        'B_any%': round(100 * n / max(n_hadm_any, 1), 1),   # A 와 같은 분모(any hadm)
        'B_전체%': round(100 * n / N_HADM, 1),               # 전체 hadm 분모
        'A_any%': A_PREV.get(k, float('nan')),
    })
df = pd.DataFrame(rows)
df['차이(B-A)'] = (df['B_any%'] - df['A_any%']).round(1)
df = df.sort_values('차이(B-A)', ascending=False)

print()
print('=' * 74)
print('2. 유병률 — A(원논문) vs B(doc.ents).  분모 통일: 엔티티 1개 이상인 hadm')
print('=' * 74)
print(df.to_string(index=False))

# ---- 3. 임상 통상 범위 대조 ----
def pct(name):
    return 100 * int(cnt.get(name, 0)) / max(n_hadm_any, 1)

diab = 100 * b[b.comorbidity.isin(['diabetes', 'diabetes mellitus'])].hadm_id.nunique() / max(n_hadm_any, 1)
check = {
    'hypertension': pct('hypertension'), 'diabetes(+mellitus)': diab,
    'heart failure': pct('heart failure'),
    'cerebrovascular accident': pct('cerebrovascular accident'),
    'acute kidney injury': pct('acute kidney injury'),
}
print()
print('=' * 74)
print('3. 임상 통상 범위 대조')
print('=' * 74)
print(f"{'항목':28s} {'A':>7s} {'B':>7s} {'통상(ICU)':>12s}")
for k, rng in CLINICAL.items():
    a = A_PREV.get(k, diab if k.startswith('diabetes') else float('nan'))
    if k == 'diabetes(+mellitus)':
        a = A_PREV['diabetes'] + A_PREV['diabetes mellitus']
    print(f"{k:28s} {a:>6.1f}% {check[k]:>6.1f}% {rng:>11s}%")

# ---- 4. 판정 ----
print()
print('=' * 74)
print('4. 판정')
print('=' * 74)
htn = pct('hypertension')
empty = 100 * (N_HADM - n_hadm_any) / N_HADM
if htn >= 45 and empty <= 20:
    print(f'  hypertension {htn:.1f}%, 빈 노트 {empty:.1f}% -> 원인 확정 & 해결.')
    print('  -> 3단계(merge) 로 진행한다.')
elif htn > A_PREV['hypertension'] * 1.5:
    print(f'  hypertension {A_PREV["hypertension"]:.1f}% -> {htn:.1f}% 로 개선됐으나 통상범위(50~60%)에 못 미친다.')
    print('  -> 남은 원인 후보: 노트 구조(Past Medical History 섹션 파싱), TargetRule 표기 변형("HTN" 등).')
else:
    print(f'  hypertension {htn:.1f}% — 개선폭이 작다. context_graph.edges 만이 원인은 아니다.')

# ---- 5. wide 저장 ----
w = (b.assign(v=1)
       .pivot_table(index='hadm_id', columns='comorbidity', values='v',
                    aggfunc='max', fill_value=0))
for c in COMORBIDITIES:
    if c not in w.columns:
        w[c] = 0
w = w[COMORBIDITIES].astype(int).reset_index()
w.to_csv(WIDE, index=False)
print()
print(f'저장: {WIDE}  shape={w.shape}')
