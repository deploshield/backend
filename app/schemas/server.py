from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ServerCreate(BaseModel):
    name: str
    target_type: str = "kvm"  # cloud_run, ec2, kvm, vps
    deploy_method: str = "container"  # container, webserver

    # SSH targets
    ip_address: Optional[str] = None
    ssh_user: str = "root"
    ssh_port: int = 22
    ssh_private_key: Optional[str] = None
    ssh_password: Optional[str] = None

    # Cloud Run
    gcp_project_id: Optional[str] = None
    gcp_region: Optional[str] = None
    gcp_service_account_json: Optional[str] = None
    cloud_run_service_name: Optional[str] = None
    artifact_registry_repo: Optional[str] = None

    # Domain & Nginx
    domain: Optional[str] = None
    setup_nginx: bool = False
    setup_ssl: bool = False
    app_port: int = 3000

    # Env variables
    env_variables: Optional[dict] = None


class ServerResponse(BaseModel):
    id: str
    name: str
    target_type: str
    deploy_method: str
    ip_address: Optional[str] = None
    ssh_user: Optional[str] = None
    ssh_port: Optional[int] = None
    gcp_project_id: Optional[str] = None
    gcp_region: Optional[str] = None
    cloud_run_service_name: Optional[str] = None
    artifact_registry_repo: Optional[str] = None
    domain: Optional[str] = None
    setup_nginx: bool = False
    setup_ssl: bool = False
    app_port: int = 3000
    env_variables: Optional[dict] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
