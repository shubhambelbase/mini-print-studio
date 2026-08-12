import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from backend.services.printer_manager import PrinterManager
from backend.api.printers import get_printer_manager

logger = logging.getLogger("EventsAPI")

router = APIRouter(prefix="/api", tags=["Events"])


@router.get("/events")
async def event_stream(manager: PrinterManager = Depends(get_printer_manager)):
    """
    Server-Sent Events stream. Pushes JSON events on print-job state
    transitions and printer connect/disconnect:

        data: {"type": "job", "job_id": "...", "status": "printing", "title": "..."}

    A `: keep-alive` comment is emitted every 15s to keep the connection open
    through idle proxies.
    """
    async def generate():
        async for chunk in manager.event_stream():
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
