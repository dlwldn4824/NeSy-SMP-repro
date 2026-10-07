import pandas as pd
D = '/content/drive/MyDrive'
C = ['acute kidney injury','aids','atrial fibrillation','cad','cancer',
     'cerebrovascular accident','cirrhosis','copd','dementia','diabetes',
     'diabetes mellitus','heart failure','hiv','hypertension','kidney disease',
     'kidney failure','leukemia','lymphoma','metastatic cancer',
     'metastatic disease','peptic ulcer disease','pneumonia','trauma']
A = dict(zip(C, [0.5,0.3,9.8,24.9,20.0,0.4,8.6,12.7,5.2,10.7,3.3,7.8,2.0,
                 24.6,2.4,0.4,0.9,2.9,0.2,2.7,0.4,25.6,3.7]))

b = pd.read_csv(f'{D}/comorbidities_B.csv')
b['comorbidity'] = b.comorbidity.str.strip().str.lower()
b = b.drop_duplicates(['hadm_id','comorbidity'])
h = pd.read_csv(f'{D}/discharge_icu.csv.gz', compression='gzip',
                usecols=['hadm_id'], low_memory=False).hadm_id.dropna()
N, n = h.astype('int64').nunique(), b.hadm_id.nunique()

print(f'고유 hadm    {N:,}')
print(f'엔티티>=1    B {n:,} ({100*n/N:.1f}%)   A 28,744 ({100*28744/N:.1f}%)')
print(f'엔티티 수    B {len(b):,}   A 49,137   -> {len(b)/49137:.2f}배')
print(f'hadm당 평균  B {len(b)/n:.2f}   A 1.71')
print(f'빈 hadm      B {100*(N-n)/N:.1f}%   A {100*(N-28744)/N:.1f}%\n')

c = b.groupby('comorbidity').hadm_id.nunique()
t = pd.DataFrame({'n': c.reindex(C).fillna(0).astype(int)})
t['B_any%'] = (100*t.n/n).round(1)
t['B_all%'] = (100*t.n/N).round(1)
t['A_any%'] = [A[k] for k in t.index]
t['diff'] = (t['B_any%'] - t['A_any%']).round(1)
print(t.sort_values('diff', ascending=False).to_string(), '\n')

f = lambda k: 100*int(c.get(k,0))/n
dm = 100*b[b.comorbidity.isin(['diabetes','diabetes mellitus'])].hadm_id.nunique()/n
for k, a, v, r in [('hypertension',24.6,f('hypertension'),'50~60'),
                   ('diabetes(+dm)',14.0,dm,'30~40'),
                   ('heart failure',7.8,f('heart failure'),'20~30'),
                   ('cva',0.4,f('cerebrovascular accident'),'5~10'),
                   ('aki',0.5,f('acute kidney injury'),'20~50')]:
    print(f'{k:14s} A {a:5.1f}%   B {v:5.1f}%   ICU통상 {r}%')

w = b.assign(v=1).pivot_table(index='hadm_id', columns='comorbidity',
                              values='v', aggfunc='max', fill_value=0)
for x in C:
    if x not in w: w[x] = 0
w = w[C].astype(int).reset_index()
w.to_csv(f'{D}/comorbidities_B_wide.csv', index=False)
print(f'\n저장 comorbidities_B_wide.csv {w.shape}')
