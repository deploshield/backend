from datetime import datetime

from app.services.container_deploy_service import deploy_container
from app.services.webserver_deploy_service import deploy_webserver
from app.services.cloudrun_deploy_service import deploy_cloud_run, setup_cloud_run_secrets
from app.services.nginx_service import setup_nginx_and_ssl


def run_deploy(
    server: object,
    repo_url: str,
    branch: str,
    project_name: str,
    generated_dockerfile: str | None = None,
) -> dict:
    """Route deployment to the correct strategy based on server.target_type and server.deploy_method."""

    target_type = getattr(server, "target_type", "kvm")
    deploy_method = getattr(server, "deploy_method", "container")
    env_variables = getattr(server, "env_variables", None)

    stages = []
    result = None

    # --- Cloud Run ---
    if target_type == "cloud_run":
        if not server.gcp_project_id or not server.gcp_service_account_json:
            return {
                "success": False,
                "error": "Cloud Run requires gcp_project_id and gcp_service_account_json",
                "stages": [],
                "completed_at": datetime.utcnow().isoformat(),
            }

        result = deploy_cloud_run(
            gcp_project_id=server.gcp_project_id,
            gcp_region=server.gcp_region or "us-central1",
            gcp_service_account_json=server.gcp_service_account_json,
            cloud_run_service_name=server.cloud_run_service_name or project_name,
            artifact_registry_repo=server.artifact_registry_repo,
            repo_url=repo_url,
            branch=branch,
            project_name=project_name,
            app_port=server.app_port or 3000,
            env_variables=env_variables,
        )

        # Setup secrets if there are env vars marked as secrets
        if result["success"] and env_variables:
            secrets = {k: v for k, v in env_variables.items() if k.startswith("SECRET_")}
            if secrets:
                secret_result = setup_cloud_run_secrets(
                    gcp_project_id=server.gcp_project_id,
                    gcp_service_account_json=server.gcp_service_account_json,
                    cloud_run_service_name=server.cloud_run_service_name or project_name,
                    gcp_region=server.gcp_region or "us-central1",
                    secrets=secrets,
                )
                if secret_result.get("created_secrets"):
                    result["stages"].append({
                        "name": "secrets",
                        "status": "success",
                        "log": f"Created secrets: {', '.join(secret_result['created_secrets'])}",
                    })

    # --- SSH-based targets (ec2, kvm, vps) ---
    elif target_type in ("ec2", "kvm", "vps"):
        if not server.ip_address or not server.ssh_private_key:
            return {
                "success": False,
                "error": f"{target_type} target requires ip_address and ssh_private_key",
                "stages": [],
                "completed_at": datetime.utcnow().isoformat(),
            }

        if deploy_method == "container":
            result = deploy_container(
                ip_address=server.ip_address,
                ssh_user=server.ssh_user or "root",
                ssh_port=server.ssh_port or 22,
                ssh_private_key=server.ssh_private_key,
                ssh_password=getattr(server, "ssh_password", None),
                repo_url=repo_url,
                branch=branch,
                project_name=project_name,
                app_port=server.app_port or 3000,
                env_variables=env_variables,
                generated_dockerfile=generated_dockerfile,
            )
        elif deploy_method == "webserver":
            result = deploy_webserver(
                ip_address=server.ip_address,
                ssh_user=server.ssh_user or "root",
                ssh_port=server.ssh_port or 22,
                ssh_private_key=server.ssh_private_key,
                ssh_password=getattr(server, "ssh_password", None),
                repo_url=repo_url,
                branch=branch,
                project_name=project_name,
                app_port=server.app_port or 3000,
                env_variables=env_variables,
            )
        else:
            return {
                "success": False,
                "error": f"Unknown deploy_method: {deploy_method}. Use 'container' or 'webserver'.",
                "stages": [],
                "completed_at": datetime.utcnow().isoformat(),
            }

        # Setup Nginx + SSL if requested and deploy succeeded
        if result["success"] and server.domain and server.setup_nginx:
            nginx_result = setup_nginx_and_ssl(
                ip_address=server.ip_address,
                ssh_user=server.ssh_user or "root",
                ssh_port=server.ssh_port or 22,
                ssh_private_key=server.ssh_private_key,
                domain=server.domain,
                app_port=server.app_port or 3000,
                setup_ssl=server.setup_ssl or False,
            )

            result["stages"].extend(nginx_result.get("stages", []))

            if nginx_result["success"]:
                result["url"] = nginx_result["url"]
                result["ssl_status"] = nginx_result.get("ssl_status")

    else:
        return {
            "success": False,
            "error": f"Unknown target_type: {target_type}. Use 'cloud_run', 'ec2', 'kvm', or 'vps'.",
            "stages": [],
            "completed_at": datetime.utcnow().isoformat(),
        }

    result["completed_at"] = datetime.utcnow().isoformat()
    return result
