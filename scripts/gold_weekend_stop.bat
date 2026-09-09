@echo off
REM Weekly Friday stop for the gold bot: sentinel, kill the bot, close open gold.
REM Scheduled by trading-bot-gold-fri (weekly Friday 21:00 SAST = 19:00 UTC).
REM Bitcoin is untouched - it runs 24/7 on its own task.
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"

if not exist "%ROOT%\output" mkdir "%ROOT%\output"

echo [gold-weekend] Friday stop: writing sentinel so the supervisor exits cleanly
type nul > "%ROOT%\output\live_cent.stop"

set "BPID="
if exist "%ROOT%\output\live_cent.pid" set /p BPID=<"%ROOT%\output\live_cent.pid"
if defined BPID (
    echo [gold-weekend] stopping gold bot pid %BPID%
    taskkill /PID %BPID% /F >nul 2>&1
) else (
    echo [gold-weekend] no gold bot pidfile - nothing to kill
)

echo [gold-weekend] closing any open gold position
"%PY%" scripts\close_gold_position.py --config config\config-cent.toml --confirm

echo [gold-weekend] done - gold stays off until Monday's start task
endlocal
exit /b 0
