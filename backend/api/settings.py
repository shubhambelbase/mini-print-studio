import os
import json
from fastapi import APIRouter, HTTPException
from backend.models.settings import AppSettings

router = APIRouter(prefix="/api/settings", tags=["Settings"])

SETTINGS_FILE = os.path.join(
    os.environ.get("MPS_DATA_DIR", "data"),
    "settings.json"
)


def read_settings() -> AppSettings:
    """Loads settings from disk, returning defaults if the file is missing or corrupt."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return AppSettings(**data)
        except Exception:
            pass
    return AppSettings()


def save_settings(settings: AppSettings) -> bool:
    """Persists settings to disk. Returns True on success."""
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE) or ".", exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings.model_dump(), f, indent=2)
        return True
    except Exception:
        return False


@router.get("", response_model=AppSettings)
async def get_settings():
    """Returns the current application settings."""
    return read_settings()


@router.post("", response_model=AppSettings)
async def update_settings(settings: AppSettings):
    """Replaces the entire application settings object and persists to disk."""
    if not save_settings(settings):
        raise HTTPException(status_code=500, detail="Failed to save settings.")
    return settings
