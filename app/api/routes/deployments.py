import threading
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db, SessionLocal
from app.models.project import Project
from app.models.server import Server
from app.models.deployment import Deployment
from app.schemas.deployment import ValidateRequest, DeployRequest, DeploymentResponse
from app.services.validate_service import run_validation
from app.services.deploy_service import deploy_to_server

router = APIRouter(prefix="/deployments", tags=["Deployments"])


def _run_validate_thread(deployment_id: str, repo_url: str, branch: str):
    try:
        result = run_validation(repo_url, branch, deployment_id)
    except Exception as e:
        result = {"success": False, "error": str(e), "stages": []}

    db = SessionLocal()
    try:
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if deployment:
            deployment.status = "success" if result["success"] else "failed"
            deployment.result = result
            deployment.completed_at = datetime.utcnow()
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _run_deploy_thread(
    deployment_id: str,
    ip_address: str,
    ssh_user: str,
    ssh_port: int,
    ssh_private_key: str,
    repo_url: str,
    branch: str,
    project_name: str,
):
    try:
        result = deploy_to_server(
            ip_address=ip_address,
            ssh_user=ssh_user,
            ssh_port=ssh_port,
            ssh_private_key=ssh_private_key,
            repo_url=repo_url,
            branch=branch,
            project_name=project_name,
        )
    except Exception as e:
        result = {"success": False, "error": str(e), "stages": []}

    db = SessionLocal()
    try:
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if deployment:
            deployment.status = "success" if result["success"] else "failed"
            deployment.result = result
            deployment.completed_at = datetime.utcnow()
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@router.post("/validate", response_model=DeploymentResponse)
def validate_build(data: ValidateRequest, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == data.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    deployment = Deployment(
        project_id=project.id,
        status="running",
        trigger_type="validate",
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    thread = threading.Thread(
        target=_run_validate_thread,
        args=(deployment.id, project.repo_url, project.branch),
    )
    thread.start()

    return deployment


@router.post("/deploy", response_model=DeploymentResponse)
def deploy_project(data: DeployRequest, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == data.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    server = db.query(Server).filter(Server.id == data.server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    deployment = Deployment(
        project_id=project.id,
        server_id=server.id,
        status="running",
        trigger_type="deploy",
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    thread = threading.Thread(
        target=_run_deploy_thread,
        args=(
            deployment.id,
            server.ip_address,
            server.ssh_user,
            server.ssh_port,
            server.ssh_private_key,
            project.repo_url,
            project.branch,
            project.name,
        ),
    )
    thread.start()

    return deployment


@router.get("/{deployment_id}", response_model=DeploymentResponse)
def get_deployment(deployment_id: str, db: Session = Depends(get_db)):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment


@router.get("/", response_model=list[DeploymentResponse])
def list_deployments(db: Session = Depends(get_db)):
    return db.query(Deployment).order_by(Deployment.started_at.desc()).all()
