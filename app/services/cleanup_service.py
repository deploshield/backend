
import subprocess
import tempfile
from pathlib import Path


def cleanup_deployment(
    ip_address: str,
    ssh_user: str,
    ssh_port: int,
    ssh_private_key: str | None = None,
    ssh_password: str | None = None,
    project_name: str = "",
    domain: str | None = None,
) -> dict:
    """Stop container, remove code and nginx config on remote server."""

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

    cleanup_commands = f"""
# Stop and remove Docker container
docker stop {project_name} 2>/dev/null || true
docker rm {project_name} 2>/dev/null || true
docker rmi {project_name} 2>/dev/null || true

# Remove project folder
rm -rf /opt/deployshield/{project_name}

# Remove pm2 process if exists
pm2 stop {project_name} 2>/dev/null || true
pm2 delete {project_name} 2>/dev/null || true

# Remove systemd service if exists
systemctl stop {project_name} 2>/dev/null || true
systemctl disable {project_name} 2>/dev/null || true
rm -f /etc/systemd/system/{project_name}.service
systemctl daemon-reload 2>/dev/null || true
"""

    if domain:
        cleanup_commands += f"""
# Remove nginx config
rm -f /etc/nginx/sites-enabled/{domain}
rm -f /etc/nginx/sites-available/{domain}
nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null || true
"""

    cleanup_commands += '\necho "CLEANUP_DONE"'

    try:
        result = subprocess.run(
            build_ssh_cmd(cleanup_commands),
            capture_output=True, text=True, timeout=30,
        )

        full_output = result.stdout + "\n" + result.stderr

        if "CLEANUP_DONE" in result.stdout:
            return {"success": True, "log": full_output}
        else:
            return {"success": False, "error": result.stderr.strip() or "Cleanup may have partially failed", "log": full_output}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Cleanup timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if key_path:
            Path(key_path).unlink(missing_ok=True)
