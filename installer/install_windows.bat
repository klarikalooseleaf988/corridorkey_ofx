@echo off
REM CorridorKey for Resolve - Windows Installer
REM Installs both the OFX plugin and Python backend
setlocal

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
set OFX_DEST=C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle

echo ============================================================
echo   CorridorKey for Resolve - Installer
echo ============================================================
echo.

REM Check admin privileges for plugin install
net session >nul 2>&1
if errorlevel 1 (
    echo WARNING: Not running as Administrator.
    echo Plugin install to Program Files requires admin rights.
    echo Please right-click and "Run as administrator".
    echo.
    pause
    exit /b 1
)

REM Step 1: Build plugin
echo [Step 1] Building OFX plugin...
call "%PROJECT_DIR%\scripts\build_plugin.bat"
if errorlevel 1 (
    echo Plugin build failed. Aborting.
    exit /b 1
)
echo.

REM Step 2: Install plugin bundle
echo [Step 2] Installing OFX plugin bundle...
if exist "%OFX_DEST%" (
    echo Removing existing installation...
    rmdir /S /Q "%OFX_DEST%"
)
xcopy /E /I /Y "%PROJECT_DIR%\plugin\build\CorridorKeyForResolve.ofx.bundle" "%OFX_DEST%\"
echo Plugin installed to: %OFX_DEST%
echo.

REM Step 3: Install Python backend
echo [Step 3] Installing Python backend...
python "%PROJECT_DIR%\backend\install.py"
if errorlevel 1 (
    echo Backend installation failed.
    exit /b 1
)
echo.

echo ============================================================
echo   Installation Complete!
echo.
echo   1. Start the backend: scripts\start_backend.bat
echo   2. Open DaVinci Resolve 20
echo   3. Apply "CorridorKey" from OFX plugins
echo ============================================================
pause
