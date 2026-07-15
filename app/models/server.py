from sqlalchemy import Column, String, Integer, DateTime, Boolean, JSON, func
import uuid

from app.core.database import Base


class Server(Base):
    __tablename__ = "servers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)

    # Target type: cloud_run, ec2, kvm, vps
    target_type = Column(String, default="kvm")
    # Deploy method: container, webserver (for SSH-based targets only)
    deploy_method = Column(String, default="container")

    # SSH credentials (ec2, kvm, vps)
    ip_address = Column(String, nullable=True)
    ssh_user = Column(String, default="root")
    ssh_port = Column(Integer, default=22)
    ssh_private_key = Column(String, nullable=True)
    ssh_password = Column(String, nullable=True)

    # Cloud Run (GCP)
    gcp_project_id = Column(String, nullable=True)
    gcp_region = Column(String, nullable=True)
    gcp_service_account_json = Column(String, nullable=True)
    cloud_run_service_name = Column(String, nullable=True)
    artifact_registry_repo = Column(String, nullable=True)

    # Domain & Nginx (for SSH targets)
    domain = Column(String, nullable=True)
    setup_nginx = Column(Boolean, default=False)
    setup_ssl = Column(Boolean, default=False)
    app_port = Column(Integer, default=3000)

    # Environment variables / secrets
    env_variables = Column(JSON, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
