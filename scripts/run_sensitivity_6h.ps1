# 민감도 실험 (논문 조건 아님) — 논문 조건 재현 학습(run_paper_train.ps1)이 끝난 뒤 6h 로 실행
#   A  공리 조건에서 0(패딩·첫 측정 전 빈칸)을 측정 없음으로 : upstream_sensitivity_axiom (패치 S1) + 논문 조건 입력
#   B  기록 오류 극단값 제거 (mimic-code 유효 범위)        : upstream_faithful (원본 그대로) + validrange 입력
$ErrorActionPreference = 'Continue'
$py    = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$out   = 'C:\data\mimic-iv-derived'
$repo  = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$leads = Join-Path $out 'paper_leads'
$log   = Join-Path $out 'paper_repro.log'
$env:PYTHONIOENCODING = 'utf-8'
function L($m){ $t = Get-Date -Format 'HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

# 기존 로그의 FAIL 1건(17:38, 원본 코드 버그 수정 전)은 무시하고, 그 뒤 새 DONE/FAIL 을 기다린다
$failBefore = (Select-String -Path $log -Pattern 'FAIL' | Measure-Object).Count
L 'SENS WAIT for paper training'
while ($true) {
    $done = Select-String -Path $log -Pattern '^\S+ DONE$' -Quiet
    $fails = (Select-String -Path $log -Pattern 'FAIL' | Measure-Object).Count
    if ($done -or $fails -gt $failBefore) { break }
    Start-Sleep -Seconds 120
}

$runs = @(
    @{ name = 'sens_axiom_6h';      code = 'upstream_sensitivity_axiom'; data = 'events_6h_wide_paper_como.csv' },
    @{ name = 'sens_validrange_6h'; code = 'upstream_faithful';          data = 'events_6h_wide_paper_como_validrange.csv' }
)
foreach ($r in $runs) {
    $res = Join-Path $repo ("results_" + $r.name)
    New-Item -ItemType Directory -Force $res | Out-Null
    Set-Location $res
    $env:NESY_DATA = Join-Path $leads $r.data
    L ("SENS TRAIN " + $r.name)
    & $py -u (Join-Path $repo ($r.code + '\stratified_main.py')) 2>&1 | Out-File -Encoding utf8 (Join-Path $res 'train.log')
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L ("SENS OK " + $r.name) } else { L ("SENS FAILED " + $r.name) }
}
L 'SENS ALL DONE'
