# 연구 큐 12 — 패혈증 슬롯: D4(논문 §4.5 목록대로 LowMAP 추가) -> D6(데이터 비율) -> D7(반복)
#   패혈증 학습은 메모리(약 26GB) 때문에 한 번에 하나만 돌린다. 큐 7(connect4 -> PADIS 48h) 뒤에 이어 붙는다.
# 이 파일은 UTF-8 BOM 으로 저장해야 한다.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$run  = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$out  = 'C:\data\mimic-iv-derived'
$log  = Join-Path $out 'research_queue12.log'
$env:PYTHONIOENCODING = 'utf-8'
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

function Wait-NoSepsisTrain {
    # 다른 패혈증 학습이 돌고 있으면 끝날 때까지 기다린다 (최대 48시간)
    $deadline = (Get-Date).AddHours(48)
    while ((Get-Date) -lt $deadline) {
        $p = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
             Where-Object { $_.CommandLine -match 'stratified_main\.py' }
        if (-not $p) { return }
        Start-Sleep -Seconds 180
    }
    L 'WARN 대기 시간 초과 - 그래도 진행'
}

function Run-Sepsis($name, $variant, $csv, $resdir) {
    $res = Join-Path $run $resdir
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L "SKIP $name (already done)"; return }
    Wait-NoSepsisTrain
    Start-Sleep -Seconds 60
    if (Test-Path $res) { Remove-Item -Recurse -Force $res }
    New-Item -ItemType Directory -Force $res | Out-Null
    Set-Location $res
    $env:NESY_DATA = $csv
    $v = Join-Path $run ($variant + '\stratified_main.py')
    if (-not (Test-Path $v)) { $v = Join-Path $run ('variants\' + $variant + '\stratified_main.py') }
    L "START $name ($variant)"
    & $py -u $v 2>&1 | Out-File -Encoding utf8 (Join-Path $res 'train.log')
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L "OK $name" } else { L "FAIL $name" }
}

# ---- D4) 논문 §4.5 목록대로 LowMAP 을 Anchor+함축으로 추가, 6h
Run-Sepsis 'D4 MAP 6h' 'upstream_sens_map' (Join-Path $out 'paper_leads\events_6h_wide_paper_como.csv') 'results_sens_map_6h'

# ---- D6) 학습 데이터 비율 (10% -> 5% -> 1%). 데이터가 적을 때 지식이 돕는지
foreach ($f in '0.10','0.05','0.01') {
    $env:NESY_SUBSET = $f
    $tag = 'results_sens_subset_' + ($f -replace '0\.','p') + '_6h'
    Run-Sepsis ("D6 학습셋 " + ([double]$f * 100) + "% 6h") 'upstream_sens_subset' (Join-Path $out 'paper_leads\events_6h_wide_paper_como.csv') $tag
}
Remove-Item Env:\NESY_SUBSET -ErrorAction SilentlyContinue

# ---- D7) 변동 확인: 같은 코드(원본)로 12h·24h·48h 재실행 (r2)
foreach ($h in 12,24,48) {
    Run-Sepsis "D7 원본 ${h}h r2" 'upstream_faithful_log' (Join-Path $out ("paper_leads\events_${h}h_wide_paper_como.csv")) ("results_paper_${h}h_r2")
}
L 'QUEUE12 ALL DONE'
