import subprocess
import tempfile
from pathlib import Path


def deploy_webserver(
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
        if env_variables:
            env_lines = "\\n".join([f"{k}={v}" for k, v in env_variables.items()])
            env_file_cmd = f'echo -e "{env_lines}" > /opt/deployshield/{project_name}/.env'

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

# Write env file
{env_file_cmd}

# Detect project type and install/run
if [ -f "package.json" ]; then
    # Node.js project
    if ! command -v node &> /dev/null; then
        echo "ERROR: Node.js is not installed on this server"
        exit 1
    fi

    # Install dependencies
    if [ -f "package-lock.json" ]; then
        npm ci --production
    elif [ -f "yarn.lock" ]; then
        yarn install --production
    elif [ -f "pnpm-lock.yaml" ]; then
        pnpm install --prod
    else
        npm install --production
    fi

    # Build if needed
    if grep -q '"build"' package.json; then
        npm run build 2>&1 || true
    fi

    # Install pm2 if not present
    if ! command -v pm2 &> /dev/null; then
        npm install -g pm2
    fi

    # Stop existing and start with pm2
    pm2 stop {project_name} 2>/dev/null || true
    pm2 delete {project_name} 2>/dev/null || true

    # Determine start command
    if grep -q '"start"' package.json; then
        pm2 start npm --name {project_name} -- start
    elif [ -f "server.js" ]; then
        PORT={app_port} pm2 start server.js --name {project_name}
    elif [ -f "index.js" ]; then
        PORT={app_port} pm2 start index.js --name {project_name}
    elif [ -f "app.js" ]; then
        PORT={app_port} pm2 start app.js --name {project_name}
    else
        echo "ERROR: No start script or entry file found"
        exit 1
    fi

    pm2 save
    echo "DEPLOYED_VIA=pm2"

elif [ -f "requirements.txt" ]; then
    # Python project
    if ! command -v python3 &> /dev/null; then
        echo "ERROR: Python3 is not installed on this server"
        exit 1
    fi

    # Create venv and install
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

    # Create systemd service
    cat > /etc/systemd/system/{project_name}.service << SVCEOF
[Unit]
Description={project_name}
After=network.target

[Service]
Type=simple
User={ssh_user}
WorkingDirectory=/opt/deployshield/{project_name}
EnvironmentFile=/opt/deployshield/{project_name}/.env
ExecStart=/opt/deployshield/{project_name}/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port {app_port}
Restart=always

[Install]
WantedBy=multi-user.target
SVCEOF

    systemctl daemon-reload
    systemctl restart {project_name}
    systemctl enable {project_name}
    echo "DEPLOYED_VIA=systemd"

else
    echo "ERROR: Could not detect project type (no package.json or requirements.txt)"
    exit 1
fi

# Verify it's running
sleep 3
if curl -s -o /dev/null -w "%{{http_code}}" http://localhost:{app_port} | grep -qE "^[23]"; then
    echo "APP_STATUS=healthy"
else
    echo "APP_STATUS=starting (may need more time)"
fi
"""

        # Test SSH connection
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
