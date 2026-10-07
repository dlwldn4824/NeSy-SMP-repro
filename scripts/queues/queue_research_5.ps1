# 연구 큐 5 — 구조 가설 3개 (섬망 코호트, 로컬 GPU). sepsis 큐와 병렬.
#   S1 eda/35  공리 경로 바꾸기 (비음수 가중 · 섬망만 통과 · 2단계 학습) × 진짜/가짜 공리
#   S2 eda/36  추론 시 제약 투영 (학습은 공리 없이, 예측만 보정) λ 스윕
#   S3 eda/37  공리 만족도를 감사·설명 지표로 (환자 단위 · 오류 분석)
# 이 파일은 UTF-8 BOM 으로 저장해야 한다 (PowerShell 5.1 한글 경로).
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$repo = 'C:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro'
$log  = 'C:\data\mimic-iv-derived\research_queue5.log'
$env:PYTHONIOENCODING = 'utf-8'
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'   # forrtl error(200) 방지
$env:EDA_DATA = Join-Path $repo 'notes\eda'
$env:EDA_OUT  = 'C:\data\padis_eda_out'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

Set-Location $repo
foreach ($q in @(
    @{ id = 'S1 35_structural_bottleneck'; s = 'eda\35_structural_bottleneck.py'; o = 's1_35.log'; seeds = '42,7,2024' },
    @{ id = 'S2 36_constraint_projection'; s = 'eda\36_constraint_projection.py'; o = 's2_36.log'; seeds = '42,7,2024' },
    @{ id = 'S3 37_axiom_audit';           s = 'eda\37_axiom_audit.py';           o = 's3_37.log'; seeds = '42' })) {
    L ("START " + $q.id)
    & $py -u (Join-Path $repo $q.s) --seeds $q.seeds --epochs 10 2>&1 |
        Out-File -Encoding utf8 (Join-Path $env:EDA_OUT $q.o)
    if ($LASTEXITCODE -eq 0) { L ("OK " + $q.id) } else { L ("FAIL " + $q.id + " exit=" + $LASTEXITCODE) }
}
L 'QUEUE5 ALL DONE'
