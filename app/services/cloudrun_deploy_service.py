import json
import subprocess
import tempfile
from pathlib import Path


def deploy_cloud_run(
    gcp_project_id: str,
    gcp_region: str,
    gcp_service_account_json: str,
    cloud_run_service_name: str,
    artifact_registry_repo: str | None,
    repo_url: str,
    branch: str,
    project_name: str,
    app_port: int = 3000,
    env_variables: dict | None = None,
) -> dict:
    stages = []

    # Write service account key to temp file
    sa_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    sa_file.write(gcp_service_account_json)
    sa_file.close()
    sa_path = sa_file.name

    # Use artifact registry or default gcr.io
    registry = artifact_registry_repo or f"gcr.io/{gcp_project_id}"
    image_name = f"{registry}/{project_name}:latest"

    try:
        # Step 1: Authenticate with GCP
        auth_result = subprocess.run(
            ["gcloud", "auth", "activate-service-account", "--key-file", sa_path],
            capture_output=True, text=True, timeout=30,
        )

        if auth_result.returncode != 0:
            stages.append({"name": "gcp_auth", "status": "failed", "error": auth_result.stderr.strip()})
            return {"success": False, "stages": stages, "error": f"GCP auth failed: {auth_result.stderr.strip()}"}

        stages.append({"name": "gcp_auth", "status": "success", "log": "Authenticated with GCP service account"})

        # Set project
        subprocess.run(
            ["gcloud", "config", "set", "project", gcp_project_id],
            capture_output=True, text=True, timeout=10,
        )

        # Step 2: Configure Docker for artifact registry
        configure_result = subprocess.run(
            ["gcloud", "auth", "configure-docker", gcp_region + "-docker.pkg.dev", "--quiet"],
            capture_output=True, text=True, timeout=30,
        )

        if configure_result.returncode != 0:
            # Try gcr.io fallback
            subprocess.run(
                ["gcloud", "auth", "configure-docker", "--quiet"],
                capture_output=True, text=True, timeout=30,
            )

        stages.append({"name": "docker_auth", "status": "success", "log": "Docker configured for GCP registry"})

        # Step 3: Clone repo locally and build
        clone_dir = tempfile.mkdtemp(prefix="deployshield-cloudrun-")

        clone_result = subprocess.run(
            ["git", "clone", "--branch", branch, "--depth", "1", repo_url, clone_dir],
            capture_output=True, text=True, timeout=120,
        )

        if clone_result.returncode != 0:
            stages.append({"name": "clone", "status": "failed", "error": clone_result.stderr.strip()})
            return {"success": False, "stages": stages, "error": f"Git clone failed: {clone_result.stderr.strip()}"}

        stages.append({"name": "clone", "status": "success", "log": f"Cloned {repo_url} ({branch})"})

        # Step 4: Build Docker image
        build_result = subprocess.run(
            ["docker", "build", "-t", image_name, "."],
            cwd=clone_dir,
            capture_output=True, text=True, timeout=600,
        )

        if build_result.returncode != 0:
            stages.append({"name": "docker_build", "status": "failed", "error": build_result.stderr.strip()})
            return {"success": False, "stages": stages, "error": f"Docker build failed: {build_result.stderr.strip()}"}

        stages.append({"name": "docker_build", "status": "success", "log": "Image built successfully"})

        # Step 5: Push to registry
        push_result = subprocess.run(
            ["docker", "push", image_name],
            capture_output=True, text=True, timeout=300,
        )

        if push_result.returncode != 0:
            stages.append({"name": "docker_push", "status": "failed", "error": push_result.stderr.strip()})
            return {"success": False, "stages": stages, "error": f"Docker push failed: {push_result.stderr.strip()}"}

        stages.append({"name": "docker_push", "status": "success", "log": f"Pushed image to {image_name}"})

        # Step 6: Deploy to Cloud Run
        deploy_cmd = [
            "gcloud", "run", "deploy", cloud_run_service_name,
            "--image", image_name,
            "--region", gcp_region,
            "--platform", "managed",
            "--allow-unauthenticated",
            "--port", str(app_port),
            "--quiet",
        ]

        # Add env variables
        if env_variables:
            env_str = ",".join([f"{k}={v}" for k, v in env_variables.items()])
            deploy_cmd.extend(["--set-env-vars", env_str])

        deploy_result = subprocess.run(
            deploy_cmd,
            capture_output=True, text=True, timeout=300,
        )

        if deploy_result.returncode != 0:
            stages.append({"name": "cloud_run_deploy", "status": "failed", "error": deploy_result.stderr.strip()})
            return {"success": False, "stages": stages, "error": f"Cloud Run deploy failed: {deploy_result.stderr.strip()}"}

        # Extract the service URL from output
        service_url = ""
        for line in deploy_result.stderr.split("\n"):
            if "https://" in line and ".run.app" in line:
                service_url = line.strip().split()[-1]
                break

        if not service_url:
            # Try to get URL with describe
            url_result = subprocess.run(
                [
                    "gcloud", "run", "services", "describe", cloud_run_service_name,
                    "--region", gcp_region, "--format", "value(status.url)",
                ],
                capture_output=True, text=True, timeout=30,
            )
            service_url = url_result.stdout.strip()

        stages.append({
            "name": "cloud_run_deploy",
            "status": "success",
            "log": f"Deployed to Cloud Run: {service_url}",
            "url": service_url,
        })

        # Cleanup clone dir
        subprocess.run(["rm", "-rf", clone_dir], capture_output=True, timeout=10)

        return {
            "success": True,
            "stages": stages,
            "url": service_url,
            "log": f"Successfully deployed to {service_url}",
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "stages": stages, "error": "Cloud Run deployment timed out"}
    except FileNotFoundError:
        return {"success": False, "stages": stages, "error": "gcloud CLI not found. Install Google Cloud SDK on this server."}
    except Exception as e:
        return {"success": False, "stages": stages, "error": str(e)}
    finally:
        Path(sa_path).unlink(missing_ok=True)


