"""
IPC Server for CorridorKey for Resolve backend.

Listens on a Windows named pipe for control messages and processes
frames via shared memory using the CorridorKey inference engine.
"""

import ctypes
import ctypes.wintypes
import logging
import mmap
import struct
import sys
import signal
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import numpy as np

from ipc_protocol import (
    PIPE_NAME,
    SHM_NAME_INPUT,
    SHM_NAME_OUTPUT,
    SHM_NAME_ALPHA_HINT,
    MAX_SHM_SIZE,
    FRAME_HEADER_SIZE,
    BYTES_PER_PIXEL,
    MessageType,
    OutputMode,
    AlphaHintMode,
    InputColorspace,
    ProcessFrameRequest,
    encode_message,
    decode_message,
    encode_frame_header,
    decode_frame_header,
)
from inference_wrapper import InferenceWrapper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("corridorkey-backend")

# Windows API constants
PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_BYTE = 0x00000000
PIPE_READMODE_BYTE = 0x00000000
PIPE_WAIT = 0x00000000
PIPE_UNLIMITED_INSTANCES = 255
BUFFER_SIZE = 65536
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
PAGE_READWRITE = 0x04
FILE_MAP_ALL_ACCESS = 0x000F001F

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# Set proper return/arg types for kernel32 functions
kernel32.CreateFileMappingW.restype = ctypes.wintypes.HANDLE
kernel32.CreateFileMappingW.argtypes = [
    ctypes.wintypes.HANDLE,  # hFile
    ctypes.c_void_p,         # lpAttributes
    ctypes.wintypes.DWORD,   # flProtect
    ctypes.wintypes.DWORD,   # dwMaximumSizeHigh
    ctypes.wintypes.DWORD,   # dwMaximumSizeLow
    ctypes.wintypes.LPCWSTR, # lpName
]
kernel32.MapViewOfFile.restype = ctypes.c_void_p
kernel32.MapViewOfFile.argtypes = [
    ctypes.wintypes.HANDLE,  # hFileMappingObject
    ctypes.wintypes.DWORD,   # dwDesiredAccess
    ctypes.wintypes.DWORD,   # dwFileOffsetHigh
    ctypes.wintypes.DWORD,   # dwFileOffsetLow
    ctypes.c_size_t,         # dwNumberOfBytesToMap
]
kernel32.UnmapViewOfFile.restype = ctypes.wintypes.BOOL
kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
kernel32.CreateNamedPipeW.restype = ctypes.wintypes.HANDLE
kernel32.CreateNamedPipeW.argtypes = [
    ctypes.wintypes.LPCWSTR,  # lpName
    ctypes.wintypes.DWORD,    # dwOpenMode
    ctypes.wintypes.DWORD,    # dwPipeMode
    ctypes.wintypes.DWORD,    # nMaxInstances
    ctypes.wintypes.DWORD,    # nOutBufferSize
    ctypes.wintypes.DWORD,    # nInBufferSize
    ctypes.wintypes.DWORD,    # nDefaultTimeOut
    ctypes.c_void_p,          # lpSecurityAttributes
]
kernel32.ConnectNamedPipe.restype = ctypes.wintypes.BOOL
kernel32.ConnectNamedPipe.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p]
kernel32.DisconnectNamedPipe.restype = ctypes.wintypes.BOOL
kernel32.DisconnectNamedPipe.argtypes = [ctypes.wintypes.HANDLE]
kernel32.ReadFile.restype = ctypes.wintypes.BOOL
kernel32.ReadFile.argtypes = [
    ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.wintypes.DWORD,
    ctypes.POINTER(ctypes.wintypes.DWORD), ctypes.c_void_p,
]
kernel32.WriteFile.restype = ctypes.wintypes.BOOL
kernel32.WriteFile.argtypes = [
    ctypes.wintypes.HANDLE, ctypes.c_void_p, ctypes.wintypes.DWORD,
    ctypes.POINTER(ctypes.wintypes.DWORD), ctypes.c_void_p,
]
kernel32.FlushFileBuffers.restype = ctypes.wintypes.BOOL
kernel32.FlushFileBuffers.argtypes = [ctypes.wintypes.HANDLE]


