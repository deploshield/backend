from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("/", response_model=ProjectResponse)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=data.name, repo_url=data.repo_url, branch=data.branch)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/", response_model=list[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, data: ProjectCreate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"message": "Project deleted"}
