@echo off
setlocal enableextensions

:: ============================================================
:: CorridorKey for Resolve - One-Click Installer
:: ============================================================

echo.
echo ============================================================
echo  CorridorKey for Resolve - Installer
echo ============================================================
echo.

:: Save script directory
set "INSTALLER_DIR=%~dp0"

:: Configuration
set "APPDATA_DIR=%APPDATA%\CorridorKeyForResolve"
set "VENV_DIR=%APPDATA_DIR%\venv"
set "CK_REPO_DIR=%APPDATA_DIR%\CorridorKey"
set "OFX_DIR=C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle"
set "CK_ZIP_URL=https://github.com/nikopueringer/CorridorKey/archive/refs/heads/main.zip"
set "CKPT_URL=https://huggingface.co/nikopueringer/CorridorKey_v1.0/resolve/main/CorridorKey_v1.0.pth"

:: --------------------------------------------------------
:: Step 1: Find Python 3.10-3.13
:: --------------------------------------------------------
echo [1/6] Finding Python...

set "PYTHON_EXE="
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if "%PYTHON_EXE%"=="" if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if "%PYTHON_EXE%"=="" if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if "%PYTHON_EXE%"=="" if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"

if "%PYTHON_EXE%"=="" (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        for /f "delims=" %%p in ('where python') do set "PYTHON_EXE=%%p"
    )
)

if "%PYTHON_EXE%"=="" (
    echo.
    echo  ERROR: Python not found!
    echo  Install Python 3.13 from:
    echo    https://www.python.org/downloads/release/python-31312/
    echo  Check "Add Python to PATH" during installation.
    echo.
    goto :error
)

echo   Found: %PYTHON_EXE%
for /f "tokens=2 delims= " %%v in ('"%PYTHON_EXE%" --version 2^>^&1') do set "PY_VER=%%v"
echo   Version: %PY_VER%

:: Check version range
for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do set "PY_MAJOR=%%a" & set "PY_MINOR=%%b"
if %PY_MINOR% lss 10 goto :bad_python
if %PY_MINOR% gtr 13 goto :bad_python
goto :python_ok

:bad_python
echo.
echo  ERROR: Python %PY_VER% is not supported!
echo  PyTorch requires Python 3.10-3.13.
echo  Install Python 3.13 from:
echo    https://www.python.org/downloads/release/python-31312/
echo.
goto :error

:python_ok

:: --------------------------------------------------------
:: Step 2: Install OFX plugin (needs admin)
:: --------------------------------------------------------
echo.
echo [2/6] Installing OFX plugin...

set "BUNDLE_SRC="
if exist "%INSTALLER_DIR%CorridorKeyForResolve.ofx.bundle\Contents\Win64\CorridorKeyForResolve.ofx" set "BUNDLE_SRC=%INSTALLER_DIR%CorridorKeyForResolve.ofx.bundle"
if "%BUNDLE_SRC%"=="" if exist "%INSTALLER_DIR%plugin\build\CorridorKeyForResolve.ofx.bundle\Contents\Win64\CorridorKeyForResolve.ofx" set "BUNDLE_SRC=%INSTALLER_DIR%plugin\build\CorridorKeyForResolve.ofx.bundle"

if "%BUNDLE_SRC%"=="" (
    echo.
    echo  ERROR: OFX plugin bundle not found!
    echo  Download from: https://github.com/gitcapoom/corridorkey_ofx/releases
    echo.
    goto :error
)

echo   Copying plugin to Program Files (may prompt for admin)...
powershell -Command "Start-Process powershell -ArgumentList '-Command Copy-Item -Path ''%BUNDLE_SRC%'' -Destination ''C:\Program Files\Common Files\OFX\Plugins\'' -Recurse -Force' -Verb RunAs -Wait"

if not exist "%OFX_DIR%\Contents\Win64\CorridorKeyForResolve.ofx" (
    echo  ERROR: Failed to install OFX plugin. Close DaVinci Resolve and retry.
    goto :error
)
echo   Plugin installed.

:: --------------------------------------------------------
:: Step 3: Create virtual environment
:: --------------------------------------------------------
echo.
echo [3/6] Setting up Python environment...

if not exist "%APPDATA_DIR%" mkdir "%APPDATA_DIR%"

if not exist "%VENV_DIR%\Scripts\python.exe" goto :create_venv

:: Check existing venv version - recreate if incompatible
for /f "tokens=2 delims= " %%v in ('"%VENV_DIR%\Scripts\python.exe" --version 2^>^&1') do set "VENV_VER=%%v"
for /f "tokens=2 delims=." %%m in ("%VENV_VER%") do set "VENV_MINOR=%%m"
if %VENV_MINOR% gtr 13 goto :recreate_venv
if %VENV_MINOR% lss 10 goto :recreate_venv
echo   Virtual environment exists (Python %VENV_VER%).
goto :venv_ready

:recreate_venv
echo   Existing venv uses Python %VENV_VER% - recreating...
rmdir /S /Q "%VENV_DIR%"

:create_venv
echo   Creating virtual environment...
"%PYTHON_EXE%" -m venv "%VENV_DIR%"
if %errorlevel% neq 0 goto :venv_error
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1

