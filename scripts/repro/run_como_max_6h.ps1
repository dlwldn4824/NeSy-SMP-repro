# 최대 근접 arm — 원본에 맞출 수 있는 입력 차이를 전부 맞춘 판.
#   ICD 동반질환 arm 입력 + 빠진 검사 5종·admission_type (add_missing_inputs.py)
#                       + 약물 투여 이벤트 (add_medication_events.py)
#   + 원본 지식 규칙 (--kb upstream), 모델 5종 전부
# 여전히 못 맞추는 것: 코호트 목록 · 원본 이벤트 로그 구성 · 노트/병합 · 생존자 창 난수.
# 앞 GPU 작업(como_med_6h)이 끝날 때까지 기다린다.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$out  = 'C:\data\mimic-iv-derived'
$repo = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$db   = 'C:\Users\dlwld\Downloads\MIMIC4-hosp-icu.db'
$log  = Join-Path $out 'como_max_6h.log'
function L($m){ $t = Get-Date -Format 'HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }
$env:PYTHONIOENCODING = 'utf-8'

$filled = Join-Path $out 'events_6h_wide_s3_como_filled.csv'
$max    = Join-Path $out 'events_6h_wide_s3_como_max.csv'
Set-Location (Join-Path $repo 'data')
if (-not (Test-Path $filled)) {
    L 'BUILD missing inputs'
    & $py -u add_missing_inputs.py --wide (Join-Path $out 'events_6h_wide_s3_como.csv') --cohort (Join-Path $out 'cohort_sepsis3_paperlike.csv') --db $db --output $filled --cache (Join-Path $out 'missing_inputs_events.csv')
    if ($LASTEXITCODE -ne 0) { L "build missing failed $LASTEXITCODE"; exit 1 }
}
if (-not (Test-Path $max)) {
    L 'BUILD medication events on filled'
    & $py -u add_medication_events.py --wide $filled --cohort (Join-Path $out 'cohort_sepsis3_paperlike.csv') --db $db --output $max
    if ($LASTEXITCODE -ne 0) { L "build med failed $LASTEXITCODE"; exit 1 }
}

$prev = Join-Path $out 'como_med_6h.log'
L 'WAIT for como_med_6h'
while ($true) {
    $txt = if (Test-Path $prev) { Get-Content $prev -Raw } else { '' }
    if ($txt -match 'DONE|FAIL') { break }
    Start-Sleep -Seconds 60
}

L 'TRAIN 6h max-fidelity (--kb upstream)'
Set-Location $repo
Remove-Item Env:NESY_NOTE_MISSING -ErrorAction SilentlyContinue
& $py -u reproduce_tables.py --csv $max --out-dir results_s3_6h_como_max --seed 42 --epochs 30 --epochs-nesy 15 --kb upstream
$code = $LASTEXITCODE
if (Test-Path (Join-Path $repo 'results_s3_6h_como_max\table1_summary.csv')) { L "OK train exit=$code" } else { L "FAIL no summary exit=$code"; exit 1 }
L 'DONE'
