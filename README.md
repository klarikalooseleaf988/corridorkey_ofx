# CorridorKey for Resolve

An OFX plugin that brings [CorridorKey](https://github.com/CorridorDigital/corridorkey) — Corridor Digital's AI-powered green screen keyer — into DaVinci Resolve 20 as a native plugin.

CorridorKey produces physically accurate foreground color unmixing with clean linear alpha channels. This plugin wraps the full inference engine, delivering a native Resolve experience backed by PyTorch on your GPU.

## Architecture

A thin C++ OFX plugin handles Resolve integration (UI, frame I/O, node graph), while a background Python process runs CorridorKey's inference engine natively via PyTorch.

```
DaVinci Resolve  <-->  OFX Plugin (C++ DLL)  <-->  Python Backend (PyTorch)
                       shared memory + pipes         CorridorKey + BiRefNet
```

## Requirements

- Windows 10/11
- DaVinci Resolve 20 (Free or Studio)
- NVIDIA GPU with CUDA support (tested on RTX 4090)
- Python 3.10+
- Visual Studio 2022 (for building the plugin)
- CMake 3.20+

## Building

### C++ Plugin

```bash
cd plugin
cmake -B build -G "Visual Studio 17 2022"
cmake --build build --config Release
```

The built `.ofx` DLL will be in `plugin/build/Release/`.

### Python Backend

```bash
cd backend
pip install -e .
```

## Installation

1. Copy the built OFX bundle to:
   ```
   C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle\
   ```

2. Set up the Python backend:
   ```
   python backend/install.py
   ```

3. Start the backend before launching Resolve:
   ```
   scripts\start_backend.bat
   ```

## Usage

1. Start the Python backend (`scripts\start_backend.bat`)
2. Open DaVinci Resolve, go to the Color page
3. Add a node and apply "CorridorKey" from the OFX plugins
4. Connect your green screen plate to the Source input
5. Choose Mode:
   - **Auto**: BiRefNet generates an alpha hint automatically
   - **External**: Connect a mask from upstream (qualifier, Delta Keyer, roto)
6. Adjust parameters as needed
7. Select output mode (Processed, Matte, FG, or Composite preview)

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| Mode | Choice | Auto | Alpha hint source |
| BiRefNet Model | Choice | General | Model variant (Auto mode) |
| Input Colorspace | Choice | sRGB | sRGB Gamma or Linear |
| Despill Strength | Double | 1.0 | Green spill removal (0-10) |
| Auto Despeckle | Boolean | On | Remove small alpha artifacts |
| Despeckle Size | Integer | 400 | Min pixel area threshold |
| Refiner Strength | Double | 1.0 | CNN refiner multiplier |
| Output Mode | Choice | Processed | Output selection |

## License

CC BY-NC-SA 4.0 — matching the upstream CorridorKey license.
