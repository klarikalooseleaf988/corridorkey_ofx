@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: CorridorKey for Resolve - One-Click Installer
:: ============================================================
:: This script installs everything needed to run CorridorKey
:: in DaVinci Resolve. Just double-click to run.
:: ============================================================

echo.
echo ============================================================
echo  CorridorKey for Resolve - Installer
echo ============================================================
echo.

:: Check for admin rights, self-elevate if needed
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

:: Configuration
set "APPDATA_DIR=%APPDATA%\CorridorKeyForResolve"
set "VENV_DIR=%APPDATA_DIR%\venv"
set "CK_REPO_DIR=%APPDATA_DIR%\CorridorKey"
set "OFX_DIR=C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle"
set "SCRIPT_DIR=%~dp0"
set "CK_REPO_URL=https://github.com/nikopueringer/CorridorKey.git"

:: --------------------------------------------------------
:: Step 1: Find Python
:: --------------------------------------------------------
echo [1/6] Finding Python...

set "PYTHON_EXE="

:: Prefer Python 3.13 (3.14+ lacks PyTorch wheels)
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
) do (
    if exist %%p (
        set "PYTHON_EXE=%%~p"
        goto :found_python
    )
)

:: Try PATH
where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%p in ('where python') do (
        set "PYTHON_EXE=%%p"
        goto :found_python
    )
)

echo ERROR: Python not found.
echo Please install Python 3.10-3.13 from https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during installation.
goto :error

:found_python
echo   Found: %PYTHON_EXE%

:: Check version
for /f "tokens=2 delims= " %%v in ('"%PYTHON_EXE%" --version 2^>^&1') do set "PY_VER=%%v"
echo   Version: %PY_VER%

:: --------------------------------------------------------
:: Step 2: Check for Git
:: --------------------------------------------------------
echo.
echo [2/6] Checking for Git...
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Git not found.
    echo Please install Git from https://git-scm.com/download/win
    goto :error
)
echo   Git found.

:: --------------------------------------------------------
:: Step 3: Install OFX plugin bundle
:: --------------------------------------------------------
echo.
echo [3/6] Installing OFX plugin...

:: Check if pre-built bundle exists in the repo
if exist "%SCRIPT_DIR%plugin\build\CorridorKeyForResolve.ofx.bundle\Contents\Win64\CorridorKeyForResolve.ofx" (
    set "BUNDLE_SRC=%SCRIPT_DIR%plugin\build\CorridorKeyForResolve.ofx.bundle"
    goto :install_bundle
)

:: Check for release bundle next to this script
if exist "%SCRIPT_DIR%CorridorKeyForResolve.ofx.bundle\Contents\Win64\CorridorKeyForResolve.ofx" (
    set "BUNDLE_SRC=%SCRIPT_DIR%CorridorKeyForResolve.ofx.bundle"
    goto :install_bundle
)

echo ERROR: OFX plugin bundle not found.
echo Expected at: %SCRIPT_DIR%CorridorKeyForResolve.ofx.bundle\
echo.
echo Download the latest release from:
echo   https://github.com/gitcapoom/corridorkey_ofx/releases
echo.
echo Extract the .ofx.bundle folder next to this install.bat and run again.
goto :error

:install_bundle
if not exist "%OFX_DIR%" mkdir "%OFX_DIR%"
xcopy /E /Y /Q "%BUNDLE_SRC%" "%OFX_DIR%\" >nul
if %errorlevel% neq 0 (
    echo ERROR: Failed to copy OFX plugin. Is DaVinci Resolve running?
    echo Close Resolve and try again.
    goto :error
)
echo   Plugin installed to: %OFX_DIR%

:: --------------------------------------------------------
:: Step 4: Create virtual environment
:: --------------------------------------------------------
echo.
echo [4/6] Setting up Python environment...

if not exist "%APPDATA_DIR%" mkdir "%APPDATA_DIR%"

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo   Virtual environment already exists.
) else (
    echo   Creating virtual environment...
    "%PYTHON_EXE%" -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        goto :error
    )
    "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip --quiet
)

set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

:: --------------------------------------------------------
:: Step 5: Clone CorridorKey and install dependencies
:: --------------------------------------------------------
echo.
echo [5/6] Installing CorridorKey and dependencies...
echo   This may take several minutes on first install.
echo.

if exist "%CK_REPO_DIR%\.git" (
    echo   CorridorKey repo already cloned. Pulling latest...
    git -C "%CK_REPO_DIR%" pull --quiet 2>nul
) else (
    echo   Cloning CorridorKey repository...
    git clone --depth 1 "%CK_REPO_URL%" "%CK_REPO_DIR%"
    if %errorlevel% neq 0 (
        echo ERROR: Failed to clone CorridorKey repository.
        goto :error
    )
)

echo   Installing PyTorch with CUDA...
"%VENV_PYTHON%" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124 --quiet
if %errorlevel% neq 0 (
    echo ERROR: Failed to install PyTorch.
    goto :error
)

echo   Installing Triton for torch.compile...
"%VENV_PYTHON%" -m pip install triton-windows --quiet 2>nul
if %errorlevel% neq 0 (
    echo   Warning: Triton install failed. Performance will be reduced.
    echo   You can install it manually later with:
    echo     "%VENV_PYTHON%" -m pip install triton-windows
)

echo   Installing other dependencies...
"%VENV_PYTHON%" -m pip install numpy Pillow opencv-python timm transformers huggingface_hub --quiet
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    goto :error
)

:: --------------------------------------------------------
:: Step 6: Copy backend files
:: --------------------------------------------------------
echo.
echo [6/6] Installing backend files...

for %%f in (server.py ipc_protocol.py inference_wrapper.py) do (
    if exist "%SCRIPT_DIR%backend\%%f" (
        copy /Y "%SCRIPT_DIR%backend\%%f" "%APPDATA_DIR%\%%f" >nul
        echo   Copied %%f
    )
)

:: --------------------------------------------------------
:: Done!
:: --------------------------------------------------------
echo.
echo ============================================================
echo  Installation complete!
echo ============================================================
echo.
echo  Plugin:   %OFX_DIR%
echo  Backend:  %APPDATA_DIR%
echo.
echo  How to use:
echo    1. Open DaVinci Resolve
echo    2. Go to Color page or Fusion page
echo    3. Add CorridorKey from OFX plugins
echo    4. The backend starts automatically on first use
echo.
echo  NOTE: The first frame takes ~60 seconds while the AI model
echo  compiles optimized GPU kernels. After that, each frame
echo  renders in ~3 seconds.
echo ============================================================
echo.
pause
exit /b 0

:error
echo.
echo Installation failed. See errors above.
echo.
pause
exit /b 1
