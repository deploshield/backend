from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.server import Server
from app.schemas.server import ServerCreate, ServerResponse

router = APIRouter(prefix="/servers", tags=["Servers"])


@router.post("/", response_model=ServerResponse)
def create_server(data: ServerCreate, db: Session = Depends(get_db)):
    server = Server(
        name=data.name,
        ip_address=data.ip_address,
        ssh_user=data.ssh_user,
        ssh_port=data.ssh_port,
        ssh_private_key=data.ssh_private_key,
    )
    db.add(server)
    db.commit()
    db.refresh(server)
    return server


@router.get("/", response_model=list[ServerResponse])
def list_servers(db: Session = Depends(get_db)):
    return db.query(Server).order_by(Server.created_at.desc()).all()


@router.get("/{server_id}", response_model=ServerResponse)
def get_server(server_id: str, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


@router.delete("/{server_id}")
def delete_server(server_id: str, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    db.delete(server)
    db.commit()
    return {"message": "Server deleted"}
