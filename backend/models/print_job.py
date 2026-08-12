from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime


class ContentBlock(BaseModel):
    type: str = Field(..., description="text, image, qr, barcode, line, space")
    
    # Text attributes
    content: Optional[str] = None
    font_size: Optional[str] = Field("normal", description="small, normal, large, title")
    custom_font_size: Optional[int] = Field(None, description="Explicit font size in px (overrides font_size)")
    font_family: Optional[str] = Field("arial", description="arial, courier, times, tahoma, verdana, georgia, comic, impact, consolas, calibri")
    line_spacing: Optional[float] = Field(1.3, description="Line height multiplier")
    letter_spacing: Optional[int] = Field(0, description="Extra pixels between characters")
    bold: Optional[bool] = False
    italic: Optional[bool] = False
    monospace: Optional[bool] = False
    align: Optional[str] = Field("left", description="left, center, right")
    invert: Optional[bool] = False
    underline: Optional[bool] = False
    
    # Image attributes
    image_data: Optional[str] = Field(None, description="Base64 encoded string or URL")
    dither_mode: Optional[str] = Field("atkinson", description="atkinson, floyd-steinberg, stucki, bayer, threshold")
    brightness: Optional[float] = 1.0
    contrast: Optional[float] = 1.0
    sharpen: Optional[float] = 1.0
    scale_mode: Optional[str] = Field("fit", description="fit, crop, original")
    auto_level: Optional[bool] = Field(True, description="Smart histogram stretch (only when the image is washed out)")
    smooth: Optional[float] = Field(0.7, description="Pre-dither Gaussian blur radius for photos (0 = off)")
    processing_preset: Optional[str] = Field(
        None, description="photo, photo_detail, manga, line_art, text, qr — thermal-tuned pipeline defaults"
    )
    gamma: Optional[float] = Field(None, description="Tone curve: <1 lifts midtones (lighter print), 1.0 = none")
    
    # QR Code attributes
    qr_payload: Optional[str] = None
    qr_size: Optional[int] = Field(4, description="Size multiplier 1-10")
    qr_ecc: Optional[str] = Field("M", description="L, M, Q, H")
    
    # Barcode attributes
    barcode_payload: Optional[str] = None
    barcode_type: Optional[str] = Field("code128", description="code128, ean13, ean8, upca")
    barcode_height: Optional[int] = Field(50, description="Height in pixels")
    show_barcode_text: Optional[bool] = True
    
    # Line separator attributes
    line_style: Optional[str] = Field("solid", description="solid, dashed, dotted, double")
    
    # Spacer attributes
    space_height: Optional[int] = Field(16, description="Spacer height in pixels")

    # Table block attributes (receipt / label designer)
    table_headers: Optional[List[str]] = Field(None, description="Optional column headers")
    table_rows: Optional[List[List[str]]] = Field(None, description="Cells, one list per row")
    table_col_widths: Optional[List[int]] = Field(None, description="Explicit column widths in px")

    # Totals block attributes (label/value lines with dotted leaders)
    totals_lines: Optional[List[Dict[str, Any]]] = Field(
        None, description="Each: {label, value, bold, dotted}"
    )


class PrintRequest(BaseModel):
    title: str = "Untitled Print Job"
    blocks: List[ContentBlock] = Field(default_factory=list)
    width_px: Optional[int] = 384
    margin_px: Optional[int] = 8
    feed_lines: Optional[int] = 3
    cut_paper: Optional[bool] = False
    copies: Optional[int] = Field(1, ge=1, le=99, description="Number of copies to print")
    raw_payload: Optional[bytes] = Field(
        None, description="Pre-built protocol bytes; skips block rendering when set (internal use)"
    )


class CalibrateRequest(BaseModel):
    """One-tap image density calibration: prints the same processed image at
    several energy levels (0xAF) in a single job so the user can pick the
    density that suits their paper roll."""
    image_data: str
    width_px: int = 384
    processing_preset: str = "photo"
    dither_mode: Optional[str] = None
    brightness: Optional[float] = None
    contrast: Optional[float] = None
    sharpen: Optional[float] = None
    smooth: Optional[float] = None
    auto_level: Optional[bool] = None
    gamma: Optional[float] = None
    invert: bool = False
    scale_mode: str = "fit"
    densities: List[int] = Field(default_factory=lambda: [5, 6, 7, 8, 9, 10])


class ImageProcessRequest(BaseModel):
    image_data: str
    width_px: int = 384
    dither_mode: Optional[str] = None
    brightness: Optional[float] = None
    contrast: Optional[float] = None
    sharpen: Optional[float] = None
    invert: bool = False
    scale_mode: str = "fit"
    auto_level: Optional[bool] = None
    smooth: Optional[float] = None
    processing_preset: str = "photo"
    gamma: Optional[float] = None


class PrintJobRecord(BaseModel):
    id: str
    title: str
    timestamp: str
    content_types: List[str]
    printer_name: str
    width_px: int
    height_px: int
    status: str = Field("queued", description="queued, preparing, printing, completed, failed, cancelled")
    queue_position: Optional[int] = None
    preview_url: Optional[str] = None
    error_message: Optional[str] = None
    blocks: Optional[List[Dict[str, Any]]] = Field(None, description="Original content blocks, used for reprinting")


class CSVLabelRequest(BaseModel):
    csv_text: str = Field(..., description="Raw CSV content")
    name_col: int = 0
    sku_col: int = 1
    price_col: int = 2
    has_header: bool = True
    copies: int = Field(1, ge=1, le=99)
    title_prefix: str = "Label"
