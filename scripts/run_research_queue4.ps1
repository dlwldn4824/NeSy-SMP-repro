# 연구 큐 4 (sepsis 파이프라인) — 5순위: 안 2 를 12·24·48h 로 확장.
# Q4(6h) 가 끝나기를 기다렸다가, 결과 파일이 생기면 세 시점을 차례로 돌린다.
# 이 파일은 UTF-8 BOM 으로 저장해야 한다 (PowerShell 5.1 한글 경로).
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$repo = 'C:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro'
$run  = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$out  = 'C:\data\mimic-iv-derived'
$log  = Join-Path $out 'research_queue4.log'
$env:PYTHONIOENCODING = 'utf-8'
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'   # forrtl error(200) 방지 - 콘솔 CLOSE 로 죽는 것
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

# ---- Q4(6h) 완료 대기 (최대 48시간)
$done6 = Join-Path $run 'results_sens_padisvars_6h\stratified_results.txt'
L 'WAIT for 6h (sens_padisvars)'
$deadline = (Get-Date).AddHours(48)
while (-not (Test-Path $done6) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 300 }
if (-not (Test-Path $done6)) { L 'ABORT - 6h 결과가 없다'; exit 1 }
L 'OK 6h detected'

# ---- 12·24·48h 입력 생성 (캐시 재사용이라 빠르다)
L 'START add_padis_vars (12,24,48)'
Set-Location $run
& $py -u (Join-Path $repo 'NeSy-SMP\data\add_padis_vars.py') --leads 12,24,48 2>&1 |
    Out-File -Encoding utf8 (Join-Path $out 'q5_add_padis_vars.log')
L 'DONE add_padis_vars'

foreach ($h in 12, 24, 48) {
    $csv = Join-Path $out ("paper_leads\events_" + $h + "h_wide_paper_como_padis.csv")
    if (-not (Test-Path $csv)) { L ("SKIP " + $h + "h (csv 없음)"); continue }
    $res = Join-Path $run ("results_sens_padisvars_" + $h + "h")
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L ("SKIP " + $h + "h (완료)"); continue }
    if (Test-Path $res) { Remove-Item -Recurse -Force $res }
    New-Item -ItemType Directory -Force $res | Out-Null
    Set-Location $res
    $env:NESY_DATA = $csv
    L ("START " + $h + "h sens_padisvars")
    & $py -u (Join-Path $run 'upstream_sens_padis\stratified_main.py') 2>&1 |
        Out-File -Encoding utf8 (Join-Path $res 'train.log')
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L ("OK " + $h + "h") } else { L ("FAIL " + $h + "h") }
}
L 'QUEUE4 ALL DONE'
