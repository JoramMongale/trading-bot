@echo off
REM Weekly Monday start for the gold bot: clear any sentinel, run the supervisor task.
REM Scheduled by trading-bot-gold-mon (weekly Monday 08:00 SAST = 06:00 UTC).
setlocal
cd /d "%~dp0.."
set "ROOT=%CD%"

if exist "%ROOT%\output\live_cent.stop" del "%ROOT%\output\live_cent.stop" >nul 2>&1

echo [gold-weekend] Monday start: launching trading-bot-cent
schtasks /Run /TN trading-bot-cent

endlocal
exit /b 0
