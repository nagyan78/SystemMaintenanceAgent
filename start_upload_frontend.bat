@echo off
setlocal
cd /d "%~dp0"
title Standard Product Upload Diagnosis

echo ============================================================
echo Standard Product Upload Diagnosis
echo ============================================================
echo Project folder:
echo %CD%
echo.

set "PYTHON_EXE=.\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo ERROR: Python runtime was not found:
  echo %CD%\.venv\Scripts\python.exe
  echo.
  echo Please install dependencies first, or tell Codex to repair the environment.
  echo.
  pause
  exit /b 1
)

echo Checking Python dependencies...
"%PYTHON_EXE%" -B -c "import pandas, openpyxl" >nul 2>nul
if errorlevel 1 (
  echo ERROR: Missing Python dependencies.
  echo.
  echo Try running this command in this folder:
  echo %PYTHON_EXE% -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo Starting local web server...
echo The browser should open automatically.
echo If it does not, copy this URL into your browser:
echo http://127.0.0.1:8765/
echo.
echo Keep this window open while using the web page.
echo Press Ctrl+C to stop the server.
echo ============================================================
echo.

"%PYTHON_EXE%" -B -m src.web_app --host 127.0.0.1 --port 8765 --open-browser

echo.
echo The server stopped or failed to start.
echo If there is an error above, send it to Codex.
echo.
pause