class SharedMemoryRegion:
    """Manages a Windows shared memory region."""

    def __init__(self, name: str, size: int):
        self.name = name
        self.size = size + FRAME_HEADER_SIZE
        self._handle = None
        self._ptr = None

    def create(self) -> None:
        """Create or open the shared memory region."""
        self._handle = kernel32.CreateFileMappingW(
            ctypes.wintypes.HANDLE(INVALID_HANDLE_VALUE),
            None,
            PAGE_READWRITE,
            (self.size >> 32) & 0xFFFFFFFF,
            self.size & 0xFFFFFFFF,
            self.name,
        )
        if not self._handle:
            raise OSError(f"CreateFileMapping failed for '{self.name}': {ctypes.get_last_error()}")

        self._ptr = kernel32.MapViewOfFile(
            self._handle, FILE_MAP_ALL_ACCESS, 0, 0, self.size
        )
        if not self._ptr:
            kernel32.CloseHandle(self._handle)
            raise OSError(f"MapViewOfFile failed for '{self.name}'")

    def write_frame(self, width: int, height: int, data: np.ndarray) -> None:
        """Write frame header + pixel data to shared memory."""
        header = encode_frame_header(width, height, data.shape[-1] if data.ndim > 2 else 1)
        raw = data.tobytes()
        total = len(header) + len(raw)
        if total > self.size:
            raise ValueError(f"Frame data ({total} bytes) exceeds shared memory ({self.size} bytes)")
        ctypes.memmove(self._ptr, header, len(header))
        ctypes.memmove(self._ptr + len(header), raw, len(raw))

    def read_frame(self) -> tuple[int, int, int, np.ndarray]:
        """Read frame header + pixel data from shared memory.

        Returns (width, height, channels, data_as_float32_array).
        """
        header_bytes = (ctypes.c_char * FRAME_HEADER_SIZE).from_address(self._ptr)
        width, height, channels = decode_frame_header(bytes(header_bytes))

        pixel_bytes = width * height * channels * 4  # float32
        raw_array = (ctypes.c_char * pixel_bytes).from_address(self._ptr + FRAME_HEADER_SIZE)
        data = np.frombuffer(bytes(raw_array), dtype=np.float32).reshape(height, width, channels)
        return width, height, channels, data

    def close(self) -> None:
        """Release shared memory resources."""
        if self._ptr is not None:
            kernel32.UnmapViewOfFile(self._ptr)
            self._ptr = None
        if self._handle is not None:
            kernel32.CloseHandle(self._handle)
            self._handle = None


class PipeServer:
    """Windows named pipe server for IPC control messages."""

    def __init__(self, pipe_name: str = PIPE_NAME):
        self.pipe_name = pipe_name
        self._handle = None

    def create(self) -> None:
        """Create the named pipe and wait for a client connection."""
        self._handle = kernel32.CreateNamedPipeW(
            self.pipe_name,
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
            PIPE_UNLIMITED_INSTANCES,
            BUFFER_SIZE,
            BUFFER_SIZE,
            0,
            None,
        )
        if self._handle is None or self._handle == INVALID_HANDLE_VALUE or self._handle == -1:
            err = ctypes.get_last_error()
            raise OSError(f"CreateNamedPipe failed: error {err}")

    def wait_for_client(self) -> bool:
        """Wait for a client to connect. Returns True on success."""
        logger.info("Waiting for client connection on %s", self.pipe_name)
        result = kernel32.ConnectNamedPipe(self._handle, None)
        if not result:
            err = ctypes.get_last_error()
            # ERROR_PIPE_CONNECTED means client already connected
            if err != 535:
                logger.error("ConnectNamedPipe failed: %d", err)
                return False
        logger.info("Client connected")
        return True

    def read_message(self) -> Optional[tuple[MessageType, dict]]:
        """Read a complete message from the pipe."""
        # Read header (8 bytes: msg_type + payload_length)
        header = self._read_bytes(8)
        if header is None:
            return None

        msg_type_raw, payload_len = struct.unpack("<II", header)
        payload_bytes = b""
        if payload_len > 0:
            payload_bytes = self._read_bytes(payload_len)
            if payload_bytes is None:
                return None

        return decode_message(header + payload_bytes)

    def write_message(self, msg_type: MessageType, payload: Optional[dict] = None) -> bool:
        """Write a complete message to the pipe."""
        data = encode_message(msg_type, payload)
        bytes_written = ctypes.wintypes.DWORD()
        result = kernel32.WriteFile(
            self._handle, data, len(data), ctypes.byref(bytes_written), None
        )
        if not result:
            logger.error("WriteFile failed: %d", ctypes.get_last_error())
            return False
        kernel32.FlushFileBuffers(self._handle)
        return True

    def _read_bytes(self, count: int) -> Optional[bytes]:
        """Read exactly count bytes from the pipe."""
        buf = ctypes.create_string_buffer(count)
        bytes_read = ctypes.wintypes.DWORD()
        result = kernel32.ReadFile(
            self._handle, buf, count, ctypes.byref(bytes_read), None
        )
        if not result or bytes_read.value != count:
            return None
        return buf.raw[:bytes_read.value]

    def disconnect(self) -> None:
        """Disconnect the current client."""
        if self._handle is not None:
            kernel32.DisconnectNamedPipe(self._handle)

    def close(self) -> None:
        """Close the pipe handle."""
        if self._handle is not None:
            kernel32.CloseHandle(self._handle)
            self._handle = None


