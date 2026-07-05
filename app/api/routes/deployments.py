import threading
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db, SessionLocal
from app.models.project import Project
from app.models.server import Server
from app.models.deployment import Deployment
from app.schemas.deployment import ValidateRequest, DeployRequest, SetupDomainRequest, DeploymentResponse
from app.services.validate_service import run_validation
from app.services.deploy_service import run_deploy
from app.services.cleanup_service import cleanup_deployment
from app.services.nginx_service import setup_nginx_and_ssl

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


def _run_deploy_thread(deployment_id: str, server_id: str, repo_url: str, branch: str, project_name: str):
    db = SessionLocal()
    try:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            result = {"success": False, "error": "Server not found", "stages": []}
        else:
            result = run_deploy(
                server=server,
                repo_url=repo_url,
                branch=branch,
                project_name=project_name,
            )
    except Exception as e:
        result = {"success": False, "error": str(e), "stages": []}

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
        args=(deployment.id, server.id, project.repo_url, project.branch, project.name),
    )
    thread.start()

    return deployment


@router.delete("/{deployment_id}")
def delete_deployment(deployment_id: str, db: Session = Depends(get_db)):
    """Stop container, remove files from server, delete DB record."""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    cleanup_result = {"skipped": True}

    # If it was a deploy (not just validate), clean up the server
    if deployment.trigger_type == "deploy" and deployment.server_id:
        server = db.query(Server).filter(Server.id == deployment.server_id).first()
        project = db.query(Project).filter(Project.id == deployment.project_id).first()

        if server and project and server.ip_address:
            cleanup_result = cleanup_deployment(
                ip_address=server.ip_address,
                ssh_user=server.ssh_user or "root",
                ssh_port=server.ssh_port or 22,
                ssh_private_key=server.ssh_private_key,
                ssh_password=getattr(server, "ssh_password", None),
                project_name=project.name,
                domain=server.domain,
            )

    db.delete(deployment)
    db.commit()

    return {
        "message": "Deployment deleted",
        "cleanup": cleanup_result,
    }


@router.post("/{deployment_id}/setup-domain")
def setup_domain(deployment_id: str, data: SetupDomainRequest, db: Session = Depends(get_db)):
    """Setup Nginx + SSL for a successful deployment."""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")

    if deployment.status != "success" or deployment.trigger_type != "deploy":
        raise HTTPException(status_code=400, detail="Can only setup domain for successful deployments")

    server = db.query(Server).filter(Server.id == deployment.server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if not server.ip_address:
        raise HTTPException(status_code=400, detail="Server has no IP address")

    result = setup_nginx_and_ssl(
        ip_address=server.ip_address,
        ssh_user=server.ssh_user or "root",
        ssh_port=server.ssh_port or 22,
        ssh_private_key=server.ssh_private_key,
        ssh_password=getattr(server, "ssh_password", None),
        domain=data.domain,
        app_port=server.app_port or 3000,
        setup_ssl=data.setup_ssl,
    )

    # Update deployment result with domain info
    if result["success"]:
        dep_result = deployment.result or {}
        dep_result["domain"] = data.domain
        dep_result["url"] = result["url"]
        dep_result["ssl_status"] = result.get("ssl_status")
        deployment.result = dep_result
        db.commit()

    return result


@router.get("/{deployment_id}", response_model=DeploymentResponse)
def get_deployment(deployment_id: str, db: Session = Depends(get_db)):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment


@router.get("/", response_model=list[DeploymentResponse])
def list_deployments(db: Session = Depends(get_db)):
    return db.query(Deployment).order_by(Deployment.started_at.desc()).all()
