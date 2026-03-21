@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: CorridorKey for Resolve - One-Click Installer
:: ============================================================
:: Requirements: Python 3.10-3.13, NVIDIA GPU with CUDA
:: ============================================================

echo.
echo ============================================================
echo  CorridorKey for Resolve - Installer
echo ============================================================
echo.

:: Save our directory before anything can change it
set "INSTALLER_DIR=%~dp0"

:: Configuration
set "APPDATA_DIR=%APPDATA%\CorridorKeyForResolve"
set "VENV_DIR=%APPDATA_DIR%\venv"
set "CK_REPO_DIR=%APPDATA_DIR%\CorridorKey"
set "OFX_DIR=C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle"
set "CK_ZIP_URL=https://github.com/nikopueringer/CorridorKey/archive/refs/heads/main.zip"

:: --------------------------------------------------------
:: Step 1: Find Python 3.10-3.13
:: --------------------------------------------------------
echo [1/5] Finding Python...

set "PYTHON_EXE="

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

where python >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%p in ('where python') do (
        set "PYTHON_EXE=%%p"
        goto :found_python
    )
)

echo.
echo  ERROR: Python not found!
echo.
echo  Please install Python 3.13 from:
echo    https://www.python.org/downloads/release/python-31312/
echo.
echo  IMPORTANT: Check "Add Python to PATH" during installation.
echo.
goto :error

:found_python
echo   Found: %PYTHON_EXE%

for /f "tokens=2 delims= " %%v in ('"%PYTHON_EXE%" --version 2^>^&1') do set "PY_VER=%%v"
echo   Version: %PY_VER%

for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do (
    set "PY_MAJOR=%%a"
    set "PY_MINOR=%%b"
)
if %PY_MAJOR% geq 4 goto :bad_python
if %PY_MAJOR% equ 3 if %PY_MINOR% geq 14 goto :bad_python
if %PY_MAJOR% equ 3 if %PY_MINOR% lss 10 goto :bad_python
goto :python_ok

:bad_python
echo.
echo  ERROR: Python %PY_VER% is not supported!
echo.
echo  PyTorch requires Python 3.10-3.13.
echo  Please install Python 3.13 from:
echo    https://www.python.org/downloads/release/python-31312/
echo.
echo  You do NOT need to uninstall your current Python.
echo  Just install 3.13 alongside it and re-run this installer.
echo.
goto :error

:python_ok

:: --------------------------------------------------------
:: Step 2: Install OFX plugin (needs admin)
:: --------------------------------------------------------
echo.
echo [2/5] Installing OFX plugin...

set "BUNDLE_SRC="
if exist "%INSTALLER_DIR%plugin\build\CorridorKeyForResolve.ofx.bundle\Contents\Win64\CorridorKeyForResolve.ofx" (
    set "BUNDLE_SRC=%INSTALLER_DIR%plugin\build\CorridorKeyForResolve.ofx.bundle"
)
if exist "%INSTALLER_DIR%CorridorKeyForResolve.ofx.bundle\Contents\Win64\CorridorKeyForResolve.ofx" (
    set "BUNDLE_SRC=%INSTALLER_DIR%CorridorKeyForResolve.ofx.bundle"
)

if "%BUNDLE_SRC%"=="" (
    echo.
    echo  ERROR: OFX plugin bundle not found!
    echo.
    echo  Download the latest release from:
    echo    https://github.com/gitcapoom/corridorkey_ofx/releases
    echo.
    goto :error
)

:: Use PowerShell to elevate ONLY the copy operation
echo   Copying plugin to Program Files (may prompt for admin)...
powershell -Command "Start-Process powershell -ArgumentList '-Command \"Copy-Item -Path \\\"%BUNDLE_SRC%\\\" -Destination \\\"C:\Program Files\Common Files\OFX\Plugins\\\" -Recurse -Force\"' -Verb RunAs -Wait" 2>nul

