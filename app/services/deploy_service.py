import subprocess
import tempfile
from pathlib import Path


def deploy_to_server(
    ip_address: str,
    ssh_user: str,
    ssh_port: int,
    ssh_private_key: str,
    repo_url: str,
    branch: str,
    project_name: str,
    generated_dockerfile: str | None = None,
) -> dict:
    stages = []

    key_file = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
    key_file.write(ssh_private_key)
    key_file.close()
    key_path = key_file.name

    try:
        # If we have a generated Dockerfile, write it on the server after clone
        write_dockerfile_cmd = ""
        if generated_dockerfile:
            escaped = generated_dockerfile.replace("'", "'\\''")
            write_dockerfile_cmd = f"echo '{escaped}' > Dockerfile"

        deploy_commands = f"""
cd /opt/deployshield || mkdir -p /opt/deployshield && cd /opt/deployshield

if [ -d "{project_name}" ]; then
    cd {project_name}
    git pull origin {branch}
else
    git clone --branch {branch} {repo_url} {project_name}
    cd {project_name}
fi

{write_dockerfile_cmd}

if [ -f "docker-compose.yml" ] || [ -f "docker-compose.yaml" ]; then
    docker compose down
    docker compose up -d --build
elif [ -f "Dockerfile" ]; then
    docker build -t {project_name} .
    docker stop {project_name} 2>/dev/null || true
    docker rm {project_name} 2>/dev/null || true
    docker run -d --name {project_name} --restart unless-stopped {project_name}
else
    echo "ERROR: No Dockerfile or docker-compose.yml found"
    exit 1
fi
"""

        result = subprocess.run(
            [
                "ssh",
                "-i", key_path,
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
                "-p", str(ssh_port),
                f"{ssh_user}@{ip_address}",
                deploy_commands,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            stages.append({
                "name": "deploy",
                "status": "failed",
                "error": result.stderr.strip(),
                "log": result.stdout,
            })
            return {
                "success": False,
                "stages": stages,
                "error": result.stderr.strip(),
            }

        stages.append({
            "name": "deploy",
            "status": "success",
            "log": result.stdout,
        })

        return {
            "success": True,
            "stages": stages,
            "log": result.stdout,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stages": [{"name": "deploy", "status": "failed", "error": "SSH connection timed out"}],
            "error": "Deployment timed out after 300 seconds",
        }
    except Exception as e:
        return {
            "success": False,
            "stages": [{"name": "deploy", "status": "failed", "error": str(e)}],
            "error": str(e),
        }
    finally:
        Path(key_path).unlink(missing_ok=True)
