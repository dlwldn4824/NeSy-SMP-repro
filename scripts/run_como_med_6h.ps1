# 약물 투여 이벤트 arm — ICD 동반질환 arm(events_6h_wide_s3_como.csv)에 inputevents 약물 투여를 넣은 판.
# 비교 대상: results_s3_6h_como (같은 입력에서 약물만 없음). 지식 규칙은 같게 --kb simple(기본값).
# 앞 GPU 작업(rolling_s12_h24)이 끝날 때까지 기다린다.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$out  = 'C:\data\mimic-iv-derived'
$repo = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$log  = Join-Path $out 'como_med_6h.log'
function L($m){ $t = Get-Date -Format 'HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

$prev = Join-Path $out 'rolling_s12_h24.log'
L 'WAIT for rolling_s12_h24'
while ($true) {
    $txt = if (Test-Path $prev) { Get-Content $prev -Raw } else { '' }
    if ($txt -match 'DONE|FAIL') { break }
    Start-Sleep -Seconds 60
}

$med = Join-Path $out 'events_6h_wide_s3_como_med.csv'
if (-not (Test-Path $med)) {
    L 'BUILD medication events'
    Set-Location (Join-Path $repo 'data')
    & $py -u add_medication_events.py --wide (Join-Path $out 'events_6h_wide_s3_como.csv') --cohort (Join-Path $out 'cohort_sepsis3_paperlike.csv') --db 'C:\Users\dlwld\Downloads\MIMIC4-hosp-icu.db' --output $med
    if ($LASTEXITCODE -ne 0) { L "build failed $LASTEXITCODE"; exit 1 }
}

L 'TRAIN 6h ICD + medication'
Set-Location $repo
Remove-Item Env:NESY_NOTE_MISSING -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING = 'utf-8'
& $py -u reproduce_tables.py --csv $med --out-dir results_s3_6h_como_med --seed 42 --epochs 30 --epochs-nesy 15
$code = $LASTEXITCODE
if (Test-Path (Join-Path $repo 'results_s3_6h_como_med\table1_summary.csv')) { L "OK train exit=$code" } else { L "FAIL no summary exit=$code"; exit 1 }
L 'DONE'
