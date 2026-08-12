import logging
from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from backend.services.printer_manager import PrinterManager
from backend.api.printers import get_printer_manager
from backend.protocols.iprint import IPrintProtocol

logger = logging.getLogger("DebugAPI")

router = APIRouter(prefix="/api/debug", tags=["Debug"])


@router.get("/trace")
async def debug_trace(manager: PrinterManager = Depends(get_printer_manager)):
    """
    Recent raw wire activity (direction + hex) captured by the adapter.
    Falls back to the last job payload when no trace is available.
    """
    result: Dict[str, Any] = {}
    if manager.current_adapter is None:
        return {"connected": False, "trace": [], "note": "No printer adapter."}
    result["connected"] = manager.current_adapter.is_connected()
    trace = manager.current_adapter.get_trace()
    result["trace"] = trace
    result["trace_size"] = len(trace)
    result["protocol"] = manager.current_adapter.protocol
    result["device_info"] = manager.current_adapter.get_device_info()
    result["write_uuid"] = getattr(manager.current_adapter, "write_uuid", None)
    return result


@router.get("/last-payload")
async def debug_last_payload(manager: PrinterManager = Depends(get_printer_manager)):
    """
    Parses the most recent raw payload into its iPrint packets with CRC
    validation (doc 3/4) for debugging jobs that printed incorrectly.
    """
    adapter = manager.current_adapter
    payload = getattr(adapter, "last_payload", None) if adapter else None

    if not payload:
        return {"protocol": adapter.protocol if adapter else None, "total_bytes": 0, "packets": [], "note": "No job payload sent yet."}

    packets = IPrintProtocol.parse_stream(payload)
    crc_failures = [p for p in packets if p.get("crc_ok") is False]
    return {
        "protocol": adapter.protocol if adapter else None,
        "total_bytes": len(payload),
        "packet_count": len(packets),
        "crc_failures": len(crc_failures),
        "packets": packets,
        "payload_hex": payload[:2000].hex(),
    }
