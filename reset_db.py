"""
Reset all tables and seed initial user.
Run from the backend/ directory:
    python reset_db.py
Make sure DATABASE_URL in .env has the real password before running.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text, Column, String, Integer, Boolean, JSON, DateTime, func
from sqlalchemy.orm import DeclarativeBase

from app.core.database import engine


class Base(DeclarativeBase):
    pass


# ── Model definitions (must match app/models/*.py) ───────────────────────────

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    clerk_id = Column(String, nullable=False, unique=True, index=True)
    email = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class Project(Base):
    __tablename__ = "projects"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    repo_url = Column(String, nullable=False)
    branch = Column(String, default="main")
    created_at = Column(DateTime, server_default=func.now())


class Server(Base):
    __tablename__ = "servers"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    target_type = Column(String, default="kvm")
    deploy_method = Column(String, default="container")
    ip_address = Column(String, nullable=True)
    ssh_user = Column(String, default="root")
    ssh_port = Column(Integer, default=22)
    ssh_private_key = Column(String, nullable=True)
    ssh_password = Column(String, nullable=True)
    gcp_project_id = Column(String, nullable=True)
    gcp_region = Column(String, nullable=True)
    gcp_service_account_json = Column(String, nullable=True)
    cloud_run_service_name = Column(String, nullable=True)
    artifact_registry_repo = Column(String, nullable=True)
    domain = Column(String, nullable=True)
    setup_nginx = Column(Boolean, default=False)
    setup_ssl = Column(Boolean, default=False)
    app_port = Column(Integer, default=3000)
    env_variables = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Deployment(Base):
    __tablename__ = "deployments"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    project_id = Column(String, nullable=False)
    server_id = Column(String, nullable=True)
    status = Column(String, default="queued")
    trigger_type = Column(String, default="validate")
    result = Column(JSON, nullable=True)
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)


# ── Reset & seed ─────────────────────────────────────────────────────────────

SEED_CLERK_ID = "user_3JJ6TokJxLNrpGZEzZ4vag4pskI"
SEED_EMAIL = "vamsidulam11@gmail.com"

with engine.begin() as conn:
    print("Dropping all tables...")
    conn.execute(text("DROP TABLE IF EXISTS deployments CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS servers CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS projects CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
    print("  ✓ All tables dropped")

print("Creating tables...")
Base.metadata.create_all(engine)
print("  ✓ users, projects, servers, deployments created")

print("Seeding user...")
with engine.begin() as conn:
    conn.execute(
        text(
            "INSERT INTO users (id, clerk_id, email, created_at) "
            "VALUES (:id, :clerk_id, :email, :created_at)"
        ),
        {
            "id": str(uuid.uuid4()),
            "clerk_id": SEED_CLERK_ID,
            "email": SEED_EMAIL,
            "created_at": datetime.now(timezone.utc),
        },
    )
print(f"  ✓ User seeded — clerk_id: {SEED_CLERK_ID}, email: {SEED_EMAIL}")

print("\nDone! Database is ready.")
