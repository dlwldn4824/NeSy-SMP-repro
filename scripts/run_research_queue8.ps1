# 연구 큐 8 — 랩 피드백 반영: LTN 라이브러리 연산 + 논문식 loss (w_D + w_K = 1)
#   eda/39  w_K ∈ {0, 0.1, 0.2, 0.5, 0.8} × 진짜/가짜 공리 · 시드 3 · 10 epoch
#   섬망 코호트(GPU)라 패혈증 큐와 병렬로 돈다.
# 이 파일은 UTF-8 BOM 으로 저장해야 한다.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$repo = 'C:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro'
$log  = 'C:\data\mimic-iv-derived\research_queue8.log'
$env:PYTHONIOENCODING = 'utf-8'
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'
$env:EDA_DATA = Join-Path $repo 'notes\eda'
$env:EDA_OUT  = 'C:\data\padis_eda_out'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

Set-Location $repo
L 'START 39_ltn_paper_loss'
& $py -u (Join-Path $repo 'eda\39_ltn_paper_loss.py') --seeds 42,7,2024 --epochs 10 2>&1 |
    Out-File -Encoding utf8 (Join-Path $env:EDA_OUT 'q8_39.log')
if ($LASTEXITCODE -eq 0) { L 'OK 39_ltn_paper_loss' } else { L ("FAIL 39 exit=" + $LASTEXITCODE) }
L 'QUEUE8 ALL DONE'
