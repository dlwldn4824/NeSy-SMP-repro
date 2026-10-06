# 민감도 실험 C-2 (S5) — 연결 함축에서 **혈당만 제외** (GCS·수축기혈압·호흡수·크레아티닌 4개), 6h
#   connect(S3·S4) 와의 차이는 '혈당 → 사망' 함축 한 줄뿐이다.
#   순서: connect r2 완료 대기 → (큐6 이 시작한 48h 가 있으면 중단) → connect4 6h → 안 2 48h
# 이 파일은 UTF-8 BOM 으로 저장해야 한다.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$run  = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$out  = 'C:\data\mimic-iv-derived'
$log  = Join-Path $out 'research_queue7.log'
$env:PYTHONIOENCODING = 'utf-8'
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

# ---- 1) connect r2 완료 대기 (최대 36시간)
$doneR2 = Join-Path $run 'results_sens_connect_6h_r2\stratified_results.txt'
L 'WAIT for connect r2'
$deadline = (Get-Date).AddHours(36)
while (-not (Test-Path $doneR2) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 120 }
if (-not (Test-Path $doneR2)) { L 'WARN r2 미완료 - 그래도 진행' }

# ---- 2) 큐6 이 바로 시작한 48h 가 있으면 멈춘다 (connect4 를 먼저 돌린다)
Start-Sleep -Seconds 30
$res48 = Join-Path $run 'results_sens_padisvars_48h'
$p48 = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
       Where-Object { $_.CommandLine -match 'upstream_sens_padis' }
if ($p48) {
    L 'STOP 48h (connect4 먼저) - 나중에 다시 돌린다'
    $p48 | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 30
    if (Test-Path $res48) { Remove-Item -Recurse -Force $res48 }
}

# ---- 3) connect4 6h
$res = Join-Path $run 'results_sens_connect4_6h'
if (Test-Path (Join-Path $res 'stratified_results.txt')) {
    L 'SKIP connect4 6h (already done)'
} else {
    if (Test-Path $res) { Remove-Item -Recurse -Force $res }
    New-Item -ItemType Directory -Force $res | Out-Null
    Set-Location $res
    $env:NESY_DATA = Join-Path $out 'paper_leads\events_6h_wide_paper_como.csv'
    L 'START connect4 6h (upstream_sensitivity_connect4)'
    & $py -u (Join-Path $run 'upstream_sensitivity_connect4\stratified_main.py') 2>&1 |
        Out-File -Encoding utf8 (Join-Path $res 'train.log')
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L 'OK connect4 6h' } else { L 'FAIL connect4 6h' }
}

# ---- 4) 미뤄 둔 안 2 48h
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
}
L 'QUEUE7 ALL DONE'
