"""
Image Processing Module.
Resizes and normalizes imagery for downstream Machine Learning models (ResNet/CNN scale).
"""

import io
import logging
from PIL import Image

logger = logging.getLogger(__name__)

def resize_and_normalize(image_bytes: bytes, target_size=(224, 224)) -> bytes:
    """
    Takes raw image bytes from scraping payloads.
    Resizes aggressively to standard CNN format (224x224), ensures robust RGB mapping.
    """
    if not image_bytes:
        return b""
        
    try:
        img_buffer = io.BytesIO(image_bytes)
        img = Image.open(img_buffer)
        
        # Ensure correct channel mapping (stripping rogue Alphas/CMYK space for dataset unity)
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        # Downscale via rigorous Lanczos filter
        scaled_img = img.resize(target_size, Image.Resampling.LANCZOS)
        
        out_buffer = io.BytesIO()
        scaled_img.save(out_buffer, format="JPEG", quality=95)
        return out_buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Image normalization sequence failed: {e}")
        return image_bytes # Fail softly by returning raw unscaled bytes
