# 연구 큐 6 — 패혈증: 빠진 연결 5개 추가(S4) 실험을 48h 보다 먼저 돌린다.
#   1) 안 2 의 24h 가 끝나기를 기다린다 (패혈증 학습은 메모리 때문에 한 번에 하나만)
#   2) S4 fullchain 6h : 결측 처리 수정(S1) + GCS·호흡수·수축기혈압·크레아티닌·평균혈압 → 사망 함축 추가
#   3) 그 뒤에 안 2 의 48h
# 이 파일은 UTF-8 BOM 으로 저장해야 한다.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$run  = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$out  = 'C:\data\mimic-iv-derived'
$log  = Join-Path $out 'research_queue6.log'
$env:PYTHONIOENCODING = 'utf-8'
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

# ---- 1) 24h 완료 대기 (최대 12시간)
$done24 = Join-Path $run 'results_sens_padisvars_24h\stratified_results.txt'
L 'WAIT for padisvars 24h'
$deadline = (Get-Date).AddHours(12)
while (-not (Test-Path $done24) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 60 }
if (-not (Test-Path $done24)) { L 'WARN 24h 미완료 - 그래도 진행' }
Start-Sleep -Seconds 60     # 24h 프로세스가 메모리를 놓을 시간

# ---- 2) S4 fullchain 6h (논문 조건 입력)
$res = Join-Path $run 'results_sens_fullchain_6h'
if (Test-Path (Join-Path $res 'stratified_results.txt')) {
    L 'SKIP S4 fullchain 6h (already done)'
} else {
    if (Test-Path $res) { Remove-Item -Recurse -Force $res }
    New-Item -ItemType Directory -Force $res | Out-Null
    Set-Location $res
    $env:NESY_DATA = Join-Path $out 'paper_leads\events_6h_wide_paper_como.csv'
    # 변형 폴더는 실행 클론(평평한 upstream_*)과 저장소(variants 하위) 양쪽에 있을 수 있다
    $v = Join-Path $run 'upstream_sens_fullchain\stratified_main.py'
    if (-not (Test-Path $v)) { $v = Join-Path $run 'variants\upstream_sens_fullchain\stratified_main.py' }
    L 'START S4 fullchain 6h (폐기된 MAP 설계 — 기록용. 실제 실험은 upstream_sensitivity_connect)'
    & $py -u $v 2>&1 |
        Out-File -Encoding utf8 (Join-Path $res 'train.log')
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L 'OK S4 fullchain 6h' } else { L 'FAIL S4 fullchain 6h' }
}

# ---- 3) 뒤로 미뤄 둔 안 2 의 48h (자리표시 파일 제거 후 실행)
$res48 = Join-Path $run 'results_sens_padisvars_48h'
$csv48 = Join-Path $out 'paper_leads\events_48h_wide_paper_como_padis.csv'
if (Test-Path $csv48) {
    if (Test-Path $res48) { Remove-Item -Recurse -Force $res48 }
    New-Item -ItemType Directory -Force $res48 | Out-Null
    Set-Location $res48
    $env:NESY_DATA = $csv48
    L 'START padisvars 48h'
    & $py -u (Join-Path $run 'upstream_sens_padis\stratified_main.py') 2>&1 |
        Out-File -Encoding utf8 (Join-Path $res48 'train.log')
    if (Test-Path (Join-Path $res48 'stratified_results.txt')) { L 'OK padisvars 48h' } else { L 'FAIL padisvars 48h' }
} else {
    L 'SKIP 48h (csv 없음)'
}
L 'QUEUE6 ALL DONE'
