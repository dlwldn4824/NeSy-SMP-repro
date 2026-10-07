# Sepsis 시점 단위 설계 (stride 12h · horizon 24h · ICD 동반질환 · 환자 단위 70/15/15) + 원본식 샘플링 대조군.
# 데이터: data/make_rolling_windows.py → C:\data\mimic-iv-derived\rolling_s3_icd_s12_h24.pt
# 앞 GPU 작업(kb_upstream_icd_6h)이 끝날 때까지 기다린다.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$out  = 'C:\data\mimic-iv-derived'
$repo = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$log  = Join-Path $out 'rolling_s12_h24.log'
function L($m){ $t = Get-Date -Format 'HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

$prev = Join-Path $out 'kb_upstream_icd_6h.log'
L 'WAIT for kb_upstream_icd_6h'
while ($true) {
    $txt = if (Test-Path $prev) { Get-Content $prev -Raw } else { '' }
    if ($txt -match 'DONE|FAIL') { break }
    Start-Sleep -Seconds 60
}

L 'TRAIN rolling s12 h24'
Set-Location $repo
Remove-Item Env:NESY_NOTE_MISSING -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING = 'utf-8'
& $py -u rolling_tables.py --data (Join-Path $out 'rolling_s3_icd_s12_h24.pt') --out-dir results_rolling_s12_h24 --seed 42 --epochs 30 --epochs-nesy 15 --select auprc --kb upstream
$code = $LASTEXITCODE
if (Test-Path (Join-Path $repo 'results_rolling_s12_h24\metrics.csv')) { L "OK train exit=$code" } else { L "FAIL no metrics exit=$code"; exit 1 }
L 'DONE'
