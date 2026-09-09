# Start/stop the Next.js dashboard (plan 03-05, DASH-01/DASH-02).
#
#   powershell -ExecutionPolicy Bypass -File scripts\web_dashboard.ps1 start
#   powershell -ExecutionPolicy Bypass -File scripts\web_dashboard.ps1 stop
#
# The dashboard is READ-ONLY and hard-binds 127.0.0.1 (loopback only). It reads
# the DuckDB marts (data/analytics/trading.duckdb) via @duckdb/node-api; the
# warehouse must be loaded first with `python scripts/warehouse_cli.py load`
# and `dbt run` (the start script warns, does not block).
param([string]$Action = "start")

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Web = Join-Path $Root "web"
$PidFile = Join-Path $Web ".next\.dashboard.pid"
$OutFile = Join-Path $Web ".next\dashboard.out"
$ErrFile = Join-Path $Web ".next\dashboard.err"

function Start-Dashboard {
  if (Test-Path $PidFile) {
    $old = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
      Write-Host "Dashboard already running (pid $old) on http://127.0.0.1:3000"
      return
    }
  }
  $db = Join-Path $Root "data\analytics\trading.duckdb"
  if (-not (Test-Path $db)) {
    Write-Host "WARNING: warehouse not found ($db)."
    Write-Host "  Run: python scripts\warehouse_cli.py load   then: (cd dbt; dbt run)"
    Write-Host "  Starting anyway - pages will show the empty state."
  }
  $proc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run start -- -H 127.0.0.1 -p 3000" `
    -WorkingDirectory $Web `
    -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput $OutFile -RedirectStandardError $ErrFile
  $proc.Id | Set-Content $PidFile
  Write-Host "Dashboard starting on http://127.0.0.1:3000 (pid $($proc.Id))"
}

function Stop-Dashboard {
  if (-not (Test-Path $PidFile)) {
    Write-Host "Dashboard not running (no pidfile)"
    return
  }
  $pidToKill = Get-Content $PidFile -ErrorAction SilentlyContinue
  if ($pidToKill -and (Get-Process -Id $pidToKill -ErrorAction SilentlyContinue)) {
    Stop-Process -Id $pidToKill -Force
    Write-Host "Dashboard stopped (pid $pidToKill)"
  } else {
    Write-Host "Dashboard pidfile stale - nothing to stop"
  }
  Remove-Item $PidFile -ErrorAction SilentlyContinue
}

switch ($Action.ToLower()) {
  "start" { Start-Dashboard }
  "stop"  { Stop-Dashboard }
  default {
    Write-Host "usage: scripts\web_dashboard.ps1 [start|stop]"
    exit 2
  }
}
