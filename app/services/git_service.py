import subprocess
import shutil
from pathlib import Path

from app.core.config import TEMP_PATH


def clone_repository(repo_url: str, branch: str, deployment_id: str) -> dict:
    clone_dir = TEMP_PATH / str(deployment_id)

    if clone_dir.exists():
        shutil.rmtree(clone_dir)

    try:
        result = subprocess.run(
            ["git", "clone", "--branch", branch, "--single-branch", "--depth", "1", repo_url, str(clone_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "stage": "clone",
                "error": result.stderr.strip(),
                "path": None,
            }

        return {
            "success": True,
            "stage": "clone",
            "path": str(clone_dir),
            "log": f"Repository cloned successfully to {clone_dir}",
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stage": "clone",
            "error": "Clone timed out after 120 seconds",
            "path": None,
        }
    except Exception as e:
        return {
            "success": False,
            "stage": "clone",
            "error": str(e),
            "path": None,
        }


def cleanup_repository(deployment_id: str):
    clone_dir = TEMP_PATH / str(deployment_id)
    if clone_dir.exists():
        def on_rm_error(func, path, exc_info):
            import stat
            os.chmod(path, stat.S_IWRITE)
            func(path)

        import os
        shutil.rmtree(clone_dir, onerror=on_rm_error)
