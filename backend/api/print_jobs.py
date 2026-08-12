import io
import csv
import logging
from fastapi import APIRouter, HTTPException, Depends, Response
from typing import Dict, Any, Optional, List
from backend.models.print_job import PrintRequest, PrintJobRecord, ContentBlock, CSVLabelRequest, CalibrateRequest
from backend.services.printer_manager import PrinterManager
from backend.services.print_engine import PrintEngine
from backend.services.image_processor import ImageProcessor
from backend.api.printers import get_printer_manager

logger = logging.getLogger("PrintJobsAPI")

router = APIRouter(prefix="/api/print", tags=["Print Jobs"])


@router.post("/csv", response_model=Dict[str, Any])
async def print_csv_labels(req: CSVLabelRequest, manager: PrinterManager = Depends(get_printer_manager)):
    """
    Parses CSV text and enqueues one barcode label job per row.
    """
    if not manager.current_adapter or not manager.current_adapter.is_connected():
        raise HTTPException(status_code=503, detail="No printer connected. Please connect to a physical printer.")

    try:
        rows = list(csv.reader(io.StringIO(req.csv_text.lstrip("\ufeff"))))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")
    if not rows:
        raise HTTPException(status_code=400, detail="CSV is empty.")

    start = 1 if (req.has_header and len(rows) > 0) else 0
    data_rows = rows[start:]
    if not data_rows:
        raise HTTPException(status_code=400, detail="CSV has no data rows after the header.")

    job_ids: List[str] = []
    errors = []
    for i, row in enumerate(data_rows):
        name = row[req.name_col] if req.name_col < len(row) else ""
        sku = row[req.sku_col] if req.sku_col < len(row) else ""
        price = row[req.price_col] if req.price_col < len(row) else ""
        if not (name or sku):
            errors.append(i + 1)
            continue
        blocks = [
            ContentBlock(type="text", content=(name or "").upper(), font_size="large", align="center"),
        ]
        if sku:
            blocks.append(ContentBlock(type="barcode", barcode_payload=sku, barcode_type="code128", barcode_height=55, show_barcode_text=True, align="center"))
        if price:
            blocks.append(ContentBlock(type="text", content=f"PRICE: {price}", font_size="small", align="center"))
        blocks.append(ContentBlock(type="space", space_height=10))
        try:
            job = await manager.submit_print_job(PrintRequest(
                title=f"{req.title_prefix} {i + 1}",
                blocks=blocks,
                copies=req.copies,
                feed_lines=2,
                cut_paper=False
            ))
            job_ids.append(job.id)
        except Exception as e:
            errors.append(i + 1)
    return {"submitted": len(job_ids), "job_ids": job_ids, "skipped_rows": errors}


@router.post("", response_model=PrintJobRecord)
async def create_print_job(
    print_req: PrintRequest,
    manager: PrinterManager = Depends(get_printer_manager)
):
    """
    Submits a print job payload containing layout blocks to be rendered and printed.
    Returns immediately; the job is processed asynchronously by the queue.
    """
    if not print_req.blocks:
        raise HTTPException(status_code=400, detail="Print job request must contain at least one content block.")
    try:
        return await manager.submit_print_job(print_req)
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/calibrate", response_model=PrintJobRecord)
async def print_image_calibration(req: CalibrateRequest, manager: PrinterManager = Depends(get_printer_manager)):
    """
    One-tap image density calibration. Processes the uploaded image with the
    requested preset/tone settings, then prints it as labeled strips at
    several energy levels (0xAF) in a single job — pick the density that
    looks best on your paper and set it in Settings.
    """
    if not manager.current_adapter or not manager.current_adapter.is_connected():
        raise HTTPException(status_code=503, detail="No printer connected. Please connect to a physical printer.")
    try:
        raw_img = ImageProcessor.load_image(req.image_data)
        processed = ImageProcessor.process_image(
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
        payload = PrintEngine.build_density_calibration(processed, densities=req.densities)
        job = await manager.submit_print_job(PrintRequest(
            title="Image Density Calibration",
            blocks=[],
            width_px=req.width_px,
            margin_px=0,
            feed_lines=0,
            cut_paper=False,
            copies=1,
            raw_payload=payload
        ))
        return job
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Calibration error: {str(e)}")


@router.get("/jobs/{job_id}", response_model=PrintJobRecord)
async def get_print_job(job_id: str, manager: PrinterManager = Depends(get_printer_manager)):
    """
    Returns the current status of a queued/active/finished print job.
    """
    job = manager.get_job_record(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Print job '{job_id}' not found.")
    return job


@router.get("/queue", response_model=Dict[str, Any])
async def get_print_queue(manager: PrinterManager = Depends(get_printer_manager)):
    """
    Returns the active job and the list of queued jobs.
    """
    return manager.get_queue_status()


@router.post("/preview", response_model=Dict[str, Any])
async def generate_print_preview(print_req: PrintRequest):
    """
    Renders layout blocks into a 1-bit thermal paper preview Image (base64 PNG) without hardware printing.
    """
    if not print_req.blocks:
        raise HTTPException(status_code=400, detail="Preview request must contain at least one content block.")

    width_px = print_req.width_px or 384
    margin_px = print_req.margin_px if print_req.margin_px is not None else 8

    rendered_img = PrintEngine.render_blocks_to_image(
        blocks=print_req.blocks,
        target_width_px=width_px,
        margin_px=margin_px
    )

    preview_b64 = ImageProcessor.to_base64_png(rendered_img)
    return {
        "width_px": rendered_img.width,
        "height_px": rendered_img.height,
        "preview_url": preview_b64,
        "paper_width_mm": 58 if width_px == 384 else 80
    }


@router.post("/export")
async def export_print(print_req: PrintRequest, fmt: str = "png"):
    """
    Renders layout blocks and returns the output as a downloadable PNG or PDF file.
    """
    if not print_req.blocks:
        raise HTTPException(status_code=400, detail="Export request must contain at least one content block.")

    width_px = print_req.width_px or 384
    margin_px = print_req.margin_px if print_req.margin_px is not None else 8

    rendered_img = PrintEngine.render_blocks_to_image(
        blocks=print_req.blocks,
        target_width_px=width_px,
        margin_px=margin_px
    )

    fmt = fmt.lower()
    if fmt == "pdf":
        buffer = io.BytesIO()
        rendered_img.convert("RGB").save(buffer, format="PDF", resolution=96)
        media_type = "application/pdf"
        extension = "pdf"
    elif fmt == "png":
        buffer = io.BytesIO()
        rendered_img.save(buffer, format="PNG")
        media_type = "image/png"
        extension = "png"
    else:
        raise HTTPException(status_code=400, detail="Unsupported export format. Use 'png' or 'pdf'.")

    buffer.seek(0)
    safe_title = "".join(c for c in (print_req.title or "print") if c.isalnum() or c in " -_").strip() or "print"
    filename = f"{safe_title[:40]}.{extension}"
    return Response(
        content=buffer.getvalue(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/cancel")
async def cancel_print_job(payload: Optional[Dict[str, Any]] = None, manager: PrinterManager = Depends(get_printer_manager)):
    """
    Cancels a specific print job (body: {"job_id": "..."}), or the active job and
    everything queued behind it when no id is given.
    """
    job_id = (payload or {}).get("job_id") if payload else None
    cancelled = manager.cancel_job(job_id=job_id)
    if not cancelled:
        return {"status": "none", "message": "No active or queued print job to cancel."}
    return {"status": "cancelled", "cancelled_jobs": cancelled, "message": f"Cancelled {len(cancelled)} job(s)."}
