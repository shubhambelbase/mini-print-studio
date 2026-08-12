from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from backend.models.template import PrintTemplate
from backend.services.template_manager import TemplateManager
from backend.api.settings import read_settings, save_settings

router = APIRouter(prefix="/api/templates", tags=["Templates"])
template_manager = TemplateManager()


@router.get("", response_model=List[PrintTemplate])
async def list_templates():
    return template_manager.get_all_templates()


@router.post("/{template_id}/favorite", response_model=Dict[str, Any])
async def set_template_favorite(template_id: str, payload: Dict[str, Any]):
    tpl = template_manager.get_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")
    favorite = bool((payload or {}).get("favorite", True))

    settings = read_settings()
    favs = list(settings.app.favorite_templates)
    if favorite and template_id not in favs:
        favs.append(template_id)
    elif not favorite and template_id in favs:
        favs.remove(template_id)
    settings.app.favorite_templates = favs
    if not save_settings(settings):
        raise HTTPException(status_code=500, detail="Failed to save favorite.")
    return {"favorite": favorite, "favorite_templates": favs}


@router.get("/{template_id}", response_model=PrintTemplate)
async def get_template(template_id: str):
    tpl = template_manager.get_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")
    return tpl


@router.post("", response_model=PrintTemplate)
async def save_template(template: PrintTemplate):
    success = template_manager.save_custom_template(template)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save custom template.")
    return template


@router.delete("/{template_id}")
async def delete_template(template_id: str):
    tpl = template_manager.get_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found.")
    if tpl.is_builtin:
        raise HTTPException(status_code=400, detail="Cannot delete built-in templates.")

    deleted = template_manager.delete_custom_template(template_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete template file.")
    return {"status": "success", "message": f"Template '{template_id}' deleted."}
