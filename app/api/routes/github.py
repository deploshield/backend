from fastapi import APIRouter, HTTPException, Query
import httpx

from app.core.config import settings

router = APIRouter(prefix="/github", tags=["GitHub"])

CLERK_API_BASE = "https://api.clerk.com/v1"


async def _get_github_token(clerk_user_id: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{CLERK_API_BASE}/users/{clerk_user_id}/oauth_access_tokens/oauth_github",
            headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Could not fetch GitHub token from Clerk")
        data = resp.json()
        if not data or len(data) == 0:
            raise HTTPException(status_code=404, detail="No GitHub connection found. Please sign in with GitHub first.")
        return data[0]["token"]


@router.get("/repos")
async def list_repos(clerk_user_id: str = Query(...), page: int = 1, per_page: int = 30):
    token = await _get_github_token(clerk_user_id)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            params={
                "sort": "updated",
                "direction": "desc",
                "per_page": per_page,
                "page": page,
                "type": "all",
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="GitHub API error")
        repos = resp.json()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "full_name": r["full_name"],
                "private": r["private"],
                "html_url": r["html_url"],
                "clone_url": r["clone_url"],
                "default_branch": r["default_branch"],
                "language": r["language"],
                "updated_at": r["updated_at"],
                "owner": {
                    "login": r["owner"]["login"],
                    "avatar_url": r["owner"]["avatar_url"],
                    "type": r["owner"]["type"],
                },
            }
            for r in repos
        ]


@router.get("/orgs")
async def list_orgs(clerk_user_id: str = Query(...)):
    token = await _get_github_token(clerk_user_id)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.github.com/user/orgs",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="GitHub API error")
        orgs = resp.json()
        return [
            {
                "id": o["id"],
                "login": o["login"],
                "avatar_url": o["avatar_url"],
                "description": o.get("description", ""),
            }
            for o in orgs
        ]


@router.get("/orgs/{org}/repos")
async def list_org_repos(org: str, clerk_user_id: str = Query(...), page: int = 1, per_page: int = 30):
    token = await _get_github_token(clerk_user_id)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/orgs/{org}/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            params={
                "sort": "updated",
                "direction": "desc",
                "per_page": per_page,
                "page": page,
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="GitHub API error")
        repos = resp.json()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "full_name": r["full_name"],
                "private": r["private"],
                "html_url": r["html_url"],
                "clone_url": r["clone_url"],
                "default_branch": r["default_branch"],
                "language": r["language"],
                "updated_at": r["updated_at"],
            }
            for r in repos
        ]


@router.get("/repos/{owner}/{repo}/branches")
async def list_branches(owner: str, repo: str, clerk_user_id: str = Query(...)):
    token = await _get_github_token(clerk_user_id)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/branches",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            params={"per_page": 100},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="GitHub API error")
        branches = resp.json()
        return [{"name": b["name"]} for b in branches]
