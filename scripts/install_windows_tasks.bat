@echo off
REM ===========================================================================
REM  Register (or remove) the scheduled tasks that keep the bots running.
REM
REM    scripts\install_windows_tasks.bat
REM    scripts\install_windows_tasks.bat /remove
REM    scripts\install_windows_tasks.bat /only cent
REM
REM  The Windows counterpart of the com.joram.trading-bot-*.plist launchd
REM  agents. One task per bot, each starting that bot's supervisor at logon.
REM
REM  WHY AT LOGON, AND NOT AS A SERVICE. The MetaTrader5 pip package talks to a
REM  terminal running in an interactive desktop session. A Windows service runs
REM  in session 0 with no desktop, so a service-hosted bot would find no
REM  terminal to attach to -- the same class of quiet failure as attaching to
REM  the wrong terminal. An at-logon task runs in the session the terminals live
REM  in, which is the only place this can work.
REM
REM  The consequence, which must not be glossed over: THE NUC MUST BE LOGGED IN.
REM  Set it to auto-logon, or the bots do not start. The supervisor disables
REM  sleep and hibernate on AC power itself.
REM
REM  Restart-on-failure is NOT configured here. schtasks can only express it via
REM  an XML import, and it would be the wrong layer anyway: supervise_live.bat
REM  already knows the difference between "died once" and "cannot start
REM  cleanly", and an outer restarter would defeat its crash-loop brake by
REM  relaunching the supervisor every time it correctly gave up.
REM ===========================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0.."
set "ROOT=%CD%"
set "SUP=%ROOT%\scripts\supervise_live.bat"
REM pythonw = no console window, for the helper tasks below.
set "PYW=%ROOT%\.venv\Scripts\pythonw.exe"

set "MODE=install"
set "ONLY="
:parse
if "%~1"=="" goto :parsed
if /i "%~1"=="/remove" set "MODE=remove" & shift & goto :parse
if /i "%~1"=="/only"   set "ONLY=%~2"    & shift & shift & goto :parse
echo Unknown argument: %~1
echo Usage: install_windows_tasks.bat [/remove] [/only TAG]
exit /b 1
:parsed

if not exist "%SUP%" (
    echo FAIL: missing %SUP%
    exit /b 1
)

call :handle cent   config\config-cent.toml   live_cent.log   || goto :fail
call :handle btc    config\config-btc.toml    live_btc.log    || goto :fail
call :handle eurjpy config\config-eurjpy.toml live_eurjpy.log || goto :fail
call :helpers || goto :fail

if /i "%MODE%"=="remove" goto :done

echo.
echo Registered at LOGON, not at boot -- the terminals need a desktop session.
echo.
echo   start now:   schtasks /Run   /TN trading-bot-cent
echo   stop  one:   type nul ^> output\live_cent.stop
echo                (the supervisor sees the sentinel and exits cleanly;
echo                 schtasks /End alone orphans the bot process, still trading)
echo   status:      schtasks /Query /TN trading-bot-cent
echo   log:         type output\supervise_cent.log
echo.
echo Each bot needs its OWN terminal install and its OWN account. Set
echo [live] terminal_path in every config first -- see docs\windows-deployment.md.
echo.
echo Helper tasks:
echo   trading-bot-terminals  at logon: opens the cent + btc MT5 terminals
echo   trading-bot-watchdog   every 5 min: phone alerts ^(watchdog.py --new-topic, then the ntfy app^)
echo.
echo For a reboot to come back on its own, Windows must also AUTO-LOGON to this
echo user -- see docs\windows-deployment.md, "Surviving a reboot".
echo.
echo EUR/JPY ships DISABLED. Its task is registered so it is ready, but the bot
echo will refuse to trade until you work the checklist in config-eurjpy.toml.
echo.

:done
endlocal
exit /b 0

:fail
endlocal
exit /b 1


REM ===========================================================================
:handle
REM %1 = tag, %2 = config, %3 = log
set "TAG=%~1"
set "CFG=%~2"
set "LOG=%~3"
set "TN=trading-bot-%TAG%"

if defined ONLY if /i not "%ONLY%"=="%TAG%" exit /b 0

if /i "%MODE%"=="remove" (
    schtasks /Query /TN "%TN%" >nul 2>&1
    if errorlevel 1 (
        echo absent    %TN%
    ) else (
        schtasks /Delete /TN "%TN%" /F >nul
        if errorlevel 1 ( echo FAIL: could not delete %TN% & exit /b 1 )
        echo removed   %TN%
    )
    exit /b 0
)

if not exist "%ROOT%\%CFG%" (
    echo FAIL: missing %CFG% -- refusing to register a task that cannot run
    exit /b 1
)

REM The inner quoting is what schtasks needs: /TR takes ONE string, and the
REM path to the supervisor contains spaces, so its quotes are doubled.
REM /DELAY 90s: let trading-bot-terminals open the MT5 terminals first.
schtasks /Create /TN "%TN%" /SC ONLOGON /DELAY 0001:30 /RL HIGHEST /F /RU "%USERDOMAIN%\%USERNAME%" /TR "\"%SUP%\" \"%CFG%\" \"%LOG%\" \"%TAG%\"" >nul
if errorlevel 1 (
    echo FAIL: could not register %TN%
    exit /b 1
)
echo registered  %TN%  -^>  %CFG%
exit /b 0


REM ===========================================================================
:helpers
REM trading-bot-terminals (at logon) and trading-bot-watchdog (every 5 min).
if defined ONLY exit /b 0
for %%N in (trading-bot-terminals trading-bot-watchdog) do (
    if /i "%MODE%"=="remove" (
        schtasks /Query /TN "%%N" >nul 2>&1
        if errorlevel 1 (
            echo absent    %%N
        ) else (
            schtasks /Delete /TN "%%N" /F >nul
            echo removed   %%N
        )
    )
)
if /i "%MODE%"=="remove" exit /b 0

if not exist "%PYW%" (
    echo FAIL: missing %PYW% -- run scripts\setup.bat first
    exit /b 1
)
schtasks /Create /TN "trading-bot-terminals" /SC ONLOGON /RL HIGHEST /F /RU "%USERDOMAIN%\%USERNAME%" /TR "\"%PYW%\" \"%ROOT%\scripts\start_terminals.py\"" >nul
if errorlevel 1 ( echo FAIL: could not register trading-bot-terminals & exit /b 1 )
echo registered  trading-bot-terminals  -^>  opens the MT5 terminals at logon
schtasks /Create /TN "trading-bot-watchdog" /SC MINUTE /MO 5 /RL HIGHEST /F /RU "%USERDOMAIN%\%USERNAME%" /TR "\"%PYW%\" \"%ROOT%\scripts\watchdog.py\"" >nul
if errorlevel 1 ( echo FAIL: could not register trading-bot-watchdog & exit /b 1 )
echo registered  trading-bot-watchdog   -^>  every 5 minutes
exit /b 0
