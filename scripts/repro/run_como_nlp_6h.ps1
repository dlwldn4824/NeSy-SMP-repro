# NLP(방식 B) 동반질환 arm — run_como_6h.ps1 의 ICD 판을 NLP 로 바꾼 것.
# 선행조건: Drive 의 comorbidities_B_wide.csv 를 $out 에 내려받아 둘 것.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$out  = 'C:\data\mimic-iv-derived'
$repo = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$log  = Join-Path $out 'como_nlp_6h.log'
function L($m){ $t = Get-Date -Format 'HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

$como = Join-Path $out 'comorbidities_B_wide.csv'
if (-not (Test-Path $como)) { L "없음: $como  (Drive 에서 먼저 내려받을 것)"; exit 1 }

L 'COVERAGE CHECK'
& $py -c @"
import pandas as pd
w = pd.read_csv(r'$out\events_6h_wide_s3.csv', usecols=['hadm_id'], low_memory=False)
c = pd.read_csv(r'$como', usecols=['hadm_id'])
h = set(w.hadm_id.astype('int64')); k = set(c.hadm_id.astype('int64'))
print(f'코호트 hadm {len(h):,} · NLP 보유 {len(h & k):,} ({100*len(h & k)/len(h):.1f}%)')
"@

L 'MERGE 6h'
Set-Location (Join-Path $repo 'data')
& $py -u merge_comorbidities.py --wide (Join-Path $out 'events_6h_wide_s3.csv') --como-wide $como --output (Join-Path $out 'events_6h_wide_s3_como_nlp.csv')
if ($LASTEXITCODE -ne 0) { L "merge failed $LASTEXITCODE"; exit 1 }

L 'TRAIN 6h COMO-NLP'
Set-Location $repo
& $py -u reproduce_tables.py --csv (Join-Path $out 'events_6h_wide_s3_como_nlp.csv') --out-dir results_s3_6h_como_nlp --seed 42 --epochs 30 --epochs-nesy 15
$code = $LASTEXITCODE
if (Test-Path (Join-Path $repo 'results_s3_6h_como_nlp\table1_summary.csv')) { L "OK train exit=$code" } else { L "FAIL no summary exit=$code"; exit 1 }
L 'DONE'
