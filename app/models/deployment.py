from sqlalchemy import Column, String, DateTime, JSON, func
import uuid

from app.core.database import Base


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, nullable=False)
    server_id = Column(String, nullable=True)
    status = Column(String, default="queued")
    trigger_type = Column(String, default="validate")
    result = Column(JSON, nullable=True)
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
