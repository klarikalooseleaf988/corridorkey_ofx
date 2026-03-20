"""
IPC Protocol for CorridorKey for Resolve.

Communication between C++ OFX plugin and Python backend uses:
- Windows Named Pipes for control messages (JSON)
- Windows Shared Memory for frame data (raw float32 RGBA)

Protocol flow:
1. Plugin connects to named pipe
2. Plugin sends PROCESS_FRAME message with parameters
3. Plugin writes frame data to shared memory
4. Backend reads frame, runs inference, writes result to shared memory
5. Backend sends FRAME_DONE message via pipe
6. Plugin reads result from shared memory
"""

import json
import struct
from dataclasses import dataclass, asdict
from enum import IntEnum
from typing import Optional

# IPC constants
PIPE_NAME = r"\\.\pipe\CorridorKeyForResolve"
SHM_NAME_INPUT = "CorridorKeyForResolve_Input"
SHM_NAME_OUTPUT = "CorridorKeyForResolve_Output"
SHM_NAME_ALPHA_HINT = "CorridorKeyForResolve_AlphaHint"

# Maximum frame size: 8K RGBA float32 = 7680 * 4320 * 4 * 4 = ~530MB
# We'll allocate for 4K max = 4096 * 2160 * 4 * 4 = ~141MB
MAX_FRAME_WIDTH = 4096
MAX_FRAME_HEIGHT = 4096
BYTES_PER_PIXEL = 16  # 4 channels * 4 bytes (float32)
MAX_SHM_SIZE = MAX_FRAME_WIDTH * MAX_FRAME_HEIGHT * BYTES_PER_PIXEL

# Frame header in shared memory (prepended to pixel data)
# Format: width(u32) + height(u32) + channels(u32) + reserved(u32) = 16 bytes
FRAME_HEADER_SIZE = 16


class MessageType(IntEnum):
    """Control message types sent over named pipe."""
    # Plugin -> Backend
    PING = 0
    PROCESS_FRAME = 1
    SHUTDOWN = 2
    LOAD_MODEL = 3

    # Backend -> Plugin
    PONG = 100
    FRAME_DONE = 101
    ERROR = 102
    MODEL_LOADED = 103
    STATUS = 104


class OutputMode(IntEnum):
    """Which output the plugin requests."""
    PROCESSED = 0  # Premultiplied RGBA (despilled, despeckled)
    MATTE = 1      # Alpha channel only
    FOREGROUND = 2  # Straight foreground color
    COMPOSITE = 3   # Preview composite over checkerboard


class AlphaHintMode(IntEnum):
    """How the alpha hint is generated."""
    AUTO = 0       # BiRefNet generates the hint
    EXTERNAL = 1   # Plugin provides external alpha hint via shared memory


class InputColorspace(IntEnum):
    """Input frame colorspace."""
    SRGB = 0
    LINEAR = 1


@dataclass
class ProcessFrameRequest:
    """Parameters for a frame processing request."""
    width: int
    height: int
    mode: int = AlphaHintMode.AUTO
    birefnet_model: str = "general"
    input_colorspace: int = InputColorspace.SRGB
    despill_strength: float = 1.0
    auto_despeckle: bool = True
    despeckle_size: int = 400
    refiner_strength: float = 1.0
    output_mode: int = OutputMode.PROCESSED
    has_alpha_hint: bool = False


@dataclass
class FrameDoneResponse:
    """Response after frame processing is complete."""
    width: int
    height: int
    channels: int
    output_mode: int
    processing_time_ms: float


@dataclass
class ErrorResponse:
    """Error response from backend."""
    code: int
    message: str


def encode_message(msg_type: MessageType, payload: Optional[dict] = None) -> bytes:
    """Encode a control message for the named pipe.

    Format: msg_type(u32) + payload_length(u32) + payload_json(utf8)
    """
    if payload is None:
        payload = {}
    payload_bytes = json.dumps(payload).encode("utf-8")
    header = struct.pack("<II", int(msg_type), len(payload_bytes))
    return header + payload_bytes


def decode_message(data: bytes) -> tuple[MessageType, dict]:
    """Decode a control message from the named pipe.

    Returns (message_type, payload_dict).
    """
    if len(data) < 8:
        raise ValueError(f"Message too short: {len(data)} bytes")
    msg_type_raw, payload_len = struct.unpack("<II", data[:8])
    msg_type = MessageType(msg_type_raw)
    if payload_len > 0:
        payload = json.loads(data[8:8 + payload_len].decode("utf-8"))
    else:
        payload = {}
    return msg_type, payload


def encode_frame_header(width: int, height: int, channels: int = 4) -> bytes:
    """Encode frame header for shared memory."""
    return struct.pack("<IIII", width, height, channels, 0)


def decode_frame_header(data: bytes) -> tuple[int, int, int]:
    """Decode frame header from shared memory. Returns (width, height, channels)."""
    width, height, channels, _ = struct.unpack("<IIII", data[:FRAME_HEADER_SIZE])
    return width, height, channels
