@echo off
REM Start the CorridorKey for Resolve Python backend server
setlocal

set APPDATA_DIR=%APPDATA%\CorridorKeyForResolve
set VENV_PYTHON=%APPDATA_DIR%\venv\Scripts\python.exe
set SERVER_SCRIPT=%APPDATA_DIR%\server.py

REM Check if installed
if not exist "%VENV_PYTHON%" (
    echo ERROR: Backend not installed. Run the installer first:
    echo   python backend\install.py
    exit /b 1
)

if not exist "%SERVER_SCRIPT%" (
    echo ERROR: server.py not found at %SERVER_SCRIPT%
    echo Run the installer to copy backend files.
    exit /b 1
)

echo Starting CorridorKey backend server...
echo Press Ctrl+C to stop.
echo.

"%VENV_PYTHON%" "%SERVER_SCRIPT%" %*
