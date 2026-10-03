# 연구 큐 2 — Q3(PADIS 변수 추출·병합) · Q4(안 2 학습) 만. Q1·Q2 는 2026-10-03 완료.
# 이 파일은 UTF-8 BOM 으로 저장해야 한다 (PowerShell 5.1 한글 경로).
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$repo = 'C:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro'
$run  = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$out  = 'C:\data\mimic-iv-derived'
$log  = Join-Path $out 'research_queue.log'
$env:PYTHONIOENCODING = 'utf-8'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

$padisCsv = Join-Path $out 'paper_leads\events_6h_wide_paper_como_padis.csv'
if (-not (Test-Path $padisCsv)) {
    L 'START Q3 add_padis_vars (6h) [retry]'
    Set-Location $run
    & $py -u (Join-Path $repo 'NeSy-SMP\data\add_padis_vars.py') --leads 6 2>&1 |
        Out-File -Encoding utf8 (Join-Path $out 'q3_add_padis_vars.log')
    if (Test-Path $padisCsv) { L 'OK Q3' } else { L 'FAIL Q3 (csv missing)' }
}
if (Test-Path $padisCsv) {
    $res = Join-Path $run 'results_sens_padisvars_6h'
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L 'SKIP Q4 (already done)' }
    else {
        if (Test-Path $res) { Remove-Item -Recurse -Force $res }
        New-Item -ItemType Directory -Force $res | Out-Null
        Set-Location $res
        $env:NESY_DATA = $padisCsv
        L 'START Q4 sens_padisvars_6h (upstream_sens_padis)'
        & $py -u (Join-Path $run 'upstream_sens_padis\stratified_main.py') 2>&1 |
            Out-File -Encoding utf8 (Join-Path $res 'train.log')
        if (Test-Path (Join-Path $res 'stratified_results.txt')) { L 'OK Q4' } else { L 'FAIL Q4' }
    }
}
L 'QUEUE2 ALL DONE'
