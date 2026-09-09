@echo off
REM ===========================================================================
REM  One-shot bootstrap for a BRAND-NEW Windows 11 machine.
REM
REM    Right-click this file -> "Run as administrator"
REM
REM  Takes a bare machine to "ready to configure accounts":
REM
REM    1. Python 3.11+ 64-bit            (winget)
REM    2. MetaTrader 5                   (existing, or winget, or you fetch it)
REM    3. Three PORTABLE terminal installs + launchers
REM    4. .venv, dependencies, test suite    (delegates to scripts\setup.bat)
REM
REM  Pure batch on purpose. An earlier version put the real work in PowerShell;
REM  it was written on a Mac where no PowerShell existed to run it, so it would
REM  have had its first execution on the machine that holds real money. Batch is
REM  clumsier but every line here is something that can be reasoned about
REM  without an interpreter to test it against.
REM
REM  Every step is idempotent: re-running skips what is already done. That
REM  matters because step 2 can legitimately stop and ask you to download the
REM  Exness build by hand, after which you just run this again.
REM
REM  What it deliberately does NOT do: log in to any account, or enable Algo
REM  Trading. Both need your password and your eyes on a real balance.
REM ===========================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0.."
set "ROOT=%CD%"

echo.
echo  trading-bot :: Windows bootstrap
echo  root: %ROOT%
echo.

REM ---------------------------------------------------------------------------
echo == [0] Checking the machine
REM ---------------------------------------------------------------------------

REM Self-elevation is deliberately NOT attempted. Doing it in batch means
REM shelling out to PowerShell or writing a temp VBScript, and a bootstrap that
REM silently relaunches itself in another window is harder to trust than one
REM that tells you what it needs.
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo    FAIL  not running as administrator.
    echo.
    echo          Installing Python and MetaTrader, and writing to C:\MT5-*,
    echo          all need admin rights.
    echo.
    echo          Close this window, RIGHT-CLICK bootstrap_windows.bat and
    echo          choose "Run as administrator".
    echo.
    goto :fail
)
echo    ok   running as administrator

if /i not "%PROCESSOR_ARCHITECTURE%"=="AMD64" if /i not "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
    echo    FAIL  this is a 32-bit Windows ^(%PROCESSOR_ARCHITECTURE%^).
    echo          The MetaTrader5 package needs 64-bit.
    goto :fail
)
echo    ok   64-bit Windows ^(%PROCESSOR_ARCHITECTURE%^)

REM winget ships with Windows 11. Missing means a very stale build or Windows
REM Server, and nothing below can install anything -- better to say so now than
REM to fail four steps later.
where winget >nul 2>&1
if errorlevel 1 (
    echo.
    echo    FAIL  winget is not available.
    echo.
    echo          It ships with Windows 11. If this really is a fresh install,
    echo          get "App Installer" from the Microsoft Store, then re-run.
    echo.
    goto :fail
)
echo    ok   winget present

REM ---------------------------------------------------------------------------
echo.
echo == [1] Python 3.11+ ^(64-bit^)
REM ---------------------------------------------------------------------------

call :find_python
if defined PYEXE (
    echo    ok   already installed: !PYEXE!
    goto :python_ready
)

echo    ..   installing Python 3.12 via winget ^(takes a few minutes^)
winget install --id Python.Python.3.12 --scope machine --accept-package-agreements --accept-source-agreements --silent --disable-interactivity
echo    ..   looking for the interpreter it just installed

REM No registry PATH reparsing: this session started before winget wrote those
REM entries and will never see them. Searching the install locations directly is
REM both simpler and more reliable than trying to rebuild PATH in batch, where
REM REG_EXPAND_SZ values come back with %%SystemRoot%% unexpanded.
call :find_python
if not defined PYEXE (
    echo.
    echo    FAIL  Python installed but no 64-bit 3.11+ interpreter was found.
    echo.
    echo          Open a NEW Command Prompt and run:  python --version
    echo          If that works, re-run this script.
    echo.
    goto :fail
)
echo    ok   installed: !PYEXE!

:python_ready
for %%I in ("!PYEXE!") do set "PYDIR=%%~dpI"
if "!PYDIR:~-1!"=="\" set "PYDIR=!PYDIR:~0,-1!"
REM Put it at the FRONT of this session's PATH so the setup.bat we call in
REM step 4 -- which looks for a bare `python` -- finds this exact interpreter
REM and not, say, the Microsoft Store stub.
set "PATH=!PYDIR!;!PYDIR!\Scripts;%PATH%"
"!PYEXE!" --version

