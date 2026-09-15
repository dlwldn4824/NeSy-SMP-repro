# NLP 동반질환 + '기록 없음' 지시변수 arm — run_como_nlp_6h.ps1 에 note_missing 을 더한 판.
# NLP arm 에서 퇴원기록이 없는 23.4% 가 fillna(0) 로 '동반질환 없음'이 되던 문제를 모델이 구분하게 한다.
# 선행조건: Drive 의 comorbidities_B_wide.csv 를 $out 에 내려받아 둘 것.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$out  = 'C:\data\mimic-iv-derived'
$repo = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$log  = Join-Path $out 'como_nlp_nm_6h.log'
function L($m){ $t = Get-Date -Format 'HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

$como = Join-Path $out 'comorbidities_B_wide.csv'
if (-not (Test-Path $como)) { L "없음: $como  (Drive 에서 먼저 내려받을 것)"; exit 1 }

L 'MERGE 6h (+note_missing)'
Set-Location (Join-Path $repo 'data')
& $py -u merge_comorbidities.py --wide (Join-Path $out 'events_6h_wide_s3.csv') --como-wide $como --output (Join-Path $out 'events_6h_wide_s3_como_nlp_nm.csv') --note-missing-flag
if ($LASTEXITCODE -ne 0) { L "merge failed $LASTEXITCODE"; exit 1 }

L 'TRAIN 6h COMO-NLP + note_missing'
Set-Location $repo
$env:NESY_NOTE_MISSING = '1'
& $py -u reproduce_tables.py --csv (Join-Path $out 'events_6h_wide_s3_como_nlp_nm.csv') --out-dir results_s3_6h_como_nlp_nm --seed 42 --epochs 30 --epochs-nesy 15
$code = $LASTEXITCODE
if (Test-Path (Join-Path $repo 'results_s3_6h_como_nlp_nm\table1_summary.csv')) { L "OK train exit=$code" } else { L "FAIL no summary exit=$code"; exit 1 }
L 'DONE'
