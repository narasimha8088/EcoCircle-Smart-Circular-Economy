@echo off
echo.
echo  EcoCircle - Smart Circular Economy Platform
echo  ============================================
echo.

REM ── Kill any existing process on port 5000 using PowerShell ───────────────
echo  Checking for processes on port 5000...
powershell -NoProfile -Command "$conn = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue; if ($conn) { Write-Host '  Stopping previous server (PID' $conn.OwningProcess ')...'; Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2 } else { Write-Host '  Port 5000 is free. Good to go.' }"

cd backend

REM Create venv if missing
if not exist "venv" (
  echo Creating virtual environment...
  python -m venv venv
  call venv\Scripts\activate.bat
  echo Installing dependencies (first-time setup, please wait)...
  pip install -r requirements.txt -q
) else (
  call venv\Scripts\activate.bat
)

REM Copy env if missing
if not exist ".env" (
  if exist ".env.example" (
    copy ".env.example" ".env" >nul
  )
)

echo.
echo  Starting EcoCircle Platform...
echo  A clickable link will appear below - Ctrl+Click it to open the app.
echo  (The browser also opens automatically.)  Press Ctrl+C to stop.
echo.
python app.py
pause
