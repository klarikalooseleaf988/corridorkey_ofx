"""
One-click installer for CorridorKey for Resolve backend.

Clones CorridorKey repo, downloads model weights, sets up Python
virtual environment, and installs dependencies.
"""

import os
import subprocess
import sys
from pathlib import Path

APPDATA_DIR = Path(os.environ.get("APPDATA", "")) / "CorridorKeyForResolve"
MODELS_DIR = APPDATA_DIR / "models"
VENV_DIR = APPDATA_DIR / "venv"
CORRIDORKEY_REPO_DIR = APPDATA_DIR / "CorridorKey"

CORRIDORKEY_REPO_URL = "https://github.com/nikopueringer/CorridorKey.git"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def setup_venv() -> Path:
    """Create a virtual environment if it doesn't exist."""
    if VENV_DIR.exists():
        print(f"Virtual environment already exists at {VENV_DIR}")
        return VENV_DIR / "Scripts" / "python.exe"

    print(f"Creating virtual environment at {VENV_DIR}...")

    # Prefer Python 3.13 (3.14+ lacks PyTorch wheels)
    python_exe = sys.executable
    py313 = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python313" / "python.exe"
    if py313.exists():
        python_exe = str(py313)
    subprocess.check_call([python_exe, "-m", "venv", str(VENV_DIR)])
    python = VENV_DIR / "Scripts" / "python.exe"

    # Upgrade pip
    subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip"])

    return python


def clone_corridorkey() -> None:
    """Clone the CorridorKey repository."""
    if CORRIDORKEY_REPO_DIR.exists():
        print(f"  CorridorKey repo already exists at {CORRIDORKEY_REPO_DIR}")
        # Pull latest
        subprocess.run(
            ["git", "-C", str(CORRIDORKEY_REPO_DIR), "pull"],
            check=False,
        )
        return

    print(f"  Cloning CorridorKey to {CORRIDORKEY_REPO_DIR}...")
    subprocess.check_call([
        "git", "clone", "--depth", "1",
        CORRIDORKEY_REPO_URL, str(CORRIDORKEY_REPO_DIR),
    ])
    print("  CorridorKey cloned successfully")


def install_dependencies(python: Path) -> None:
    """Install Python dependencies into the virtual environment."""
    print("Installing dependencies...")

    # Install PyTorch with CUDA
    subprocess.check_call([
        str(python), "-m", "pip", "install",
        "torch", "torchvision",
        "--index-url", "https://download.pytorch.org/whl/cu124",
    ])

    # Install CorridorKey's dependencies (timm, opencv, etc.)
    subprocess.check_call([
        str(python), "-m", "pip", "install",
        "numpy", "Pillow", "opencv-python", "timm",
        "transformers",  # for BiRefNet via HuggingFace
    ])

    # Install Triton for torch.compile (critical for performance)
    subprocess.check_call([
        str(python), "-m", "pip", "install",
        "triton-windows",
    ])

    print("Dependencies installed successfully")


def download_models(python: Path) -> None:
    """Download model weights using CorridorKey's own download mechanism if available,
    otherwise download from HuggingFace."""
    ensure_dir(MODELS_DIR)
    print("Checking model weights...")

    # Check if CorridorKey has its own model download script
    ck_models_dir = CORRIDORKEY_REPO_DIR / "models"
    if ck_models_dir.exists():
        # Look for existing weights
        pth_files = list(ck_models_dir.glob("*.pth"))
        if pth_files:
            # Symlink or copy to our models dir
            for pth in pth_files:
                dest = MODELS_DIR / pth.name
                if not dest.exists():
                    import shutil
                    shutil.copy2(str(pth), str(dest))
                    print(f"  Copied model: {pth.name}")
            return

    print("  Model weights need to be downloaded manually.")
    print(f"  Place corridorkey model checkpoint (.pth) in: {MODELS_DIR}")
    print("  See CorridorKey repo for model download instructions:")
    print(f"  {CORRIDORKEY_REPO_URL}")


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
    print("[1/5] Setting up Python environment...")
    python = setup_venv()
    print()

    # Step 2: Clone CorridorKey
    print("[2/5] Cloning CorridorKey repository...")
    clone_corridorkey()
    print()

    # Step 3: Install dependencies
    print("[3/5] Installing dependencies...")
    install_dependencies(python)
    print()

    # Step 4: Download models
    print("[4/5] Checking model weights...")
    download_models(python)
    print()

    # Step 5: Copy backend files
    print("[5/5] Installing backend files...")
    copy_backend_files()
    print()

    print("=" * 60)
    print("Installation complete!")
    print()
    print(f"Backend installed to:  {APPDATA_DIR}")
    print(f"CorridorKey repo at:   {CORRIDORKEY_REPO_DIR}")
    print(f"Models stored in:      {MODELS_DIR}")
    print()
    print("To start the backend, run:")
    print(f'  "{VENV_DIR / "Scripts" / "python.exe"}" "{APPDATA_DIR / "server.py"}"')
    print("=" * 60)


if __name__ == "__main__":
    main()
