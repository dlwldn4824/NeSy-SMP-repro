# 연구 큐 (2026-10-03 교수님 피드백 대응) — 순서대로 하나씩. 창 없이 돌고 세션이 끝나도 유지된다.
#   Q1 eda/29  안 1: 결과를 원내 사망·7일 사망으로 교체 (섬망 = 중간 개념)
#   Q2 eda/30  KG 범위별(합의/조건별/합집합/사람) 공리 비교
#   Q3 PADIS 변수 추출·병합 (sepsis 코호트, 6h)
#   Q4 안 2: sepsis 사망 예측에 PADIS 변수 추가 (upstream_sens_padis)
# 로그: C:\data\mimic-iv-derived\research_queue.log
# 주의: 이 파일은 UTF-8 BOM 으로 저장해야 한다 (PowerShell 5.1 이 한글 경로를 깨뜨리지 않도록).
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$repo = 'C:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro'
$run  = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$out  = 'C:\data\mimic-iv-derived'
$log  = Join-Path $out 'research_queue.log'
$env:PYTHONIOENCODING = 'utf-8'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

# ---------------- Q1 · Q2 : 섬망 코호트 (로컬 GPU, 1~2시간) ----------------
$env:EDA_DATA = Join-Path $repo 'notes\eda'
$env:EDA_OUT  = 'C:\data\padis_eda_out'
foreach ($q in @(
    @{ id = 'Q1 29_outcome_mortality'; script = 'eda\29_outcome_mortality.py'; log = 'q1_29.log' },
    @{ id = 'Q2 30_kg_variants';       script = 'eda\30_kg_variants.py';       log = 'q2_30.log' })) {
    L ("START " + $q.id)
    Set-Location $repo
    & $py -u (Join-Path $repo $q.script) --seeds 42,7,2024 --epochs 10 2>&1 |
        Out-File -Encoding utf8 (Join-Path $env:EDA_OUT $q.log)
    if ($LASTEXITCODE -eq 0) { L ("OK " + $q.id) } else { L ("FAIL " + $q.id + " exit=" + $LASTEXITCODE) }
}

# ---------------- Q3 : PADIS 변수 추출·병합 (sepsis 코호트) ----------------
L 'START Q3 add_padis_vars (6h)'
Set-Location $run
& $py -u (Join-Path $repo 'NeSy-SMP\data\add_padis_vars.py') --leads 6 2>&1 |
    Out-File -Encoding utf8 (Join-Path $out 'q3_add_padis_vars.log')
$padisCsv = Join-Path $out 'paper_leads\events_6h_wide_paper_como_padis.csv'
if (Test-Path $padisCsv) { L 'OK Q3' } else { L 'FAIL Q3 (csv missing) - skip Q4' }

# ---------------- Q4 : 안 2 학습 (sepsis 6h + PADIS 변수) ----------------
if (Test-Path $padisCsv) {
    $res = Join-Path $run 'results_sens_padisvars_6h'
    if (Test-Path (Join-Path $res 'stratified_results.txt')) {
        L 'SKIP Q4 (already done)'
    } else {
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
L 'QUEUE ALL DONE'
