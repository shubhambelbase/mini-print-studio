from fastapi import APIRouter, HTTPException
from typing import List
from backend.models.document import PrintDocument, DocumentSaveRequest
from backend.services.document_manager import DocumentManager

router = APIRouter(prefix="/api/documents", tags=["Documents"])
document_manager = DocumentManager()


@router.get("", response_model=List[PrintDocument])
async def list_documents():
    return document_manager.list_documents()


@router.get("/{document_id}", response_model=PrintDocument)
async def get_document(document_id: str):
    doc = document_manager.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")
    return doc


@router.post("", response_model=PrintDocument)
async def save_document(req: DocumentSaveRequest):
    try:
        return document_manager.save_document(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save document: {str(e)}")


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    if not document_manager.delete_document(document_id):
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")
    return {"status": "success", "message": f"Document '{document_id}' deleted."}
