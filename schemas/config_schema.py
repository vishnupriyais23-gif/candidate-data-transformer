from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class FieldProjection(BaseModel):
    path: str
    from_path: Optional[str] = Field(default=None, alias="from")
    type: str  # e.g., "string", "string[]", "number", "object", etc.
    required: bool = False
    normalize: Optional[str] = None

class ProjectionConfig(BaseModel):
    fields: List[FieldProjection]
    include_confidence: bool = True
    include_provenance: bool = True
    include_confidence_breakdown: bool = False
    on_missing: Literal["null", "omit", "error"] = "null"
