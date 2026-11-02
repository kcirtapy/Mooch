@echo off
REM One-off run: fetch, classify, and open the HTML report.
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
  echo No .venv found in this folder. See START-HERE.md, Stage 1.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
mooch run --open
echo.
pause
