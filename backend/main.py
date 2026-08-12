import os
import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.api import printers, print_jobs, images, settings, templates, history, documents, events, debug
from backend.api.printers import get_printer_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Reconnect to the last used printer in the background after startup.
    reconnect_task = asyncio.create_task(get_printer_manager().auto_reconnect())
    yield
    reconnect_task.cancel()


app = FastAPI(
    title="Mini Print Studio API",
    description="Local hardware interface and print server for thermal receipt and label printers.",
    version="1.1.0",
    lifespan=lifespan
)

# Security: Restrict CORS to local host origin by default
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(printers.router)
app.include_router(print_jobs.router)
app.include_router(images.router)
app.include_router(settings.router)
app.include_router(templates.router)
app.include_router(history.router)
app.include_router(documents.router)
app.include_router(events.router)
app.include_router(debug.router)

# Mount frontend directory for static web files
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/", response_class=FileResponse)
async def serve_index():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Mini Print Studio API is running. Frontend index.html not found."}


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
