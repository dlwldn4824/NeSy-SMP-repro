# 연구 큐 3 (섬망 코호트, 로컬 GPU) — 1·2·3·4순위. Q4(sepsis 학습)와 병렬로 돈다.
#   P1 eda/31  공리 음성 대조군 + 가중치·집계 탐색 + 운영 지표
#   P2 eda/32  미매핑 개념 회수 (억제대·기계환기·오피오이드·멜라토닌) — DB 스캔
#   P2 eda/33  회수 개념으로 KG 범위 비교 재실행
#   P3 eda/34  연도 도메인 이동 (2008-2016 학습 → 2020-22 평가) + 운영 지표
# 이 파일은 UTF-8 BOM 으로 저장해야 한다 (PowerShell 5.1 한글 경로).
$ErrorActionPreference = 'Continue'
$py   = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$repo = 'C:\Users\dlwld\OneDrive\Desktop\학연생\NeSy-SMP-repro'
$log  = 'C:\data\mimic-iv-derived\research_queue3.log'
$env:PYTHONIOENCODING = 'utf-8'
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'   # forrtl error(200) 방지 - 콘솔 CLOSE 로 죽는 것
$env:EDA_DATA = Join-Path $repo 'notes\eda'
$env:EDA_OUT  = 'C:\data\padis_eda_out'
function L($m){ $t = Get-Date -Format 'MM-dd HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }

$items = @(
    @{ id = 'P1 31_axiom_control';   script = 'eda\31_axiom_control.py';   log = 'p1_31.log'; seeds = $true },
    @{ id = 'P2 32_recover_concepts'; script = 'eda\32_recover_concepts.py'; log = 'p2_32.log'; seeds = $false },
    @{ id = 'P2 33_kg_variants_v2';  script = 'eda\33_kg_variants_v2.py';  log = 'p2_33.log'; seeds = $true },
    @{ id = 'P3 34_domain_shift';    script = 'eda\34_domain_shift.py';    log = 'p3_34.log'; seeds = $true }
)
Set-Location $repo
foreach ($q in $items) {
    L ("START " + $q.id)
    if ($q.seeds) {
        & $py -u (Join-Path $repo $q.script) --seeds 42,7,2024 --epochs 10 2>&1 |
            Out-File -Encoding utf8 (Join-Path $env:EDA_OUT $q.log)
    } else {
        & $py -u (Join-Path $repo $q.script) 2>&1 |
            Out-File -Encoding utf8 (Join-Path $env:EDA_OUT $q.log)
    }
    if ($LASTEXITCODE -eq 0) { L ("OK " + $q.id) } else { L ("FAIL " + $q.id + " exit=" + $LASTEXITCODE) }
}
L 'QUEUE3 ALL DONE'
