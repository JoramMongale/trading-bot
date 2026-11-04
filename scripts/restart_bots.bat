@echo off
REM ===========================================================================
REM  Stop / start / restart the live bots. Run as administrator.
REM
REM    scripts\restart_bots.bat              restart cent and btc
REM    scripts\restart_bots.bat cent         restart just one
REM    scripts\restart_bots.bat stop         stop cent and btc
REM    scripts\restart_bots.bat start        start cent and btc
REM    scripts\restart_bots.bat stop cent    (modes take tags too)
REM
REM  UPDATING CODE: stop -> git pull -> start. Never git pull while the bots
REM  run: cmd re-reads a batch file as it executes, so a pull that rewrites
REM  supervise_live.bat under a running supervisor is undefined behaviour.
REM  A plain restart (no pull in between) is fine for config-only changes
REM  made before running it.
REM
REM  For each bot (restart = stop then start):
REM    1. stop it cleanly: write output\live_<tag>.stop, so the supervisor
REM       exits instead of restarting, then kill the bot process (the stop
REM       file alone does nothing while the bot is running -- the supervisor
REM       only checks it after the bot exits)
REM    2. wait until scheduled task trading-bot-<tag> is no longer Running
REM    3. start the task again (preflight runs first, as always)
REM    4. wait for the bot to really start (its live_start line); if the
REM       startup check keeps failing, report NOT STARTED with the reason
REM    5. show the first sentiment / gold-veto reading
REM
REM  Open trades are safe while the bot is down: their stop loss and take
REM  profit are held by the broker, not by the bot.
REM
REM  Never starts a second copy: if a bot will not stop, that bot is left
REM  alone and reported as FAILED.
REM ===========================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"

REM The tasks run with highest privileges, so the bot process is elevated and
REM a normal (non-admin) prompt gets "Access is denied" trying to stop it.
net session >nul 2>&1
if errorlevel 1 (
    echo FAIL: run this as administrator ^(right-click restart_bots.bat -^> Run as administrator^).
    goto :end_fail
)
if not exist "%PY%" (
    echo FAIL: no virtualenv at %PY% -- run scripts\setup.bat first
    goto :end_fail
)

set "MODE=restart"
if /i "%~1"=="stop" (
    set "MODE=stop"
    shift
)
if /i "%~1"=="start" (
    set "MODE=start"
    shift
)
set "TAGS="
:collect
if "%~1"=="" goto :collected
set "TAGS=!TAGS! %~1"
shift
goto :collect
:collected
if not defined TAGS set "TAGS= cent btc"
set "FAILED="

for %%T in (%TAGS%) do call :one %%T

echo.
if defined FAILED (
    echo ==== %MODE% FAILED for: !FAILED!-- see the messages above ====
    goto :end_fail
)
echo ==== %MODE% done:%TAGS% ====
if /i "%MODE%"=="stop" echo Bots are stopped. Now: git pull, then scripts\restart_bots.bat start
echo Logs: output\live_^<tag^>.log  ^(decisions^)   output\supervise_^<tag^>.log  ^(supervisor^)
pause
exit /b 0

:end_fail
pause
exit /b 1


REM ===========================================================================
:one
set "TAG=%~1"
set "TN=trading-bot-%TAG%"
set "PIDFILE=%ROOT%\output\live_%TAG%.pid"
set "STOPFILE=%ROOT%\output\live_%TAG%.stop"
set "LOG=%ROOT%\output\live_%TAG%.log"
set "SUPLOG=%ROOT%\output\supervise_%TAG%.log"
echo.
echo ===== %TAG% =====

schtasks /Query /TN "%TN%" >nul 2>&1
if errorlevel 1 (
    echo FAIL: no scheduled task %TN% -- run scripts\install_windows_tasks.bat first
    set "FAILED=!FAILED!%TAG% "
    exit /b 0
)

if /i "%MODE%"=="start" goto :start_only

REM -- 1. stop ----------------------------------------------------------------
REM Stop-file first, always: a supervisor between retries then exits at the top
REM of its loop instead of starting a fresh bot under us.
type nul > "%STOPFILE%"
call :bot_pid
if defined BOTPID (
    echo stopping bot ^(pid !BOTPID!^) ...
    taskkill /PID !BOTPID! /F >nul 2>&1
    if errorlevel 1 (
        echo FAIL: could not stop pid !BOTPID! -- leaving %TAG% alone
        del "%STOPFILE%" >nul 2>&1
        set "FAILED=!FAILED!%TAG% "
        exit /b 0
    )
) else (
    echo bot process not running
)

