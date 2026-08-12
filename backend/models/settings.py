from typing import Optional, List
from pydantic import BaseModel, Field


class PrinterConfig(BaseModel):
    name: str = "Unconfigured Thermal Printer"
    connection_type: str = "ble"
    mac_address: Optional[str] = None
    protocol: str = "escpos"
    printable_width_px: int = 384
    paper_width_mm: int = 58
    margin_px: int = 8
    density: int = 8
    speed: int = 4
    default_alignment: str = "center"
    auto_feed_mm: int = 10
    tear_bar_feed_dots: int = 130


class ImageDefaults(BaseModel):
    default_brightness: float = 1.0
    default_contrast: float = 1.0
    default_dither: str = "atkinson"
    default_sharpen: float = 1.0
    default_scaling: str = "fit"


class AppPreferences(BaseModel):
    theme: str = "dark"
    default_template: str = "simple_note"
    history_retention_days: int = 30
    debug_mode: bool = False
    favorite_templates: List[str] = Field(default_factory=list)


class AppSettings(BaseModel):
    printer: PrinterConfig = Field(default_factory=PrinterConfig)
    image: ImageDefaults = Field(default_factory=ImageDefaults)
    app: AppPreferences = Field(default_factory=AppPreferences)
