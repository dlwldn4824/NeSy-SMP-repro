# 논문 원문 조건 재현 파이프라인 (De Santis et al., EAAI 2026)
#   1 코호트    data/build_cohort_paper.py  (mimic-code Sepsis-3 · 성인 · ICU LOS>=24h · 입원 중 ICU 1회 · v2.2 기간)
#   2 동반질환  extract_comorbidities_paper.py (HPI·PMH 섹션, 공개 코드 규칙)  — 앞 단계와 병행 실행 중
#   3 이벤트    data/build_dataset_gcs.py --cohort   (논문 §5.1 변수: 바이탈 6 · 검사 14 · GCS)
#   4 창        data/make_leadtime_csvs.py            (원본 extract_before_death.py 로직, lead 6/12/24/48)
#   5 wide      data/long_to_wide.py → data/merge_comorbidities.py
#   6 학습      upstream_faithful/stratified_main.py  (원본 코드 + 실행 패치 4개, epoch 50/20)
$ErrorActionPreference = 'Continue'
$py    = 'C:\dev\NeSy-SMP-repro\.venv\Scripts\python.exe'
$out   = 'C:\data\mimic-iv-derived'
$repo  = 'C:\dev\NeSy-SMP-repro\NeSy-SMP'
$db    = 'C:\Users\dlwld\Downloads\MIMIC4-hosp-icu.db'
$leads = Join-Path $out 'paper_leads'
$log   = Join-Path $out 'paper_repro.log'
$env:PYTHONIOENCODING = 'utf-8'
function L($m){ $t = Get-Date -Format 'HH:mm:ss'; Add-Content $log "$t $m"; Write-Host "$t $m" }
function WaitFor($file, $pattern) {
    while ($true) {
        $txt = if (Test-Path $file) { Get-Content $file -Raw } else { '' }
        if ($txt -match $pattern) { return $Matches[0] }
        Start-Sleep -Seconds 60
    }
}

L 'WAIT cohort + NLP'
$c = WaitFor (Join-Path $out 'cohort_paper.log') 'exit \d+'
if ($c -ne 'exit 0') { L "cohort failed: $c"; exit 1 }
$n = WaitFor (Join-Path $out 'nlp_paper.log') 'exit \d+'
if ($n -ne 'exit 0') { L "NLP failed: $n"; exit 1 }

$cohort = Join-Path $out 'cohort_sepsis3_paper.csv'
$dataset = Join-Path $out 'dataset_gcs_paper.csv'
L 'EVENTS'
Set-Location (Join-Path $repo 'data')
& $py -u build_dataset_gcs.py --db $db --out-dir $out --cohort $cohort --dataset-name 'dataset_gcs_paper.csv' --cache-name '_cache_paper_events'
if (-not (Test-Path $dataset)) { L 'events failed'; exit 1 }

L 'WINDOWS'
& $py -u make_leadtime_csvs.py --input $dataset --out-dir $leads --hours 6 12 24 48 --seed 32
if ($LASTEXITCODE -ne 0) { L "windows failed $LASTEXITCODE"; exit 1 }

foreach ($h in 6, 12, 24, 48) {
    $long = Join-Path $leads "events_${h}h_before_death_gcs.csv"
    $wide = Join-Path $leads "events_${h}h_wide_paper.csv"
    $como = Join-Path $leads "events_${h}h_wide_paper_como.csv"
    L "WIDE ${h}h"
    & $py -u long_to_wide.py --input $long --output $wide
    & $py -u merge_comorbidities.py --wide $wide --como-wide (Join-Path $out 'comorbidities_paper_wide.csv') --output $como
    if (-not (Test-Path $como)) { L "wide/merge failed ${h}h"; exit 1 }
}

foreach ($h in 6, 12, 24, 48) {
    $res = Join-Path $repo "results_paper_${h}h"
    New-Item -ItemType Directory -Force $res | Out-Null
    Set-Location $res
    $env:NESY_DATA = Join-Path $leads "events_${h}h_wide_paper_como.csv"
    L "TRAIN ${h}h (upstream stratified_main.py, 50/20)"
    & $py -u (Join-Path $repo 'upstream_faithful\stratified_main.py') *> (Join-Path $res 'train.log')
    if (Test-Path (Join-Path $res 'stratified_results.txt')) { L "OK ${h}h" } else { L "FAIL ${h}h exit=$LASTEXITCODE"; exit 1 }
}
L 'DONE'
