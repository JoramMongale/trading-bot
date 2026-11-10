@echo off
rem Download EUR/JPY 5-minute history from the gold MT5 terminal, then
rem backtest the live strategy on it. Read-only: it places no trades and
rem changes no settings, so it is safe to run while the bots are trading.
rem
rem   scripts\eurjpy_check.bat
rem
rem The result is saved to output\eurjpy_backtest.txt.
setlocal
cd /d "%~dp0.."
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Cannot find %PY% - run this from the trading-bot folder.
  pause
  exit /b 1
)

echo Step 1 of 2: downloading EUR/JPY history from the gold terminal...
echo.
"%PY%" scripts\fetch_broker_history.py --config config\config-cent.toml --symbol EURJPYc --out data\processed\EURJPYc_M5_broker.csv --spec
if errorlevel 1 goto fetch_failed

echo.
echo Step 2 of 2: backtesting, this takes a few minutes...
echo.
"%PY%" scripts\backtest_market.py --config config\config-eurjpy-backtest.toml --csv data\processed\EURJPYc_M5_broker.csv --report output\eurjpy_backtest.txt
if errorlevel 1 goto test_failed

echo.
echo Done. The result is in output\eurjpy_backtest.txt - copy it to Claude.
pause
exit /b 0

:fetch_failed
echo.
echo DOWNLOAD FAILED - see the message above.
echo Check the gold MT5 terminal is open and logged in, and that EURJPYc
echo is listed in its Market Watch.
pause
exit /b 1

:test_failed
echo.
echo BACKTEST FAILED - copy the message above to Claude.
pause
exit /b 1
