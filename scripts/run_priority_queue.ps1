# 우선순위 대기열 (2026-09-17 재편) — 현재 6h 논문 조건 학습이 끝나면 12h 로 넘어가지 않고 아래 순서로 실행
#   1 sens_axiom_6h       Missing-aware (패치 S1 + 기록 P6)            논문 조건 입력
#   2 paper_log_6h        원본 코드 재실행 (기록 P6 만 추가)           논문 조건 입력  → satisfaction 비교 기준 · 시드 미고정 편차
#   3 sens_validrange_6h  원본 코드 (기록 P6)                          극단값 제거 입력
#   4 paper 12h · 24h · 48h (원본 코드 + 기록 P6)
# 메모리 한계(프로세스당 커밋 ~29GB, 여유 ~10GB)로 동시에 하나씩만 돌린다.
$ErrorActionPreference = 'Continue'
$py    = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$out   = 'C:\data\mimic-iv-derived'
$repo  = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$leads = Join-Path $out 'paper_leads'
$log   = Join-Path $out 'paper_repro.log'
$env:PYTHONIOENCODING = 'utf-8'
function L($m){ $t = Get-Date -Format 'HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

function Stop-Tree($procId) {
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$procId" | ForEach-Object { Stop-Tree $_.ProcessId }
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}

# --- 1) 기존 run_paper_train.ps1 의 6h 가 끝나기를 기다렸다가 그 체인(12h 이후)을 멈춘다
$base = (Get-Content $log).Count
L 'QUEUE WAIT for paper 6h'
while ($true) {
    $new = Get-Content $log | Select-Object -Skip $base
    if ($new -match ' (OK|FAIL) 6h$') { break }
    Start-Sleep -Seconds 30
}
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
    Where-Object { $_.CommandLine -match 'run_paper_train\.ps1|run_sensitivity_6h\.ps1' } |
    ForEach-Object { Stop-Tree $_.ProcessId }
Start-Sleep -Seconds 5
$partial = Join-Path $repo 'results_paper_12h'
if ((Test-Path $partial) -and -not (Test-Path (Join-Path $partial 'stratified_results.txt'))) { Remove-Item -Recurse -Force $partial }
L 'QUEUE stopped old chain (12h+) after 6h'

$runs = @(
    @{ name = 'sens_axiom_6h';      code = 'upstream_sensitivity_axiom'; data = 'events_6h_wide_paper_como.csv' },
    @{ name = 'paper_log_6h';       code = 'upstream_faithful_log';      data = 'events_6h_wide_paper_como.csv' },
    @{ name = 'sens_validrange_6h'; code = 'upstream_faithful_log';      data = 'events_6h_wide_paper_como_validrange.csv' },
    @{ name = 'paper_12h';          code = 'upstream_faithful_log';      data = 'events_12h_wide_paper_como.csv' },
    @{ name = 'paper_24h';          code = 'upstream_faithful_log';      data = 'events_24h_wide_paper_como.csv' },
    @{ name = 'paper_48h';          code = 'upstream_faithful_log';      data = 'events_48h_wide_paper_como.csv' }
)
foreach ($r in $runs) {
    $res = Join-Path $repo ("results_" + $r.name)
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L ("QUEUE SKIP (done) " + $r.name); continue }
    if (Test-Path $res) { Remove-Item -Recurse -Force $res }
    New-Item -ItemType Directory -Force $res | Out-Null
    Set-Location $res
    $env:NESY_DATA = Join-Path $leads $r.data
    L ("QUEUE TRAIN " + $r.name + " (" + $r.code + ")")
    & $py -u (Join-Path $repo ($r.code + '\stratified_main.py')) 2>&1 | Out-File -Encoding utf8 (Join-Path $res 'train.log')
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L ("QUEUE OK " + $r.name) } else { L ("QUEUE FAIL " + $r.name) }
}
L 'QUEUE ALL DONE'
