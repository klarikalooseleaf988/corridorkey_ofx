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
if /i not "%CONFIRM%"=="Y" goto :cancelled

echo.

:: Remove backend directory
if not exist "%APPDATA%\CorridorKeyForResolve" goto :no_backend
echo   Removing backend files...
rmdir /S /Q "%APPDATA%\CorridorKeyForResolve"
echo   Done.
goto :remove_ofx

:no_backend
echo   Backend directory not found.

:remove_ofx
:: Remove OFX plugin
set "OFX_PLUGIN=C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle"
if not exist "%OFX_PLUGIN%" goto :no_ofx

echo   Removing OFX plugin (may prompt for admin)...
powershell -Command "Start-Process powershell -ArgumentList '-Command Remove-Item -LiteralPath ''C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle'' -Recurse -Force' -Verb RunAs -Wait"

if exist "%OFX_PLUGIN%" (
    echo   WARNING: Could not remove OFX plugin. Delete manually.
) else (
    echo   OFX plugin removed.
)
goto :done

:no_ofx
echo   OFX plugin not found.

:done
echo.
echo ============================================================
echo  Uninstall complete.
echo ============================================================
echo.
pause
exit /b 0

:cancelled
echo  Cancelled.
pause
exit /b 0
