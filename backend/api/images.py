from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from backend.models.print_job import ImageProcessRequest
from backend.services.image_processor import ImageProcessor

router = APIRouter(prefix="/api/images", tags=["Images"])


@router.post("/process", response_model=Dict[str, Any])
async def process_image_preview(req: ImageProcessRequest):
    """
    Processes an uploaded image through the thermal imaging pipeline
    (Resize -> Grayscale -> Tone -> Contrast -> Smooth -> Tone-map -> Dither).
    Returns the 1-bit thermal preview image as a base64 PNG data URL.
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
            smooth=req.smooth,
            processing_preset=req.processing_preset,
            gamma=req.gamma
        )

        b64_url = ImageProcessor.to_base64_png(processed_img)
        return {
            "original_width": raw_img.width,
            "original_height": raw_img.height,
            "processed_width": processed_img.width,
            "processed_height": processed_img.height,
            "preview_url": b64_url,
            "dither_mode": req.dither_mode or "preset",
            "processing_preset": req.processing_preset
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Image processing error: {str(e)}")


@router.post("/compare", response_model=Dict[str, Any])
async def compare_image_pipeline(req: ImageProcessRequest):
    """
    Stage-by-stage comparison for the same image:
      original  → resized source (384 px)
      grayscale → tone-mapped 'L' image (what the dither sees)
      final     → the exact 1-bit bitmap sent to the printer
      variants  → the same tone-mapped image dithered with every algorithm
                  (floyd-steinberg, atkinson, bayer, threshold)

    Lets the user judge which algorithm suits their printer + paper, and
    confirms the on-screen preview matches the actual raster output.
    """
    try:
        raw_img = ImageProcessor.load_image(req.image_data)
        stages = ImageProcessor.process_stages(
            image=raw_img,
            target_width_px=req.width_px,
            dither_mode=req.dither_mode,
            brightness=req.brightness,
            contrast=req.contrast,
            sharpen=req.sharpen,
            scale_mode=req.scale_mode,
            invert=req.invert,
            auto_level=req.auto_level,
            smooth=req.smooth,
            processing_preset=req.processing_preset,
            gamma=req.gamma
        )

        return {
            "original_url": ImageProcessor.to_base64_png(stages["original"]),
            "grayscale_url": ImageProcessor.to_base64_png(stages["grayscale"]),
            "final_url": ImageProcessor.to_base64_png(stages["final"]),
            "dither": stages["dither"],
            "variants": {
                algo: ImageProcessor.to_base64_png(img)
                for algo, img in stages["variants"].items()
            },
            "width_px": stages["final"].width,
            "height_px": stages["final"].height,
            "processing_preset": req.processing_preset
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Image comparison error: {str(e)}")
