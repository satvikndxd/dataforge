"""
Image Processing Module.
Resizes and normalizes imagery for downstream Machine Learning models (ResNet/CNN scale).
Supports configurable preprocessing: resolution, quality, format, and augmentations.
"""

import io
import logging
from PIL import Image, ImageFilter, ImageOps

logger = logging.getLogger(__name__)

# Preset resolution targets
RESOLUTION_PRESETS = {
    "224": (224, 224),
    "256": (256, 256),
    "384": (384, 384),
    "512": (512, 512),
}


def resize_and_normalize(
    image_bytes: bytes,
    target_size=(224, 224),
    quality: int = 95,
    output_format: str = "JPEG",
    grayscale: bool = False,
    edge_enhance: bool = False,
    equalize: bool = False,
) -> bytes:
    """
    Takes raw image bytes from scraping payloads.
    Resizes to the target CNN format, ensures robust RGB mapping.
    Optionally applies augmentations: grayscale, edge enhance, histogram equalization.
    """
    if not image_bytes:
        return b""

    try:
        img_buffer = io.BytesIO(image_bytes)
        img = Image.open(img_buffer)

        # Ensure correct channel mapping (stripping rogue Alphas/CMYK space for dataset unity)
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Optional augmentations
        if equalize:
            img = ImageOps.equalize(img)
        if edge_enhance:
            img = img.filter(ImageFilter.EDGE_ENHANCE_MORE)
        if grayscale:
            img = ImageOps.grayscale(img)
            img = img.convert('RGB')  # Keep 3-channel for CNN compatibility

        # Downscale via rigorous Lanczos filter
        scaled_img = img.resize(target_size, Image.Resampling.LANCZOS)

        out_buffer = io.BytesIO()
        fmt = output_format.upper()
        if fmt == "PNG":
            scaled_img.save(out_buffer, format="PNG")
        else:
            scaled_img.save(out_buffer, format="JPEG", quality=quality)
        return out_buffer.getvalue()

    except Exception as e:
        logger.error(f"Image normalization sequence failed: {e}")
        return image_bytes  # Fail softly by returning raw unscaled bytes


def get_preprocessing_info(
    target_size=(224, 224),
    quality: int = 95,
    output_format: str = "JPEG",
    grayscale: bool = False,
    edge_enhance: bool = False,
    equalize: bool = False,
) -> dict:
    """Return a summary of the preprocessing configuration."""
    steps = [
        f"Resize to {target_size[0]}x{target_size[1]} (Lanczos)",
        "RGB channel normalization",
    ]
    if equalize:
        steps.append("Histogram equalization")
    if edge_enhance:
        steps.append("Edge enhancement")
    if grayscale:
        steps.append("Grayscale conversion (3-ch)")
    steps.append(f"Export as {output_format.upper()} (quality={quality})")
    return {
        "target_size": list(target_size),
        "quality": quality,
        "format": output_format.upper(),
        "augmentations": {
            "grayscale": grayscale,
            "edge_enhance": edge_enhance,
            "equalize": equalize,
        },
        "steps": steps,
    }
