import os
import json
import uuid
import logging
from datetime import datetime
from typing import List, Optional
from backend.models.document import PrintDocument, DocumentSaveRequest

logger = logging.getLogger("DocumentManager")


class DocumentManager:
    """
    Manages saved print documents (drafts) stored as JSON files.
    """

    def __init__(self, documents_dir: str = "data/documents"):
        self.documents_dir = documents_dir
        os.makedirs(self.documents_dir, exist_ok=True)

    def _path(self, doc_id: str) -> str:
        safe_id = "".join(c for c in doc_id if c.isalnum() or c in "-_")
        return os.path.join(self.documents_dir, f"{safe_id}.json")

    def list_documents(self) -> List[PrintDocument]:
        docs = []
        if not os.path.exists(self.documents_dir):
            return docs
        for file_name in sorted(os.listdir(self.documents_dir)):
            if not file_name.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.documents_dir, file_name), "r", encoding="utf-8") as f:
                    data = json.load(f)
                docs.append(PrintDocument(**data))
            except Exception as e:
                logger.error(f"Failed to load document {file_name}: {e}")
        docs.sort(key=lambda d: d.updated_at or "", reverse=True)
        return docs

    def get_document(self, doc_id: str) -> Optional[PrintDocument]:
        path = self._path(doc_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return PrintDocument(**json.load(f))
        except Exception as e:
            logger.error(f"Failed to load document {doc_id}: {e}")
            return None

    def save_document(self, req: DocumentSaveRequest) -> PrintDocument:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        doc_id = req.id or f"doc-{uuid.uuid4().hex[:8]}"
        existing = self.get_document(doc_id)
        doc = PrintDocument(
            id=doc_id,
            title=req.title or "Untitled Document",
            blocks=req.blocks,
            created_at=existing.created_at if existing and existing.created_at else now,
            updated_at=now
        )
        with open(self._path(doc_id), "w", encoding="utf-8") as f:
            json.dump(doc.model_dump(), f, indent=2)
        return doc

    def delete_document(self, doc_id: str) -> bool:
        path = self._path(doc_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False
