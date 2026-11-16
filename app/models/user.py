from sqlalchemy import Column, String, DateTime, func
import uuid

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    clerk_id = Column(String, nullable=False, unique=True, index=True)
    email = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
