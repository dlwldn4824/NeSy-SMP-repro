# 연구 큐 7(재시작) — connect4 6h 를 처음부터 다시 + 미뤄 둔 안2 48h
#   앞선 실행은 10-08 00:17 에 fold 4(마지막) 시작 직후 외부 요인으로 죽었다(fold 1~3 은 로그에 남아 있다).
#   예약 작업이 가리키던 옛 경로(scripts\run_sensitivity_connect4_6h.ps1)는 저장소 재정리로 사라져 이 파일로 대체한다.
# 이 파일은 UTF-8 BOM 으로 저장해야 한다.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$run  = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$out  = 'C:\data\mimic-iv-derived'
$log  = Join-Path $out 'research_queue7.log'
$env:PYTHONIOENCODING = 'utf-8'
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

# ---- 1) connect4 6h (죽은 실행의 로그는 _killed 로 보관)
$res = Join-Path $run 'results_sens_connect4_6h'
if (Test-Path (Join-Path $res 'stratified_results.txt')) {
    L 'SKIP connect4 6h (already done)'
} else {
    $keep = Join-Path $run 'results_sens_connect4_6h_killed_1008'
    if ((Test-Path $res) -and -not (Test-Path $keep)) { Rename-Item $res $keep }
    elseif (Test-Path $res) { Remove-Item -Recurse -Force $res }
    New-Item -ItemType Directory -Force $res | Out-Null
    Set-Location $res
    $env:NESY_DATA = Join-Path $out 'paper_leads\events_6h_wide_paper_como.csv'
    L 'START connect4 6h (재시작)'
    & $py -u (Join-Path $run 'upstream_sensitivity_connect4\stratified_main.py') 2>&1 |
        Out-File -Encoding utf8 (Join-Path $res 'train.log')
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L 'OK connect4 6h' } else { L 'FAIL connect4 6h' }
}

# ---- 2) 미뤄 둔 안 2(PADIS 변수 주입) 48h
$res48 = Join-Path $run 'results_sens_padisvars_48h'
$csv48 = Join-Path $out 'paper_leads\events_48h_wide_paper_como_padis.csv'
if ((Test-Path $csv48) -and -not (Test-Path (Join-Path $res48 'stratified_results.txt'))) {
    if (Test-Path $res48) { Remove-Item -Recurse -Force $res48 }
    New-Item -ItemType Directory -Force $res48 | Out-Null
    Set-Location $res48
    $env:NESY_DATA = $csv48
    L 'START padisvars 48h'
    & $py -u (Join-Path $run 'upstream_sens_padis\stratified_main.py') 2>&1 |
        Out-File -Encoding utf8 (Join-Path $res48 'train.log')
    if (Test-Path (Join-Path $res48 'stratified_results.txt')) { L 'OK padisvars 48h' } else { L 'FAIL padisvars 48h' }
} else { L 'SKIP padisvars 48h' }
L 'QUEUE7 ALL DONE'
