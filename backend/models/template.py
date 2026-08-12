from typing import List, Optional
from pydantic import BaseModel, Field
from backend.models.print_job import ContentBlock


class PrintTemplate(BaseModel):
    id: str
    name: str
    description: str
    category: str = Field("General", description="General, Notes, Labels, Receipts, Art")
    icon: str = "file-text"
    blocks: List[ContentBlock] = Field(default_factory=list)
    is_builtin: bool = False
