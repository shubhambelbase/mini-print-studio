from typing import List, Optional
from pydantic import BaseModel, Field
from backend.models.print_job import ContentBlock


class PrintDocument(BaseModel):
    id: str
    title: str
    blocks: List[ContentBlock] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentSaveRequest(BaseModel):
    id: Optional[str] = None
    title: str
    blocks: List[ContentBlock] = Field(default_factory=list)
