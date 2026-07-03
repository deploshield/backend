from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ServerCreate(BaseModel):
    name: str
    ip_address: str
    ssh_user: str = "root"
    ssh_port: int = 22
    ssh_private_key: str


class ServerResponse(BaseModel):
    id: str
    name: str
    ip_address: str
    ssh_user: str
    ssh_port: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
