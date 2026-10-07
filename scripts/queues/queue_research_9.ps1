# 연구 큐 9 — 랩 피드백 2: 공리 앞부분(antecedent)을 모델 예측값 대신 **관측된 개념값**으로
#   eda/39 을 ANTECEDENT=data 로 다시 실행 (논문식 loss 유지)
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$repo = 'C:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro'
$log  = 'C:\data\mimic-iv-derived\research_queue9.log'
$env:PYTHONIOENCODING = 'utf-8'
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'
$env:EDA_DATA = Join-Path $repo 'notes\eda'
$env:EDA_OUT  = 'C:\data\padis_eda_out'
$env:ANTECEDENT = 'data'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }
Set-Location $repo
L 'START 39 (ANTECEDENT=data)'
& $py -u (Join-Path $repo 'eda\39_ltn_paper_loss.py') --seeds 42,7,2024 --epochs 10 2>&1 |
    Out-File -Encoding utf8 (Join-Path $env:EDA_OUT 'q9_39_data.log')
if ($LASTEXITCODE -eq 0) { L 'OK 39 (data)' } else { L ("FAIL 39 data exit=" + $LASTEXITCODE) }
L 'QUEUE9 ALL DONE'
