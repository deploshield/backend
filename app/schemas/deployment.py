from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any


class ValidateRequest(BaseModel):
    project_id: str
    env_vars: Optional[str] = None


class DeployRequest(BaseModel):
    project_id: str
    server_id: str


class SetupDomainRequest(BaseModel):
    domain: str
    setup_ssl: bool = True


class DeploymentResponse(BaseModel):
    id: str
    project_id: str
    server_id: Optional[str] = None
    status: str
    trigger_type: str
    result: Optional[Any] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
