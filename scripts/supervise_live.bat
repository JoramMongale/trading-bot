@echo off
REM ===========================================================================
REM  Keep a REAL-money bot running 24/7 on Windows, with a crash-loop brake.
REM
REM    scripts\supervise_live.bat config\config-cent.toml live_cent.log cent
REM
REM  The Windows counterpart of scripts/supervise_live.sh, and a port rather
REM  than a rewrite: same preflight-before-every-start, same exponential
REM  backoff, same hard stop after too many rapid failures. Where it diverges,
REM  the reason is written down -- a supervisor whose safety behaviour quietly
REM  differs per platform is worse than two obviously different scripts.
REM
REM  THE CRASH-LOOP BRAKE IS THE POINT. Unattended restart is the dangerous half
REM  of 24/7: a bot that dies for a reason that will recur -- bad config, a
REM  symbol the broker stopped quoting, an expired password -- will otherwise be
REM  restarted forever, and each restart is a fresh chance to do the wrong thing
REM  with real money. Stopping and staying stopped is the correct behaviour for
REM  a bot that cannot start cleanly. The account's own 6%% daily-loss halt is
REM  the second line of defence, not the first.
REM
REM  Runs in the FOREGROUND and never detaches, so Task Scheduler can supervise
REM  it (see scripts\install_windows_tasks.bat) or it can be left in a window.
REM ===========================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0.."
set "ROOT=%CD%"

set "CONFIG=%~1"
set "LOGNAME=%~2"
set "TAG=%~3"
if "%CONFIG%"==""  set "CONFIG=config\config-cent.toml"
if "%LOGNAME%"=="" set "LOGNAME=live_cent.log"
if "%TAG%"==""     set "TAG=cent"

set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo FAIL: no virtualenv at %PY% -- run scripts\setup.bat first
    exit /b 1
)

if not exist "%ROOT%\output" mkdir "%ROOT%\output"
set "PIDFILE=%ROOT%\output\live_%TAG%.pid"
set "STOPFILE=%ROOT%\output\live_%TAG%.stop"
set "SUPLOG=%ROOT%\output\supervise_%TAG%.log"
set "BOTOUT=%ROOT%\output\live_%TAG%.out"

set /a MAX_FAILURES=5
set /a FAILURE_WINDOW=900
set /a BACKOFF_START=10
set /a BACKOFF_MAX=300

set /a BACKOFF=%BACKOFF_START%
set /a NFAIL=0
set "FAILSTAMPS="

call :say "supervisor starting  config=%CONFIG% log=%LOGNAME% tag=%TAG%"

REM -- the supervisor pidfile, and why it is NOT written -----------------------
REM
REM The bash supervisor records its own pid with `echo $$`. Batch has no
REM equivalent, and every workaround is a guess: matching on process name picks
REM the wrong cmd.exe when two bots run, and `for /f` spawns an intermediate
REM cmd.exe so a child's getppid() reports a process that dies immediately.
REM
REM A WRONG pid is worse than none -- health_check would report a dead
REM supervisor as alive the moment Windows reused that number. So
REM output/supervise_%TAG%.pid is deliberately left unwritten, and on Windows
REM the scheduled task is the source of truth for whether the supervisor lives:
REM
REM     schtasks /Query /TN trading-bot-%TAG%
REM
REM The BOT pidfile is written accurately, from inside the bot's own process by
REM scripts\run_with_pidfile.py, so health_check, dashboard, monitor_trade and
REM tune_risk all keep working.

REM A stale stop-file from a previous run would make this exit immediately and
REM look like it had never started.
if exist "%STOPFILE%" (
    call :say "clearing stale stop-file"
    del "%STOPFILE%" >nul 2>&1
)

REM -- keeping the machine awake ----------------------------------------------
REM The macOS original ties `caffeinate` to the supervisor's lifetime. Batch has
REM no equivalent that can be scoped to a process, so this is a machine-level
REM setting instead, applied once and left: a NUC that sleeps stops the bot.
REM Undo with: powercfg /change standby-timeout-ac 30
powercfg /change standby-timeout-ac 0 >nul 2>&1
powercfg /change hibernate-timeout-ac 0 >nul 2>&1
call :say "sleep and hibernate disabled on AC power"


:loop

REM A deliberate stop, checked before preflight so it takes effect even while
REM the supervisor is sitting in a preflight backoff.
REM
REM WHY A FILE AND NOT AN EXIT CODE. The bash original tells a deliberate stop
REM from a crash by exit code (143 = SIGTERM, 130 = SIGINT). Windows has no such
REM convention: taskkill produces a code indistinguishable from a crash, so an
REM exit-code test here would either restart a bot you just stopped or read real
REM crashes as intentional. Both are worse than an explicit sentinel.
if exist "%STOPFILE%" (
    call :say "stop-file present -- supervisor exiting"
    del "%STOPFILE%" >nul 2>&1
    goto :clean_exit
)

REM Preflight before EVERY start, not just the first. A restart four hours later
REM is a different world: the terminal may be logged out, Algo Trading may have
REM reset after a re-login, the feed may be stale. Starting blind into that is
REM how a bot ends up trading on prices from yesterday.
"%PY%" scripts\preflight_live.py --config "%CONFIG%" --real-account >>"%SUPLOG%" 2>&1
if errorlevel 1 (
    call :say "preflight FAILED -- not starting; retrying in !BACKOFF!s"
    timeout /t !BACKOFF! /nobreak >nul
    call :grow_backoff
    goto :loop
)

