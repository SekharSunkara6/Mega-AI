from pydantic import BaseModel
from typing import Any

class QueryRequest(BaseModel):
    query: str

class ApprovalRequest(BaseModel):
    rewrite_id: str
    approved: bool
    reviewer_note: str = ""

class ErrorResponse(BaseModel):
    error_code: str
    message: str
    job_id: str | None = None