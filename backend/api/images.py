from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from backend.models.print_job import ImageProcessRequest
from backend.services.image_processor import ImageProcessor

router = APIRouter(prefix="/api/images", tags=["Images"])


@router.post("/process", response_model=Dict[str, Any])
async def process_image_preview(req: ImageProcessRequest):
    """
    Processes an uploaded image through the thermal imaging pipeline (Resize -> Grayscale -> Contrast -> Dither).
    Returns a 1-bit thermal preview image as a base64 PNG data URL.
    """
    try:
        raw_img = ImageProcessor.load_image(req.image_data)
        processed_img = ImageProcessor.process_image(
            image=raw_img,
            target_width_px=req.width_px,
            dither_mode=req.dither_mode,
            brightness=req.brightness,
            contrast=req.contrast,
            sharpen=req.sharpen,
            scale_mode=req.scale_mode,
            invert=req.invert,
            auto_level=req.auto_level,
            smooth=req.smooth
        )

        b64_url = ImageProcessor.to_base64_png(processed_img)
        return {
            "original_width": raw_img.width,
            "original_height": raw_img.height,
            "processed_width": processed_img.width,
            "processed_height": processed_img.height,
            "preview_url": b64_url,
            "dither_mode": req.dither_mode
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Image processing error: {str(e)}")
