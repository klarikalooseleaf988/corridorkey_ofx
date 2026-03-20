"""
One-click installer for CorridorKey for Resolve backend.

Downloads model weights, sets up Python virtual environment,
and installs dependencies.
"""

import os
import subprocess
import sys
from pathlib import Path

APPDATA_DIR = Path(os.environ.get("APPDATA", "")) / "CorridorKeyForResolve"
MODELS_DIR = APPDATA_DIR / "models"
VENV_DIR = APPDATA_DIR / "venv"

# Model download URLs (HuggingFace)
MODELS = {
    "corridorkey_v1.pth": "https://huggingface.co/CorridorDigital/corridorkey/resolve/main/corridorkey_v1.pth",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def download_file(url: str, dest: Path) -> None:
    """Download a file with progress indication."""
    if dest.exists():
        print(f"  Already exists: {dest.name}")
        return

    print(f"  Downloading {dest.name}...")
    try:
        import urllib.request
        urllib.request.urlretrieve(url, str(dest))
        print(f"  Done: {dest.name}")
    except Exception as e:
        print(f"  Failed to download {dest.name}: {e}")
        raise


def setup_venv() -> Path:
    """Create a virtual environment if it doesn't exist."""
    if VENV_DIR.exists():
        print(f"Virtual environment already exists at {VENV_DIR}")
        return VENV_DIR / "Scripts" / "python.exe"

    print(f"Creating virtual environment at {VENV_DIR}...")
    subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])
    python = VENV_DIR / "Scripts" / "python.exe"

    # Upgrade pip
    subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip"])

    return python


def install_dependencies(python: Path) -> None:
    """Install Python dependencies into the virtual environment."""
    print("Installing dependencies...")

    # Install PyTorch with CUDA
    subprocess.check_call([
        str(python), "-m", "pip", "install",
        "torch", "torchvision",
        "--index-url", "https://download.pytorch.org/whl/cu121",
    ])

    # Install other deps
    backend_dir = Path(__file__).parent
    subprocess.check_call([
        str(python), "-m", "pip", "install",
        "numpy", "Pillow", "corridorkey", "birefnet",
    ])

    print("Dependencies installed successfully")


def download_models() -> None:
    """Download model weights."""
    ensure_dir(MODELS_DIR)
    print("Downloading model weights...")
    for filename, url in MODELS.items():
        download_file(url, MODELS_DIR / filename)


def copy_backend_files() -> None:
    """Copy backend Python files to the install directory."""
    backend_dir = Path(__file__).parent
    for filename in ["server.py", "ipc_protocol.py", "inference_wrapper.py"]:
        src = backend_dir / filename
        dst = APPDATA_DIR / filename
        if src.exists():
            import shutil
            shutil.copy2(str(src), str(dst))
            print(f"  Copied {filename}")


def main():
    print("=" * 60)
    print("CorridorKey for Resolve - Backend Installer")
    print("=" * 60)
    print()

    ensure_dir(APPDATA_DIR)

    # Step 1: Virtual environment
    print("[1/4] Setting up Python environment...")
    python = setup_venv()
    print()

    # Step 2: Install dependencies
    print("[2/4] Installing dependencies...")
    install_dependencies(python)
    print()

    # Step 3: Download models
    print("[3/4] Downloading model weights...")
    download_models()
    print()

    # Step 4: Copy backend files
    print("[4/4] Installing backend files...")
    copy_backend_files()
    print()

    print("=" * 60)
    print("Installation complete!")
    print()
    print(f"Backend installed to: {APPDATA_DIR}")
    print(f"Models stored in:     {MODELS_DIR}")
    print()
    print("To start the backend, run:")
    print(f'  "{VENV_DIR / "Scripts" / "python.exe"}" "{APPDATA_DIR / "server.py"}"')
    print("=" * 60)


if __name__ == "__main__":
    main()