if exist "%OFX_DIR%\Contents\Win64\CorridorKeyForResolve.ofx" (
    echo   Plugin installed to: %OFX_DIR%
) else (
    echo.
    echo  ERROR: Failed to install OFX plugin.
    echo  You may need to close DaVinci Resolve first, or
    echo  manually copy the bundle to:
    echo    %OFX_DIR%
    echo.
    goto :error
)

:: --------------------------------------------------------
:: Step 3: Create virtual environment
:: --------------------------------------------------------
echo.
echo [3/5] Setting up Python environment...

if not exist "%APPDATA_DIR%" mkdir "%APPDATA_DIR%"

:: Check if existing venv uses a compatible Python version
if exist "%VENV_DIR%\Scripts\python.exe" (
    for /f "tokens=2 delims= " %%v in ('"%VENV_DIR%\Scripts\python.exe" --version 2^>^&1') do set "VENV_PY_VER=%%v"
    for /f "tokens=2 delims=." %%m in ("!VENV_PY_VER!") do set "VENV_PY_MINOR=%%m"
    if !VENV_PY_MINOR! geq 14 (
        echo   Existing venv uses Python !VENV_PY_VER! - recreating with 3.13...
        rmdir /S /Q "%VENV_DIR%"
    ) else if !VENV_PY_MINOR! lss 10 (
        echo   Existing venv uses Python !VENV_PY_VER! - recreating with 3.13...
        rmdir /S /Q "%VENV_DIR%"
    )
)

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo   Virtual environment already exists.
) else (
    echo   Creating virtual environment...
    "%PYTHON_EXE%" -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo.
        echo  ERROR: Failed to create virtual environment.
        echo.
        goto :error
    )
    "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
)

set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

:: --------------------------------------------------------
:: Step 4: Download CorridorKey and install dependencies
:: --------------------------------------------------------
echo.
echo [4/6] Installing CorridorKey and dependencies...
echo   This may take several minutes on first install.

:: Download CorridorKey
if exist "%CK_REPO_DIR%\CorridorKeyModule\inference_engine.py" (
    echo   CorridorKey already downloaded.
) else (
    echo.
    echo   Downloading CorridorKey...
    set "CK_ZIP=%APPDATA_DIR%\corridorkey_download.zip"
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%CK_ZIP_URL%' -OutFile '!CK_ZIP!'"
    if %errorlevel% neq 0 (
        echo   ERROR: Failed to download CorridorKey. Check your internet connection.
        goto :error
    )
    echo   Extracting...
    powershell -Command "Expand-Archive -Path '!CK_ZIP!' -DestinationPath '%APPDATA_DIR%\ck_temp' -Force"
    if %errorlevel% neq 0 (
        echo   ERROR: Failed to extract CorridorKey.
        goto :error
    )
    for /d %%d in ("%APPDATA_DIR%\ck_temp\CorridorKey*") do (
        if exist "%CK_REPO_DIR%" rmdir /S /Q "%CK_REPO_DIR%"
        move "%%d" "%CK_REPO_DIR%" >nul
    )
    rmdir /S /Q "%APPDATA_DIR%\ck_temp" 2>nul
    del "!CK_ZIP!" 2>nul
    echo   CorridorKey downloaded successfully.
)

:: Download model weights
set "CKPT_DIR=%CK_REPO_DIR%\CorridorKeyModule\checkpoints"
set "CKPT_FILE=%CKPT_DIR%\CorridorKey_v1.0.pth"
set "CKPT_URL=https://huggingface.co/nikopueringer/CorridorKey_v1.0/resolve/main/CorridorKey_v1.0.pth"

if exist "%CKPT_FILE%" (
    echo   Model weights already downloaded.
) else (
    echo.
    echo   Downloading model weights (~400MB)...
    if not exist "%CKPT_DIR%" mkdir "%CKPT_DIR%"
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%CKPT_URL%' -OutFile '%CKPT_FILE%'"
    if %errorlevel% neq 0 (
        echo   ERROR: Failed to download model weights.
        echo   You can retry manually by visiting:
        echo     https://huggingface.co/nikopueringer/CorridorKey_v1.0
        echo   and placing the .pth file in: %CKPT_DIR%
        goto :error
    )
    echo   Model weights downloaded successfully.
)