REM -- 2. wait for the supervisor task to finish ------------------------------
call :wait_not_running 60
if "!RUNNING!"=="1" (
    REM Still Running with no bot process: the supervisor is sitting in a
    REM preflight backoff. Ending it now cannot orphan a bot, because there is
    REM no bot -- checked again right here.
    call :bot_pid
    if defined BOTPID (
        echo FAIL: bot pid !BOTPID! is running again -- not starting a second copy
        set "FAILED=!FAILED!%TAG% "
        exit /b 0
    )
    echo supervisor waiting in preflight backoff -- ending the task
    schtasks /End /TN "%TN%" >nul 2>&1
    call :wait_not_running 30
    if "!RUNNING!"=="1" (
        echo FAIL: %TN% will not stop -- not starting a second copy
        set "FAILED=!FAILED!%TAG% "
        exit /b 0
    )
)
REM A bot the supervisor launched in the last moment before it ended would be
REM orphaned and still trading -- catch it.
call :bot_pid
if defined BOTPID (
    echo stopping orphaned bot ^(pid !BOTPID!^) ...
    taskkill /PID !BOTPID! /F >nul 2>&1
    timeout /t 2 /nobreak >nul
    call :bot_pid
    if defined BOTPID (
        echo FAIL: bot pid !BOTPID! will not stop -- not starting a second copy
        set "FAILED=!FAILED!%TAG% "
        exit /b 0
    )
)
echo stopped.
if exist "%STOPFILE%" del "%STOPFILE%" >nul 2>&1
if /i "%MODE%"=="stop" exit /b 0
goto :do_start

:start_only
REM Start mode must not create a second copy either.
call :bot_pid
if defined BOTPID (
    echo already running ^(bot pid !BOTPID!^) -- left alone
    exit /b 0
)
call :wait_not_running 0
if "!RUNNING!"=="1" (
    echo task %TN% is already running -- left alone
    exit /b 0
)

:do_start
REM -- 3. start ---------------------------------------------------------------
set "LOGSIZE=0"
if exist "%LOG%" for %%F in ("%LOG%") do set "LOGSIZE=%%~zF"
REM A stop-file left over from step 1 would make the new supervisor exit at
REM once. It clears stale ones itself, but remove it here too to be sure.
if exist "%STOPFILE%" del "%STOPFILE%" >nul 2>&1
schtasks /Run /TN "%TN%" >nul 2>&1
if errorlevel 1 (
    echo FAIL: schtasks /Run %TN% failed
    set "FAILED=!FAILED!%TAG% "
    exit /b 0
)
echo started %TN% -- waiting for the bot to come up ^(up to 3 min^) ...

REM -- 4. did it really start? ----------------------------------------------
REM "Started the task" is not "the bot is trading": the supervisor runs the
REM startup check first and retries quietly if it fails. Wait for the bot's
REM own live_start line; without it within 3 minutes, report NOT STARTED.
"%PY%" scripts\wait_for_log.py "%LOG%" !LOGSIZE! event=live_start 180 >nul
if errorlevel 1 (
    echo NOT STARTED: the startup check is failing. Reason from the supervisor log:
    if exist "%SUPLOG%" "%PY%" -c "import sys; L=[l.rstrip() for l in open(sys.argv[1], encoding='utf-8', errors='replace')][-40:]; F=[l for l in L if '[FAIL]' in l]; print(chr(10).join(F[-3:] or L[-6:]))" "%SUPLOG%"
    echo Usual fixes: Algo Trading on ^(Ctrl+E^), right account logged in, terminal connected, no pop-ups.
    echo The supervisor keeps retrying on its own -- once fixed it starts within 5 minutes.
    set "FAILED=!FAILED!%TAG% "
    exit /b 0
)
echo bot is up. First reading:
"%PY%" scripts\wait_for_log.py "%LOG%" !LOGSIZE! "sentiment_|macro_veto" 60
if errorlevel 1 echo   ^(no sentiment reading yet -- normal if [sentiment] enabled = false^)
exit /b 0


REM ===========================================================================
REM BOTPID = pid from output\live_<tag>.pid, but only if that pid is a running
REM python.exe. A stale pidfile must never get some other program killed.
:bot_pid
set "BOTPID="
if not exist "%PIDFILE%" exit /b 0
set "CANDIDATE="
set /p CANDIDATE=<"%PIDFILE%"
if not defined CANDIDATE exit /b 0
tasklist /FI "PID eq %CANDIDATE%" /FI "IMAGENAME eq python.exe" /NH 2>nul | findstr /i "python.exe" >nul
if not errorlevel 1 set "BOTPID=%CANDIDATE%"
exit /b 0

REM RUNNING = 1 while task %TN% shows Running, waiting up to %1 seconds.
:wait_not_running
set /a WAITED=0
:wnr_loop
set "RUNNING=0"
schtasks /Query /TN "%TN%" /FO LIST | findstr /i /c:"Running" >nul && set "RUNNING=1"
if "!RUNNING!"=="0" exit /b 0
if !WAITED! geq %1 exit /b 0
timeout /t 3 /nobreak >nul
set /a WAITED+=3
goto :wnr_loop
