# 논문 재현 — 학습만 (run_paper_repro.ps1 의 6단계). 데이터는 이미 C:\data\mimic-iv-derived\paper_leads 에 있음.
# 원본 stratified_main.py + 패치 5개 (upstream_faithful/PATCHES.md), 기본 epoch 50/20.
$ErrorActionPreference = 'Continue'
$py    = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$out   = 'C:\data\mimic-iv-derived'
$repo  = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$leads = Join-Path $out 'paper_leads'
$log   = Join-Path $out 'paper_repro.log'
$env:PYTHONIOENCODING = 'utf-8'
function L($m){ $t = Get-Date -Format 'HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

foreach ($h in 6, 12, 24, 48) {
    $res = Join-Path $repo "results_paper_${h}h"
    New-Item -ItemType Directory -Force $res | Out-Null
    Set-Location $res
    $env:NESY_DATA = Join-Path $leads "events_${h}h_wide_paper_como.csv"
    L "TRAIN ${h}h (upstream stratified_main.py, 50/20)"
    & $py -u (Join-Path $repo 'upstream_faithful\stratified_main.py') 2>&1 | Out-File -Encoding utf8 (Join-Path $res 'train.log')
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L "OK ${h}h" } else { L "FAIL ${h}h"; exit 1 }
}
L 'DONE'