REM ---------------------------------------------------------------------------
echo.
echo == [2] MetaTrader 5
REM ---------------------------------------------------------------------------

call :find_mt5
if defined MTEXE (
    echo    ok   found: !MTEXE!
    goto :mt5_ready
)

echo    ..   no terminal found -- trying winget
REM Best-effort on purpose. This package id may not exist in every winget
REM source, and where it does it is the GENERIC MetaQuotes build, not the
REM Exness one. If it fails the script stops and asks for the Exness build,
REM which is the better outcome anyway.
winget install --id MetaQuotes.MetaTrader5 --accept-package-agreements --accept-source-agreements --silent --disable-interactivity
call :find_mt5

if not defined MTEXE (
    echo.
    echo    ----------------------------------------------------------------
    echo     MetaTrader 5 could not be installed automatically.
    echo.
    echo     Download the EXNESS build from your Exness Personal Area
    echo     ^(Settings -^> Platforms -^> MetaTrader 5 for Windows^) and
    echo     install it with the default options.
    echo.
    echo     Use the Exness build, not the generic MetaQuotes one -- it
    echo     already knows the Exness servers, so you will not have to type
    echo     Exness-MT5Real10 by hand.
    echo.
    echo     Then run this script again. Everything above is already done
    echo     and will be skipped.
    echo    ----------------------------------------------------------------
    echo.
    goto :fail
)
echo    ok   found: !MTEXE!

:mt5_ready
for %%I in ("!MTEXE!") do set "MTDIR=%%~dpI"
if "!MTDIR:~-1!"=="\" set "MTDIR=!MTDIR:~0,-1!"

REM ---------------------------------------------------------------------------
echo.
echo == [3] Three portable terminal installs
REM ---------------------------------------------------------------------------

REM One install per account. Portable mode keeps each one's settings and saved
REM account inside its OWN folder instead of the shared %%APPDATA%% tree.
REM
REM This is not tidiness. Without it all three terminals share one accounts.dat
REM and log each other out -- the exact failure that cost a live session when a
REM bitcoin login landed in the gold terminal and the gold bot lost its account
REM mid-position.

call :make_install "C:\MT5-Gold" "MT5 Gold 77020"    || goto :fail
call :make_install "C:\MT5-BTC"  "MT5 Bitcoin 77021" || goto :fail
call :make_install "C:\MT5-FX"   "MT5 EURJPY 77022"  || goto :fail

REM ---------------------------------------------------------------------------
echo.
echo == [4] Project: venv, dependencies, tests
REM ---------------------------------------------------------------------------

if not exist "%ROOT%\scripts\setup.bat" (
    echo    FAIL  missing scripts\setup.bat -- is this the unzipped project root?
    goto :fail
)

REM Delegated rather than duplicated: setup.bat is the tested path and already
REM refuses to continue when the suite fails.
call "%ROOT%\scripts\setup.bat"
if errorlevel 1 (
    echo.
    echo    FAIL  setup.bat failed -- see the output above.
    goto :fail
)