:: Install PyTorch with CUDA
echo.
echo   Installing PyTorch with CUDA (large download ~2.5GB)...
echo.
"%VENV_PYTHON%" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
if %errorlevel% neq 0 (
    echo.
    echo  -------------------------------------------------------
    echo  PyTorch installation failed.
    echo.
    echo  Common causes:
    echo    - No internet connection
    echo    - Python version not supported (need 3.10-3.13)
    echo    - Disk space (PyTorch needs ~3GB free)
    echo    - Corporate firewall blocking download.pytorch.org
    echo.
    echo  Your Python version: %PY_VER%
    echo.
    echo  To retry manually, run:
    echo    "%VENV_PYTHON%" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
    echo  -------------------------------------------------------
    echo.
    goto :error
)

:: Verify CUDA is available in the installed PyTorch
"%VENV_PYTHON%" -c "import torch; assert torch.cuda.is_available(), 'no CUDA'; print(f'  PyTorch {torch.__version__} with CUDA {torch.version.cuda}')" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo  WARNING: PyTorch installed but CUDA is not available.
    echo  This may mean the CPU-only version was installed.
    echo  Reinstall with:
    echo    "%VENV_PYTHON%" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124 --force-reinstall
    echo.
)

:: Install Triton (non-critical)
echo   Installing Triton for torch.compile...
"%VENV_PYTHON%" -m pip install triton-windows >nul 2>&1
if %errorlevel% neq 0 (
    echo   Warning: Triton install failed. torch.compile will be slower.
)

:: Install other dependencies
echo   Installing other dependencies...
"%VENV_PYTHON%" -m pip install numpy Pillow opencv-python timm transformers huggingface_hub
if %errorlevel% neq 0 (
    echo.
    echo  WARNING: Some dependencies failed to install.
    echo.
)

:: --------------------------------------------------------
:: Step 5: Copy backend files
:: --------------------------------------------------------
echo.
echo [5/6] Installing backend files...

set "BACKEND_COPIED=0"
for %%f in (server.py ipc_protocol.py inference_wrapper.py) do (
    if exist "%INSTALLER_DIR%backend\%%f" (
        copy /Y "%INSTALLER_DIR%backend\%%f" "%APPDATA_DIR%\%%f" >nul
        echo   Copied %%f
        set "BACKEND_COPIED=1"
    ) else (
        echo   WARNING: Not found: %INSTALLER_DIR%backend\%%f
    )
)

if "%BACKEND_COPIED%"=="0" (
    echo.
    echo  ERROR: No backend files were found!
    echo  Make sure install.bat and the backend\ folder are in the same directory.
    echo  Installer location: %INSTALLER_DIR%
    echo.
    goto :error
)

if not exist "%APPDATA_DIR%\server.py" (
    echo.
    echo  ERROR: server.py was not installed to %APPDATA_DIR%
    echo.
    goto :error
)

:: --------------------------------------------------------
:: Step 6: Verify installation
:: --------------------------------------------------------
echo.
echo [6/6] Verifying installation...

set "INSTALL_OK=1"
if not exist "%OFX_DIR%\Contents\Win64\CorridorKeyForResolve.ofx" (
    echo   MISSING: OFX plugin
    set "INSTALL_OK=0"
)
if not exist "%APPDATA_DIR%\server.py" (
    echo   MISSING: server.py
    set "INSTALL_OK=0"
)
if not exist "%CKPT_FILE%" (
    echo   MISSING: Model weights
    set "INSTALL_OK=0"
)
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo   MISSING: Python virtual environment
    set "INSTALL_OK=0"
)
if "%INSTALL_OK%"=="0" (
    echo.
    echo  ERROR: Installation incomplete. See missing items above.
    echo.
    goto :error
)
echo   All components verified.

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
echo  Installation failed. See errors above.
echo  You can re-run this installer after fixing the issue.
echo.
pause
exit /b 1
