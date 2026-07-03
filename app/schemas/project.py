from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ProjectCreate(BaseModel):
    name: str
    repo_url: str
    branch: str = "main"


class ProjectResponse(BaseModel):
    id: str
    name: str
    repo_url: str
    branch: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
