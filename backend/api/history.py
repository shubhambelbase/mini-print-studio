from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from datetime import datetime
from backend.services.printer_manager import PrinterManager
from backend.api.printers import get_printer_manager

router = APIRouter(prefix="/api/history", tags=["History"])


@router.get("", response_model=List[Dict[str, Any]])
async def get_history(manager: PrinterManager = Depends(get_printer_manager)):
    """Returns the full print job history list."""
    return manager.get_job_history()


@router.get("/stats", response_model=Dict[str, Any])
async def get_history_stats(manager: PrinterManager = Depends(get_printer_manager)):
    """Aggregated stats: totals by status, content-type breakdown, paper usage, and today's count."""
    history = manager.get_job_history()
    status_counts: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    est_paper_mm = 0.0
    today = datetime.now().strftime("%Y-%m-%d")
    today_jobs = 0
    for h in history:
        status_counts[h.get("status", "unknown")] = status_counts.get(h.get("status", "unknown"), 0) + 1
        for t in (h.get("content_types") or []):
            by_type[t] = by_type.get(t, 0) + 1
        est_paper_mm += (h.get("height_px") or 0) / 8.0
        if (h.get("timestamp") or "").startswith(today):
            today_jobs += 1
    return {
        "total_jobs": len(history),
        "status_counts": status_counts,
        "by_type": by_type,
        "est_paper_mm": round(est_paper_mm, 1),
        "today_jobs": today_jobs
    }


@router.delete("")
async def clear_history(manager: PrinterManager = Depends(get_printer_manager)):
    """Deletes all print job history records."""
    manager.clear_job_history()
    return {"status": "success", "message": "Print job history cleared."}
