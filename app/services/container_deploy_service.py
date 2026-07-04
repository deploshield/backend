import subprocess
import tempfile
from pathlib import Path


def deploy_container(
    ip_address: str,
    ssh_user: str,
    ssh_port: int,
    ssh_private_key: str | None = None,
    ssh_password: str | None = None,
    repo_url: str = "",
    branch: str = "main",
    project_name: str = "",
    app_port: int = 3000,
    env_variables: dict | None = None,
    generated_dockerfile: str | None = None,
) -> dict:
    stages = []

    key_path = None
    if ssh_private_key:
        key_file = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
        key_file.write(ssh_private_key)
        key_file.close()
        key_path = key_file.name

    def build_ssh_cmd(command: str) -> list:
        if key_path:
            return [
                "ssh", "-i", key_path,
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
                "-p", str(ssh_port),
                f"{ssh_user}@{ip_address}",
                command,
            ]
        else:
            return [
                "sshpass", "-p", ssh_password,
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
                "-p", str(ssh_port),
                f"{ssh_user}@{ip_address}",
                command,
            ]

    try:
        # Build env file content
        env_file_cmd = ""
        docker_env_flag = ""
        if env_variables:
            env_lines = "\n".join([f"{k}={v}" for k, v in env_variables.items()])
            env_file_cmd = f'echo "{env_lines}" > /opt/deployshield/{project_name}/.env'
            docker_env_flag = f"--env-file /opt/deployshield/{project_name}/.env"

        # Dockerfile generation command
        write_dockerfile_cmd = ""
        if generated_dockerfile:
            escaped = generated_dockerfile.replace("'", "'\\''")
            write_dockerfile_cmd = f"echo '{escaped}' > Dockerfile"

        deploy_commands = f"""
set -e

mkdir -p /opt/deployshield
cd /opt/deployshield

# Clone or pull
if [ -d "{project_name}" ]; then
    cd {project_name}
    git fetch origin
    git reset --hard origin/{branch}
else
    git clone --branch {branch} {repo_url} {project_name}
    cd {project_name}
fi

{write_dockerfile_cmd}

# Write env file
{env_file_cmd}

# Check Docker is installed
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed on this server"
    exit 1
fi

# Auto-generate Dockerfile if missing
if [ ! -f "Dockerfile" ] && [ ! -f "docker-compose.yml" ] && [ ! -f "docker-compose.yaml" ]; then
    if [ -f "package.json" ]; then
        if grep -q "next" package.json 2>/dev/null; then
            cat > Dockerfile << 'DEOF'
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
DEOF
        elif grep -q "nest" package.json 2>/dev/null; then
            cat > Dockerfile << 'DEOF'
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["node", "dist/main"]
DEOF
        else
            cat > Dockerfile << 'DEOF'
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --production
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
DEOF
        fi
        echo "DOCKERFILE_GENERATED=nodejs"
    elif [ -f "requirements.txt" ]; then
        cat > Dockerfile << 'DEOF'
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
DEOF
        echo "DOCKERFILE_GENERATED=python"
    elif [ -f "go.mod" ]; then
        cat > Dockerfile << 'DEOF'
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.* ./
RUN go mod download
COPY . .
RUN go build -o main .
FROM alpine:3.19
WORKDIR /app
COPY --from=builder /app/main .
EXPOSE 8080
CMD ["./main"]
DEOF
        echo "DOCKERFILE_GENERATED=go"
    else
        echo "ERROR: No Dockerfile found and cannot detect project type"
        exit 1
    fi
fi

# Build and deploy
if [ -f "docker-compose.yml" ] || [ -f "docker-compose.yaml" ]; then
    docker compose down 2>/dev/null || true
    docker compose up -d --build
    echo "DEPLOYED_VIA=docker-compose"
elif [ -f "Dockerfile" ]; then
    docker build -t {project_name} .
    docker stop {project_name} 2>/dev/null || true
    docker rm {project_name} 2>/dev/null || true
    docker run -d --name {project_name} --restart unless-stopped \\
        -p {app_port}:{app_port} \\
        {docker_env_flag} \\
        {project_name}
    echo "DEPLOYED_VIA=docker"
else
    echo "ERROR: No Dockerfile or docker-compose.yml found"
    exit 1
fi

# Verify container is running
sleep 3
if docker ps | grep -q {project_name}; then
    echo "CONTAINER_STATUS=running"
else
    echo "CONTAINER_STATUS=crashed"
    docker logs --tail 30 {project_name} 2>&1
    exit 1
fi
"""

        # Test SSH connection first
        test_result = subprocess.run(
            build_ssh_cmd("echo 'SSH_OK'"),
            capture_output=True, text=True, timeout=15,
        )

        if test_result.returncode != 0:
            stages.append({"name": "ssh_connect", "status": "failed", "error": test_result.stderr.strip()})
            return {"success": False, "stages": stages, "error": f"SSH connection failed: {test_result.stderr.strip()}"}

        stages.append({"name": "ssh_connect", "status": "success", "log": f"Connected to {ssh_user}@{ip_address}"})

        # Run deploy
        result = subprocess.run(
            build_ssh_cmd(deploy_commands),
            capture_output=True, text=True, timeout=600,
        )

        full_output = result.stdout + "\n" + result.stderr

        if result.returncode != 0:
            stages.append({"name": "deploy", "status": "failed", "error": result.stderr.strip(), "log": full_output})
            return {"success": False, "stages": stages, "error": result.stderr.strip(), "log": full_output}

        stages.append({"name": "deploy", "status": "success", "log": full_output})

        # Determine URL
        url = f"http://{ip_address}:{app_port}"

        return {
            "success": True,
            "stages": stages,
            "url": url,
            "log": full_output,
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "stages": stages, "error": "Deployment timed out after 600 seconds"}
    except Exception as e:
        return {"success": False, "stages": stages, "error": str(e)}
    finally:
        if key_path:
            Path(key_path).unlink(missing_ok=True)
