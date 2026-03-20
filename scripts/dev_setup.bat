@echo off
REM Developer setup: builds plugin and runs backend from source
setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..

echo === CorridorKey for Resolve - Dev Setup ===
echo.

REM Build plugin
echo [1/2] Building OFX plugin...
call "%SCRIPT_DIR%build_plugin.bat"
if errorlevel 1 exit /b 1
echo.

REM Install plugin bundle (requires admin for Program Files)
echo [2/2] To install the plugin, run as Administrator:
echo   xcopy /E /Y "%PROJECT_DIR%\plugin\build\CorridorKeyForResolve.ofx.bundle" "C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle\"
echo.

echo To run the backend from source (for development):
echo   cd "%PROJECT_DIR%\backend"
echo   pip install -e .
echo   python server.py --verbose
echo.

echo === Dev setup complete ===
