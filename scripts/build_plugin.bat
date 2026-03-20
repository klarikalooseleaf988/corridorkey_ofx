@echo off
REM Build the CorridorKey OFX plugin for Windows
setlocal

set SCRIPT_DIR=%~dp0
set PLUGIN_DIR=%SCRIPT_DIR%..\plugin

echo === Building CorridorKey for Resolve OFX Plugin ===
echo.

cd /d "%PLUGIN_DIR%"

if not exist build (
    echo Configuring CMake...
    cmake -B build -G "Visual Studio 17 2022" -A x64
    if errorlevel 1 (
        echo CMake configuration failed!
        exit /b 1
    )
)

echo Building...
cmake --build build --config Release
if errorlevel 1 (
    echo Build failed!
    exit /b 1
)

echo.
echo === Build successful ===
echo OFX bundle: %PLUGIN_DIR%\build\CorridorKeyForResolve.ofx.bundle\
echo.
echo To install, copy the bundle to:
echo   C:\Program Files\Common Files\OFX\Plugins\
