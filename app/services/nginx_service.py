import subprocess
import tempfile
from pathlib import Path


NGINX_TEMPLATE = """server {{
    listen 80;
    server_name {domain};

    location / {{
        proxy_pass http://localhost:{app_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }}
}}
"""


def setup_nginx_and_ssl(
    ip_address: str,
    ssh_user: str,
    ssh_port: int,
    ssh_private_key: str,
    domain: str,
    app_port: int,
    setup_ssl: bool = True,
) -> dict:
    stages = []

    key_file = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False)
    key_file.write(ssh_private_key)
    key_file.close()
    key_path = key_file.name

    nginx_config = NGINX_TEMPLATE.format(domain=domain, app_port=app_port)
    escaped_config = nginx_config.replace("'", "'\\''")

    ssl_cmd = ""
    if setup_ssl:
        ssl_cmd = f"""
# Install certbot if not present
if ! command -v certbot &> /dev/null; then
    apt-get update -qq
    apt-get install -y -qq certbot python3-certbot-nginx
fi

# Check if DNS resolves to this server
RESOLVED_IP=$(dig +short {domain} | tail -1)
SERVER_IP=$(curl -s ifconfig.me)

if [ "$RESOLVED_IP" != "$SERVER_IP" ]; then
    echo "WARNING: Domain {domain} resolves to $RESOLVED_IP but this server is $SERVER_IP"
    echo "SSL_STATUS=skipped (DNS not pointing to this server yet)"
else
    certbot --nginx -d {domain} --non-interactive --agree-tos --register-unsafely-without-email
    echo "SSL_STATUS=enabled"
fi
"""

    commands = f"""
set -e

# Install nginx if not present
if ! command -v nginx &> /dev/null; then
    apt-get update -qq
    apt-get install -y -qq nginx
fi

# Write nginx config
echo '{escaped_config}' > /etc/nginx/sites-available/{domain}

# Enable site
ln -sf /etc/nginx/sites-available/{domain} /etc/nginx/sites-enabled/{domain}

# Remove default if exists
rm -f /etc/nginx/sites-enabled/default

# Test nginx config
nginx -t

# Reload nginx
systemctl reload nginx
echo "NGINX_STATUS=configured"

{ssl_cmd}
"""

    try:
        result = subprocess.run(
            [
                "ssh", "-i", key_path,
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=10",
                "-p", str(ssh_port),
                f"{ssh_user}@{ip_address}",
                commands,
            ],
            capture_output=True, text=True, timeout=120,
        )

        full_output = result.stdout + "\n" + result.stderr

        if result.returncode != 0:
            stages.append({"name": "nginx_setup", "status": "failed", "error": result.stderr.strip(), "log": full_output})
            return {"success": False, "stages": stages, "error": result.stderr.strip()}

        # Check if SSL was set up
        ssl_status = "not requested"
        if setup_ssl:
            if "SSL_STATUS=enabled" in result.stdout:
                ssl_status = "enabled"
            elif "SSL_STATUS=skipped" in result.stdout:
                ssl_status = "skipped (DNS not ready)"
            else:
                ssl_status = "attempted"

        stages.append({
            "name": "nginx_setup",
            "status": "success",
            "log": full_output,
            "ssl_status": ssl_status,
        })

        url = f"https://{domain}" if ssl_status == "enabled" else f"http://{domain}"

        return {
            "success": True,
            "stages": stages,
            "url": url,
            "ssl_status": ssl_status,
            "log": full_output,
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "stages": stages, "error": "Nginx setup timed out"}
    except Exception as e:
        return {"success": False, "stages": stages, "error": str(e)}
    finally:
        Path(key_path).unlink(missing_ok=True)