def setup_cloud_run_secrets(
    gcp_project_id: str,
    gcp_service_account_json: str,
    cloud_run_service_name: str,
    gcp_region: str,
    secrets: dict,
) -> dict:
    """Create secrets in Google Secret Manager and bind them to Cloud Run service."""
    sa_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    sa_file.write(gcp_service_account_json)
    sa_file.close()
    sa_path = sa_file.name

    try:
        subprocess.run(
            ["gcloud", "auth", "activate-service-account", "--key-file", sa_path],
            capture_output=True, text=True, timeout=30,
        )
        subprocess.run(
            ["gcloud", "config", "set", "project", gcp_project_id],
            capture_output=True, text=True, timeout=10,
        )

        created_secrets = []

        for secret_name, secret_value in secrets.items():
            # Create secret (ignore if exists)
            subprocess.run(
                ["gcloud", "secrets", "create", secret_name, "--replication-policy", "automatic"],
                capture_output=True, text=True, timeout=30,
            )

            # Add version with the value
            version_result = subprocess.run(
                ["gcloud", "secrets", "versions", "add", secret_name, "--data-file", "-"],
                input=secret_value,
                capture_output=True, text=True, timeout=30,
            )

            if version_result.returncode == 0:
                created_secrets.append(secret_name)

        # Update Cloud Run service to use secrets
        if created_secrets:
            secrets_flag = ",".join([f"{s}={s}:latest" for s in created_secrets])
            update_result = subprocess.run(
                [
                    "gcloud", "run", "services", "update", cloud_run_service_name,
                    "--region", gcp_region,
                    "--set-secrets", secrets_flag,
                    "--quiet",
                ],
                capture_output=True, text=True, timeout=60,
            )

            if update_result.returncode != 0:
                return {"success": False, "error": f"Failed to bind secrets: {update_result.stderr.strip()}"}

        return {"success": True, "created_secrets": created_secrets}

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        Path(sa_path).unlink(missing_ok=True)
