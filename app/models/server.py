from sqlalchemy import Column, String, Integer, DateTime, func
import uuid

from app.core.database import Base


class Server(Base):
    __tablename__ = "servers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    ssh_user = Column(String, default="root")
    ssh_port = Column(Integer, default=22)
    ssh_private_key = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
