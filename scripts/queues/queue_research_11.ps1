# 연구 큐 11 — D3(논문식 손실로 섬망 자체 예측) + 공리 재타깃 실험
#   1) 큐 10 완료 대기 (같은 GPU)
#   2) eda/40  논문식 손실 · 예측 대상 = 섬망 · 공리 앞부분 pred / data 두 종
#   3) eda/41  공리를 사망용으로 재타깃했을 때의 비교 (29_ §6-1 의 빈칸)
# 이 파일은 UTF-8 BOM 으로 저장해야 한다.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$repo = 'C:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro'
$log  = 'C:\data\mimic-iv-derived\research_queue11.log'
$env:PYTHONIOENCODING = 'utf-8'
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'
$env:EDA_DATA = Join-Path $repo 'notes\eda'
$env:EDA_OUT  = 'C:\data\padis_eda_out'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

Set-Location $repo
L 'WAIT for queue 10'
$q10 = 'C:\data\mimic-iv-derived\research_queue10.log'
$deadline = (Get-Date).AddHours(6)
while ((Get-Date) -lt $deadline) {
    if ((Test-Path $q10) -and (Select-String -Path $q10 -Pattern 'QUEUE10 ALL DONE' -Quiet)) { break }
    Start-Sleep -Seconds 60
}
Start-Sleep -Seconds 20

# 순서: 40(pred) -> 41 -> 40(data). 41 이 "clinical outcome 에서의 NeSy 효과"를 직접 재는 핵심이라 앞으로 당겼다.
function Run-Eda($label, $script, $logname) {
    L "START $label"
    & $py -u (Join-Path $repo ('eda\' + $script)) --seeds 42,7,2024 --epochs 10 2>&1 |
        Out-File -Encoding utf8 (Join-Path $env:EDA_OUT $logname)
    if ($LASTEXITCODE -eq 0) { L "OK $label" } else { L ("FAIL $label exit=" + $LASTEXITCODE) }
}

$env:ANTECEDENT = 'pred'
Run-Eda '40 섬망 예측 (pred)' '40_ltn_paper_loss_delirium.py' 'q11_40_pred.log'

Remove-Item Env:\ANTECEDENT -ErrorAction SilentlyContinue
Run-Eda '41 공리 재타깃' '41_retarget_axioms.py' 'q11_41.log'

$env:ANTECEDENT = 'data'
Run-Eda '40 섬망 예측 (data)' '40_ltn_paper_loss_delirium.py' 'q11_40_data.log'
Remove-Item Env:\ANTECEDENT -ErrorAction SilentlyContinue
L 'QUEUE11 ALL DONE'