class BackendServer:
    """Main backend server coordinating IPC and inference."""

    def __init__(self):
        self.pipe = PipeServer()
        self.shm_input = SharedMemoryRegion(SHM_NAME_INPUT, MAX_SHM_SIZE)
        self.shm_output = SharedMemoryRegion(SHM_NAME_OUTPUT, MAX_SHM_SIZE)
        self.shm_alpha_hint = SharedMemoryRegion(SHM_NAME_ALPHA_HINT, MAX_SHM_SIZE)
        self.inference = InferenceWrapper()
        self._running = False

    def start(self) -> None:
        """Initialize resources and start the server loop."""
        logger.info("Starting CorridorKey backend server")

        # Create shared memory regions
        self.shm_input.create()
        self.shm_output.create()
        self.shm_alpha_hint.create()
        logger.info("Shared memory regions created")

        # Load models
        try:
            self.inference.load_corridorkey()
        except (ImportError, FileNotFoundError) as e:
            logger.error("Failed to load CorridorKey: %s", e)
            logger.warning("Server will start but inference will fail until model is available")

        self._running = True
        self._serve_loop()

    def _serve_loop(self) -> None:
        """Main server loop: accept connections and process messages."""
        while self._running:
            try:
                self.pipe.create()
                if not self.pipe.wait_for_client():
                    self.pipe.close()
                    continue

                self._handle_client()

            except Exception as e:
                logger.error("Error in server loop: %s", e, exc_info=True)
            finally:
                self.pipe.disconnect()
                self.pipe.close()

        self._cleanup()

    def _handle_client(self) -> None:
        """Handle messages from a connected client."""
        while self._running:
            msg = self.pipe.read_message()
            if msg is None:
                logger.info("Client disconnected")
                break

            msg_type, payload = msg
            logger.debug("Received message: %s", msg_type.name)

            try:
                if msg_type == MessageType.PING:
                    self.pipe.write_message(MessageType.PONG)

                elif msg_type == MessageType.PROCESS_FRAME:
                    self._handle_process_frame(payload)

                elif msg_type == MessageType.LOAD_MODEL:
                    self._handle_load_model(payload)

                elif msg_type == MessageType.SHUTDOWN:
                    logger.info("Shutdown requested")
                    self._running = False
                    break

                else:
                    logger.warning("Unknown message type: %s", msg_type)

            except Exception as e:
                logger.error("Error handling message %s: %s", msg_type.name, e, exc_info=True)
                self.pipe.write_message(
                    MessageType.ERROR,
                    {"code": -1, "message": str(e)},
                )

    def _handle_process_frame(self, payload: dict) -> None:
        """Process a single frame."""
        req = ProcessFrameRequest(**payload)
        t0 = time.perf_counter()

        # Read input frame from shared memory
        w, h, c, input_frame = self.shm_input.read_frame()
        logger.info("Processing frame %dx%d", w, h)

        # Read alpha hint if provided externally
        alpha_hint = None
        if req.has_alpha_hint and req.mode == AlphaHintMode.EXTERNAL:
            _, _, _, alpha_hint_rgba = self.shm_alpha_hint.read_frame()
            if alpha_hint_rgba.ndim == 3 and alpha_hint_rgba.shape[2] >= 1:
                alpha_hint = alpha_hint_rgba[:, :, 0]
            else:
                alpha_hint = alpha_hint_rgba

        # Generate alpha hint with BiRefNet if auto mode
        if req.mode == AlphaHintMode.AUTO and alpha_hint is None:
            if self.inference.birefnet_model is None:
                self.inference.load_birefnet(req.birefnet_model)

        # Run inference (cached if frame hasn't changed) + post-processing
        colorspace = "srgb" if req.input_colorspace == InputColorspace.SRGB else "linear"
        input_is_linear = (colorspace == "linear")

        result = self.inference.process_frame(
            image_rgba=input_frame,
            alpha_hint=alpha_hint,
            despill_strength=req.despill_strength,
            auto_despeckle=req.auto_despeckle,
            despeckle_size=req.despeckle_size,
            refiner_strength=req.refiner_strength,
            input_colorspace=colorspace,
        )

        # Select output with proper colorspace for the pipeline.
        #
        # CorridorKey engine returns:
        #   processed:      linear premul RGBA — always correct for linear pipeline
        #   matte:          raw alpha [0,1] — needs srgb_to_linear for linear pipeline
        #   foreground_*:   available in both sRGB and linear
        #   composite_lin:  linear RGB
        #
        # When input_is_linear, Resolve expects linear data in its pipeline.
        # When sRGB, Resolve expects sRGB data.
        output_mode = OutputMode(req.output_mode)

        if output_mode == OutputMode.PROCESSED:
            if input_is_linear:
                output = result["processed"]
            else:
                # Convert premul linear RGBA to sRGB for sRGB pipeline
                from CorridorKeyModule.core import color_utils as cu
                processed = result["processed"]
                rgb_lin = processed[:, :, :3]
                alpha = processed[:, :, 3:4]
                # Unpremultiply, convert to sRGB, re-premultiply
                rgb_straight = cu.unpremultiply(rgb_lin, alpha)
                rgb_srgb = cu.linear_to_srgb(rgb_straight)
                output = np.concatenate([cu.premultiply(rgb_srgb, alpha), alpha], axis=-1)

        elif output_mode == OutputMode.MATTE:
            matte = result["matte"]
            if input_is_linear:
                # Alpha values are perceptual — apply srgb_to_linear so that
                # the display gamma in a linear pipeline cancels it out and
                # the matte looks correct in the viewer.
                from CorridorKeyModule.core import color_utils as cu
                matte = cu.srgb_to_linear(matte)
            ones = np.ones_like(matte)
            output = np.stack([matte, matte, matte, ones], axis=-1)

        elif output_mode == OutputMode.FOREGROUND:
            # Straight foreground + alpha (not premultiplied)
            if input_is_linear:
                fg = result["foreground_lin"]
            else:
                fg = result["foreground_srgb"]
            alpha = result["matte"]
            if alpha.ndim == 2:
                alpha = alpha[:, :, np.newaxis]
            output = np.concatenate([fg, alpha], axis=-1)

        elif output_mode == OutputMode.COMPOSITE:
            comp = result["composite_lin"]
            if not input_is_linear:
                from CorridorKeyModule.core import color_utils as cu
                comp = cu.linear_to_srgb(comp)
            ones = np.ones((*comp.shape[:2], 1), dtype=np.float32)
            output = np.concatenate([comp, ones], axis=-1)

        else:
            output = result["processed"]

        # Write output frame to shared memory
        self.shm_output.write_frame(w, h, output.astype(np.float32))

        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Send completion message
        self.pipe.write_message(
            MessageType.FRAME_DONE,
            {
                "width": w,
                "height": h,
                "channels": output.shape[-1] if output.ndim > 2 else 1,
                "output_mode": int(output_mode),
                "processing_time_ms": round(elapsed_ms, 1),
            },
        )
        logger.info("Frame done in %.1f ms", elapsed_ms)

    def _handle_load_model(self, payload: dict) -> None:
        """Handle model loading request."""
        model_name = payload.get("model", "corridorkey")
        variant = payload.get("variant", "general")

        if model_name == "corridorkey":
            self.inference.load_corridorkey()
        elif model_name == "birefnet":
            self.inference.load_birefnet(variant)

        self.pipe.write_message(
            MessageType.MODEL_LOADED,
            {"model": model_name, "variant": variant},
        )

    def _cleanup(self) -> None:
        """Release all resources."""
        logger.info("Cleaning up resources")
        self.inference.cleanup()
        self.shm_input.close()
        self.shm_output.close()
        self.shm_alpha_hint.close()
        self.pipe.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="CorridorKey for Resolve backend server")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    server = BackendServer()

    def signal_handler(sig, frame):
        logger.info("Signal received, shutting down...")
        server._running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down...")
    finally:
        server._cleanup()


if __name__ == "__main__":
    main()
