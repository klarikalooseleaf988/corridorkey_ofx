# CorridorKey for Resolve (Windows)

An OFX plugin that brings [CorridorKey](https://github.com/nikopueringer/CorridorKey) — Corridor Digital's AI-powered green screen keyer — into DaVinci Resolve 20 as a native plugin.

> **Note:** This is a Windows-only release. The plugin uses Windows-specific APIs (named pipes, shared memory via `CreateFileMapping`) for IPC between the C++ plugin and Python backend.

CorridorKey produces physically accurate foreground color unmixing with clean linear alpha channels. This plugin wraps the full inference engine, delivering a native Resolve experience backed by PyTorch on your GPU.

## Architecture

A thin C++ OFX plugin handles Resolve integration (UI, frame I/O, node graph), while a background Python process runs CorridorKey's inference engine via PyTorch. Communication uses Windows shared memory for frame data and named pipes for control messages.

```
DaVinci Resolve  <-->  OFX Plugin (C++ DLL)  <-->  Python Backend (PyTorch)
                       shared memory + pipes         CorridorKey + BiRefNet
```

The backend auto-launches when you first apply the plugin in Resolve — no manual startup required.

## Requirements

- Windows 10/11
- DaVinci Resolve 20 (Free or Studio)
- NVIDIA GPU with CUDA support (tested on RTX 4090)
- Python 3.13 (3.14+ lacks PyTorch wheels)
- Visual Studio 2022 Build Tools (only if building from source)

## Quick Install

1. Install [Python 3.13](https://www.python.org/downloads/) — check "Add Python to PATH" during setup
2. Download the latest release from [GitHub Releases](https://github.com/gitcapoom/corridorkey_ofx/releases)
3. Extract the zip
4. Double-click **`install.bat`**

The installer handles everything automatically: copies the OFX plugin, creates a Python environment, installs PyTorch + CUDA + Triton, clones CorridorKey, and downloads model weights.

## Building from Source

If you prefer to build the C++ plugin yourself instead of using the pre-built release:

```bash
cd plugin
cmake -B build -G "Visual Studio 17 2022"
cmake --build build --config Release
```

Then run `install.bat` or `python backend/install.py` to set up the backend.

### Dependencies Installed

| Package | Purpose |
|---------|---------|
| `torch` + `torchvision` (CUDA 12.4) | Neural network inference |
| `triton-windows` | `torch.compile` kernel generation (critical for performance) |
| `transformers` | BiRefNet model loading via HuggingFace |
| `timm` | Vision model backbones |
| `opencv-python` | Image processing (resize, morphology) |
| `numpy` | Array operations |

## Usage

### Color Page

1. Open DaVinci Resolve and go to the **Color** page
2. Add a corrector node and apply **CorridorKey** from the OFX plugins list
3. Connect your green screen plate to the Source input
4. The plugin auto-launches the backend on first use

### Fusion Page

1. Go to the **Fusion** page
2. Add a CorridorKey node from the OFX tools
3. Connect your MediaIn to the Source input
4. Optionally connect an external mask to the AlphaHint input

### Input Pins (Color Page)

| Pin | Color | Purpose |
|-----|-------|---------|
| Source RGB | Green | Green screen footage (required) |
| Source Alpha | Blue | Alpha channel of source |
| Alpha Hint | Blue | External mask input for External mode (optional) |

### First-Time Startup

On the first render after launching the backend, there is a **one-time warmup delay of ~60 seconds**. This is `torch.compile` generating optimized CUDA kernels via Triton for your specific GPU. Subsequent frames render in ~1.5-2 seconds. This compilation is cached by PyTorch and will be faster on future launches.

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| **Mode** | Choice | Auto | Alpha hint source: Auto (BiRefNet) or External (user-provided mask) |
| **BiRefNet Model** | Choice | General | BiRefNet variant: General, Portrait, or Matting |
| **Input Colorspace** | Choice | sRGB | Colorspace of source footage: sRGB Gamma or Linear |
| **Despill Strength** | Double | 1.0 | Green spill removal intensity (0–10) |
| **Auto Despeckle** | Boolean | On | Remove small isolated alpha artifacts |
| **Despeckle Size** | Integer | 400 | Minimum pixel area threshold for despeckle |
| **Refiner Strength** | Double | 1.0 | CNN refiner multiplier (0–5) |
| **Output Mode** | Choice | Processed | What to output downstream |

### Output Modes

| Mode | Description |
|------|-------------|
| **Processed** | Premultiplied linear RGBA — primary output for compositing |
| **Matte** | Alpha channel visualized as grayscale |
| **Foreground** | Straight (unpremultiplied) foreground with alpha |
| **Composite** | Preview composite over checkerboard |

### Input Colorspace

Set this to match your Resolve project's working colorspace:

- **sRGB Gamma**: Standard footage, Rec.709 projects
- **Linear**: ACES, linear workflow, or EXR footage

All outputs are delivered in the matching colorspace so they integrate correctly into Resolve's pipeline.

## Performance

Tested on RTX 4090 with 2880px footage:

| Stage | Time |
|-------|------|
| BiRefNet alpha hint | ~1.5s (cached per frame) |
| CorridorKey inference | ~1.5s (fp16 + torch.compile) |
| Post-processing | ~50ms |
| **Total (first frame)** | **~3s** |
| **Changing output mode/despill** | **~50ms** (cached) |

### Performance Features

- **fp16 inference**: Both CorridorKey and BiRefNet run in half precision for maximum GPU throughput
- **torch.compile + Triton**: Generates optimized CUDA kernels, ~3x faster than eager mode
- **GPU resize**: Upscaling from model resolution back to frame resolution happens on GPU (bicubic)
- **Inference caching**: Changing output mode, despill, or despeckle doesn't re-run the neural network
- **BiRefNet caching**: Alpha hint is cached per-frame, not regenerated on parameter tweaks
- **Auto-reconnect**: Plugin automatically reconnects if the backend restarts

## File Locations

| What | Path |
|------|------|
| OFX Plugin | `C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle\` |
| Backend install | `%APPDATA%\CorridorKeyForResolve\` |
| Virtual environment | `%APPDATA%\CorridorKeyForResolve\venv\` |
| CorridorKey repo | `%APPDATA%\CorridorKeyForResolve\CorridorKey\` |
| Model weights | `%APPDATA%\CorridorKeyForResolve\CorridorKey\CorridorKeyModule\checkpoints\` |

## Troubleshooting

### Plugin shows passthrough (no effect)
The backend isn't running or the connection was lost. The plugin auto-launches the backend, but if it fails:
```bash
%APPDATA%\CorridorKeyForResolve\venv\Scripts\python.exe %APPDATA%\CorridorKeyForResolve\server.py
```

### Node turns red in Fusion
The project may not be set to 32-bit float processing. Check Project Settings > Color Management.

### "torch.compile failed" in backend logs
Install or update Triton:
```bash
%APPDATA%\CorridorKeyForResolve\venv\Scripts\python.exe -m pip install triton-windows
```
Ensure the Triton version is compatible with your PyTorch version.

### Slow first frame (~60s)
This is normal — `torch.compile` is generating optimized CUDA kernels for your GPU. This only happens once per backend launch and is cached by PyTorch.

## IPC Protocol

Communication between the C++ plugin and Python backend:

- **Named pipe**: `\\.\pipe\CorridorKeyForResolve` (JSON control messages)
- **Shared memory**: `CorridorKeyForResolve_Input`, `_Output`, `_AlphaHint` (float32 RGBA frames)
- **Frame header**: 16 bytes (width u32 + height u32 + channels u32 + reserved u32)
- **Max frame size**: 4096×4096 (configurable)

## License

CC BY-NC-SA 4.0 — matching the upstream CorridorKey license.
