"""
Inference wrapper for CorridorKey and BiRefNet models.

Wraps the CorridorKey inference engine and BiRefNet alpha hint generator
into a single interface used by the IPC server.
"""

import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch

logger = logging.getLogger(__name__)

# Default model cache directory
DEFAULT_MODEL_DIR = Path.home() / "AppData" / "Roaming" / "CorridorKeyForResolve" / "models"


class InferenceWrapper:
    """Wraps CorridorKey engine and BiRefNet for the backend server."""

    def __init__(self, model_dir: Optional[Path] = None, device: str = "cuda"):
        self.model_dir = model_dir or DEFAULT_MODEL_DIR
        self.device = device
        self.corridorkey_engine = None
        self.birefnet_model = None
        self._birefnet_variant = None

    def load_corridorkey(self) -> None:
        """Load the CorridorKey inference engine."""
        try:
            from corridorkey import CorridorKeyEngine

            model_path = self.model_dir / "corridorkey_v1.pth"
            if not model_path.exists():
                raise FileNotFoundError(
                    f"CorridorKey model not found at {model_path}. "
                    "Run install.py to download models."
                )

            logger.info("Loading CorridorKey model from %s", model_path)
            self.corridorkey_engine = CorridorKeyEngine(
                checkpoint_path=str(model_path),
                device=self.device,
            )
            logger.info("CorridorKey model loaded successfully")

        except ImportError:
            raise ImportError(
                "corridorkey package not installed. "
                "Install with: pip install corridorkey"
            )

    def load_birefnet(self, variant: str = "general") -> None:
        """Load the BiRefNet model for automatic alpha hint generation."""
        if self._birefnet_variant == variant and self.birefnet_model is not None:
            return

        try:
            from birefnet import BiRefNet

            logger.info("Loading BiRefNet model (variant: %s)", variant)
            self.birefnet_model = BiRefNet.from_pretrained(
                f"ZhengPeng7/BiRefNet-{variant}",
                cache_dir=str(self.model_dir / "birefnet"),
            )
            self.birefnet_model.to(self.device)
            self.birefnet_model.eval()
            self._birefnet_variant = variant
            logger.info("BiRefNet model loaded successfully")

        except ImportError:
            raise ImportError(
                "birefnet package not installed. "
                "Install with: pip install birefnet"
            )

    def generate_alpha_hint(self, image_rgb: np.ndarray) -> np.ndarray:
        """Generate an alpha hint mask using BiRefNet.

        Args:
            image_rgb: Input image as float32 numpy array, shape (H, W, 3), range [0, 1].

        Returns:
            Alpha hint as float32 numpy array, shape (H, W), range [0, 1].
        """
        if self.birefnet_model is None:
            raise RuntimeError("BiRefNet model not loaded. Call load_birefnet() first.")

        h, w = image_rgb.shape[:2]

        # BiRefNet expects (B, C, H, W) tensor, normalized
        tensor = torch.from_numpy(image_rgb).permute(2, 0, 1).unsqueeze(0).float()
        tensor = tensor.to(self.device)

        with torch.no_grad():
            # BiRefNet returns a list of predictions at different scales;
            # we use the final (highest resolution) output
            preds = self.birefnet_model(tensor)
            if isinstance(preds, (list, tuple)):
                pred = preds[-1]
            else:
                pred = preds

            # Sigmoid to get [0,1] range, then resize to original
            pred = torch.sigmoid(pred)
            if pred.shape[-2:] != (h, w):
                pred = torch.nn.functional.interpolate(
                    pred, size=(h, w), mode="bilinear", align_corners=False
                )

        alpha_hint = pred.squeeze().cpu().numpy().astype(np.float32)
        return alpha_hint

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
        """Process a single frame through CorridorKey.

        Args:
            image_rgba: Input RGBA image, float32 (H, W, 4), range [0, 1].
            alpha_hint: Optional alpha hint mask, float32 (H, W), range [0, 1].
            despill_strength: Green spill removal intensity.
            auto_despeckle: Whether to remove small isolated alpha artifacts.
            despeckle_size: Minimum pixel area threshold for despeckle.
            refiner_strength: CNN refiner multiplier.
            input_colorspace: "srgb" or "linear".

        Returns:
            Dict with keys: "processed" (premul RGBA), "matte" (alpha),
            "foreground" (straight RGB), "composite" (preview over checker).
        """
        if self.corridorkey_engine is None:
            raise RuntimeError(
                "CorridorKey engine not loaded. Call load_corridorkey() first."
            )

        t0 = time.perf_counter()

        # Extract RGB from RGBA input
        image_rgb = image_rgba[:, :, :3]

        # Generate alpha hint if not provided
        if alpha_hint is None:
            alpha_hint = self.generate_alpha_hint(image_rgb)

        # Run CorridorKey inference
        result = self.corridorkey_engine.process(
            image=image_rgb,
            alpha_hint=alpha_hint,
            despill_strength=despill_strength,
            auto_despeckle=auto_despeckle,
            despeckle_size=despeckle_size,
            refiner_strength=refiner_strength,
            input_colorspace=input_colorspace,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info("Frame processed in %.1f ms", elapsed_ms)

        # Build output dict
        # CorridorKey returns: foreground (RGB), matte (alpha), processed (premul RGBA)
        matte = result.get("matte", result.get("alpha"))
        foreground = result.get("foreground", result.get("fg"))
        processed = result.get("processed", result.get("result"))

        # If processed not directly available, construct premultiplied RGBA
        if processed is None and foreground is not None and matte is not None:
            alpha_3ch = np.expand_dims(matte, axis=-1)
            processed = np.concatenate(
                [foreground * alpha_3ch, alpha_3ch], axis=-1
            ).astype(np.float32)

        # Build composite preview (foreground over checkerboard)
        composite = self._make_composite(foreground, matte) if foreground is not None and matte is not None else None

        return {
            "processed": processed,
            "matte": matte,
            "foreground": foreground,
            "composite": composite,
            "elapsed_ms": elapsed_ms,
        }

    def _make_composite(self, fg: np.ndarray, alpha: np.ndarray) -> np.ndarray:
        """Composite foreground over a checkerboard pattern."""
        h, w = fg.shape[:2]
        checker = np.zeros((h, w, 3), dtype=np.float32)
        block = 16
        for y in range(0, h, block):
            for x in range(0, w, block):
                if ((y // block) + (x // block)) % 2 == 0:
                    checker[y:y+block, x:x+block] = 0.8
                else:
                    checker[y:y+block, x:x+block] = 0.5

        a = np.expand_dims(alpha, axis=-1)
        comp = fg * a + checker * (1.0 - a)
        # Return as RGBA
        return np.concatenate([comp, np.ones((h, w, 1), dtype=np.float32)], axis=-1)

    def cleanup(self) -> None:
        """Release GPU resources."""
        if self.corridorkey_engine is not None:
            del self.corridorkey_engine
            self.corridorkey_engine = None
        if self.birefnet_model is not None:
            del self.birefnet_model
            self.birefnet_model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("GPU resources released")
