import logging
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from backend.models.printer import PrinterDevice, PrinterStatus, ConnectionRequest
from backend.models.print_job import PrintJobRecord
from backend.services.printer_manager import PrinterManager

logger = logging.getLogger("PrintersAPI")

router = APIRouter(prefix="/api/printers", tags=["Printers"])

# Global singleton manager instance (to be injected or accessed)
_printer_manager = PrinterManager()

def get_printer_manager() -> PrinterManager:
    return _printer_manager


@router.get("", response_model=Dict[str, List[PrinterDevice]])
async def list_printers(mode: Optional[str] = None, manager: PrinterManager = Depends(get_printer_manager)):
    """
    Scans for and returns available thermal printers. Mode can be 'ble' or 'mock'.
    """
    try:
        printers = await manager.scan_printers(mode=mode)
        return {"printers": printers}
    except Exception as e:
        logger.error(f"Error scanning printers: {e}")
        return {"printers": []}


@router.get("/status", response_model=PrinterStatus)
async def get_printer_status(manager: PrinterManager = Depends(get_printer_manager)):
    """
    Gets real-time connection status, battery, paper, and queue info.
    """
    return manager.get_status()


@router.post("/connect", response_model=PrinterStatus)
async def connect_printer(req: ConnectionRequest, manager: PrinterManager = Depends(get_printer_manager)):
    """
    Connects to the specified printer.
    """
    return await manager.connect_printer(req)


@router.post("/disconnect", response_model=PrinterStatus)
async def disconnect_printer(manager: PrinterManager = Depends(get_printer_manager)):
    """
    Disconnects the active printer.
    """
    return await manager.disconnect_printer()


@router.post("/test", response_model=PrintJobRecord)
async def print_test_page(manager: PrinterManager = Depends(get_printer_manager)):
    """
    Generates and prints a hardware diagnostic test page.
    """
    test_req = manager.generate_test_print_request()
    return await manager.submit_print_job(test_req)
