"""
Inference wrapper for CorridorKey and BiRefNet models.

Uses CorridorKey's own backend.create_engine() which handles model
download and loading automatically.

Separates neural network inference (expensive) from post-processing
(cheap) to allow caching and instant parameter tweaking.

Performance optimizations:
- fp16 precision for both CorridorKey and BiRefNet (4090 has massive fp16 throughput)
- BiRefNet alpha hint is cached per-frame
- Raw inference results cached to skip re-inference on param tweaks
"""

import hashlib
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch

logger = logging.getLogger(__name__)

DEFAULT_INSTALL_DIR = Path(os.environ.get("APPDATA", "")) / "CorridorKeyForResolve"
CORRIDORKEY_REPO_DIR = DEFAULT_INSTALL_DIR / "CorridorKey"


def ensure_corridorkey_on_path():
    """Add CorridorKey repo to sys.path so we can import CorridorKeyModule."""
    repo_dir = str(CORRIDORKEY_REPO_DIR)
    if repo_dir not in sys.path:
        sys.path.insert(0, repo_dir)


def _frame_hash(image: np.ndarray) -> bytes:
    """Quick hash of frame content for cache invalidation.

    Samples a few rows instead of hashing the entire frame.
    """
    h = image.shape[0]
    rows = [0, h // 4, h // 2, 3 * h // 4, h - 1]
    sample = b"".join(image[r].tobytes() for r in rows)
    return hashlib.md5(sample).digest()


class InferenceWrapper:
    """Wraps CorridorKey engine and BiRefNet for the backend server.

    Caches raw neural network outputs so that post-processing param
    changes (despill, despeckle) and output mode changes don't
    re-run inference.
    """

    def __init__(self, device: str = "cuda"):
        self.device = device
        self.corridorkey_engine = None
        self.birefnet_model = None
        self._birefnet_variant = None
        # Cache for raw CorridorKey inference results
        self._cache_hash: Optional[bytes] = None
        self._cache_refiner: Optional[float] = None
        self._cache_is_linear: Optional[bool] = None
        self._cached_raw_alpha: Optional[np.ndarray] = None
        self._cached_raw_fg_srgb: Optional[np.ndarray] = None
        # Cache for BiRefNet alpha hint
        self._birefnet_cache_hash: Optional[bytes] = None
        self._cached_alpha_hint: Optional[np.ndarray] = None
        self._color_utils = None

    def _get_color_utils(self):
        if self._color_utils is None:
            ensure_corridorkey_on_path()
            from CorridorKeyModule.core import color_utils
            self._color_utils = color_utils
        return self._color_utils

    def load_corridorkey(self) -> None:
        """Load the CorridorKey inference engine in fp16 for maximum 4090 throughput."""
        ensure_corridorkey_on_path()

        try:
            from CorridorKeyModule.inference_engine import CorridorKeyEngine
            from CorridorKeyModule.backend import _discover_checkpoint, TORCH_EXT
        except ImportError:
            raise ImportError(
                f"CorridorKey not found. Expected repo at {CORRIDORKEY_REPO_DIR}.\n"
                "Run install.py to clone it."
            )

        logger.info("Loading CorridorKey engine (device=%s, precision=fp16)...", self.device)
        prev_cwd = os.getcwd()
        os.chdir(str(CORRIDORKEY_REPO_DIR))
        try:
            ckpt = _discover_checkpoint(TORCH_EXT)
            self.corridorkey_engine = CorridorKeyEngine(
                checkpoint_path=str(ckpt),
                device=self.device,
                model_precision=torch.float16,
                mixed_precision=True,
            )
        finally:
            os.chdir(prev_cwd)
        logger.info("CorridorKey engine loaded successfully (fp16)")

    def load_birefnet(self, variant: str = "general") -> None:
        """Load the BiRefNet model in fp16 for automatic alpha hint generation."""
        if self._birefnet_variant == variant and self.birefnet_model is not None:
            return

        try:
            from transformers import AutoModelForImageSegmentation
        except ImportError:
            raise ImportError(
                "transformers package not installed. "
                "Install with: pip install transformers"
            )

        model_id = "ZhengPeng7/BiRefNet"
        if variant and variant != "general":
            model_id = f"ZhengPeng7/BiRefNet-{variant}"

        logger.info("Loading BiRefNet model (%s) in fp16...", model_id)
        self.birefnet_model = AutoModelForImageSegmentation.from_pretrained(
            model_id,
            trust_remote_code=True,
        )
        self.birefnet_model.half().to(self.device)
        self.birefnet_model.eval()
        self._birefnet_variant = variant
        logger.info("BiRefNet model loaded successfully (fp16)")

    def generate_alpha_hint(self, image_rgb: np.ndarray, frame_hash: bytes) -> np.ndarray:
        """Generate an alpha hint mask using BiRefNet.

        Caches result per-frame so repeated calls with same frame skip inference.

        Args:
            image_rgb: float32 (H, W, 3), range [0, 1].
            frame_hash: hash of the input frame for cache invalidation.

        Returns:
            float32 (H, W), range [0, 1].
        """
        # Check BiRefNet cache
        if frame_hash == self._birefnet_cache_hash and self._cached_alpha_hint is not None:
            logger.info("Using cached BiRefNet alpha hint")
            return self._cached_alpha_hint

        if self.birefnet_model is None:
            raise RuntimeError("BiRefNet not loaded. Call load_birefnet() first.")

        t0 = time.perf_counter()
        h, w = image_rgb.shape[:2]
        birefnet_size = 1024

        tensor = torch.from_numpy(image_rgb).permute(2, 0, 1).unsqueeze(0).half()
        tensor = tensor.to(self.device)
        tensor = torch.nn.functional.interpolate(
            tensor, size=(birefnet_size, birefnet_size),
            mode="bilinear", align_corners=False
        )

        with torch.no_grad():
            preds = self.birefnet_model(tensor)
            pred = preds[-1] if isinstance(preds, (list, tuple)) else preds
            pred = torch.sigmoid(pred)

        # Resize back to original resolution on GPU
        pred = torch.nn.functional.interpolate(
            pred, size=(h, w), mode="bilinear", align_corners=False
        )

        result = pred.squeeze().float().cpu().numpy().astype(np.float32)

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("BiRefNet alpha hint: %.1f ms", elapsed)

        # Cache
        self._birefnet_cache_hash = frame_hash
        self._cached_alpha_hint = result

        return result

    def run_inference(
        self,
        image_rgba: np.ndarray,
        alpha_hint: Optional[np.ndarray],
        refiner_strength: float,
        input_is_linear: bool,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Run neural network inference, returning raw alpha + raw fg.

        Uses cache if the frame and inference params haven't changed.
        Calls engine with despill=0 and despeckle=False to get raw outputs.
        """
        if self.corridorkey_engine is None:
            raise RuntimeError("CorridorKey not loaded. Call load_corridorkey() first.")

        fh = _frame_hash(image_rgba)

        # Check CorridorKey cache
        if (fh == self._cache_hash
                and refiner_strength == self._cache_refiner
                and input_is_linear == self._cache_is_linear
                and self._cached_raw_alpha is not None):
            logger.info("Using cached CorridorKey inference result")
            return self._cached_raw_alpha, self._cached_raw_fg_srgb

        t0 = time.perf_counter()

        image_rgb = image_rgba[:, :, :3].copy()

        # Generate alpha hint if not provided (uses BiRefNet with its own cache)
        if alpha_hint is None:
            alpha_hint = self.generate_alpha_hint(image_rgb, fh)

        if alpha_hint.ndim == 3:
            alpha_hint = alpha_hint[:, :, 0]

        # Run engine with NO post-processing to get raw model outputs
        result = self.corridorkey_engine.process_frame(
            image=image_rgb,
            mask_linear=alpha_hint,
            refiner_scale=refiner_strength,
            input_is_linear=input_is_linear,
            fg_is_straight=True,
            despill_strength=0.0,
            auto_despeckle=False,
        )

        raw_alpha = result["alpha"]
        raw_fg_srgb = result["fg"]

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("Total inference (BiRefNet + CorridorKey): %.1f ms", elapsed)

        # Cache
        self._cache_hash = fh
        self._cache_refiner = refiner_strength
        self._cache_is_linear = input_is_linear
        self._cached_raw_alpha = raw_alpha
        self._cached_raw_fg_srgb = raw_fg_srgb

        return raw_alpha, raw_fg_srgb

    def apply_postprocessing(
        self,
        raw_alpha: np.ndarray,
        raw_fg_srgb: np.ndarray,
        despill_strength: float,
        auto_despeckle: bool,
        despeckle_size: int,
        input_is_linear: bool,
    ) -> dict[str, np.ndarray]:
        """Apply post-processing to raw inference results.

        Returns dict with all output variants, properly colorspace-tagged.
        """
        cu = self._get_color_utils()

        # Ensure alpha is [H,W,1]
        if raw_alpha.ndim == 2:
            alpha_3d = raw_alpha[:, :, np.newaxis]
        else:
            alpha_3d = raw_alpha

        # Despeckle
        if auto_despeckle:
            processed_alpha = cu.clean_matte(alpha_3d, area_threshold=despeckle_size, dilation=25, blur_size=5)
        else:
            processed_alpha = alpha_3d

        if processed_alpha.ndim == 2:
            processed_alpha = processed_alpha[:, :, np.newaxis]

        # Despill (operates in sRGB space)
        fg_despilled_srgb = cu.despill(raw_fg_srgb, green_limit_mode="average", strength=despill_strength)

        # Convert fg to linear
        fg_despilled_lin = cu.srgb_to_linear(fg_despilled_srgb)

        # Premultiplied linear RGBA (the "processed" output)
        fg_premul_lin = cu.premultiply(fg_despilled_lin, processed_alpha)
        processed_rgba = np.concatenate([fg_premul_lin, processed_alpha], axis=-1).astype(np.float32)

        # Matte as [H,W] for output
        matte_2d = processed_alpha.squeeze()

        # Composite: straight fg over gray checkerboard, both in linear
        h, w = raw_alpha.shape[:2]
        bg_srgb = cu.create_checkerboard(w, h, checker_size=128, color1=0.15, color2=0.55)
        bg_lin = cu.srgb_to_linear(bg_srgb)
        comp_lin = cu.composite_straight(fg_despilled_lin, bg_lin, processed_alpha)

        return {
            "processed": processed_rgba,
            "matte": matte_2d,
            "foreground_srgb": fg_despilled_srgb,
            "foreground_lin": fg_despilled_lin,
            "composite_lin": comp_lin,
        }

    def process_frame(
        self,
        image_rgba: np.ndarray,
        alpha_hint: Optional[np.ndarray] = None,
        despill_strength: float = 1.0,
        auto_despeckle: bool = True,
        despeckle_size: int = 400,
        refiner_strength: float = 1.0,
        input_colorspace: str = "srgb",
    ) -> dict[str, np.ndarray]:
        """Full pipeline with caching.

        Neural network inference is cached — only re-runs when the
        input frame or refiner_strength changes. Post-processing
        (despill, despeckle) is always re-applied from cached outputs.
        """
        input_is_linear = (input_colorspace == "linear")

        raw_alpha, raw_fg_srgb = self.run_inference(
            image_rgba, alpha_hint, refiner_strength, input_is_linear,
        )

        t0 = time.perf_counter()
        result = self.apply_postprocessing(
            raw_alpha, raw_fg_srgb,
            despill_strength, auto_despeckle, despeckle_size,
            input_is_linear,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("Post-processing: %.1f ms", elapsed)

        return result

    def cleanup(self) -> None:
        """Release GPU resources."""
        if self.corridorkey_engine is not None:
            del self.corridorkey_engine
            self.corridorkey_engine = None
        if self.birefnet_model is not None:
            del self.birefnet_model
            self.birefnet_model = None
        self._cached_raw_alpha = None
        self._cached_raw_fg_srgb = None
        self._cached_alpha_hint = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("GPU resources released")
