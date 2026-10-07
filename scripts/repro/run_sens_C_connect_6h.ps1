# 민감도 실험 C — 빠진 사망 연결 5개 추가 + 혈당 버그 수정 (S3·S4), 6h
#   코드: NeSy-SMP/variants/upstream_sensitivity_connect  (= S1 missing-aware + P6 기록 + S3 + S4)
#   입력: 논문 조건 재현 6h (events_6h_wide_paper_como.csv)
#   같은 설정 2회 (r1·r2) — 원본이 torch 시드를 고정하지 않아 실행 간 ±0.1~0.3 편차가 있다.
#   그 뒤 뒤로 미뤄 둔 안 2 의 48h 를 돌린다 (자리표시 파일 제거 후).
# 이 파일은 UTF-8 BOM 으로 저장해야 한다 (PowerShell 5.1 한글 경로).
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$run  = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$out  = 'C:\data\mimic-iv-derived'
$log  = Join-Path $out 'research_queue6.log'
$env:PYTHONIOENCODING = 'utf-8'
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

# 패혈증 학습은 메모리 때문에 한 번에 하나만 — 다른 sepsis 학습이 돌고 있으면 기다린다
$deadline = (Get-Date).AddHours(12)
while ((Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'upstream_' -and $_.PrivatePageCount -gt 10GB }) -and
       (Get-Date) -lt $deadline) {
    L 'WAIT - 다른 sepsis 학습이 메모리를 쓰고 있다'
    Start-Sleep -Seconds 300
}

foreach ($r in 'r1', 'r2') {
    $res = Join-Path $run ("results_sens_connect_6h_" + $r)
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L ("SKIP connect 6h " + $r); continue }
    if (Test-Path $res) { Remove-Item -Recurse -Force $res }
    New-Item -ItemType Directory -Force $res | Out-Null
    Set-Location $res
    $env:NESY_DATA = Join-Path $out 'paper_leads\events_6h_wide_paper_como.csv'
    L ("START connect 6h " + $r + " (upstream_sensitivity_connect)")
    & $py -u (Join-Path $run 'variants\upstream_sensitivity_connect\stratified_main.py') 2>&1 |
        Out-File -Encoding utf8 (Join-Path $res 'train.log')
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L ("OK connect 6h " + $r) }
    else { L ("FAIL connect 6h " + $r) }
}

# 뒤로 미뤄 둔 안 2 의 48h
$res48 = Join-Path $run 'results_sens_padisvars_48h'
$csv48 = Join-Path $out 'paper_leads\events_48h_wide_paper_como_padis.csv'
if (Test-Path $csv48) {
    if (Test-Path $res48) { Remove-Item -Recurse -Force $res48 }   # 자리표시 제거
    New-Item -ItemType Directory -Force $res48 | Out-Null
    Set-Location $res48
    $env:NESY_DATA = $csv48
    L 'START padisvars 48h'
    & $py -u (Join-Path $run 'upstream_sens_padis\stratified_main.py') 2>&1 |
        Out-File -Encoding utf8 (Join-Path $res48 'train.log')
    if (Test-Path (Join-Path $res48 'stratified_results.txt')) { L 'OK padisvars 48h' } else { L 'FAIL padisvars 48h' }
} else { L 'SKIP 48h (csv 없음)' }
L 'CONNECT QUEUE DONE'
