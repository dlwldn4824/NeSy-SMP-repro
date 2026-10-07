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

foreach ($mode in 'pred','data') {
    $env:ANTECEDENT = $mode
    L "START 40_ltn_paper_loss_delirium ($mode)"
    & $py -u (Join-Path $repo 'eda\40_ltn_paper_loss_delirium.py') --seeds 42,7,2024 --epochs 10 2>&1 |
        Out-File -Encoding utf8 (Join-Path $env:EDA_OUT "q11_40_$mode.log")
    if ($LASTEXITCODE -eq 0) { L "OK 40 $mode" } else { L ("FAIL 40 $mode exit=" + $LASTEXITCODE) }
}

Remove-Item Env:\ANTECEDENT -ErrorAction SilentlyContinue
L 'START 41_retarget_axioms'
& $py -u (Join-Path $repo 'eda\41_retarget_axioms.py') --seeds 42,7,2024 --epochs 10 2>&1 |
    Out-File -Encoding utf8 (Join-Path $env:EDA_OUT 'q11_41.log')
if ($LASTEXITCODE -eq 0) { L 'OK 41' } else { L ("FAIL 41 exit=" + $LASTEXITCODE) }
L 'QUEUE11 ALL DONE'
