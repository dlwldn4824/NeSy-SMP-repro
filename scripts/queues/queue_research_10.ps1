# 연구 큐 10 — 코드 수정 A1·A3·A4 반영 후 섬망 쪽 재실행 (D1·D2)
#   A1 에폭마다 1회 셔플 / A3 비음수 제약을 섬망 가중치에만 / A4 가짜 공리 머리 분포 보존
#   이전(수정 전) 결과는 stage35_prefixA · stage39_prefixA · stage39_data_prefixA 로 보관한다.
#   GPU 작업이라 패혈증 큐(7)와 병렬로 돈다.
# 이 파일은 UTF-8 BOM 으로 저장해야 한다.
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$repo = 'C:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro'
$log  = 'C:\data\mimic-iv-derived\research_queue10.log'
$env:PYTHONIOENCODING = 'utf-8'
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'
$env:EDA_DATA = Join-Path $repo 'notes\eda'
$env:EDA_OUT  = 'C:\data\padis_eda_out'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

Set-Location $repo
foreach ($d in 'stage35','stage39','stage39_data') {
    $src = Join-Path $env:EDA_OUT $d; $dst = Join-Path $env:EDA_OUT ($d + '_prefixA')
    if ((Test-Path $src) -and -not (Test-Path $dst)) { Rename-Item $src $dst; L "보관 $d -> ${d}_prefixA" }
}

L 'START 35_structural_bottleneck (A1·A3·A4 반영)'
& $py -u (Join-Path $repo 'eda\35_structural_bottleneck.py') --seeds 42,7,2024 --epochs 12 2>&1 |
    Out-File -Encoding utf8 (Join-Path $env:EDA_OUT 'q10_35.log')
if ($LASTEXITCODE -eq 0) { L 'OK 35' } else { L ("FAIL 35 exit=" + $LASTEXITCODE) }

$env:ANTECEDENT = 'pred'
L 'START 39_ltn_paper_loss (pred · A1·A4 반영)'
& $py -u (Join-Path $repo 'eda\39_ltn_paper_loss.py') --seeds 42,7,2024 --epochs 10 2>&1 |
    Out-File -Encoding utf8 (Join-Path $env:EDA_OUT 'q10_39_pred.log')
if ($LASTEXITCODE -eq 0) { L 'OK 39 pred' } else { L ("FAIL 39 pred exit=" + $LASTEXITCODE) }

$env:ANTECEDENT = 'data'
L 'START 39_ltn_paper_loss (data · A1·A4 반영)'
& $py -u (Join-Path $repo 'eda\39_ltn_paper_loss.py') --seeds 42,7,2024 --epochs 10 2>&1 |
    Out-File -Encoding utf8 (Join-Path $env:EDA_OUT 'q10_39_data.log')
if ($LASTEXITCODE -eq 0) { L 'OK 39 data' } else { L ("FAIL 39 data exit=" + $LASTEXITCODE) }
L 'QUEUE10 ALL DONE'
