from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PrinterDevice(BaseModel):
    id: str
    name: str
    connection_type: str = Field(..., description="mock, ble, or bluetooth_classic")
    address: str = Field(..., description="MAC address, BLE UUID, or mock identifier")
    protocol: str = Field("escpos", description="escpos or tspl")
    printable_width_px: int = Field(384, description="Resolution in pixels across printable area")
    paper_width_mm: int = Field(58, description="Physical paper width in millimeters")
    status: str = Field("available", description="available, connected, disconnected, printing, error")
    rssi: Optional[int] = None
    is_default: bool = False


class ConnectionRequest(BaseModel):
    printer_id: str
    connection_type: Optional[str] = "ble"
    address: Optional[str] = None
    protocol: Optional[str] = "escpos"


class PrinterStatus(BaseModel):
    connected: bool
    current_printer: Optional[PrinterDevice] = None
    active_job_id: Optional[str] = None
    queue_length: int = 0
    paper_present: bool = True
    battery_level: Optional[int] = None
    device_info: Optional[Dict[str, Any]] = None
    message: str = "Ready"
