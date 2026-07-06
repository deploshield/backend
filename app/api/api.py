from fastapi import APIRouter

from app.api.routes import health, projects, servers, deployments, github

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(projects.router)
api_router.include_router(servers.router)
api_router.include_router(deployments.router)
api_router.include_router(github.router)
