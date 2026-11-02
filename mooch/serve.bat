@echo off
REM Runs Mooch continuously and serves the feed to the Android app.
REM Leave this window open (minimise it). Close it to stop.
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
  echo No .venv found in this folder.
  echo Run setup first:  python -m venv .venv  then  .venv\Scripts\activate  then  pip install -e .
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
mooch serve
echo.
echo Mooch stopped. Read any error above.
pause