:venv_ready
set "PIP=%VENV_DIR%\Scripts\python.exe -m pip"
goto :venv_ok

:venv_error
echo  ERROR: Failed to create virtual environment.
goto :error

:venv_ok

:: --------------------------------------------------------
:: Step 4: Download CorridorKey source + model weights
:: --------------------------------------------------------
echo.
echo [4/6] Downloading CorridorKey...

:: Download source code
if exist "%CK_REPO_DIR%\CorridorKeyModule\inference_engine.py" (
    echo   Source code already downloaded.
) else (
    echo   Downloading source code...
    powershell -Command "Invoke-WebRequest -Uri '%CK_ZIP_URL%' -OutFile '%APPDATA_DIR%\ck.zip'"
    if %errorlevel% neq 0 goto :download_error
    echo   Extracting...
    powershell -Command "Expand-Archive -Path '%APPDATA_DIR%\ck.zip' -DestinationPath '%APPDATA_DIR%\ck_temp' -Force"
    for /d %%d in ("%APPDATA_DIR%\ck_temp\CorridorKey*") do move "%%d" "%CK_REPO_DIR%" >nul
    rmdir /S /Q "%APPDATA_DIR%\ck_temp" 2>nul
    del "%APPDATA_DIR%\ck.zip" 2>nul
    echo   Source code ready.
)

:: Download model weights
set "CKPT_DIR=%CK_REPO_DIR%\CorridorKeyModule\checkpoints"
set "CKPT_FILE=%CKPT_DIR%\CorridorKey_v1.0.pth"

if exist "%CKPT_FILE%" (
    echo   Model weights already downloaded.
) else (
    echo   Downloading model weights (~400MB)...
    if not exist "%CKPT_DIR%" mkdir "%CKPT_DIR%"
    powershell -Command "Invoke-WebRequest -Uri '%CKPT_URL%' -OutFile '%CKPT_FILE%'"
    if %errorlevel% neq 0 goto :download_error
    echo   Model weights ready.
)

goto :download_ok

:download_error
echo  ERROR: Download failed. Check your internet connection.
goto :error

:download_ok

:: --------------------------------------------------------
:: Step 5: Install Python dependencies
:: --------------------------------------------------------
echo.
echo [5/6] Installing Python dependencies...

echo   Installing PyTorch with CUDA (~2.5GB)...
%PIP% install torch torchvision --index-url https://download.pytorch.org/whl/cu124
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: PyTorch installation failed.
    echo  Python version: %PY_VER%
    echo  Retry: %PIP% install torch torchvision --index-url https://download.pytorch.org/whl/cu124
    echo.
    goto :error
)

echo   Installing other dependencies...
%PIP% install numpy Pillow opencv-python timm transformers huggingface_hub
if %errorlevel% neq 0 echo   WARNING: Some dependencies failed.

echo   Installing Triton...
%PIP% install triton-windows >nul 2>&1
if %errorlevel% neq 0 echo   Warning: Triton unavailable. torch.compile will be slower.

:: --------------------------------------------------------
:: Step 6: Install backend files and verify
:: --------------------------------------------------------
echo.
echo [6/6] Installing backend files...

set "MISSING="
for %%f in (server.py ipc_protocol.py inference_wrapper.py) do (
    if exist "%INSTALLER_DIR%backend\%%f" (
        copy /Y "%INSTALLER_DIR%backend\%%f" "%APPDATA_DIR%\%%f" >nul
        echo   Copied %%f
    ) else (
        echo   NOT FOUND: %INSTALLER_DIR%backend\%%f
        set "MISSING=1"
    )
)

if defined MISSING (
    echo.
    echo  ERROR: Backend files not found next to install.bat
    echo  Script location: %INSTALLER_DIR%
    goto :error
)

:: Final verification
echo.
echo   Verifying...
set "FAIL="
if not exist "%OFX_DIR%\Contents\Win64\CorridorKeyForResolve.ofx" echo   MISSING: OFX plugin & set "FAIL=1"
if not exist "%APPDATA_DIR%\server.py" echo   MISSING: server.py & set "FAIL=1"
if not exist "%CKPT_FILE%" echo   MISSING: Model weights & set "FAIL=1"
if not exist "%VENV_DIR%\Scripts\python.exe" echo   MISSING: Python venv & set "FAIL=1"

if defined FAIL (
    echo  ERROR: Installation incomplete.
    goto :error
)
echo   All components OK.

:: --------------------------------------------------------
:: Done!
:: --------------------------------------------------------
echo.
echo ============================================================
echo  Installation complete!
echo ============================================================
echo.
echo  How to use:
echo    1. Open DaVinci Resolve
echo    2. Go to Color page or Fusion page
echo    3. Add CorridorKey from OFX plugins
echo    4. The backend starts automatically
echo.
echo  NOTE: The first frame takes ~60s for one-time GPU
echo  kernel compilation. After that: ~3s per frame.
echo ============================================================
echo.
pause
exit /b 0

:error
echo.
echo  Installation failed. Fix the issue above and re-run.
echo.
pause
exit /b 1