call :say "preflight ok -- starting bot"

REM Synchronous: batch waits here for the whole life of the bot, and errorlevel
REM afterwards is the bot's exit code. run_with_pidfile.py writes the pid from
REM inside the bot process, because batch cannot learn a child's pid reliably.
"%PY%" scripts\run_with_pidfile.py "%PIDFILE%" live --mode live --config "%CONFIG%" --log "%LOGNAME%" >>"%BOTOUT%" 2>&1
set "RC=!errorlevel!"

set /a BACKOFF=%BACKOFF_START%
if exist "%PIDFILE%" del "%PIDFILE%" >nul 2>&1

if exist "%STOPFILE%" (
    call :say "bot exited rc=!RC! with stop-file present (deliberate stop)"
    del "%STOPFILE%" >nul 2>&1
    goto :clean_exit
)
if "!RC!"=="0" (
    call :say "bot exited rc=0 (clean shutdown) -- supervisor exiting"
    goto :clean_exit
)

call :say "bot DIED rc=!RC!"

REM Failure accounting. Batch cannot do date arithmetic, so epoch seconds come
REM from the interpreter that is already installed -- correct across midnight,
REM month ends and DST, all of which naive %%TIME%% parsing gets wrong.
call :now NOW
if not defined NOW (
    REM Clock unavailable: treat every failure as recent so the brake still
    REM trips after MAX_FAILURES, rather than never.
    call :say "WARNING: clock unavailable -- counting every failure as recent"
    set /a NFAIL+=1
    if !NFAIL! geq %MAX_FAILURES% (
        call :say "GIVING UP: !NFAIL! failures and no clock to age them."
        endlocal
        exit /b 1
    )
    call :say "restarting in !BACKOFF!s (failure !NFAIL!/%MAX_FAILURES%)"
    timeout /t !BACKOFF! /nobreak >nul
    call :grow_backoff
    goto :loop
)
set "KEPT="
set /a NFAIL=0
for %%S in (!FAILSTAMPS! !NOW!) do (
    set /a AGE=!NOW! - %%S
    if !AGE! leq %FAILURE_WINDOW% (
        set "KEPT=!KEPT! %%S"
        set /a NFAIL+=1
    )
)
set "FAILSTAMPS=!KEPT!"

if !NFAIL! geq %MAX_FAILURES% (
    call :say "GIVING UP: !NFAIL! failures within %FAILURE_WINDOW%s."
    call :say "Something is wrong that a restart will not fix. Check"
    call :say "%SUPLOG% and %BOTOUT%, fix it, then start the supervisor again."
    endlocal
    exit /b 1
)

call :say "restarting in !BACKOFF!s (failure !NFAIL!/%MAX_FAILURES%)"
timeout /t !BACKOFF! /nobreak >nul
call :grow_backoff
goto :loop


:clean_exit
endlocal
exit /b 0


REM ===========================================================================
REM  Subroutines
REM ===========================================================================

:say
REM Timestamped to the supervisor log and the console, UTC to match the bash
REM supervisor and the bot's own structured logs.
call :utc STAMP
echo !STAMP! %~1
>>"%SUPLOG%" echo !STAMP! %~1
exit /b 0

:utc
REM The clock lives in scripts\clock.py, called with plain arguments. Inline
REM python -c "..." inside for /f breaks: cmd /c strips the outer quotes when a
REM command holds more than two, and any unquoted ) ends the for clause -- a
REM syntax error that aborts the whole supervisor. The first version left NOW
REM empty (crash-loop brake disabled); the first fix aborted at startup.
REM With exactly two quotes cmd /c keeps them when the path has spaces, and
REM strips them harmlessly when it has none.
set "%~1="
for /f %%T in ('"%PY%" scripts\clock.py utc') do set "%~1=%%T"
exit /b 0

:now
set "%~1="
for /f %%T in ('"%PY%" scripts\clock.py epoch') do set "%~1=%%T"
exit /b 0


REM ===========================================================================
REM  Subroutines
REM ===========================================================================

:say
REM Timestamped to the supervisor log and the console, UTC to match the bash
REM supervisor and the bot's own structured logs.
call :utc STAMP
echo !STAMP! %~1
>>"%SUPLOG%" echo !STAMP! %~1
exit /b 0

:utc
REM The extra outer quotes are required: for /f runs the command through
REM cmd /c, which strips the first and last quote when there are more than
REM two. Without them the path quote is broken and python never runs -- which
REM silently left NOW empty and disabled the crash-loop brake (fixed 2026-11-04).
set "%~1="
for /f %%T in ('""%PY%" -c "import datetime;print(datetime.datetime.now(datetime.timezone.utc).strftime('%%Y-%%m-%%dT%%H:%%M:%%SZ'))""') do set "%~1=%%T"
exit /b 0

:now
set "%~1="
for /f %%T in ('""%PY%" -c "import time;print(int(time.time()))""') do set "%~1=%%T"
exit /b 0

:grow_backoff
set /a BACKOFF=BACKOFF*2
if !BACKOFF! gtr %BACKOFF_MAX% set /a BACKOFF=%BACKOFF_MAX%
exit /b 0
