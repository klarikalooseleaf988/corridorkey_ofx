# CorridorKey for Resolve - Development Notes

## Project Overview
OFX plugin for DaVinci Resolve 20 that wraps CorridorKey (AI green screen keyer by Corridor Digital).
Architecture: C++ OFX plugin (thin shell) + Python backend process (inference via PyTorch).

## Build
- C++ plugin: `cd plugin && cmake -B build -G "Visual Studio 17 2022" && cmake --build build --config Release`
- Python backend: `cd backend && pip install -e .`
- Target: Windows, MSVC, RTX 4090

## Conventions
- Plugin identifier: `com.corridordigital.corridorkey`
- OFX bundle name: `CorridorKeyForResolve.ofx.bundle`
- IPC: Windows shared memory (CreateFileMapping) + named pipes for control
- Frame format: float32 RGBA via shared memory
- Named pipe: `\\.\pipe\CorridorKeyForResolve`
- Shared memory name: `CorridorKeyForResolve_Frame`

## Key Paths
- Plugin install: `C:\Program Files\Common Files\OFX\Plugins\CorridorKeyForResolve.ofx.bundle\`
- Backend install: `%APPDATA%\CorridorKeyForResolve\`
- Models: `%APPDATA%\CorridorKeyForResolve\models\`

## License
CC BY-NC-SA 4.0 (matching upstream CorridorKey)
