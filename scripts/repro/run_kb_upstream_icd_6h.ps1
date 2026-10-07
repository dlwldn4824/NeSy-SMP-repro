# NeSy 지식 규칙을 원본 stratified_main.py 와 똑같이 맞춘 재학습 (--kb upstream).
# 입력은 ICD 동반질환 arm 과 같다 — 만성질환 규칙이 동반질환을 쓰므로 0 arm 이 아니라 ICD arm 으로 비교한다.
# RF/XGB/BiLSTM/LTN 은 지식 규칙과 무관해 results_s3_6h_como 결과를 그대로 쓰고 NeSy-SMP 만 학습한다.
# 앞 작업(como_nlp_nm_6h)이 GPU 를 쓰는 동안에는 기다린다.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$out  = 'C:\data\mimic-iv-derived'
$repo = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$log  = Join-Path $out 'kb_upstream_icd_6h.log'
function L($m){ $t = Get-Date -Format 'HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

$prev = Join-Path $out 'como_nlp_nm_6h.log'
L 'WAIT for como_nlp_nm_6h'
while ($true) {
    $txt = if (Test-Path $prev) { Get-Content $prev -Raw } else { '' }
    if ($txt -match 'DONE|FAIL|merge failed') { break }
    Start-Sleep -Seconds 60
}

L 'TRAIN 6h ICD NeSy-SMP --kb upstream'
Set-Location $repo
Remove-Item Env:NESY_NOTE_MISSING -ErrorAction SilentlyContinue
& $py -u reproduce_tables.py --csv (Join-Path $out 'events_6h_wide_s3_como.csv') --out-dir results_s3_6h_como_kbup --seed 42 --epochs 30 --epochs-nesy 15 --kb upstream --only-nesy
$code = $LASTEXITCODE
if (Test-Path (Join-Path $repo 'results_s3_6h_como_kbup\table1_summary.csv')) { L "OK train exit=$code" } else { L "FAIL no summary exit=$code"; exit 1 }
L 'DONE'
