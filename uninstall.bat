@echo off
setlocal

echo.
echo ============================================================
echo  CorridorKey for Resolve - Uninstaller
echo ============================================================
echo.
echo  This will remove:
echo    - OFX plugin from Program Files
echo    - Python virtual environment
echo    - CorridorKey model files
echo    - Backend files
echo.
echo  Location: %APPDATA%\CorridorKeyForResolve
echo.

set /p CONFIRM="  Are you sure? (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo  Cancelled.
    pause
    exit /b 0
)

echo.

:: Kill any running backend
tasklist | findstr /i "python" >nul 2>&1
if %errorlevel% equ 0 (
    echo   Stopping backend processes...
    for /f "tokens=2" %%p in ('tasklist ^| findstr /i "python"') do (
        wmic process where "ProcessId=%%p" get CommandLine 2>nul | findstr /i "CorridorKeyForResolve" >nul 2>&1
        if !errorlevel! equ 0 taskkill /F /PID %%p >nul 2>&1
    )
)

:: Remove backend files and venv
if exist "%APPDATA%\CorridorKeyForResolve" (
    echo   Removing backend files...
    rmdir /S /Q "%APPDATA%\CorridorKeyForResolve"
    echo   Done.
) else (
    echo   Backend directory not found (already removed).
)

:: Remove OFX plugin (needs admin)
set "OFX_DIR=C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle"
if exist "%OFX_DIR%" (
    echo   Removing OFX plugin (may prompt for admin)...
    powershell -Command "Start-Process powershell -ArgumentList '-Command \"Remove-Item -Path \\\"C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle\\\" -Recurse -Force\"' -Verb RunAs -Wait" 2>nul
    if exist "%OFX_DIR%" (
        echo   WARNING: Could not remove OFX plugin. Delete manually:
        echo     %OFX_DIR%
    ) else (
        echo   OFX plugin removed.
    )
) else (
    echo   OFX plugin not found (already removed).
)

echo.
echo ============================================================
echo  Uninstall complete.
echo ============================================================
echo.
pause
