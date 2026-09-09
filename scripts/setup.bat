@echo off
REM One-shot setup for Windows -- the platform this bot is meant to run on.
REM
REM   scripts\setup.bat
REM
REM MetaTrader 5 and its Python API are Windows software, so there is no
REM container, no Wine and no RPC bridge here: the bot talks to the terminal
REM directly. Set bridge = "native" in config\config.toml (or leave "auto",
REM which tries native first).
REM
REM Needs Python 3.11+ from python.org with "Add Python to PATH" ticked, and
REM the MetaTrader 5 terminal installed and logged in to your account.

setlocal
cd /d "%~dp0.."

echo.
echo == checking Python
where python >nul 2>&1
if errorlevel 1 (
    echo FAILED: python is not on PATH.
    echo         Install Python 3.11+ from https://www.python.org/downloads/
    echo         and tick "Add Python to PATH" during installation.
    exit /b 1
)
REM 3.11 is the floor: the config loader uses stdlib tomllib.
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
    echo FAILED: Python 3.11 or newer is required.
    python --version
    exit /b 1
)
python --version

echo.
echo == creating .venv
if not exist .venv (
    python -m venv .venv
    if errorlevel 1 ( echo FAILED: could not create the virtualenv & exit /b 1 )
)
set VPY=.venv\Scripts\python.exe
"%VPY%" -m pip install --quiet --upgrade pip

echo.
echo == installing the project
"%VPY%" -m pip install --quiet -e ".[dev]"
if errorlevel 1 ( echo FAILED: pip install failed & exit /b 1 )

echo.
echo == installing MetaTrader5
"%VPY%" -m pip install --quiet MetaTrader5
if errorlevel 1 (
    echo WARNING: MetaTrader5 did not install. Backtesting still works;
    echo          live trading will not. It needs 64-bit Python on Windows.
) else (
    echo    ok
)

echo.
echo == running the tests
"%VPY%" -m pytest -q
if errorlevel 1 ( echo FAILED: tests did not pass -- stop here & exit /b 1 )

echo.
echo == ready
echo.
echo   backtest ^(no MetaTrader needed^):
echo       .venv\Scripts\python -m trading_bot.cli backtest
echo.
echo   dry run, places nothing:
echo       .venv\Scripts\python -m trading_bot.cli live --mode dry-run --once
echo.
echo   check the terminal connection before trading:
echo       .venv\Scripts\python scripts\preflight_demo.py
echo       ^(refuses REAL accounts by design -- that guard is deliberate^)
echo.
echo   close an open position by ticket:
echo       .venv\Scripts\python scripts\close_position.py --ticket N --dry-run
echo       .venv\Scripts\python scripts\close_position.py --ticket N --confirm
echo.
echo == which config
echo.
echo   config\config.toml         standard account, gold
echo   config\config-cent.toml    CENT account, gold ^(XAUUSDc^) -- see below
echo   config\config-btc.toml     CENT account, bitcoin ^(BTCUSDc^), trades 24/7
echo   config\config-eurjpy.toml  EUR/JPY -- ships DISABLED, has a checklist
echo                              at the top. Work it before enabling.
echo.
echo   Pass one with --config, e.g.
echo       .venv\Scripts\python -m trading_bot.cli live --config config\config-cent.toml
echo.
echo   In whichever you use, on Windows:
echo     - set bridge = "native"   ^(the container bridge is macOS/Linux only^)
echo     - RUNNING MORE THAN ONE ACCOUNT? set terminal_path to that bot's own
echo       terminal64.exe, e.g. 'C:\MT5-Gold\terminal64.exe', and run each
echo       install with /portable. Without it initialize^(^) attaches to
echo       whichever terminal it finds first and the bot trades the WRONG
echo       account, silently. See docs\windows-deployment.md.
echo     - set [live] symbol to YOUR broker's name for the instrument.
echo       Suffixes are broker-specific: XAUUSDm on a standard account here,
echo       XAUUSDc on the cent account. Read it from Market Watch, do not guess.
echo     - keep [live] mode = "demo" until you have watched it trade
echo.
echo == small balance? you probably need a CENT account
echo.
echo   The stop is structural, so on a standard account the broker's minimum
echo   0.01 lots of gold ^(1 oz^) can risk more than 100%% of a small balance and
echo   the bot will correctly refuse every setup. A USC cent account quotes gold
echo   at 1 oz per lot against a cent-denominated balance, which is what makes
echo   the same trade land near 1%% instead.
echo.
echo   Full steps: docs\cent-account-setup.md
echo.
echo == before any of it works
echo.
echo   In the terminal, enable Tools ^> Options ^> Expert Advisors
echo   ^> "Allow algorithmic trading", or every order is rejected.
echo   This RESETS when you switch accounts -- re-check after every login.
echo.
echo   Backtesting needs histdata M1 CSVs in data\raw\ -- they are not in the
echo   zip ^(gitignored^). See the README for where to download them.
echo.
endlocal