REM ---------------------------------------------------------------------------
echo.
echo ===========================================================================
echo  BOOTSTRAP COMPLETE -- what is left, and only you can do it
echo ===========================================================================
echo.
echo  1. Start each terminal from its launcher on the Desktop. They pass
echo     /portable; starting a terminal any other way silently rejoins the
echo     shared profile and the account isolation is gone.
echo.
echo        MT5 Gold 77020.cmd     -^> log in to the gold account
echo        MT5 Bitcoin 77021.cmd  -^> log in to the bitcoin account
echo        MT5 EURJPY 77022.cmd   -^> log in to the EUR/JPY account
echo.
echo     In each: Tools ^> Options ^> Expert Advisors ^> "Allow algorithmic
echo     trading". This RESETS every time you switch accounts.
echo.
echo     Dismiss any "LiveUpdate" or "open an account" dialog FIRST. They
echo     swallow keystrokes including Ctrl+E, and the Algo Trading button
echo     will not respond while they are up. Choose "Later", never
echo     "Restart", if a position is open.
echo.
echo  2. Edit each config and set:
echo.
echo        bridge        = "native"
echo        terminal_path = 'C:\MT5-Gold\terminal64.exe'   ^(that bot's OWN one^)
echo        symbol        = read it from Market Watch, do not guess
echo.
echo     terminal_path is not optional with three terminals running. Without
echo     it the bot attaches to whichever it finds first and trades the WRONG
echo     account, silently.
echo.
echo  3. Preflight each one ^(read-only, places nothing^):
echo.
echo        .venv\Scripts\python scripts\preflight_live.py --config config\config-cent.toml --real-account
echo.
echo  4. Only then install the scheduled tasks:
echo.
echo        scripts\install_windows_tasks.bat
echo.
echo  EUR/JPY ships DISABLED on purpose -- config\config-eurjpy.toml has a
echo  checklist at the top. Three of its numbers have never been measured on
echo  that instrument.
echo.
echo  Full runbook: docs\windows-deployment.md
echo.
goto :done


REM ===========================================================================
REM  Subroutines
REM ===========================================================================

:find_python
REM Sets PYEXE to a python.exe that is BOTH >= 3.11 AND 64-bit, or leaves it
REM unset. Both conditions are checked by RUNNING the interpreter: a 32-bit
REM 3.12 passes a version-string test and then cannot import MetaTrader5, which
REM is a confusing failure to hit later rather than now.
set "PYEXE="
for %%P in (python.exe) do (
    if not defined PYEXE if exist "%%~$PATH:P" call :probe_python "%%~$PATH:P"
)
for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
    if not defined PYEXE if exist "%%~fD\python.exe" call :probe_python "%%~fD\python.exe"
)
for /d %%D in ("%ProgramFiles%\Python3*") do (
    if not defined PYEXE if exist "%%~fD\python.exe" call :probe_python "%%~fD\python.exe"
)
exit /b 0

:probe_python
REM %1 = candidate python.exe. Prints "OK" only when it is 64-bit and >= 3.11.
REM The Microsoft Store stub also answers to `python` and fails this harmlessly.
set "CAND=%~1"
"%CAND%" -c "import sys,struct;print('OK' if sys.version_info>=(3,11) and struct.calcsize('P')*8==64 else 'NO')" >"%TEMP%\tb_pyprobe.txt" 2>nul
if errorlevel 1 exit /b 0
set /p PROBE=<"%TEMP%\tb_pyprobe.txt"
del "%TEMP%\tb_pyprobe.txt" >nul 2>&1
if /i "%PROBE%"=="OK" set "PYEXE=%CAND%"
exit /b 0

:find_mt5
REM Exness ships its own branded build; that is the one you want.
set "MTEXE="
for %%C in (
    "%ProgramFiles%\MetaTrader 5 EXNESS\terminal64.exe"
    "%ProgramFiles%\MetaTrader 5\terminal64.exe"
    "%ProgramFiles(x86)%\MetaTrader 5 EXNESS\terminal64.exe"
    "%ProgramFiles(x86)%\MetaTrader 5\terminal64.exe"
) do (
    if not defined MTEXE if exist %%C set "MTEXE=%%~C"
)
exit /b 0

:make_install
REM %1 = target dir, %2 = launcher label.
set "TGT=%~1"
set "LABEL=%~2"

if exist "%TGT%\terminal64.exe" (
    echo    ok   %TGT% already exists -- left alone
) else (
    echo    ..   copying "%MTDIR%" -^> "%TGT%"
    xcopy "%MTDIR%" "%TGT%\" /E /I /H /Y /Q >nul
    if errorlevel 1 (
        echo    FAIL  copy to %TGT% failed
        exit /b 1
    )
    if not exist "%TGT%\terminal64.exe" (
        echo    FAIL  copy did not produce %TGT%\terminal64.exe
        exit /b 1
    )
    echo    ok   created %TGT%
)

REM A .cmd launcher rather than a .lnk shortcut: creating a real shortcut from
REM batch needs PowerShell or a throwaway VBScript, and this does the same job
REM with nothing to go wrong. The /portable flag is the entire point of it.
set "LNK=%PUBLIC%\Desktop\%LABEL%.cmd"
> "%LNK%" echo @echo off
>>"%LNK%" echo REM %LABEL% -- ALWAYS start the terminal this way.
>>"%LNK%" echo REM /portable keeps this install's account and settings in its own
>>"%LNK%" echo REM folder. Without it all three terminals share one accounts.dat
>>"%LNK%" echo REM and log each other out.
>>"%LNK%" echo start "" "%TGT%\terminal64.exe" /portable
echo    ok   launcher: %LNK%
exit /b 0


:fail
echo.
echo == BOOTSTRAP FAILED -- nothing further was attempted.
echo.
echo Press any key to close...
pause >nul
endlocal
exit /b 1

:done
echo Press any key to close...
pause >nul
endlocal
exit /b 0
