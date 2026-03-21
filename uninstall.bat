@echo off

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

set /p CONFIRM="  Are you sure? (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo  Cancelled.
    pause
    exit /b 0
)

echo.

:: Remove backend files, venv, and models
if exist "%APPDATA%\CorridorKeyForResolve" (
    echo   Removing backend files...
    rmdir /S /Q "%APPDATA%\CorridorKeyForResolve"
    echo   Done.
) else (
    echo   Backend directory not found.
)

:: Remove OFX plugin (needs admin)
if exist "C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle" (
    echo   Removing OFX plugin (may prompt for admin)...
    powershell -Command "Start-Process powershell -ArgumentList '-Command Remove-Item -Path ''C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle'' -Recurse -Force' -Verb RunAs -Wait"
    if exist "C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle" (
        echo   WARNING: Could not remove OFX plugin. Delete manually.
    ) else (
        echo   OFX plugin removed.
    )
) else (
    echo   OFX plugin not found.
)

echo.
echo ============================================================
echo  Uninstall complete.
echo ============================================================
echo.
pause
