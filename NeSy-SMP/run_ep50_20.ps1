# Re-run with GitHub/paper-aligned epochs: BiLSTM 50, LTN/NeSy 20
# Keep current methodology: seed=42, best val macro-F1 reload for all DL models, como=0
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Py = "C:\Users\dlwld\AppData\Local\Programs\Python\Python312\python.exe"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"
$LogDir = Join-Path $Root "results\ep50_20"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$MasterLog = Join-Path $LogDir "run_log.txt"

function Write-Log([string]$msg) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
  Add-Content -LiteralPath $MasterLog -Value $line
  Write-Host $line
}

$jobs = @(
  @{ Name = "s3_6h";  Csv = "C:\data\mimic-iv-derived\events_6h_wide_s3.csv";  Out = "results\ep50_20\s3_6h" },
  @{ Name = "s3_12h"; Csv = "C:\data\mimic-iv-derived\events_12h_wide_s3.csv"; Out = "results\ep50_20\s3_12h" },
  @{ Name = "s3_24h"; Csv = "C:\data\mimic-iv-derived\events_24h_wide_s3.csv"; Out = "results\ep50_20\s3_24h" },
  @{ Name = "s3_48h"; Csv = "C:\data\mimic-iv-derived\events_48h_wide_s3.csv"; Out = "results\ep50_20\s3_48h" },
  @{ Name = "icd_6h"; Csv = "C:\data\mimic-iv-derived\events_6h_wide.csv";     Out = "results\ep50_20\icd_6h" }
)

Write-Log "START ep50/20 aligned re-run (seed=42, batch=32, como=0 for s3/icd)"
cmd /c "`"$Py`" -c `"import torch; print('cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')`"" | Tee-Object -FilePath $MasterLog -Append

foreach ($j in $jobs) {
  if (-not (Test-Path -LiteralPath $j.Csv)) {
    Write-Log "SKIP missing CSV: $($j.Csv)"
    continue
  }
  $done = Join-Path $Root ($j.Out + "\table1_summary.csv")
  if (Test-Path -LiteralPath $done) {
    Write-Log "SKIP already done: $($j.Name)"
    continue
  }
  Write-Log "RUN $($j.Name) csv=$($j.Csv) out=$($j.Out)"
  $jobLog = Join-Path $LogDir ("$($j.Name).log")
  $argList = @(
    "reproduce_tables.py",
    "--csv", $j.Csv,
    "--out-dir", $j.Out,
    "--seed", "42",
    "--epochs", "50",
    "--epochs-nesy", "20",
    "--batch-size", "32"
  )
  # Redirect via cmd so native stderr does not abort PowerShell
  cmd /c "`"$Py`" $($argList -join ' ') > `"$jobLog`" 2>&1"
  $code = $LASTEXITCODE
  Get-Content -LiteralPath $jobLog -Tail 20 | ForEach-Object { Write-Host $_ }
  if ($code -ne 0) {
    Write-Log "FAIL $($j.Name) exit=$code"
  } else {
    Write-Log "OK $($j.Name)"
  }
}

Write-Log "ALL JOBS FINISHED"
