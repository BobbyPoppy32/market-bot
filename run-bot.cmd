@echo off
REM Wrapper invoked by Windows Task Scheduler.
REM Runs the bot from this folder and appends output to logs\market-bot.log.

setlocal
cd /d "%~dp0"

if not exist "logs" mkdir "logs"

REM Any arguments passed to this script go straight through to the bot, so the
REM morning task can call:  run-bot.cmd --morning
echo.>> "logs\market-bot.log"
echo ===== run started %date% %time% (args: %*) =====>> "logs\market-bot.log"

REM Prefer the py launcher (installed with Python on Windows); fall back to python.
where py >nul 2>&1
if %errorlevel%==0 (
    py -3 "market_bot.py" %* >> "logs\market-bot.log" 2>&1
) else (
    python "market_bot.py" %* >> "logs\market-bot.log" 2>&1
)
set EXITCODE=%errorlevel%

echo ===== run finished with exit code %EXITCODE% =====>> "logs\market-bot.log"
exit /b %EXITCODE%
